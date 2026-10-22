"""Bounded published estimates, invented delays, and command-time safeguards."""
import json
import time
from unittest.mock import AsyncMock, patch

import pytest

from conftest import NOW, ZONE, fixture
from custom_components.nrg.config import settings, validate
from custom_components.nrg.fallback import PriceFallback
from custom_components.nrg.forecast import price_at
from custom_components.nrg.planner import plan, battery_modes
from custom_components.nrg.runtime import NRGRuntime
from custom_components.nrg.sensor import NRGSensor
from custom_components.nrg.statistics import Statistics


@pytest.fixture
async def resilient_runtime(hass, installed):
    runtime = installed.runtime_data
    runtime.get_text = AsyncMock(return_value=json.dumps([{"millisUTC": time.time() * 1000, "price": 4}]))
    await runtime.update_options({"price_fallback": "Custom fallback", "supply_plan": "Hourly ComEd",
                                  "comed_price_resilience": "Allow brief published estimates"})
    await hass.async_block_till_done()
    runtime.fallback = PriceFallback()
    runtime._fallback_active = False
    runtime._comed_estimated = False
    runtime.comed_continuity = {"source": "api", "last_live": NOW}
    runtime.live_cache = {"time": NOW, "supply": .04}
    runtime.prices = [{"start": NOW + i * 3600, "supply": .06, "fetched_at": NOW - 3600} for i in range(3)]
    runtime.last_fetch = NOW
    runtime.forecast_status = {}
    runtime.data = {}
    return runtime


def estimate_config(**overrides):
    return settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4,
                     "comed_price_resilience": "Allow brief published estimates", **overrides}) | {"_comed_last_live": NOW}


def test_opt_in_does_not_change_existing_defaults_or_permissions():
    config = settings({})
    assert config["comed_price_resilience"] == "Strict live pricing"
    assert config["mode"] == "Observation"
    assert not config["ev_control"] and not config["battery_control"]
    with pytest.raises(ValueError, match="During ComEd"):
        validate({"comed_price_resilience": "Unlimited estimates"})


@pytest.mark.parametrize("offset,known", [(899, True), (900, True), (1650, True), (3599, True), (3600, False), (3700, False)])
def test_allowance_is_bounded_by_verified_observation_not_hour_or_forecast_fetch(offset, known):
    now = NOW + offset
    cache = [{"start": int(now // 3600) * 3600, "supply": .06, "fetched_at": now}]
    current = price_at(now, now, estimate_config(), cache, None)
    assert current["price_known"] is known
    assert current["comed_estimated_price"] is known
    assert current["comed_estimate_until"] == NOW + 3600


@pytest.mark.parametrize("cache", [[], [{"start": NOW - 3600, "supply": .06, "fetched_at": NOW}],
                                   [{"start": NOW, "supply": .06, "fetched_at": NOW - 36 * 3600 - 1}],
                                   [{"start": NOW, "supply": .06, "fetched_at": NOW + 2000}]])
def test_only_valid_exact_hour_published_coverage_can_bridge(cache):
    current = price_at(NOW + 1650, NOW + 1650, estimate_config(), cache, None, lambda h: (.03, 5))
    assert not current["price_known"] and not current["comed_estimated_price"]


@pytest.mark.parametrize("anchor", [None, NOW + 2000])
def test_cold_start_or_clock_rollback_cannot_grant_an_extra_hour(anchor):
    config = estimate_config() | {"_comed_last_live": anchor}
    cache = [{"start": NOW, "supply": .06, "fetched_at": NOW}]
    current = price_at(NOW + 1650, NOW + 1650, config, cache, None)
    assert not current["price_known"]
    if anchor is None:
        assert price_at(NOW + 16, NOW + 16, config, cache, None)["comed_estimated_price"]


async def test_delayed_success_uses_estimate_without_renewing_anchor_and_labels_costs(resilient_runtime):
    runtime = resilient_runtime
    runtime.stats = Statistics()
    runtime.get_text.return_value = json.dumps([{"millisUTC": NOW * 1000, "price": 4}])
    snapshot = runtime.snapshot() | {"grid_kw": 2, "home_kw": 2, "solar_kw": 0, "ev_kw": 0}
    for offset in (1650, 1770):
        with (patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset),
              patch.object(runtime, "snapshot", return_value=snapshot)):
            runtime.data = await runtime._async_update_data()
            health = runtime.data["fallback"]
            assert health["state"] == "Degraded" and not health["active"]
            assert health["comed_estimated_price"] and health["price_known"]
            assert health["last_live_observation"] == NOW
            assert health["estimate_seconds_remaining"] == 3600 - offset
            assert health["forecast_age_seconds"] == 3600 + offset
            assert "published estimate" in health["reason"]
            assert "minutes old" in runtime.forecast_status["live_price"]
            assert runtime.comed_continuity["last_live"] == NOW
            assert runtime.live_supply() is None
            assert runtime.plan["cost_includes_estimates"]
            sensor = NRGSensor(runtime, "supply_price", "Invented price", None, None)
            assert sensor.native_value == 6
            assert sensor.extra_state_attributes["comed_estimated_price"]
    ledger = next(iter(runtime.stats.ledger.values()))
    assert ledger["estimated_coverage_hours"] == pytest.approx(120 / 3600)
    assert ledger["estimated_import_cost"] == pytest.approx(2 * .10 * 120 / 3600)
    assert runtime.stats.bucket["supply_values"] == []
    assert runtime.controller.last == {}  # Observation never commands equipment.


async def test_command_time_estimate_transition_revokes_old_plan_without_postponing_poll(resilient_runtime):
    runtime = resilient_runtime
    runtime.plan = {"expires_at": NOW + 3000}
    revision = runtime.revision
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 1650):
        health = runtime.evaluate_fallback()
    assert health["comed_estimated_price"] and runtime.plan == {}
    assert runtime.revision > revision and runtime.force_plan
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 3600):
        health = runtime.evaluate_fallback()
    assert health["active"] and health["missing"] == ["supply"]
    assert not health["comed_publication_bridge"]  # Next-hour bridge cannot renew an expired outage.


async def test_restart_preserves_anchor_learning_and_automatic_fallback_latch(resilient_runtime, hass):
    runtime = resilient_runtime
    runtime.stats.hours = [{"start": NOW - 3600, "house_kwh": 2}]
    runtime.stats.ledger = {"2026-10-19": {"import_cost": 1, "coverage_hours": 1}}
    await runtime.store.async_save(runtime.persisted())
    restored = NRGRuntime(hass, runtime.entry)
    await restored.load()
    restored.prices = runtime.prices
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 3500):
        assert restored.evaluate_fallback()["estimate_seconds_remaining"] == 100
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 3600):
        assert restored.evaluate_fallback()["active"]
    assert restored.stats.export() == runtime.stats.export()
    await restored.store.async_save(restored.persisted())
    restarted = NRGRuntime(hass, runtime.entry)
    await restarted.load()
    restarted.prices = runtime.prices
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 2000):
        # Even a backwards clock/restart plus a usable forecast cannot release an existing outage.
        assert restarted.evaluate_fallback(allow_recovery=True)["active"]
    assert restarted.comed_continuity["last_live"] == NOW


async def test_existing_outage_needs_distinct_fresh_live_recovery_not_estimates(resilient_runtime):
    runtime = resilient_runtime
    runtime.fallback.automatic = True
    for offset in (1650, 1800):
        with patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset):
            health = runtime.evaluate_fallback(allow_recovery=True)
            assert health["active"] and health["state"] == "Fallback"
            assert health["recovery_since"] is None
    runtime.live_cache = {"time": NOW + 1800, "supply": .04}
    for offset in (1800, 1930):
        with patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset):
            assert runtime.evaluate_fallback(allow_recovery=True)["state"] == "Recovering"
    runtime.live_cache = {"time": NOW + 2100, "supply": .05}
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 2100):
        assert runtime.evaluate_fallback(allow_recovery=True)["state"] == "Healthy"
        assert runtime.comed_continuity["last_live"] == NOW + 2100
        assert runtime.plan == {} and runtime.force_plan


async def test_missing_delivery_and_manual_requests_still_win(resilient_runtime, hass):
    runtime = resilient_runtime
    runtime.fallback.manual = True
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 1650):
        assert runtime.evaluate_fallback()["reason"] == "Manual activation"
    runtime.fallback.manual = False
    hass.config_entries.async_update_entry(runtime.entry, options=dict(runtime.entry.options) | {"delivery_cents": None})
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 1650):
        health = runtime.evaluate_fallback()
        assert health["active"] and health["missing"] == ["delivery"]


async def test_changing_live_mapping_cannot_reuse_another_sources_allowance(resilient_runtime, hass):
    runtime = resilient_runtime
    hass.config_entries.async_update_entry(runtime.entry, options=dict(runtime.entry.options) | {"mappings": {"live_supply": "sensor.invented_missing_price"}})
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 1650):
        assert runtime.evaluate_fallback()["active"]
        assert runtime.rate_context().get("_comed_last_live") is None


def test_estimate_preserves_ev_planning_and_prevents_battery_grid_refill():
    config, prices, solar, telemetry, stats = fixture(comed_price_resilience="Allow brief published estimates", has_solar=False,
                                                    has_ev=False, battery_capacity=10)
    config["_comed_last_live"] = NOW - 1700
    telemetry.update(battery_native_reserve=40, battery_reserve_mapped=True)
    result = plan(NOW + 1650, config, ZONE, telemetry, stats, prices, solar)
    current = result["slots"][0]
    assert current["comed_estimated_price"] and current["battery_action"] != "charge"
    assert "charge" not in battery_modes(current, 0, config, True)
    assert min(s["battery_soc"] for s in result["slots"] if s["battery_soc"] is not None) >= 40
    assert NOW + 1900 in [s["start"] for s in result["slots"]]  # Exact allowance expiry is a slot boundary.
    # A pending departure still charges rather than applying the saved fallback pause.
    config.update(has_ev=True, departure_override="2026-10-19T18:45:00-05:00")
    result = plan(NOW + 1650, config, ZONE, telemetry, stats, prices, solar)
    assert result["ev_amps"] > 0 and result["ev_status"] != "fallback_paused"


def test_estimated_cost_accounting_stops_at_exact_expiry():
    stats = Statistics()
    values = {"grid_kw": 2, "import_price": .10, "export_price": .02, "supply_price": .06,
              "delivery_price": .04, "_price_estimated": True, "_price_valid_until": NOW + 60}
    stats.observe(NOW, values, ZONE)
    stats.observe(NOW + 120, values, ZONE)
    ledger = next(iter(stats.ledger.values()))
    assert ledger["coverage_hours"] == pytest.approx(60 / 3600)
    assert ledger["estimated_coverage_hours"] == ledger["coverage_hours"]
    assert ledger["import_cost"] == pytest.approx(2 * .10 * 60 / 3600)


@pytest.mark.parametrize("supply", ["Flat supply", "Time-of-use supply", "External supply entity"])
def test_saved_resilience_option_does_not_change_other_supply_plans(supply):
    config = estimate_config(supply_plan=supply, flat_supply_cents=8)
    current = price_at(NOW + 1650, NOW + 1650, config, [], None)
    assert current["comed_estimate_until"] is None
    assert not current["comed_estimated_price"]


async def test_tariff_flow_and_native_select_preserve_other_options(hass, installed):
    before = dict(installed.options)
    result = await hass.config_entries.options.async_init(installed.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "tariff"})
    assert "comed_price_resilience" in {marker.schema for marker in result["data_schema"].schema}
    await hass.services.async_call("select", "select_option", {
        "entity_id": "select.nrg_comed_price_resilience", "option": "Allow brief published estimates"}, blocking=True)
    await hass.async_block_till_done()
    assert dict(installed.options) == before | {"comed_price_resilience": "Allow brief published estimates"}
    assert installed.runtime_data.config["mode"] == "Observation"
    assert not installed.runtime_data.config["battery_control"]


async def test_estimate_banner_renders_age_and_remaining_budget(hass):
    from homeassistant.helpers.template import Template
    from tools.build_ui import pricing_health_note
    hass.states.async_set("sensor.nrg_pricing_health", "Degraded", {
        "active": False, "comed_estimated_price": True, "reason": "Invented delayed feed",
        "estimate_seconds_remaining": 1800, "forecast_age_seconds": 1200})
    rendered = Template(pricing_health_note()["content"], hass).async_render(parse_result=False)
    assert "Published estimate, not a live price" in rendered
    assert "30" in rendered and "20" in rendered
    assert "battery grid charging is blocked" in rendered


@pytest.mark.parametrize("grid,expected_cost,expected_credit", [(2, -.02, 0), (-2, 0, -.04)])
def test_estimated_ledger_preserves_signed_costs_and_existing_data(grid, expected_cost, expected_credit):
    stats = Statistics()
    values = {"grid_kw": grid, "import_price": -.01, "export_price": -.02, "_price_estimated": True}
    stats.observe(NOW, values, ZONE)
    for i in range(1, 31):
        stats.observe(NOW + i * 120, values, ZONE)
    ledger = next(iter(stats.ledger.values()))
    assert ledger["estimated_import_cost"] == pytest.approx(expected_cost)
    assert ledger["estimated_export_credit"] == pytest.approx(expected_credit)
    assert ledger["estimated_coverage_hours"] == pytest.approx(1)
    restored = Statistics(stats.export())
    assert restored.ledger == stats.ledger
