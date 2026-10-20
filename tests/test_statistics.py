import pytest

from custom_components.nrg.statistics import Statistics
from conftest import NOW, ZONE


def samples(model, start, seconds, **changes):
    value = {"house_kw": 2, "solar_kw": 1, "home_kw": 2, "ev_kw": 0, "grid_kw": 1,
             "supply": .1, "import_price": .15, "export_price": .05, **changes}
    for t in range(int(start), int(start + seconds) + 1, 60):
        model.observe(t, value, ZONE)


def test_covered_hour_learns_and_cost_conserves_with_restart_gap():
    model = Statistics()
    samples(model, NOW, 3600)
    assert model.hours[0]["house_kwh"] == pytest.approx(2)
    assert model.demand(NOW, ZONE, 9, True) == pytest.approx((2, 1))
    day = "2026-10-19"
    assert model.ledger[day]["import_cost"] == pytest.approx(.15)
    restored = Statistics(model.export())
    restored.observe(NOW + 7200, {"grid_kw": 20, "import_price": 10}, ZONE)
    assert restored.ledger[day]["import_cost"] == pytest.approx(.15)


def test_sparse_hour_is_not_learned_as_zero_and_missing_cost_has_no_coverage():
    model = Statistics()
    samples(model, NOW, 600, import_price=None)
    samples(model, NOW + 3540, 120, import_price=None)
    assert not any(h["house_kwh"] is not None for h in model.hours)
    assert model.ledger["2026-10-19"]["coverage_hours"] == 0


def test_negative_import_cost_and_negative_export_credit_are_preserved():
    model = Statistics()
    samples(model, NOW, 600, import_price=-.02)
    assert model.ledger["2026-10-19"]["import_cost"] < 0
    samples(model, NOW + 600, 600, grid_kw=-1, export_price=-.03)
    assert model.ledger["2026-10-19"]["export_credit"] < 0


def test_forecast_freezes_before_hour_and_calibration_uses_no_hindsight():
    model = Statistics()
    upcoming = str(int(NOW + 3600))
    model.remember_forecast({"hours": {str(int(NOW)): 8, upcoming: 2}}, NOW)
    assert str(int(NOW)) not in model.issued
    model.remember_forecast({"hours": {upcoming: 100}}, NOW + 3600)
    assert model.issued[upcoming] == 2
    model.hours = [{"solar_forecast": None, "solar_kwh": 1}] + [{"solar_forecast": 2, "solar_kwh": 1}] * 6
    assert model.solar_quality()["factor"] == .5


def test_valid_ev_session_calibrates_energy_and_current_normalized_power():
    model = Statistics()
    for minute in range(61):
        active = 0 < minute < 60
        model.observe(NOW + minute * 60, {"ev_kw": 9 if active else 0, "ev_amps": 40,
            "ev_soc": 60 + min(minute / 6, 10), "ev_energy": minute * .15}, ZONE)
    assert len(model.ev_sessions) == 1
    assert model.ev_estimate(.5) == pytest.approx(.9, rel=.03)
    assert model.ev_power(5, 20) == pytest.approx(4.5)


def test_cost_splits_an_observed_interval_at_exact_time_of_use_boundary():
    from datetime import datetime
    from custom_components.nrg.config import settings
    from test_tariffs import schedule
    rows=schedule()
    rows[0]["end"]="13:00:30"
    rows[1]["start"]="13:00:30"
    config=settings({"supply_plan":"Time-of-use supply","supply_periods":rows,"delivery_cents":2})
    start=datetime(2026,10,19,12,59,50,tzinfo=ZONE).timestamp()
    data={"grid_kw":1,"supply_price":.1,"delivery_price":.02,"import_price":.12,"export_price":0,"_tariffs":config}
    model=Statistics()
    model.observe(start,data,ZONE)
    model.observe(start+80,data,ZONE)
    # Forty seconds at the morning 12c total, forty at the peak 22c total.
    assert model.ledger["2026-10-19"]["import_cost"] == pytest.approx((.12+.22)*40/3600)
