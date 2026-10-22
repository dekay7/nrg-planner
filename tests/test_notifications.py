from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.nrg.config import settings
from custom_components.nrg.runtime import NRGRuntime
from conftest import NOW, ZONE


async def test_advice_requires_opt_in_stability_benefit_and_quiet_hours(hass):
    sent = []
    async def delivered(call):
        sent.append(call.data)
    hass.services.async_register("notify", "household_test", delivered)
    config = settings({"notifications": False})
    runtime = SimpleNamespace(config=config, zone=ZONE, hass=hass,
        plan={"expires_at": NOW + 1000, "household": {"category": "wait", "saving": .5,
              "best_start": NOW + 3600, "summary": "Wait until 7 p.m.", "confidence": "forecast", "cost_basis": "battery"}},
        entry=SimpleNamespace(options={"notification_targets": ["notify.household_test"]}),
        pending_advice=None, delivered={}, forecast_status={}, store=SimpleNamespace(async_delay_save=Mock()), persisted=lambda: {})
    await NRGRuntime.notify(runtime, NOW)
    assert not sent
    config["notifications"] = True
    await NRGRuntime.notify(runtime, NOW)
    await NRGRuntime.notify(runtime, NOW + 119)
    assert not sent
    await NRGRuntime.notify(runtime, NOW + 120)
    assert len(sent) == 1
    assert "Observation" in sent[0]["message"]
    assert "Battery-backed use; not necessarily the cheapest grid-price window" in sent[0]["message"]
    await NRGRuntime.notify(runtime, NOW + 180)
    assert len(sent) == 1
    # Loss of dependable coverage clears pending advice, even with a large saving.
    runtime.plan["household"]["confidence"] = "limited"
    runtime.pending_advice = ("old", NOW)
    await NRGRuntime.notify(runtime, NOW + 190)
    assert runtime.pending_advice is None
    assert len(sent) == 1
    runtime.plan["household"]["confidence"] = "forecast"
    # A new worthwhile window during quiet hours waits silently.
    runtime.plan["household"]["best_start"] += 3600
    config.update(quiet_start="17:00:00", quiet_end="20:00:00")
    await NRGRuntime.notify(runtime, NOW + 240)
    await NRGRuntime.notify(runtime, NOW + 400)
    assert len(sent) == 1


@pytest.mark.parametrize("confidence", [None, "limited"])
async def test_uncertain_advice_cannot_notify_even_with_large_saving(confidence):
    runtime = SimpleNamespace(config=settings({"notifications": True}),
        plan={"expires_at": NOW + 1000, "household": {"category": "wait", "saving": 10,
              "confidence": confidence}}, pending_advice=("old", NOW))
    await NRGRuntime.notify(runtime, NOW + 120)
    assert runtime.pending_advice is None
