"""Invented capability, EV-competition and conservative-reference regressions."""
from itertools import product
import random
from unittest.mock import patch

import pytest

from conftest import fixture, NOW, ZONE
from custom_components.nrg.planner import (
    battery_modes, household_advice, plan, replacement_value, transition,
)


def row(index=0, *, price=.1, credit=.02, solar=0, house=1, hours=1):
    return {"start": NOW + index * 3600, "end": NOW + (index + hours) * 3600,
            "hours": hours, "house_kwh": house, "solar_kwh": solar,
            "solar_known": True, "price_known": True, "export_known": True,
            "import_price": price, "export_price": credit}


def config(**changes):
    cfg, *_ = fixture(**({"battery_capacity": 5, "backup_reserve": 20,
                         "battery_charge_kw": 8, "round_trip_efficiency": 100} | changes))
    return cfg | {"zone": ZONE}


def value(rows, cfg=None, **kwargs):
    return replacement_value(rows, cfg or config(), ev=kwargs.pop("ev", [0] * len(rows)), details=True, **kwargs)


def test_unsupported_grid_refill_is_not_valued_as_a_cheap_opportunity():
    rows = [row(price=.01), row(1, price=.3)]
    supported = value(rows, config() | {"allow_grid_charge": True})
    unsupported = value(rows, config() | {"allow_grid_charge": False})
    assert supported["value_per_stored_kwh"] == pytest.approx(.01)
    assert supported["basis"] == "permitted_refill"
    assert unsupported["refill_sources_stored_kwh"]["grid"] == 0
    assert unsupported["refill_covered_stored_kwh"] == 0
    assert unsupported["uncovered_stored_kwh"] == 4
    assert unsupported["value_per_stored_kwh"] == pytest.approx(.3)
    assert unsupported["basis"] == "conservative_reference"
    assert unsupported["comparison_limited"]


def test_ev_charging_blocks_grid_refill_even_if_battery_may_serve_ev():
    rows = [row(price=.01), row(1, price=.3)]
    for preserve in (False, True):
        result = value(rows, config(hold_battery_for_ev=preserve), ev=[1, 0])
        assert result["value_per_stored_kwh"] == pytest.approx(.3)
        assert result["refill_sources_stored_kwh"] == {"grid": 4, "solar": 0}
        assert result["basis"] == "permitted_refill"


def test_ev_demand_is_subtracted_before_counting_solar_surplus():
    cfg = config(export_rate="No credit") | {"allow_grid_charge": False}
    rows = [row(solar=5, price=.3, credit=0)]
    no_car = value(rows, cfg)
    with_car = value(rows, cfg, ev=[3])
    assert no_car["refill_covered_stored_kwh"] == 4
    assert no_car["value_per_stored_kwh"] == 0
    assert with_car["refill_covered_stored_kwh"] == 1
    assert with_car["uncovered_stored_kwh"] == 3
    assert with_car["value_per_stored_kwh"] == pytest.approx(.225)


@pytest.mark.parametrize("held_solar,preserve,expected", [(True, True, 4), (False, True, 0), (False, False, 4)])
def test_solar_refill_respects_modes_while_ev_is_charging(held_solar, preserve, expected):
    cfg = config(battery_solar_while_held=held_solar, hold_battery_for_ev=preserve) | {"allow_grid_charge": False}
    result = value([row(solar=8, credit=0)], cfg, ev=[1])
    assert result["refill_sources_stored_kwh"]["solar"] == expected
    assert result["comparison_limited"] == (expected == 0)


@pytest.mark.parametrize("policy,held_solar,expected_solar", [
    ("Preserve battery", False, 0), ("Preserve battery", True, 4), ("Self-consumption", False, 4),
])
def test_manual_fallback_never_claims_grid_refill_and_respects_held_solar(policy, held_solar, expected_solar):
    cfg = config(fallback_battery=policy, battery_solar_while_held=held_solar) | {"_fallback_active": True}
    result = value([row(solar=8, credit=0)], cfg)
    assert result["refill_sources_stored_kwh"] == {"grid": 0, "solar": expected_solar}


def test_unavailable_battery_has_no_claimed_refill():
    result = value([row(solar=8, credit=0)], available=False)
    assert result["refill_covered_stored_kwh"] == 0
    assert result["comparison_limited"]


def test_tiny_partial_refill_cannot_make_uncovered_capacity_free():
    cfg = config(battery_charge_kw=1) | {"allow_grid_charge": False}
    result = value([row(solar=1.1, credit=0, price=.2)], cfg)
    assert result["refill_covered_stored_kwh"] == pytest.approx(.1)
    assert result["uncovered_stored_kwh"] == pytest.approx(3.9)
    assert result["value_per_stored_kwh"] == pytest.approx(.195)


@pytest.mark.parametrize("reserve,capacity,efficiency", [(100, 5, 90), (20, 0, 90), (20, 10, 81)])
def test_effective_capacity_reserve_losses_and_finite_refill(reserve, capacity, efficiency):
    cfg = config(backup_reserve=reserve, round_trip_efficiency=efficiency, battery_charge_kw=1)
    result = value([row(price=.1)], cfg, capacity=capacity)
    need = capacity * (1 - reserve / 100)
    assert result["usable_stored_kwh"] == pytest.approx(need)
    if need == 0:
        assert result["value_per_stored_kwh"] == 0
        assert result["basis"] == "not_applicable"
    else:
        assert result["refill_covered_stored_kwh"] == pytest.approx(.9)
        assert result["reference_per_stored_kwh"] == pytest.approx(.1 / .9)


def test_refill_is_limited_by_trusted_prefix_and_ev_alignment_is_required():
    rows = [row(credit=0), row(1, solar=100, credit=0)]
    rows[1]["price_known"] = False
    result = value(rows, config() | {"allow_grid_charge": False})
    assert result["refill_covered_stored_kwh"] == 0
    with pytest.raises(ValueError, match="one EV allocation"):
        value(rows, ev=[0])


def test_insufficient_refill_marks_advice_limited_and_explains_reference():
    rows = [row(price=.1), row(1, price=.3)]
    cfg = config() | {"allow_grid_charge": False}
    actions = [{"action": "hold", "energy": 4}] * 2
    advice = household_advice(rows, [0, 0], actions, 4, cfg, 5, True, NOW)
    assert advice["confidence"] == "limited"
    assert advice["battery_valuation"]["comparison_limited"]
    assert "not a promised refill" in advice["reason"]
    assert "notifications are withheld" in advice["reason"]


async def test_generated_limited_advice_cannot_send_a_large_savings_notification():
    from types import SimpleNamespace
    from custom_components.nrg.runtime import NRGRuntime
    cfg = config() | {"allow_grid_charge": False, "notifications": True}
    rows = [row(price=.3), row(1, price=.01)]
    advice = household_advice(rows, [0, 0], [{"action": "hold", "energy": 4}] * 2, 4, cfg, 5, True, NOW)
    assert advice["category"] == "wait" and advice["saving"] > .25
    runtime = SimpleNamespace(config=cfg, plan={"expires_at": NOW + 1000, "household": advice},
                              pending_advice=("old", NOW))
    await NRGRuntime.notify(runtime, NOW + 120)
    assert runtime.pending_advice is None


def test_ev_candidates_and_advice_share_one_conservative_value():
    cfg, prices, solar, telemetry, stats = fixture()
    from custom_components.nrg import planner
    actual_search = planner.battery_search
    values = []
    def search(slots, ev, initial, cfg, capacity, terminal, available):
        values.append(terminal)
        return actual_search(slots, ev, initial, cfg, capacity, terminal, available)
    with patch.object(planner, "battery_search", search):
        result = plan(NOW, cfg, ZONE, telemetry, stats, prices, solar, .15)
    assert len(values) == 4
    assert all(v == result["terminal_value"] for v in values)
    assert result["battery_valuation"] == result["household"]["battery_valuation"]
    slots = result["slots"]
    from custom_components.nrg.planner import allocate
    candidates = [allocate(slots, 6, cfg["ev_kw_at_max"], result["deadline"] - cfg["completion_buffer"] * 60, cfg, kind)[0]
                  for kind in ("cheapest", "solar", "earliest", "latest")]
    estimates = [replacement_value(slots, cfg, result["effective_capacity_kwh"], ev=ev) for ev in candidates]
    assert len({round(v, 8) for v in estimates}) > 1
    assert result["terminal_value"] == max(estimates)
    assert result["ev_shortfall_kwh"] < .001


def test_equally_feasible_previous_schedule_retains_threshold_stability():
    cfg, prices, solar, telemetry, stats = fixture()
    previous = plan(NOW, cfg, ZONE, telemetry, stats, prices, solar, .15)
    result = plan(NOW, cfg, ZONE, telemetry, stats, prices, solar, .15, previous=previous)
    assert result["selected_candidate"] == "previous"
    assert result["battery_valuation"]["comparison_candidates"] == 5
    assert result["ev_shortfall_kwh"] < .001
    assert result["terminal_value"] == previous["terminal_value"]


def test_refill_opportunity_matches_maximum_permitted_single_interval_energy_gain():
    # Cross-check the accounting against exact physical transitions at reserve,
    # with ample headroom. Each charging kWh can be counted only once.
    for solar, car, held, preserve, grid, available in product((0, 6), (0, 2), (False, True),
                                                             (False, True), (False, True), (False, True)):
        cfg = config(battery_capacity=100, battery_charge_kw=3, battery_solar_while_held=held,
                     hold_battery_for_ev=preserve) | {"allow_grid_charge": grid}
        s = row(solar=solar)
        modes = battery_modes(s, car, cfg, available)
        physical = max(transition(s, 20, car, mode, cfg, 100, available)["energy"] - 20 for mode in modes)
        result = value([s], cfg, ev=[car], available=available)
        assert result["refill_covered_stored_kwh"] == pytest.approx(max(physical, 0))
        assert sum(result["refill_sources_stored_kwh"].values()) == pytest.approx(result["refill_covered_stored_kwh"])


def test_randomized_permission_restrictions_never_lower_value_or_create_refill():
    rng = random.Random(3017)
    for _ in range(300):
        cfg = config(round_trip_efficiency=rng.choice([50, 81, 90, 100]),
                     battery_solar_while_held=rng.choice([False, True]))
        rows = [row(i, price=rng.uniform(-.1, .5), credit=rng.uniform(-.05, .4),
                    solar=rng.uniform(0, 10), house=rng.uniform(.1, 3)) for i in range(4)]
        allowed = value(rows, cfg | {"allow_grid_charge": True})
        restricted = value(rows, cfg | {"allow_grid_charge": False})
        busy = value(rows, cfg | {"allow_grid_charge": False}, ev=[2] * 4)
        unavailable = value(rows, cfg, available=False)
        assert restricted["value_per_stored_kwh"] >= allowed["value_per_stored_kwh"] - 1e-9
        assert busy["value_per_stored_kwh"] >= restricted["value_per_stored_kwh"] - 1e-9
        assert unavailable["value_per_stored_kwh"] >= busy["value_per_stored_kwh"] - 1e-9
        assert restricted["refill_sources_stored_kwh"]["grid"] == 0
        assert busy["refill_covered_stored_kwh"] <= restricted["refill_covered_stored_kwh"] + 1e-9
        assert unavailable["refill_covered_stored_kwh"] == 0
