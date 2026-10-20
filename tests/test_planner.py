from itertools import product
from datetime import datetime
import json

import pytest

from custom_components.nrg.planner import allocate, battery_search, plan, transition, replacement_value
from conftest import fixture, NOW, ZONE


def test_cheapest_deadline_ready_and_no_selected_limit_increase():
    cfg, prices, solar, car, stats = fixture()
    result = plan(NOW, cfg, ZONE, car, stats, prices, solar, .15)
    charging = [s for s in result["slots"] if s["ev_kwh"] > 0]
    assert result["ev_shortfall_kwh"] < .001
    assert result["completion"] <= result["deadline"]
    assert sum(s["ev_kwh"] for s in charging) == pytest.approx(6)
    assert all(s["ev_amps"] <= 32 for s in charging)
    assert car["ev_limit"] == 80
    assert json.loads(json.dumps(result))["version"] == 2


def test_flat_equal_compensation_no_invented_storage_arbitrage():
    cfg, prices, solar, car, stats = fixture(supply_plan="Flat supply", flat_supply_cents=10, delivery_cents=0, export_adder_cents=0)
    car["connected"] = False
    car["battery_soc"] = 20
    result = plan(NOW, cfg, ZONE, car, stats, [], solar)
    assert not any(s["battery_action"] == "charge" for s in result["slots"])
    assert result["household"]["category"] == "normal"


def test_missing_data_does_not_authorize_grid_charging_but_charge_now_works():
    cfg, prices, solar, car, stats = fixture()
    result = plan(NOW, cfg, ZONE, car, stats, [], {}, None, charge_now=True)
    assert result["ev_status"] == "charge_now"
    assert result["ev_amps"] == 32
    assert result["battery_action"] == "hold"
    assert result["household"]["category"] == "limited"


def test_overdue_session_is_not_silently_moved_to_tomorrow():
    cfg, prices, solar, car, stats = fixture()
    due = NOW - 300
    old = {"deadline": due, "connected": True, "ev_status": "deadline", "departure_setting": "08:00:00", "departure_override": None}
    result = plan(NOW, cfg, ZONE, car, stats, prices, solar, .15, old)
    assert result["deadline"] == due
    assert result["ev_status"] == "deadline"
    assert result["ev_amps"] > 0


def test_unplugged_no_phantom_charging_and_missing_soc_no_phantom_reserve():
    cfg, prices, solar, car, stats = fixture()
    car.update(connected=False, battery_soc=None, battery_ready=False)
    result = plan(NOW, cfg, ZONE, car, stats, prices, solar, .15)
    assert all(s["ev_kwh"] == 0 for s in result["slots"])
    assert all(s["battery_action"] == "hold" for s in result["slots"])


def slot(**changes):
    return {"start": NOW, "end": NOW + 3600, "hours": 1, "house_kwh": 2, "solar_kwh": 0,
            "import_price": .2, "export_price": .1, "price_known": True, "solar_known": True, **changes}


@pytest.mark.parametrize("policy", ["Solar only", "Battery", "No exports"])
@pytest.mark.parametrize("action", ["hold", "serve", "charge"])
def test_transition_energy_conservation_reserve_and_no_battery_export_fiction(policy, action):
    cfg, *_ = fixture(export_policy=policy)
    for sun in (0, 4, 12):
        row = slot(solar_kwh=sun)
        out = transition(row, 10, 1, action, cfg, 27)
        eta = .9 ** .5
        battery_delta = (out["solar_charge_kwh"] + out["grid_charge_kwh"]) * eta - out["battery_discharge_kwh"] / eta
        assert out["energy"] - 10 == pytest.approx(battery_delta)
        assert sun + out["import_kwh"] + out["battery_discharge_kwh"] == pytest.approx(3 + out["solar_charge_kwh"] + out["grid_charge_kwh"] + out["export_kwh"] + out["curtailed_kwh"])
        assert 5.4 <= out["energy"] <= 27
        if policy == "No exports":
            assert out["export_kwh"] == 0
        assert out["export_kwh"] <= max(sun - 3, 0)


def test_short_horizon_search_matches_exhaustive_feasible_modes():
    cfg, *_ = fixture(battery_capacity=5, backup_reserve=20, battery_charge_kw=1, battery_discharge_kw=1)
    slots = [slot(import_price=p, export_price=p, house_kwh=1) for p in (.03, .4, .08)]
    score, rows = battery_search(slots, [0, 0, 0], 2, cfg, 5, .08, True)
    oracle = []
    for sequence in product(("hold", "charge", "serve"), repeat=3):
        energy, cost = 2, 0
        for s, action in zip(slots, sequence):
            out = transition(s, energy, 0, action, cfg, 5)
            energy, cost = out["energy"], cost + out["cost"]
        oracle.append(cost + (2 - energy) * .08)
    assert score == pytest.approx(min(oracle))
    assert len(rows) == 3


def test_tiny_solar_surplus_does_not_make_whole_battery_refill_free():
    cfg, *_ = fixture(battery_capacity=27)
    rows = [slot(import_price=.1, export_price=0, house_kwh=1, solar_kwh=1.1)] + [slot(import_price=.1, export_price=0)] * 24
    assert replacement_value(rows, cfg, 27) > .1


def test_solar_current_adjustment_stays_above_minimum_and_meets_energy():
    cfg, *_ = fixture(ev_max_amps=40, ev_min_amps=6)
    slots = [slot(solar_kwh=4, house_kwh=1, ev_available=True)]
    energy, amps, shortfall = allocate(slots, 2.9, 9, NOW + 3600, cfg, "solar")
    assert amps == [13]
    assert sum(energy) == pytest.approx(2.9)
    assert shortfall == 0


def test_cheap_summer_afternoon_can_charge_ev_and_refill_battery():
    cfg, *_ = fixture(battery_capacity=5, backup_reserve=20, round_trip_efficiency=100,
                      battery_charge_kw=1, battery_discharge_kw=1)
    start = datetime(2026, 7, 6, 14, tzinfo=ZONE).timestamp()
    rows = [slot(start=start, end=start + 3600, import_price=.01, house_kwh=0, ev_available=True),
            slot(start=start + 3600, end=start + 7200, import_price=.5, house_kwh=1, ev_available=True)]

    energy, _, shortfall = allocate(rows, 1, 1, start + 7200, cfg, "cheapest")
    assert energy == [1, 0] and shortfall == 0

    score, actions = battery_search(rows, [0, 0], 1, cfg, 5, 0, True)
    assert [action["action"] for action in actions] == ["charge", "serve"]
    assert score == pytest.approx(.01)
