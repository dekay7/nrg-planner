"""Estimated prices never grant speculative battery charging or new permissions."""
import pytest

from test_control import controller, services


def estimated_controller(hass, **kwargs):
    writer, runtime, snapshot = controller(hass, **kwargs)
    runtime.evaluate_fallback = lambda **kwargs: {"active": False, "price_known": True, "comed_estimated_price": True}
    runtime._comed_estimated = True
    snapshot["battery_native_reserve"] = 20
    return writer, runtime, snapshot


@pytest.mark.parametrize("key,action", [("battery_grid_charge", "on"), ("battery_mode", "charge"),
                                        ("battery_export", "Battery")])
async def test_command_time_check_rejects_estimate_unsafe_actions_even_with_a_valid_old_plan(hass, monkeypatch, key, action):
    writer, runtime, _ = estimated_controller(hass, has_ev=False)
    runtime.plan.update(battery_action="charge", battery_target_soc=90)
    calls = services(hass, monkeypatch)
    with pytest.raises(RuntimeError, match="Published-estimate"):
        await writer.set(key, action, runtime.revision)
    assert calls == []


async def test_estimated_operation_revokes_grid_charging_but_continues_ev_plan(hass, monkeypatch):
    writer, runtime, _ = estimated_controller(hass)
    runtime.plan.update(battery_action="charge", battery_target_soc=90)
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["battery_grid_charge"]).state == "off"
    assert hass.states.get(runtime.mappings["battery_mode"]).state == "backup"
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "on"
    assert not any(service == "turn_on" and data["entity_id"] == runtime.mappings["battery_grid_charge"] for _, service, data in calls)


async def test_estimated_operation_retains_native_reserve_and_caps_exports(hass, monkeypatch):
    writer, runtime, snapshot = estimated_controller(hass, has_ev=False)
    snapshot["battery_native_reserve"] = 80
    runtime.config["export_policy"] = "Battery"
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    runtime.plan["battery_action"] = "serve"
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["battery_reserve"]).state == "80"
    assert hass.states.get(runtime.mappings["battery_mode"]).state == "backup"
    assert hass.states.get(runtime.mappings["battery_export"]).state == "pv_only"
    assert not any("value" in data and data["value"] < 80 for _, _, data in calls)


async def test_estimated_discharge_rechecks_higher_native_reserve(hass, monkeypatch):
    writer, runtime, snapshot = estimated_controller(hass, has_ev=False)
    runtime.plan["battery_action"] = "serve"
    snapshot["battery_native_reserve"] = 80
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    services(hass, monkeypatch)
    with pytest.raises(RuntimeError, match="retained reserve"):
        await writer.set("battery_mode", "serve", runtime.revision)
    with pytest.raises(RuntimeError, match="cannot lower"):
        await writer.set("battery_reserve", 20, runtime.revision)


@pytest.mark.parametrize("change", ["Observation", "guard", "closing", "battery disabled", "ev disabled"])
async def test_estimate_cannot_bypass_permissions_or_guards(hass, monkeypatch, change):
    writer, runtime, snapshot = estimated_controller(hass)
    if change == "Observation":
        runtime.config["mode"] = "Observation"
    elif change == "guard":
        snapshot["native_ready"] = False
    elif change == "closing":
        runtime._closing = True
    else:
        runtime.config[change.split()[0] + "_control"] = False
    calls = services(hass, monkeypatch)
    await writer.apply()
    if change.endswith("disabled"):
        device = change.split()[0]
        ids = {value for key, value in runtime.mappings.items() if key.startswith(device + "_")}
        assert all(data["entity_id"] not in ids for _, _, data in calls)
    else:
        assert calls == []


async def test_estimated_script_context_retains_native_reserve(hass, monkeypatch):
    writer, runtime, _ = estimated_controller(hass, has_ev=False)
    runtime.config["export_policy"] = "Battery"
    runtime.config["command_scripts"]["battery_mode"] = "script.invented_estimate_mode"
    hass.states.async_set("script.invented_estimate_mode", "off")
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    calls = []
    async def call(self, domain, service, data, **kwargs):
        calls.append(data.copy())
    monkeypatch.setattr(type(hass.services), "async_call", call)
    await writer.adapters.write("battery_mode", "hold")
    assert calls[0]["reserve_soc"] == 80
    assert calls[0]["export_policy"] == "Solar only"
