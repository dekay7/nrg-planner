"""Invented adversarial inputs and independent modeling/accounting oracles."""
from datetime import datetime, timedelta
from itertools import product
import math
import random
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from conftest import NOW, ZONE, fixture
from custom_components.nrg.config import age_factor, settings, validate_sources
from custom_components.nrg.forecast import aggregate_solar, solar_response
from custom_components.nrg.planner import (
    allocate, battery_modes, battery_search, deadline, household_advice, make_slots, plan, transition,
)
from custom_components.nrg.statistics import Statistics
from custom_components.nrg.tariffs import boundaries, period_at
from test_forecasts import source


def test_missing_solar_hour_is_unknown_not_an_implicit_zero():
    hour = str(int(NOW + 3600))
    caches = {"a": {"fetched_at": NOW, "days": ["2026-10-19", "2026-10-20"],
                    "hours": {str(int(NOW)): 1}}}
    result = aggregate_solar([source("a", "roof")], caches, settings({}), NOW, ZONE)
    assert not result["known"][hour]
    assert hour not in result["hours"]
    # Alternative selection is per interval, not merely per calendar date.
    caches["b"] = {"fetched_at": NOW, "days": ["2026-10-19", "2026-10-20"], "hours": {hour: 2}}
    result = aggregate_solar([source("a", "roof"), source("b", "roof")], caches, settings({}), NOW, ZONE)
    assert result["known"][hour] and result["hours"][hour] == 2


def test_solar_internal_gap_is_rejected_instead_of_redistributing_daily_energy():
    raw = {"watts": {"2026-10-20T08:00:00-05:00": 0, "2026-10-20T09:00:00-05:00": 1000,
                     "2026-10-20T16:00:00-05:00": 1000, "2026-10-20T17:00:00-05:00": 0},
           "wh_period": {"2026-10-20T17:00:00-05:00": 8000}}
    with pytest.raises(ValueError, match="gap"):
        solar_response(raw, ZONE, NOW)


def test_explicit_zero_solar_shape_and_total_remain_known():
    raw = {"watts": {f"2026-10-20T{h:02}:00:00-05:00": 0 for h in range(6, 19)},
           "wh_period": {"2026-10-20T18:00:00-05:00": 0}}
    cache = solar_response(raw, ZONE, NOW)
    noon = str(int(datetime(2026, 10, 20, 12, tzinfo=ZONE).timestamp()))
    assert noon in cache["hours"] and cache["hours"][noon] == 0


def test_ev_counter_reset_or_soc_reversal_discards_the_whole_session():
    for failure in ("counter", "soc"):
        model = Statistics()
        for minute in range(61):
            soc, energy = 50 + minute / 6, 100 + minute * .1
            if minute == 30:
                if failure == "counter":
                    energy = 0
                else:
                    soc -= 2
            model.observe(NOW + minute * 60, {"ev_kw": 6 if minute < 60 else 0,
                          "ev_soc": soc, "ev_energy": energy, "ev_amps": 30}, ZONE)
        assert model.ev_sessions == [], failure


def test_house_learning_expires_by_elapsed_days_not_number_of_observations():
    model = Statistics({"hours": [{"start": NOW - 35 * 86400, "house_kwh": 9,
                                  "comed_hour": 18, "supply": .9}]})
    model.observe(NOW, {}, ZONE)
    assert model.demand(NOW, ZONE, 1, True) == (1, 0)
    assert model.price_prior(18) == (None, 0)


def test_observation_gap_preserves_already_covered_portions_without_filling_the_gap():
    model = Statistics()
    values = {"house_kw": 2, "solar_kw": 1}
    for minute in list(range(49)) + list(range(54, 61)):
        model.observe(NOW + minute * 60, values, ZONE)
    assert len(model.hours) == 1
    assert model.hours[0]["house_kwh"] == pytest.approx(2)
    assert model.ledger["2026-10-19"]["solar_kwh"] == pytest.approx(54 / 60)


@pytest.mark.parametrize("weight", [0, -1, float("nan"), float("inf"), True])
def test_invalid_solar_weights_are_rejected_before_aggregation(weight):
    with pytest.raises(ValueError, match="weight"):
        validate_sources([source("a", "roof", weight)])


def dst_config():
    return settings({"supply_plan": "Time-of-use supply", "delivery_cents": 0,
                     "supply_periods": [
                         {"label": "early", "start": "00:00", "end": "01:07:30", "rate_cents": 10},
                         {"label": "late", "start": "01:07:30", "end": "00:00", "rate_cents": 40}]})


def test_fall_dst_boundaries_include_both_folds_and_the_clock_rollback():
    cfg = dst_config()
    start = datetime(2026, 11, 1, 0, tzinfo=ZONE).timestamp()
    end = start + 5 * 3600
    cuts = boundaries(start, end, cfg, ZONE)
    for fold in (0, 1):
        assert datetime(2026, 11, 1, 1, 7, 30, tzinfo=ZONE, fold=fold).timestamp() in cuts
    assert datetime(2026, 11, 1, 1, tzinfo=ZONE, fold=1).timestamp() in cuts
    # Independently sample every second; no interval may straddle a rate change.
    points = sorted({start, end} | cuts)
    for a, b in zip(points, points[1:]):
        assert {period_at(t, cfg["supply_periods"], ZONE)[0] for t in range(int(a), int(b))} == {
            period_at(a, cfg["supply_periods"], ZONE)[0]}


def test_ledger_splits_a_repeated_nonquarter_hour_tariff_change():
    cfg = dst_config()
    start = datetime(2026, 11, 1, 1, 7, tzinfo=ZONE, fold=1).timestamp()
    values = {"grid_kw": 1, "supply_price": .1, "delivery_price": 0,
              "import_price": .1, "export_price": 0, "_tariffs": cfg}
    model = Statistics()
    model.observe(start, values, ZONE)
    model.observe(start + 60, values, ZONE)
    assert model.ledger["2026-11-01"]["import_cost"] == pytest.approx((.1 + .4) / 120)


def test_ev_window_boundaries_repeat_during_fall_dst():
    cfg = settings({"ev_start_time": "01:07:30", "departure_time": "01:23:30",
                    "flat_supply_cents": 10, "delivery_cents": 0})
    now = datetime(2026, 11, 1, 0, tzinfo=ZONE).timestamp()
    slots = make_slots(now, cfg, ZONE, Statistics(), [], {}, None, now + 5 * 3600)
    for fold, key in product((0, 1), ("ev_start_time", "departure_time")):
        h, m, s = map(int, cfg[key].split(":"))
        stamp = datetime(2026, 11, 1, h, m, s, tzinfo=ZONE, fold=fold).timestamp()
        assert any(slot["start"] == stamp for slot in slots)
    available = sum(s["hours"] for s in slots if s["start"] < now + 5 * 3600 and s["ev_available"])
    assert available == pytest.approx(32 / 60)


@pytest.mark.parametrize("zone_name", ["America/Chicago", "Asia/Kolkata", "Australia/Lord_Howe"])
def test_solar_normalization_matches_local_midnight_overlap_oracle(zone_name):
    zone = ZoneInfo(zone_name)
    midnight = datetime(2026, 10, 20, tzinfo=zone)
    points = [midnight + timedelta(hours=i) for i in range(49)]
    raw = {"watts": {p.isoformat(): 1000 for p in points},
           "wh_period": {(midnight + timedelta(hours=12)).isoformat(): 24000,
                         (midnight + timedelta(hours=36)).isoformat(): 48000}}
    cache = solar_response(raw, zone, midnight.timestamp())
    # Independent overlap oracle: each day has a different normalized constant
    # rate. Partial first/last UTC bins remain unknown, never scaled to an hour.
    start, middle, end = (midnight.timestamp(), (midnight + timedelta(days=1)).timestamp(),
                          (midnight + timedelta(days=2)).timestamp())
    expected = {}
    for hour in range(math.ceil(start / 3600) * 3600, math.floor(end / 3600) * 3600, 3600):
        expected[str(hour)] = (max(min(hour + 3600, middle) - hour, 0)
                               + 2 * max(hour + 3600 - max(hour, middle), 0)) / 3600
    assert cache["hours"] == pytest.approx(expected)


async def test_inconsistent_house_only_meter_is_not_learned(hass, installed):
    runtime = installed.runtime_data
    mappings = {key: "sensor.example_audit_" + key for key in ("home_power", "ev_power", "grid_power")}
    for key, value in (("home_power", 2), ("ev_power", 3), ("grid_power", 20)):
        hass.states.async_set(mappings[key], value, {"unit_of_measurement": "kW"})
    await runtime.update_options({"has_ev": True, "home_includes_ev": False, "mappings": mappings})
    assert runtime.snapshot()["house_kw"] is None
    hass.states.async_set(mappings["grid_power"], 5, {"unit_of_measurement": "kW"})
    assert runtime.snapshot()["house_kw"] == 2


async def test_runtime_uses_both_device_current_bounds_for_predictions(hass, installed):
    runtime = installed.runtime_data
    hass.states.async_set("number.example_audit_current", 16,
                          {"unit_of_measurement": "A", "min": 12, "max": 20})
    with patch("custom_components.nrg.runtime.plan", wraps=plan) as calculate:
        await runtime.update_options({"has_ev": True, "ev_control": True,
                                      "ev_min_amps": 6, "ev_max_amps": 32, "ev_kw_at_max": 7.2,
                                      "mappings": {"ev_current": "number.example_audit_current"}})
        await runtime.async_refresh()
        effective = calculate.call_args.args[1]
    assert effective["ev_min_amps"] == 12
    assert effective["ev_max_amps"] == 20
    assert effective["ev_kw_at_max"] == pytest.approx(7.2 * 20 / 32)
    assert runtime.config["ev_min_amps"] == 6  # User's manual settings are retained.
    assert runtime.config["mode"] == "Observation" and runtime.controller.last == {}


def test_random_physical_transitions_conserve_energy_and_obey_limits():
    rng = random.Random(51302)
    for _ in range(1200):
        cfg, *_ = fixture(round_trip_efficiency=rng.uniform(50, 100), backup_reserve=rng.uniform(0, 100),
                          battery_charge_kw=rng.uniform(.5, 30), battery_discharge_kw=rng.uniform(.5, 30),
                          battery_solar_while_held=rng.choice([True, False]),
                          export_policy=rng.choice(["Solar only", "No exports", "Battery"]))
        capacity, hours = rng.uniform(1, 200), rng.uniform(1 / 3600, 1)
        initial = rng.uniform(0, capacity)
        house, car, sun = (rng.uniform(0, 40) * hours for _ in range(3))
        row = {"hours": hours, "house_kwh": house, "solar_kwh": sun,
               "import_price": rng.uniform(-1, 1), "export_price": rng.uniform(-1, 1)}
        action, available = rng.choice(["hold", "serve", "charge"]), rng.choice([False, True])
        out = transition(row, initial, car, action, cfg, capacity, available)
        eta = math.sqrt(cfg["round_trip_efficiency"] / 100)
        charging = out["grid_charge_kwh"] + out["solar_charge_kwh"]
        delivered = out["battery_discharge_kwh"]
        assert out["energy"] == pytest.approx(initial + charging * eta - delivered / eta)
        assert sun + out["import_kwh"] + delivered == pytest.approx(
            house + car + charging + out["export_kwh"] + out["curtailed_kwh"])
        assert -1e-9 <= out["energy"] <= capacity + 1e-9
        assert out["energy"] >= min(initial, capacity * cfg["backup_reserve"] / 100) - 1e-9
        assert charging <= cfg["battery_charge_kw"] * hours + 1e-9
        assert delivered <= cfg["battery_discharge_kw"] * hours + 1e-9
        assert out["export_kwh"] <= max(sun - house - car, 0) + 1e-9
        assert out["cost"] == pytest.approx(out["import_kwh"] * row["import_price"]
                                            - out["export_kwh"] * row["export_price"] + out["wear_cost"])
        if not available:
            assert out["energy"] == initial and charging == delivered == 0


@pytest.mark.parametrize("zone_name,day,boundary", [
    ("America/Chicago", "2026-03-08", "02:07:30"),
    ("Australia/Lord_Howe", "2026-04-05", "01:47:30"),
    ("Australia/Lord_Howe", "2026-10-04", "02:07:30"),
])
def test_tariff_intervals_are_constant_across_skipped_and_half_hour_dst(zone_name, day, boundary):
    zone = ZoneInfo(zone_name)
    start = datetime.fromisoformat(day).replace(tzinfo=zone).timestamp()
    cfg = dst_config()
    cfg["supply_periods"][0]["end"] = cfg["supply_periods"][1]["start"] = boundary
    points = sorted({start, start + 5 * 3600} | boundaries(start, start + 5 * 3600, cfg, zone))
    for a, b in zip(points, points[1:]):
        expected = period_at(a, cfg["supply_periods"], zone)
        assert all(period_at(t, cfg["supply_periods"], zone) == expected for t in range(int(a), int(b)))


@pytest.mark.parametrize("day,time,expected_hour", [("2026-03-08", "02:30", 3), ("2026-11-01", "01:30", 1)])
def test_daily_departure_uses_documented_dst_resolution(day, time, expected_hour):
    now = datetime.fromisoformat(day).replace(tzinfo=ZONE).timestamp()
    due = datetime.fromtimestamp(deadline(now, settings({"departure_time": time}), ZONE, {}, {}), ZONE)
    assert due.hour == expected_hour and due.minute == 30 and due.fold == 0


def test_short_search_scores_are_feasible_against_an_exhaustive_oracle():
    rng = random.Random(937)
    for _ in range(80):
        cfg, *_ = fixture(battery_capacity=5, backup_reserve=rng.choice([0, 20, 100]),
                          round_trip_efficiency=rng.choice([50, 81, 100]),
                          battery_solar_while_held=rng.choice([False, True]),
                          hold_battery_for_ev=rng.choice([False, True]))
        rows = [{"hours": .25, "house_kwh": rng.uniform(0, 2), "solar_kwh": rng.uniform(0, 2),
                 "import_price": rng.uniform(-.2, .5), "export_price": rng.uniform(-.1, .3),
                 "price_known": True, "export_known": True, "solar_known": True} for _ in range(4)]
        ev, initial, terminal = [rng.choice([0, .5]) for _ in rows], rng.uniform(0, 5), rng.uniform(0, .5)
        score, path = battery_search(rows, ev, initial, cfg, 5, terminal, True)
        oracle = []
        for sequence in product(*(battery_modes(row, car, cfg, True) for row, car in zip(rows, ev))):
            energy, cash = initial, 0
            for row, car, mode in zip(rows, ev, sequence):
                out = transition(row, energy, car, mode, cfg, 5)
                energy, cash = out["energy"], cash + out["cost"]
            oracle.append(cash + (initial - energy) * terminal)
        # Approximation can lose optimality, but cannot invent a cheaper-than-
        # feasible trajectory or report a score different from its actual path.
        assert score >= min(oracle) - 1e-9
        assert score == pytest.approx(sum(row["cost"] for row in path) + (initial - path[-1]["energy"]) * terminal)
        assert all(out["action"] in battery_modes(row, car, cfg, True) for row, car, out in zip(rows, ev, path))


def test_grid_only_appliance_costs_match_an_independent_overlap_oracle():
    rng = random.Random(8702)
    for _ in range(100):
        cfg = settings({"has_ev": False, "has_battery": False, "has_solar": False,
                        "flexible_load_kwh": rng.uniform(.1, 5), "flexible_load_minutes": rng.choice([15, 45, 90])}) | {"zone": ZONE}
        slots = [{"start": NOW + i * 900, "end": NOW + (i + 1) * 900, "hours": .25,
                  "house_kwh": rng.uniform(0, 2), "solar_kwh": 0, "import_price": rng.uniform(-.2, .5),
                  "export_price": 0, "price_known": True, "export_known": True, "solar_known": True} for i in range(12)]
        actions = [transition(row, 0, 0, "hold", cfg, 0, False) for row in slots]
        advice = household_advice(slots, [0] * len(slots), actions, 0, cfg, 0, False, NOW)
        duration = cfg["flexible_load_minutes"] * 60
        for window in advice["windows"]:
            rate = sum(row["import_price"] * max(min(row["end"], window["end"]) - max(row["start"], window["start"]), 0)
                       for row in slots) / duration
            assert window["cost"] == pytest.approx(cfg["flexible_load_kwh"] * rate, abs=1e-6)
            assert window["grid_import_price"] == pytest.approx(rate)
            assert window["energy_sources"]["grid"] == pytest.approx(cfg["flexible_load_kwh"], abs=1e-6)


def test_missing_solar_does_not_publish_a_known_interval_cost():
    cfg, prices, solar, telemetry, stats = fixture()
    solar["known"][str(int(NOW + 3600))] = False
    result = plan(NOW, cfg, ZONE, telemetry, stats, prices, solar, .15)
    missing = [row for row in result["slots"] if not row["solar_known"]]
    assert missing and all(row["cost"] is None for row in missing)


def test_age_models_are_finite_monotonic_and_do_not_invent_future_age():
    from datetime import date
    for degradation in (0, .7, 2, 15):
        factors = [age_factor("2020-01-01", degradation, date(year, 1, 1)) for year in (2019, 2020, 2025, 2050)]
        assert factors[:2] == [1, 1]
        assert all(math.isfinite(v) and 0 < v <= 1 for v in factors)
        assert factors == sorted(factors, reverse=True)


@pytest.mark.parametrize("raw", [None, [], {"watts": [], "wh_period": {}}, {"watts": {}, "wh_period": []}])
def test_malformed_solar_containers_fail_with_a_handled_validation_error(raw):
    with pytest.raises(ValueError):
        solar_response(raw, ZONE, NOW)


@pytest.mark.parametrize("failure", ["duplicate", "daily_energy"])
def test_solar_rejects_duplicate_instants_and_implausible_energy(failure):
    raw = {"watts": {"2026-10-20T11:00:00-05:00": 0, "2026-10-20T12:00:00-05:00": 1000,
                     "2026-10-20T13:00:00-05:00": 0},
           "wh_period": {"2026-10-20T12:00:00-05:00": 1000}}
    if failure == "duplicate":
        raw["watts"]["2026-10-20T17:00:00+00:00"] = 1000
    else:
        raw["wh_period"]["2026-10-20T12:00:00-05:00"] = 1e100
    with pytest.raises(ValueError):
        solar_response(raw, ZONE, NOW)


def test_partial_solar_edges_and_zero_endpoints_do_not_invent_daylight_coverage():
    raw = {"watts": {"2026-10-20T10:15:00-05:00": 0, "2026-10-20T11:15:00-05:00": 1000,
                     "2026-10-20T12:15:00-05:00": 0},
           "wh_period": {"2026-10-20T12:15:00-05:00": 1000}}
    hours = solar_response(raw, ZONE, NOW)["hours"]
    assert set(hours) == {str(int(datetime(2026, 10, 20, 11, tzinfo=ZONE).timestamp()))}


def test_large_relative_solar_weights_remain_finite_and_keep_the_same_average():
    caches = {entry: {"fetched_at": NOW, "days": ["2026-10-19"], "hours": {str(int(NOW)): energy}}
              for entry, energy in (("a", 1), ("b", 3))}
    result = aggregate_solar([source("a", "roof", "1e308"), source("b", "roof", 1e308)],
                             caches, settings({}), NOW, ZONE)
    assert result["hours"][str(int(NOW))] == 2


def test_covered_zero_series_spanning_midnight_keeps_complete_coverage():
    start = datetime(2026, 10, 20, tzinfo=ZONE)
    points = [start + timedelta(hours=i) for i in range(49)]
    raw = {"watts": {p.isoformat(): 0 for p in points},
           "wh_period": {(start + timedelta(hours=12)).isoformat(): 0,
                         (start + timedelta(hours=36)).isoformat(): 0}}
    hours = solar_response(raw, ZONE, NOW)["hours"]
    assert len(hours) == 48 and set(hours.values()) == {0}


def test_random_ev_allocations_match_independent_feasible_energy_bound():
    rng = random.Random(1508)
    cfg = settings({"ev_max_amps": 32, "ev_min_amps": 6})
    for _ in range(200):
        cursor, slots = NOW, []
        for _ in range(8):
            hours = rng.uniform(.01, .5)
            slots.append({"start": cursor, "end": cursor + hours * 3600, "hours": hours,
                          "house_kwh": rng.random(), "solar_kwh": rng.uniform(0, 4),
                          "solar_known": rng.choice([False, True]), "price_known": rng.choice([False, True]),
                          "import_price": rng.uniform(-.2, .5), "export_price": rng.uniform(-.1, .3),
                          "ev_available": rng.choice([False, True])})
            cursor += hours * 3600
        need, power, cutoff = rng.uniform(0, 20), rng.uniform(1, 12), rng.uniform(NOW, cursor)
        feasible = sum(max(min(s["end"], cutoff) - s["start"], 0) / 3600 * power
                       for s in slots if s["ev_available"])
        for kind in ("earliest", "latest", "cheapest", "solar"):
            energies, amps, missing = allocate(slots, need, power, cutoff, cfg, kind)
            assert sum(energies) == pytest.approx(min(need, feasible))
            assert missing == pytest.approx(max(need - feasible, 0))
            for slot, energy, current in zip(slots, energies, amps):
                assert energy >= 0
                if energy:
                    assert slot["ev_available"] and slot["start"] < cutoff
                    assert cfg["ev_min_amps"] <= current <= cfg["ev_max_amps"]
                    assert energy <= max(min(slot["end"], cutoff) - slot["start"], 0) / 3600 * power + 1e-8
