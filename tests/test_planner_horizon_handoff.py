"""Separate planner gate: characterize the existing defect, not a policy change.

Invented constant-price case. The desired-invariance test is explicitly xfailed
until a separately reviewed horizon design passes the existing safety oracles.
"""
import pytest

from conftest import fixture, NOW, ZONE
from custom_components.nrg.planner import plan
from custom_components.nrg.statistics import forecast_net_cost


def scenario():
    config, prices, solar, telemetry, stats = fixture(
        has_ev=False, has_solar=True, battery_capacity=6, battery_charge_kw=4,
        battery_discharge_kw=3, backup_reserve=20, round_trip_efficiency=100,
        export_rate="No credit", house_kw=2,
        comed_price_resilience="Allow brief published estimates")
    config["_comed_last_live"] = NOW - 1800  # Fixed deadline: this hour at :30.
    for row in prices:
        row["supply"] = .1  # Identical numerical price throughout both outlooks.
    for offset in (2, 3):
        solar["hours"][str(int(NOW + offset * 3600))] = 8
    telemetry.update(battery_soc=80, can_grid_charge=False, connected=False)
    now = NOW + 900  # :15, both current-price paths still authorized.
    live = plan(now, config, ZONE, telemetry, stats, prices, solar, .1)
    estimated = plan(now, config, ZONE, telemetry, stats, prices, solar, None)
    observed = {"coverage_hours": 18.25, "import_cost": 1, "export_credit": 0}
    return (live, estimated,
            forecast_net_cost(now, ZONE, observed, live),
            forecast_net_cost(now, ZONE, observed, estimated))


def test_handoff_reproduces_price_gap_mode_and_cash_outlook_discontinuity():
    live, estimated, live_eod, estimated_eod = scenario()
    for planned in (live, estimated):
        assert planned["battery_forecast_available"]
        assert planned["slots"][0]["price_known"]
        assert all(row["supply_price"] == .1 for row in planned["slots"])
        assert all(row["ev_kwh"] == 0 for row in planned["slots"])
        assert all(row["battery_action"] != "charge" for row in planned["slots"])
    assert live["battery_action"] == "serve"
    assert estimated["battery_action"] == "hold"
    assert live["terminal_value"] == 0
    assert estimated["terminal_value"] == pytest.approx(.14)
    assert live["economic_until"] == NOW + 48 * 3600
    assert estimated["economic_until"] == NOW + 1800
    assert not next(row for row in estimated["slots"] if row["start"] == NOW + 1800)["price_known"]
    later = [row for row in estimated["slots"] if row["start"] >= NOW + 3600]
    assert all(row["price_known"] and row["battery_action"] == "hold" for row in later)
    # Cash projection repricing can cover the gap, but cannot repair dispatch.
    assert live_eod["net_cost"] == pytest.approx(1.56)
    assert estimated_eod["net_cost"] == pytest.approx(2.05)
    midnight = NOW + 6 * 3600
    imports = [sum(row["import_kwh"] for row in p["slots"] if row["start"] < midnight)
               for p in (live, estimated)]
    assert imports == pytest.approx([4, 7.5])


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Separate horizon review gate: docs/plans/comed-planner-horizon.md")
def test_equivalent_current_actions_and_economics_do_not_force_whole_outlook_hold():
    live, estimated, _, _ = scenario()
    # Not a general mode-stickiness requirement: the fixture has no changed
    # reserve, fallback, EV, price, solar, hardware or feasible current modes.
    assert estimated["battery_action"] == live["battery_action"]
