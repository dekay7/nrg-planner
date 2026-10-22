"""Invented price-gap, storage-accounting and explanation regressions."""
from datetime import datetime

import pytest

from conftest import fixture, NOW, ZONE
from custom_components.nrg.planner import (
    battery_search, household_advice, plan, replacement_value, trusted_prefix,
)

START = datetime(2026, 3, 9, 12, tzinfo=ZONE).timestamp()


def slot(index, *, price=.08, export=.08, solar=0, house=.2, known=True, hours=1):
    start = START + index * 3600
    return {"start": start, "end": start + hours * 3600, "hours": hours,
            "house_kwh": house, "solar_kwh": solar, "solar_known": True,
            "import_price": price, "export_price": export, "price_known": known,
            "export_known": known, "_model_import_price": price if price is not None else .04,
            "_model_export_price": export if export is not None else 0}


def compare(rows, *, initial=5, available=True, allow_grid_charge=True, **overrides):
    config, *_ = fixture(**({"has_ev": False, "battery_capacity": 5, "backup_reserve": 20,
                             "battery_charge_kw": 4, "battery_discharge_kw": 4} | overrides))
    config["zone"] = ZONE
    config["allow_grid_charge"] = allow_grid_charge
    terminal = replacement_value(trusted_prefix(rows, config), config, 5)
    ev = [0.0] * len(rows)
    score, actions = battery_search(rows, ev, initial, config, 5, terminal, available)
    advice = household_advice(rows, ev, actions, initial, config, 5, available, rows[0]["start"])
    return advice, score, actions


def gap_scenario():
    return [slot(0, solar=4, house=1), slot(1), slot(2, price=.30), slot(3, price=.18),
            slot(4, price=None, export=None, solar=8, house=0, known=False)]


def test_unknown_future_solar_refill_cannot_make_peak_appliance_energy_free():
    advice, _, actions = compare(gap_scenario())
    windows = {w["start"]: w for w in advice["windows"]}
    peak = windows[START + 2 * 3600]
    assert actions[2]["action"] == "serve"
    assert peak["cost"] == pytest.approx(.08 / .9, abs=1e-6)
    assert windows[START]["cost"] == pytest.approx(.08)
    assert advice["category"] != "wait"
    assert advice["best_start"] == START
    assert advice["forecast_until"] == START + 4 * 3600


def test_untrusted_tail_cannot_change_prefix_modes_scores_or_advice():
    rows = gap_scenario()
    expected, score, actions = compare(rows)
    # A price island after a gap, huge unknown solar, and numerical placeholders
    # must not influence the economic prefix, including its baseline modes.
    tail = [slot(4, price=-5, export=-4, solar=100, known=False),
            slot(5, price=20, export=20, solar=0)]
    actual, changed_score, changed_actions = compare(rows[:4] + tail)
    assert actual == expected
    assert changed_score == pytest.approx(score)
    assert changed_actions[:4] == actions[:4]
    assert all(a["action"] == "hold" for a in changed_actions[4:])
    assert len(changed_actions) == 6
    assert all(1 <= a["energy"] <= 5 for a in changed_actions)


@pytest.mark.parametrize("efficiency,wear", [(100, 0), (81, 0), (81, 3)])
def test_terminal_energy_accounts_for_storage_losses_and_wear(efficiency, wear):
    rows = [slot(0, house=0), slot(1, price=.4, export=.08, house=.1)]
    advice, _, _ = compare(rows, round_trip_efficiency=efficiency, battery_wear_cents=wear, battery_charge_kw=8)
    peak = next(w for w in advice["windows"] if w["start"] == START + 3600)
    assert peak["cost"] == pytest.approx(.08 / (efficiency / 100) + wear / 100, abs=1e-6)
    assert peak["energy_sources"] == {"grid": 0, "solar": 0, "battery": 1}
    assert peak["grid_import_price"] == .4


@pytest.mark.parametrize("policy", ["Solar only", "No exports"])
def test_explicit_zero_export_credit_can_legitimately_make_surplus_solar_free(policy):
    advice, _, _ = compare([slot(0, solar=4, house=1, export=0), slot(1, price=.4, export=0)],
                           export_policy=policy)
    assert advice["now_cost"] == 0
    assert advice["cost_basis"] == "solar"
    assert advice["confidence"] == "forecast"


@pytest.mark.parametrize("missing", ["price_known", "export_known", "solar_known"])
def test_no_complete_supported_window_returns_limited_advice(missing):
    row = slot(0)
    row[missing] = False
    advice, _, _ = compare([row])
    assert advice["category"] == "limited"
    assert advice["confidence"] == "limited"
    assert advice["windows"] == []
    assert advice["forecast_until"] == START


def test_incomplete_later_window_is_excluded_at_solar_gap():
    rows = [slot(0, hours=.5), slot(.5, hours=.5), slot(1)]
    rows[-1]["solar_known"] = False
    advice, _, _ = compare(rows)
    assert len(advice["windows"]) == 1
    assert advice["windows"][0]["end"] == START + 3600


@pytest.mark.parametrize("initial,available,power", [(1, True, 4), (5, False, 4), (5, True, .1)])
def test_unavailable_or_constrained_battery_does_not_claim_full_battery_supply(initial, available, power):
    rows = [slot(0, house=0), slot(1, price=.4, house=.2)]
    advice, _, _ = compare(rows, initial=initial, available=available, battery_discharge_kw=power, allow_grid_charge=False)
    peak = advice["windows"][1]
    assert peak["energy_sources"]["battery"] == 0
    assert peak["energy_sources"]["grid"] == 1
    assert peak["cost"] == pytest.approx(.4)
    if not available:
        assert advice["confidence"] == "limited"


def test_known_refill_with_zero_credit_can_support_legitimate_peak_time_advice():
    rows = [slot(0, price=.15, export=0, house=2), slot(1, price=.4, export=0, house=.1),
            slot(2, price=.4, export=0, solar=8, house=0)]
    advice, _, _ = compare(rows, battery_discharge_kw=2)
    assert advice["category"] == "wait"
    assert advice["best_start"] == START + 3600
    assert advice["cost_basis"] == "battery"
    assert advice["grid_import_price"] == .4
    assert advice["best_cost"] == 0
    assert "not necessarily the cheapest grid-price window" in advice["reason"]


def test_mixed_sources_and_time_weighted_grid_price_are_explained():
    # A fixed hold baseline avoids conflating physical appliance supply with its
    # net economic cost, which can include lost battery charging opportunities.
    config, *_ = fixture(has_ev=False, battery_capacity=5, flexible_load_minutes=60)
    config["zone"] = ZONE
    rows = [slot(0, hours=.25, price=.1, house=0, solar=.25),
            slot(.25, hours=.75, price=.3, house=0, solar=0)]
    actions = [{"action": "hold", "energy": 5}] * 2
    advice = household_advice(rows, [0, 0], actions, 5, config, 5, True, START)
    assert advice["cost_basis"] == "mixed"
    assert advice["energy_sources"] == {"grid": .75, "solar": .25, "battery": 0}
    assert advice["grid_import_price"] == pytest.approx(.25)
    assert sum(advice["energy_sources"].values()) == 1


def test_plan_cost_coverage_and_ev_feasibility_survive_price_gap():
    cfg, prices, solar, telemetry, stats = fixture()
    result = plan(NOW, cfg, ZONE, telemetry, stats, prices[:2], solar, .15, charge_now=True)
    assert result["economic_until"] == NOW + 2 * 3600
    assert not result["cost_includes_estimates"]
    assert len(result["slots"]) > 8
    assert result["ev_shortfall_kwh"] < .001
    assert result["completion"] <= result["deadline"]
    assert all(s["battery_action"] == "hold" for s in result["slots"] if s["start"] >= result["economic_until"])


@pytest.mark.parametrize("has_solar,policy", [(False, "Solar only"), (True, "No exports")])
def test_inapplicable_export_prices_do_not_block_valid_advice(has_solar, policy):
    rows = [slot(0, export=None), slot(1, export=None)]
    for row in rows:
        row["export_known"] = False
    advice, _, _ = compare(rows, has_solar=has_solar, export_policy=policy)
    assert advice["windows"]
    assert advice["confidence"] == "forecast"
    assert advice["forecast_until"] == rows[-1]["end"]


def test_known_price_island_after_current_gap_does_not_publish_economic_cost():
    cfg, prices, solar, telemetry, stats = fixture(has_ev=False)
    result = plan(NOW, cfg, ZONE, telemetry, stats, prices[1:], solar, None)
    assert result["economic_until"] == NOW
    assert result["modeled_cost"] is None
    assert all(c["modeled_cost"] is None for c in result["candidate_costs"])
    assert result["household"]["confidence"] == "limited"
    assert all(s["battery_action"] == "hold" for s in result["slots"])


@pytest.mark.parametrize("day", [(2026, 3, 8), (2026, 11, 1)])
def test_dst_windows_use_real_elapsed_duration(day):
    start = datetime(*day, 0, 30, tzinfo=ZONE).timestamp()
    rows = [slot(i) for i in range(6)]
    for i, row in enumerate(rows):
        row.update(start=start + i * 3600, end=start + (i + 1) * 3600)
    advice, _, _ = compare(rows, flexible_load_minutes=120)
    assert all(w["end"] - w["start"] == 7200 for w in advice["windows"])
    assert all(sum(w["energy_sources"].values()) == pytest.approx(1) for w in advice["windows"])
