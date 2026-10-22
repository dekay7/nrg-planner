"""Invented hourly publication delays, real outages and forecast provenance."""
import json
import time
from unittest.mock import AsyncMock, patch

from aiohttp import ClientConnectionError
import pytest

from conftest import NOW
from custom_components.nrg.fallback import PriceFallback
from custom_components.nrg.sensor import NRGSensor
from custom_components.nrg.statistics import Statistics


@pytest.fixture
async def comed_runtime(hass, installed):
    runtime = installed.runtime_data
    runtime.get_text = AsyncMock(return_value=json.dumps([{"millisUTC": time.time() * 1000, "price": 4}]))
    await runtime.update_options({"price_fallback": "Custom fallback", "supply_plan": "Hourly ComEd"})
    await hass.async_block_till_done()
    runtime.fallback = PriceFallback()
    runtime._fallback_active = False
    runtime.fallback_notice = None
    runtime.forecast_status = {}
    runtime.live_cache = {"time": NOW - 600, "supply": .04}
    runtime.prices = [{"start": NOW, "supply": .06, "fetched_at": NOW - 3600}]
    runtime.last_fetch = NOW
    return runtime


async def test_normal_hour_rollover_never_enters_fallback_or_recovery(comed_runtime):
    runtime = comed_runtime
    for offset, observed, bridge in ((16, NOW - 600, True), (136, NOW - 600, True),
                                     (296, NOW - 600, True), (316, NOW, False),
                                     (436, NOW, False), (616, NOW + 300, False)):
        runtime.get_text.return_value = json.dumps([{"millisUTC": observed * 1000, "price": 4}])
        with patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset):
            data = await runtime._async_update_data()
            runtime.data = data
            health = runtime.evaluate_fallback(publish=True)
            assert health["state"] == "Healthy"
            assert not health["active"] and not health["missing"]
            assert health["comed_publication_bridge"] is bridge
            assert data["price"]["price_known"]
            assert "live_price" not in runtime.forecast_status
            assert runtime.fallback_notice is None
            assert health["observations"]["supply"]["source"] == ("day_ahead" if bridge else "running_average")
            assert health["observations"]["supply"]["last_observation"] == (NOW - 3600 if bridge else observed)
            if bridge:
                assert runtime.live_supply() is None  # Never reuse the previous hour as live.
                assert "published current-hour forecast" in health["reason"]
            if offset == 316:
                assert runtime.plan["generated_at"] == NOW + offset  # Replan promptly on the live handover.
    assert runtime.controller.last == {}  # Observation remains command-free.


async def test_missing_or_expired_bridge_enters_fallback_even_with_a_recent_previous_hour_cache(comed_runtime):
    runtime = comed_runtime
    runtime.prices = []
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 16):
        health = runtime.evaluate_fallback()
        assert health["state"] == "Fallback" and health["missing"] == ["supply"]
    runtime.fallback = PriceFallback()
    runtime.prices = [{"start": NOW, "supply": .06, "fetched_at": NOW - 3600}]
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 600):
        health = runtime.evaluate_fallback()
        assert health["state"] == "Fallback" and health["missing"] == ["supply"]
        assert not health["comed_publication_bridge"]


async def test_forecast_bridge_does_not_release_an_existing_outage_or_count_as_live_recovery(comed_runtime):
    runtime = comed_runtime
    runtime.prices = []
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW):
        assert runtime.evaluate_fallback()["active"]
    runtime.prices = [{"start": NOW, "supply": .06, "fetched_at": NOW - 3600}]
    for offset in (16, 136, 296):
        with patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset):
            health = runtime.evaluate_fallback(allow_recovery=True)
            assert health["state"] == "Fallback" and health["active"]
            assert health["price_known"] and health["comed_publication_bridge"]
            assert health["recovery_since"] is None
    runtime.live_cache = {"time": NOW, "supply": .04}
    for offset in (316, 436):
        with patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset):
            assert runtime.evaluate_fallback(allow_recovery=True)["state"] == "Recovering"
    runtime.live_cache = {"time": NOW + 300, "supply": .04}
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 616):
        assert runtime.evaluate_fallback(allow_recovery=True)["state"] == "Healthy"


async def test_publication_bridge_does_not_hide_a_transport_failure(comed_runtime):
    runtime = comed_runtime
    runtime.get_text.side_effect = ClientConnectionError("Invented temporary connection failure")
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 16):
        data = await runtime._async_update_data()
    assert data["fallback"]["state"] == "Degraded"
    assert not data["fallback"]["active"]
    assert "ClientConnectionError" in data["forecast_status"]["live_price"]
    assert "published current-hour forecast" in data["fallback"]["reason"]


async def test_previous_hour_response_after_publication_window_is_not_normalized_as_healthy(comed_runtime):
    runtime = comed_runtime
    runtime.get_text.return_value = json.dumps([{"millisUTC": (NOW - 600) * 1000, "price": 4}])
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 600):
        data = await runtime._async_update_data()
    assert data["fallback"]["active"]
    assert "ValueError" in data["forecast_status"]["live_price"]


async def test_bridge_keeps_supply_price_visible_and_labels_its_provenance(comed_runtime):
    runtime = comed_runtime
    runtime.get_text.return_value = json.dumps([{"millisUTC": (NOW - 600) * 1000, "price": 4}])
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 16):
        runtime.data = await runtime._async_update_data()
        for key, value in (("supply_price", 6), ("import_price", 10), ("import_price_usd", .10)):
            sensor = NRGSensor(runtime, key, "Invented price", None, None)
            assert sensor.native_value == pytest.approx(value)
            assert sensor.extra_state_attributes == {"source": "day_ahead", "comed_publication_bridge": True,
                                                     "comed_estimated_price": False}


async def test_bridge_cost_coverage_uses_forecast_without_learning_it_as_live(comed_runtime):
    runtime = comed_runtime
    runtime.stats = Statistics()
    snapshot = runtime.snapshot() | {"grid_kw": 2, "home_kw": 2, "solar_kw": 0, "ev_kw": 0}
    runtime.get_text.return_value = json.dumps([{"millisUTC": (NOW - 600) * 1000, "price": 4}])
    for offset in (16, 136):
        with (patch("custom_components.nrg.runtime.time.time", return_value=NOW + offset),
              patch.object(runtime, "snapshot", return_value=snapshot)):
            runtime.data = await runtime._async_update_data()
        values = runtime.stats.previous[1]
        assert values["supply_price"] == .06
        assert values["supply"] is None
    ledger = next(iter(runtime.stats.ledger.values()))
    assert ledger["coverage_hours"] == pytest.approx(120 / 3600)
    assert ledger["import_cost"] == pytest.approx(2 * .10 * 120 / 3600)
    assert runtime.stats.bucket["supply_values"] == []


async def test_publication_bridge_cannot_mask_missing_delivery_or_manual_fallback(hass, comed_runtime):
    runtime = comed_runtime
    runtime.fallback.manual = True
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 16):
        assert runtime.evaluate_fallback()["state"] == "Fallback"
    runtime.fallback.manual = False
    await runtime.update_options({"delivery_cents": None})
    await hass.async_block_till_done()
    with patch("custom_components.nrg.runtime.time.time", return_value=NOW + 16):
        health = runtime.evaluate_fallback()
        assert health["active"] and health["missing"] == ["delivery"]
