"""Invented unpublished ComEd prices: cash projections, never control prices."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import time
from unittest.mock import AsyncMock, patch

import pytest
import yaml
from homeassistant.helpers.template import Template

from conftest import NOW, ZONE, fixture
from custom_components.nrg.forecast import cost_price_estimate, parse_comed, price_at
from custom_components.nrg.planner import plan
from custom_components.nrg.statistics import forecast_net_cost
from test_cost_forecast import ledger
from test_ui import walk

ROOT = Path(__file__).resolve().parents[1]


def published_today(now=NOW, cents=10):
    day = datetime.fromtimestamp(now, ZONE)
    text = " ".join(f"Date.UTC({day.year},{day.month - 1},{day.day},{hour},0,0),{cents}" for hour in range(24))
    return parse_comed(text, now)


def test_morning_projection_fills_unpublished_23_to_midnight_and_recovers_to_published():
    now = datetime(2026, 10, 19, 10, 15, tzinfo=ZONE).timestamp()
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False, house_kw=2)
    prices = published_today(now)
    planned = plan(now, config, ZONE, telemetry, stats, prices, {}, .07)
    observed = ledger(coverage=10.25)
    result = forecast_net_cost(now, ZONE, observed, planned)
    # Current 45 minutes uses live; then 12 published hours and one tentative hour.
    assert result["net_cost"] == pytest.approx(1.2 + 2 * (.75 * .11 + 13 * .14))
    assert result["confidence"] == "tentative"
    assert result["status"] == "ready"
    assert result["estimated_forecast_hours"] == 1
    assert len(result["estimated_forecast_intervals"]) == 1  # Quarter-hours coalesce.
    estimate = result["estimated_forecast_intervals"][0]
    assert estimate["start"] == datetime(2026, 10, 19, 23, tzinfo=ZONE).timestamp()
    assert estimate["end"] == result["forecast_end"]
    assert estimate["source"] == "published_price_median"
    assert estimate["supply_price"] == .1
    assert estimate["samples"] == 24
    assert planned["economic_until"] == estimate["start"]
    assert planned["cost_forecast_until"] == result["forecast_end"]
    assert all(s["cost"] is None and not s["price_known"] for s in planned["slots"]
               if estimate["start"] <= s["start"] < estimate["end"])

    # ComEd's next-day feed starts at today's 23:00. It wins over any estimate.
    tomorrow = " ".join(f"Date.UTC(2026,9,20,{hour},0,0),30" for hour in range(24))
    published = plan(now, config, ZONE, telemetry, stats, prices + parse_comed(tomorrow, now), {}, .07)
    recovered = forecast_net_cost(now, ZONE, observed, published)
    assert recovered["net_cost"] == pytest.approx(result["net_cost"] + 2 * .2)
    assert recovered["confidence"] == "forecast"
    assert recovered["estimated_forecast_hours"] == 0
    assert recovered["estimated_forecast_intervals"] == []


def test_recorded_matching_hour_median_precedes_published_baseline_and_preserves_negative_price():
    config, _, solar, telemetry, stats = fixture(has_ev=False, has_battery=False, house_kw=2)
    prices = published_today(cents=20)
    stats.hours = [{"start": NOW - (day + 1) * 86400, "comed_hour": 23, "supply": supply}
                   for day, supply in enumerate((-.06, -.02, .8))]
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .2)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    estimate = result["estimated_forecast_intervals"][0]
    assert estimate["source"] == "recorded_estimate"
    assert estimate["samples"] == 3
    assert estimate["supply_price"] == -.02
    assert result["remaining_net_cost"] == pytest.approx(5 * 2 * .24 + 2 * .02)
    assert result["confidence"] == "tentative"


@pytest.mark.parametrize("export_basis,credit", [("Supply plus adder", .12), ("Flat credit", .05), ("No credit", 0)])
def test_tentative_cash_prices_supply_linked_exports_but_not_delivery(export_basis, credit):
    config, _, solar, telemetry, stats = fixture(has_ev=False, has_battery=False, house_kw=1,
        export_rate=export_basis, flat_export_cents=5, delivery_cents=19)
    solar["hours"] = {stamp: 4 for stamp in solar["hours"]}
    planned = plan(NOW, config, ZONE, telemetry, stats, published_today(), solar, .1)
    result = forecast_net_cost(NOW, ZONE, ledger(import_cost=0, export_credit=.1), planned)
    assert result["net_cost"] == pytest.approx(-.1 - 6 * 3 * credit)
    assert result["estimated_forecast_intervals"][0]["export_price"] == pytest.approx(credit)


@pytest.mark.parametrize("fault", ["empty", "stale_fetch", "future_fetch", "old_hours", "other_hour_history"])
def test_no_defensible_baseline_waits_instead_of_using_flat_placeholder_or_zero(fault):
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False,
                                           flat_supply_cents=99)
    prices = published_today()
    if fault == "empty":
        prices = []
    elif fault == "stale_fetch":
        prices = [row | {"fetched_at": NOW - 36 * 3600 - 1} for row in prices]
    elif fault == "future_fetch":
        prices = [row | {"fetched_at": NOW + 1} for row in prices]
    elif fault == "old_hours":
        prices = [row | {"start": row["start"] - 7 * 86400} for row in prices]
    else:
        prices = []
        stats.hours = [{"start": NOW - 86400, "comed_hour": 22, "supply": .04}]
    planned = plan(NOW, config, ZONE, telemetry, stats, prices, {}, .1)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert result["confidence"] == "unavailable"
    assert "buying price" in result["reason"]


@pytest.mark.parametrize("fault", ["live", "delivery", "solar", "export", "battery", "ev", "stale_plan"])
def test_tentative_supply_never_hides_other_missing_inputs(fault):
    config, _, solar, telemetry, stats = fixture(has_ev=False, has_battery=False)
    now, live = NOW + 900, .1  # Beyond the strict new-hour publication bridge.
    if fault == "live":
        live = None
    elif fault == "delivery":
        config["delivery_cents"] = None
    elif fault == "solar":
        solar["known"][str(int(NOW + 5 * 3600))] = False
    elif fault == "export":
        config["export_adder_cents"] = None
    elif fault == "battery":
        config.update(has_battery=True, battery_control=False)
    elif fault == "ev":
        config.update(has_ev=True, ev_control=True)
        telemetry["ev_soc"] = None
    planned = plan(now, config, ZONE, telemetry, stats, published_today(now), solar, live)
    if fault == "stale_plan":
        planned["expires_at"] = now
    result = forecast_net_cost(now, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert result["status"] == "waiting"
    assert result["confidence"] == "unavailable"


@pytest.mark.parametrize("supply_plan", ["Flat supply", "Time-of-use supply", "External supply entity"])
def test_other_tariffs_are_never_filled_from_comed(supply_plan):
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False,
                                           supply_plan=supply_plan)
    planned = plan(NOW, config, ZONE, telemetry, stats, published_today(), {}, .1)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] is None
    assert result["estimated_forecast_intervals"] == []


def test_partial_day_and_elapsed_estimates_stay_labeled_without_double_counting():
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False, house_kw=2)
    now = datetime(2026, 10, 19, 22, 45, tzinfo=ZONE).timestamp()
    # With only recorded history, the unpublished future hour can still be priced.
    stats.hours = [{"comed_hour": 23, "supply": .1}]
    planned = plan(now, config, ZONE, telemetry, stats, [], {}, .1)
    result = forecast_net_cost(now, ZONE, ledger(coverage=2), planned)
    assert result["status"] == "partial_day"
    assert result["confidence"] == "tentative"
    assert result["uncovered_past_hours"] == 20.75
    assert result["estimated_forecast_hours"] == 1
    # Exercise elapsed/midnight clipping independent of the normal 7-minute expiry.
    planned["expires_at"] = now + 3600
    refreshed = forecast_net_cost(now + 1800, ZONE, ledger(coverage=2.5, import_cost=1.64), planned)
    assert refreshed["net_cost"] == pytest.approx(result["net_cost"])
    assert refreshed["estimated_forecast_hours"] == .75
    assert refreshed["estimated_forecast_intervals"][0]["start"] == now + 1800


@pytest.mark.parametrize("day", [datetime(2026, 3, 8), datetime(2026, 11, 1)])
def test_tentative_hours_follow_real_dst_intervals_and_next_local_midnight(day):
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False, house_kw=2)
    stats.hours = [{"comed_hour": hour, "supply": .1} for hour in range(24)]
    now = day.replace(hour=0, minute=30, tzinfo=ZONE).timestamp()
    planned = plan(now, config, ZONE, telemetry, stats, [], {}, .1)
    result = forecast_net_cost(now, ZONE, ledger(.5, .14, 0), planned)
    midnight = (day + timedelta(days=1)).replace(tzinfo=ZONE).timestamp()
    assert result["forecast_end"] == midnight
    assert result["net_cost"] == pytest.approx((midnight - (now - 1800)) / 3600 * 2 * .14)
    assert result["estimated_forecast_hours"] == (midnight - now) / 3600 - .5
    intervals = result["estimated_forecast_intervals"]
    assert all(a["end"] == b["start"] for a, b in zip(intervals, intervals[1:]))
    assert len(intervals) == result["estimated_forecast_hours"]


def test_forecast_repricing_cannot_change_selected_flows_controls_or_advice():
    config, _, solar, telemetry, stats = fixture()
    prices = published_today()
    before = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .1)
    with patch("custom_components.nrg.planner.cost_price_estimate", return_value=None):
        strict = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .1)
    assert before["economic_until"] == strict["economic_until"]
    for key in ("battery_action", "battery_target_soc", "ev_amps", "ev_stop_at", "household",
                "modeled_cost", "candidate_costs", "battery_valuation", "selected_candidate"):
        assert before[key] == strict[key]
    for tentative, original in zip(before["slots"], strict["slots"], strict=True):
        assert {key: value for key, value in tentative.items()
                if key not in ("forecast_cost", "forecast_price_estimate")} == {
                    key: value for key, value in original.items() if key != "forecast_cost"}
    assert config["mode"] == "Observation"
    assert not before["cost_includes_estimates"]  # Comparison cost remains strict.


def test_published_median_is_robust_and_does_not_reuse_unrelated_future_or_old_hours():
    config, _, _, _, _ = fixture()
    stamp = NOW + 5 * 3600
    prices = published_today()
    prices[-1]["supply"] = 5  # One published spike must not become the missing price.
    prices += [{"start": stamp + 3600, "fetched_at": NOW, "supply": 5}]
    price = price_at(stamp, NOW, config, prices, .1)
    estimate = cost_price_estimate(stamp, NOW, config, prices, price)
    assert estimate["supply_price"] == .1
    assert estimate["samples"] == 24


@pytest.mark.parametrize("cents", [-6, 0])
def test_signed_and_zero_published_medians_are_real_estimates_not_missing_prices(cents):
    config, _, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False,
                                           house_kw=2, export_rate="No credit")
    planned = plan(NOW, config, ZONE, telemetry, stats, published_today(cents=cents), {}, cents / 100)
    result = forecast_net_cost(NOW, ZONE, ledger(), planned)
    assert result["net_cost"] == pytest.approx(1.2 + 6 * 2 * (cents / 100 + .04))
    assert result["estimated_forecast_intervals"][0]["supply_price"] == cents / 100
    assert result["confidence"] == "tentative"


@pytest.mark.parametrize("estimated_observations", [False, True])
def test_existing_published_estimate_coverage_also_lowers_forecast_confidence(estimated_observations):
    config, prices, _, telemetry, stats = fixture(has_ev=False, has_battery=False, has_solar=False)
    now = NOW + 300
    observed = ledger(coverage=18 + 300 / 3600)
    live = None
    if estimated_observations:
        live = .1
        observed["estimated_coverage_hours"] = .2
    planned = plan(now, config, ZONE, telemetry, stats, prices, {}, live)
    result = forecast_net_cost(now, ZONE, observed, planned)
    assert result["net_cost"] is not None
    assert result["confidence"] == "tentative"
    if estimated_observations:
        assert result["estimated_forecast_hours"] == 0
    else:
        assert result["estimated_forecast_hours"] == pytest.approx(55 / 60)
        assert result["estimated_forecast_intervals"][0]["source"] == "day_ahead"


async def test_runtime_sensor_publishes_tentative_total_and_removes_estimate_when_feed_arrives(hass, installed):
    runtime = installed.runtime_data
    runtime.get_text = AsyncMock(return_value=json.dumps([{"millisUTC": time.time() * 1000, "price": 10}]))
    await runtime.update_options({"supply_plan": "Hourly ComEd", "house_kw": 2})
    await hass.async_block_till_done()
    now = datetime.now(ZONE).replace(hour=10, minute=15, second=0, microsecond=0).timestamp()
    runtime.prices = published_today(now)
    runtime.last_fetch = now
    runtime.live_cache = {"time": now, "supply": .1}
    runtime.stats.ledger[datetime.fromtimestamp(now, ZONE).date().isoformat()] = ledger(coverage=10.25)
    runtime.stats.previous = None
    with patch("custom_components.nrg.runtime.time.time", return_value=now):
        runtime.force_plan = True
        await runtime.async_refresh()
        await hass.async_block_till_done()
        state = hass.states.get("sensor.nrg_net_cost_eod")
        assert float(state.state) == pytest.approx(1.2 + 13.75 * 2 * .14)
        assert state.attributes["confidence"] == "tentative"
        assert state.attributes["estimated_forecast_hours"] == 1
        assert state.attributes["estimated_forecast_intervals"][0]["source"] == "published_price_median"
        assert runtime.plan["economic_until"] < state.attributes["forecast_end"]
        assert hass.states.get("sensor.nrg_import_price_usd").state == "0.14"
        assert runtime.config["mode"] == "Observation"
        assert not runtime.config["ev_control"] and not runtime.config["battery_control"]
        assert runtime.controller.last == {}

        last_hour = state.attributes["estimated_forecast_intervals"][0]["start"]
        runtime.prices.append({"start": last_hour, "supply": .3, "fetched_at": now})
        runtime.force_plan = True
        await runtime.async_refresh()
        await hass.async_block_till_done()
        recovered = hass.states.get("sensor.nrg_net_cost_eod")
        assert float(recovered.state) == pytest.approx(float(state.state) + .4)
        assert recovered.attributes["confidence"] == "forecast"
        assert recovered.attributes["estimated_forecast_intervals"] == []
        assert runtime.controller.last == {}


@pytest.mark.parametrize("attributes", [
    {},
    {"status": "waiting", "confidence": "unavailable", "reason": "Missing solar forecast coverage."},
    {"status": "ready", "confidence": "forecast"},
    {"status": "partial_day", "confidence": "tentative", "estimated_forecast_hours": 1,
     "estimated_forecast_intervals": [{"start": NOW + 5 * 3600, "end": NOW + 6 * 3600,
                                       "supply_price": .1, "source": "published_price_median"}]},
    {"status": "ready", "confidence": "tentative", "estimated_observed_coverage_hours": .2},
])
async def test_both_dashboards_render_tentative_hours_and_preserve_partial_day_warning(hass, attributes):
    hass.states.async_set("sensor.nrg_net_cost_eod", "2.34", attributes)
    for filename in ("nrg-home.yaml", "nrg-settings.yaml"):
        dashboard = yaml.safe_load((ROOT / "custom_components/nrg/dashboards" / filename).read_text())
        note = next(item["content"] for item in walk(dashboard)
                    if "Tentative forecast" in item.get("content", ""))
        rendered = Template(note, hass).async_render()
        assert ("Tentative forecast · lower confidence" in rendered) == (attributes.get("confidence") == "tentative")
        if attributes.get("estimated_forecast_intervals"):
            assert "23:00 CDT–00:00 CDT" in rendered
            assert "10.0¢/kWh supply · recent published-price median" in rendered
            assert "Partial day:" in rendered
        if attributes.get("status") == "waiting":
            assert "Forecast waiting:" in rendered and attributes["reason"] in rendered
        if attributes.get("estimated_observed_coverage_hours"):
            assert "Covered costs so far also include published-price estimates" in rendered
