import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError


async def test_manual_buttons_require_opt_in_and_persist_without_enabling_controls(hass, installed):
    runtime = installed.runtime_data
    with pytest.raises(HomeAssistantError, match="Use my fallback actions"):
        await runtime.set_manual_fallback(True)
    await runtime.update_options({"price_fallback": "Custom fallback", "fallback_battery": "Self-consumption"})
    await hass.async_block_till_done()
    await hass.services.async_call("button", "press", {"entity_id": "button.nrg_activate_fallback"}, blocking=True)
    await hass.async_block_till_done()
    assert runtime.fallback.manual
    assert runtime.evaluate_fallback()["active"]
    assert runtime.config["mode"] == "Observation"
    assert not runtime.config["ev_control"] and not runtime.config["battery_control"]
    assert runtime.controller.last == {}
    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()
    restored = installed.runtime_data
    assert restored.fallback.manual and restored.evaluate_fallback()["active"]
    assert hass.states.get("sensor.nrg_pricing_health").state == "Fallback"
    await hass.services.async_call("button", "press", {"entity_id": "button.nrg_release_fallback"}, blocking=True)
    await hass.async_block_till_done()
    assert not restored.fallback.manual and not restored.evaluate_fallback()["active"]
    assert restored.config["fallback_battery"] == "Self-consumption"


async def test_missing_delivery_activates_fallback_and_restart_reevaluates(hass, installed):
    runtime = installed.runtime_data
    await runtime.update_options({"price_fallback": "Custom fallback", "delivery_cents": None})
    await hass.async_block_till_done()
    assert runtime.evaluate_fallback()["missing"] == ["delivery"]
    assert runtime.evaluate_fallback()["active"]
    assert hass.states.get("sensor.nrg_import_price_usd").state == "unknown"
    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()
    restored = installed.runtime_data
    assert restored.evaluate_fallback()["active"]
    assert not restored.fallback.manual
    assert restored.config["delivery_cents"] is None


async def test_configured_tariffs_ignore_comed_failure_and_tomorrow_only_failure(hass, installed):
    runtime = installed.runtime_data
    await runtime.update_options({"price_fallback": "Custom fallback"})
    await hass.async_block_till_done()
    runtime.forecast_status.update(comed="Tomorrow: timeout", live_price="Live ComEd unavailable")
    assert not runtime.evaluate_fallback()["active"]
    assert runtime.evaluate_fallback()["state"] == "Healthy"
    # A known timed schedule likewise has no dependency on the API.
    await runtime.update_options({"supply_plan": "Time-of-use supply", "supply_periods": [
        {"label": "Invented all-day rate", "start": "00:00:00", "end": "00:00:00", "rate_cents": 10,
         "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}]})
    await hass.async_block_till_done()
    assert not runtime.evaluate_fallback()["active"]


async def test_comed_fetch_failure_caches_expire_and_recovery_requires_new_live_observation(hass, installed):
    runtime = installed.runtime_data
    now = time.time()
    runtime.get_text = AsyncMock(return_value=json.dumps([{"millisUTC": now * 1000, "price": 4}]))
    await runtime.update_options({"price_fallback": "Custom fallback", "supply_plan": "Hourly ComEd"})
    await hass.async_block_till_done()
    # Deterministic same-hour progression; no network requests for evaluate_fallback.
    start = int(now // 3600) * 3600 + 100
    runtime.live_cache = {"time": start, "supply": .04}
    runtime.forecast_status["live_price"] = "Live ComEd unavailable (TimeoutError)"
    with patch("custom_components.nrg.runtime.time.time", return_value=start + 100):
        state = runtime.evaluate_fallback()
        assert state["state"] == "Degraded" and not state["active"]
    runtime.plan = {"expires_at": start + 2000}
    old_revision = runtime.revision
    with patch("custom_components.nrg.runtime.time.time", return_value=start + 900):
        assert runtime.evaluate_fallback()["active"]
        assert runtime.plan == {} and runtime.revision > old_revision
    runtime.forecast_status.pop("live_price")
    runtime.live_cache = {"time": start + 901, "supply": .05}
    with patch("custom_components.nrg.runtime.time.time", return_value=start + 901):
        assert runtime.evaluate_fallback(allow_recovery=True)["state"] == "Recovering"
    with patch("custom_components.nrg.runtime.time.time", return_value=start + 1030):
        assert runtime.evaluate_fallback(allow_recovery=True)["active"]  # Same cache isn't new evidence.
    runtime.live_cache = {"time": start + 1031, "supply": .05}
    with patch("custom_components.nrg.runtime.time.time", return_value=start + 1031):
        assert not runtime.evaluate_fallback(allow_recovery=True)["active"]
        assert runtime.plan == {} and runtime.force_plan


async def test_previous_hour_comed_cache_and_external_mapping_never_authorize_current_hour(hass, installed):
    runtime = installed.runtime_data
    now = time.time()
    runtime.get_text = AsyncMock(return_value=json.dumps([{"millisUTC": now * 1000, "price": 4}]))
    await runtime.update_options({"price_fallback": "Custom fallback", "supply_plan": "Hourly ComEd"})
    await hass.async_block_till_done()
    boundary = int(now // 3600) * 3600
    runtime.live_cache = {"time": boundary - 1, "supply": .04}
    with patch("custom_components.nrg.runtime.time.time", return_value=boundary + 10):
        assert runtime.live_supply() is None
        assert runtime.evaluate_fallback()["missing"] == ["supply"]
        assert runtime.evaluate_fallback()["active"]
    hass.states.async_set("sensor.invented_price", 4, {"unit_of_measurement": "cents/kWh"})
    await runtime.update_options({"mappings": {"live_supply": "sensor.invented_price"}})
    await hass.async_block_till_done()
    stamp = hass.states.get("sensor.invented_price").last_reported.timestamp()
    with patch("custom_components.nrg.runtime.time.time", return_value=(int(stamp // 3600) + 1) * 3600):
        assert runtime.live_supply() is None


@pytest.mark.parametrize("payload", [{}, [], [None], [{"millisUTC": 1, "price": 4}],
                                     [{"millisUTC": "bad", "price": 4}], [{"millisUTC": 1, "price": "NaN"}]])
async def test_malformed_and_stale_comed_success_responses_activate_fallback(hass, installed, payload):
    runtime = installed.runtime_data
    runtime.get_text = AsyncMock(return_value=json.dumps(payload))
    await runtime.update_options({"price_fallback": "Custom fallback", "supply_plan": "Hourly ComEd"})
    await hass.async_block_till_done()
    await runtime.async_refresh()
    assert runtime.evaluate_fallback()["active"]
    assert runtime.live_supply() is None
    assert "live_price" in runtime.forecast_status


async def test_fallback_notifications_are_separate_opt_in_and_deduplicated(hass, installed):
    runtime = installed.runtime_data
    messages = []
    async def notify(call):
        messages.append(call.data)
    hass.services.async_register("notify", "invented_phone", notify)
    await runtime.update_options({"price_fallback": "Custom fallback", "notification_targets": ["notify.invented_phone"],
                                  "quiet_start": "00:00:00", "quiet_end": "00:00:00"})
    await hass.async_block_till_done()
    await runtime.set_manual_fallback(True)
    await runtime.notify_fallback(time.time())
    assert messages == []
    await runtime.update_options({"fallback_notifications": True})
    await hass.async_block_till_done()
    await runtime.notify_fallback(time.time())
    await runtime.notify_fallback(time.time() + 1)
    assert len(messages) == 1
    assert "Observation" in messages[0]["message"]
    assert not runtime.config["notifications"]  # Independent of household price advice.


async def test_command_time_health_publication_does_not_postpone_price_poll(hass, installed, monkeypatch):
    runtime = installed.runtime_data
    reset = []
    original = runtime._schedule_refresh
    def schedule():
        reset.append(True)
        original()
    monkeypatch.setattr(runtime, "_schedule_refresh", schedule)
    runtime.evaluate_fallback(publish=True)
    runtime.evaluate_fallback(publish=True)
    assert not reset


async def test_fallback_notifications_obey_quiet_hours_and_recovery_cooldown(hass, installed):
    from datetime import datetime
    runtime = installed.runtime_data
    messages = []
    async def notify(call):
        messages.append(call.data)
    hass.services.async_register("notify", "invented_phone", notify)
    await runtime.update_options({"fallback_notifications": True, "notification_targets": ["notify.invented_phone"],
                                  "quiet_start": "21:00:00", "quiet_end": "08:00:00"})
    await hass.async_block_till_done()
    night = datetime(2026, 10, 20, 22, tzinfo=runtime.zone).timestamp()
    day = datetime(2026, 10, 21, 12, tzinfo=runtime.zone).timestamp()
    runtime.fallback_notice = (True, "Invented fallback entry")
    await runtime.notify_fallback(night)
    assert not messages and runtime.fallback_notice
    await runtime.notify_fallback(day)
    assert len(messages) == 1
    runtime.fallback_notice = (False, "Invented recovery")
    await runtime.notify_fallback(day + 10)
    assert len(messages) == 1 and runtime.fallback_notice
    await runtime.notify_fallback(day + 301)
    assert len(messages) == 2 and not runtime.fallback_notice
