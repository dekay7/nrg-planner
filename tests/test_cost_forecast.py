"""Invented cash-flow projections; no utility or household history."""
from datetime import datetime, timedelta
import math

import pytest

from conftest import NOW, ZONE, fixture
from custom_components.nrg.planner import plan
from custom_components.nrg.statistics import forecast_net_cost


def outlook(now=NOW, hourly_cost=.2):
    end = now + 48 * 3600
    return {"generated_at": now, "expires_at": now + 420, "economic_until": end,
            "components": {"battery": False}, "ev_forecast_available": True,
            "modeled_cost": 999,
            "slots": [{"start": start, "end": start + 3600, "cost": hourly_cost}
                      for start in range(int(now), int(end), 3600)]}


def ledger(coverage=18, import_cost=1.5, export_credit=.3):
    return {"coverage_hours": coverage, "import_cost": import_cost, "export_credit": export_credit}


def test_forecast_adds_only_remaining_today_cash_cost_not_comparison_score():
    planned = outlook()
    # Tomorrow is deliberately expensive and must not change today's forecast.
    planned["slots"][6]["cost"] = 500
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] == pytest.approx(2.4)
    assert result["observed_net_cost"] == pytest.approx(1.2)
    assert result["remaining_net_cost"] == pytest.approx(1.2)
    assert result["forecast_coverage_hours"] == 6
    assert result["status"] == "ready"
    assert result["forecast_until"] == result["forecast_end"]


def test_refresh_prorates_elapsed_plan_time_without_double_counting_observed_cost():
    planned = outlook()
    now = NOW + 120
    observed = ledger(coverage=18 + 120 / 3600, import_cost=1.5 + .2 * 120 / 3600)
    result = forecast_net_cost(now, ZONE, observed, planned)
    assert result["net_cost"] == pytest.approx(2.4)
    assert result["remaining_net_cost"] == pytest.approx(.2 * (6 - 120 / 3600), abs=1e-4)
    assert result["forecast_start"] == now


def test_current_and_midnight_crossing_slot_are_clipped_to_actual_overlap():
    planned = outlook()
    # One interval straddles both now and midnight; its cash cost is $0.20/hour.
    planned["slots"] = [{"start": NOW - 1800, "end": NOW + 7 * 3600, "cost": 1.5}]
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] == pytest.approx(2.4)
    assert result["remaining_net_cost"] == pytest.approx(1.2)


@pytest.mark.parametrize("day,day_hours", [(datetime(2026, 3, 8), 23), (datetime(2026, 11, 1), 25)])
def test_forecast_uses_next_local_midnight_on_dst_days(day, day_hours):
    now = day.replace(hour=0, minute=30, tzinfo=ZONE).timestamp()
    midnight = (day + timedelta(days=1)).replace(tzinfo=ZONE).timestamp()
    result = forecast_net_cost(now, ZONE, ledger(.5, .1, 0), outlook(now))
    assert result["forecast_end"] == midnight
    assert result["forecast_coverage_hours"] == day_hours - .5
    assert result["net_cost"] == pytest.approx(.2 * day_hours)


def test_partial_past_is_labeled_and_never_backfilled():
    result = forecast_net_cost(NOW, ZONE, ledger(coverage=2), outlook())
    assert result["net_cost"] == pytest.approx(2.4)
    assert result["status"] == "partial_day"
    assert result["uncovered_past_hours"] == 16
    assert result["observed_coverage_hours"] == 2


def test_no_observed_coverage_including_new_day_waits_instead_of_claiming_zero():
    for now in (NOW, datetime(2026, 10, 20, tzinfo=ZONE).timestamp()):
        result = forecast_net_cost(now, ZONE, {}, outlook(now))
        assert result["net_cost"] is None
        assert result["observed_net_cost"] is None
        assert "readings" in result["reason"]


@pytest.mark.parametrize("fault", ["expired", "future_plan", "gap", "overlap", "missing_cost", "nan_cost", "short_horizon", "economic_gap"])
def test_incomplete_or_stale_future_never_becomes_a_full_day_forecast(fault):
    planned = outlook()
    if fault == "expired":
        planned["expires_at"] = NOW
    elif fault == "future_plan":
        planned["generated_at"] = NOW + 1
    elif fault == "gap":
        planned["slots"].pop(2)
    elif fault == "overlap":
        planned["slots"][2]["start"] -= 60
    elif fault == "missing_cost":
        planned["slots"][2]["cost"] = None
    elif fault == "nan_cost":
        planned["slots"][2]["cost"] = math.nan
    elif fault == "short_horizon":
        planned["slots"] = planned["slots"][:2]
    else:
        planned["economic_until"] = NOW + 2 * 3600
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert result["remaining_net_cost"] is None
    assert result["status"] == "waiting"
    assert result["forecast_until"] < result["forecast_end"]
    # The same ledger recovers automatically when a complete plan is available.
    assert forecast_net_cost(NOW, ZONE, ledger(), outlook())["net_cost"] == pytest.approx(2.4)


def test_real_grid_only_plan_matches_independent_flat_price_cash_oracle():
    config, _, _, _, stats = fixture(has_ev=False, has_battery=False, has_solar=False,
                                    supply_plan="Flat supply", flat_supply_cents=10, delivery_cents=4, house_kw=2)
    planned = plan(NOW, config, ZONE, {}, stats, [], {})
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] == pytest.approx(1.2 + 6 * 2 * .14)


def test_real_solar_export_plan_preserves_negative_net_cost():
    config, prices, solar, telemetry, stats = fixture(has_ev=False, has_battery=False, house_kw=1,
        supply_plan="Flat supply", flat_supply_cents=10, export_rate="Flat credit", flat_export_cents=5)
    solar["hours"] = {stamp: 4 for stamp in solar["hours"]}
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, solar)
    result = forecast_net_cost(NOW, ZONE, ledger(import_cost=0, export_credit=.1), planned)
    assert result["net_cost"] == pytest.approx(-.1 - 6 * 3 * .05)


@pytest.mark.parametrize("missing", ["delivery", "export", "solar"])
def test_real_plan_requires_all_applicable_future_coverage(missing):
    config, prices, solar, telemetry, stats = fixture(has_ev=False, has_battery=False)
    if missing == "delivery":
        config = config | {"delivery_plan": "External delivery entity"}
    elif missing == "export":
        config = config | {"export_rate": "Flat credit", "flat_export_cents": None}
    else:
        solar["known"][str(int(NOW + 2 * 3600))] = False
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .15)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert "coverage" in result["reason"]


@pytest.mark.parametrize("fault", ["monitoring_battery", "battery_inputs", "ev_duration", "ev_telemetry", "ev_controls"])
def test_unmodeled_equipment_waits_without_enabling_control_permissions(fault):
    config, prices, solar, telemetry, stats = fixture()
    if fault == "monitoring_battery":
        config = config | {"battery_control": False}
    elif fault == "battery_inputs":
        telemetry["battery_soc"] = None
    elif fault == "ev_duration":
        config = config | {"ev_control": False, "hold_battery_for_ev": False}
        telemetry = telemetry | {"ev_soc": None, "ev_kw": 7, "ev_busy": True}
    elif fault == "ev_telemetry":
        telemetry["ev_soc"] = None
    else:
        telemetry["ev_ready"] = False
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .15)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert result["status"] == "waiting"
    equipment = "battery" if fault.startswith(("battery", "monitoring")) else "EV"
    assert equipment in result["reason"]
    assert config["mode"] == "Observation"


def test_real_ready_battery_and_ev_use_selected_interval_cash_not_wear_or_terminal_value():
    config, prices, solar, telemetry, stats = fixture(battery_wear_cents=20)
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .15)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    cash = sum(slot["cost"] for slot in planned["slots"] if slot["start"] < result["forecast_end"])
    assert result["net_cost"] == pytest.approx(round(1.2 + cash, 4))
    assert result["net_cost"] != pytest.approx(1.2 + planned["modeled_cost"])


async def test_forecast_sensor_is_registered_read_only_updates_and_revokes_stale_plan(hass, installed):
    runtime = installed.runtime_data
    entity_id = "sensor.nrg_net_cost_eod"
    initial = hass.states.get(entity_id)
    assert initial.state == "unknown"
    assert initial.attributes["unit_of_measurement"] == "USD"
    assert initial.attributes["device_class"] == "monetary"
    assert "state_class" not in initial.attributes

    hass.states.async_set("sensor.invented_grid_power", 2, {"unit_of_measurement": "kW"})
    await runtime.update_options({"mappings": {"grid_power": "sensor.invented_grid_power"}})
    await hass.async_block_till_done()
    now = datetime.now(ZONE)
    runtime.stats.ledger[now.date().isoformat()] = ledger(coverage=1) | {
        "import_kwh": 0, "export_kwh": 0, "solar_kwh": 0, "home_kwh": 0, "ev_kwh": 0}
    runtime.stats.previous = None  # Start a new covered interval after seeding the invented ledger.
    runtime.force_plan = True
    await runtime.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert float(state.state) == runtime.data["cost_forecast"]["net_cost"]
    assert state.attributes["observed_net_cost"] == 1.2
    assert state.attributes["remaining_net_cost"] is not None
    assert state.attributes["forecast_end"] == datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), ZONE).timestamp()
    assert state.attributes["operating_mode"] == "Observation"
    assert runtime.controller.last == {}

    runtime.plan["expires_at"] = 0
    runtime.async_set_updated_data(runtime.data)
    await hass.async_block_till_done()
    stale = hass.states.get(entity_id)
    assert stale.state == "unknown"
    assert stale.attributes["status"] == "waiting"
    assert "fresh" in stale.attributes["reason"]
