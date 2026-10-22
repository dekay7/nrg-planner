import pytest

from test_control import controller, services


def fallback_controller(hass, **kwargs):
    writer, runtime, snapshot = controller(hass, **kwargs)
    runtime.config.update(price_fallback="Custom fallback", fallback_battery="Self-consumption")
    runtime.current_price_known = False
    context = {"active": True, "price_known": False}
    runtime.evaluate_fallback = lambda **kwargs: context.copy()
    return writer, runtime, snapshot, context


async def test_expired_plan_fallback_pauses_ev_and_serves_home(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass)
    runtime.plan = {}
    hass.states.async_set(runtime.mappings["ev_charge"], "on")
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "off"
    assert hass.states.get(runtime.mappings["battery_grid_charge"]).state == "off"
    assert hass.states.get(runtime.mappings["battery_mode"]).state == "self_consumption"
    assert not any(service == "turn_on" for _, service, _ in calls)
    assert "acknowledged" in writer.fallback_results["battery"]["result"]


@pytest.mark.parametrize("change", ["Observation", "ev disabled", "battery disabled", "guard", "closing"])
async def test_fallback_preserves_permissions_and_protection_guards(hass, monkeypatch, change):
    writer, runtime, snapshot, _ = fallback_controller(hass)
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
        disabled_ids = {entity for key, entity in runtime.mappings.items() if key.startswith(device + "_")}
        assert all(data["entity_id"] not in disabled_ids for _, _, data in calls)
    else:
        assert calls == []


@pytest.mark.parametrize("changed", [{"battery_soc": 20}, {"battery_ready": False, "battery_soc": None}, {"ev_busy": True}, {"ev_busy": None}])
async def test_fallback_cannot_discharge_with_bad_feedback_reserve_or_ev_activity(hass, monkeypatch, changed):
    writer, runtime, snapshot, _ = fallback_controller(hass)
    snapshot.update(changed)
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)
    assert hass.states.get(runtime.mappings["battery_grid_charge"]).state == "off"


async def test_fallback_never_lowers_native_reserve(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass, has_ev=False)
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["battery_reserve"]).state == "80"
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)
    assert not any("value" in data and data["value"] < 80 for _, _, data in calls)


async def test_fallback_serve_rechecks_native_reserve_after_prior_command(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass, has_ev=False)
    def changed(calls):
        hass.states.async_set(runtime.mappings["battery_reserve"], 90, {"min": 0, "max": 100})
    calls = services(hass, monkeypatch, changed)
    await writer.apply()
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)


@pytest.mark.parametrize("failed_device", ["ev", "battery"])
async def test_either_device_failure_does_not_skip_the_other(hass, monkeypatch, failed_device):
    writer, runtime, _, _ = fallback_controller(hass)
    hass.states.async_set(runtime.mappings["ev_charge"], "on")
    calls = services(hass, monkeypatch)
    original = writer.adapters.write
    async def write(key, action):
        if key.startswith(failed_device + "_"):
            raise RuntimeError("Invented device failure")
        await original(key, action)
    monkeypatch.setattr(writer.adapters, "write", write)
    await writer.apply()
    other = "battery" if failed_device == "ev" else "ev"
    assert any(data["entity_id"] == runtime.mappings[other + ("_grid_charge" if other == "battery" else "_charge")]
               for _, _, data in calls)
    assert "Failed" in writer.fallback_results[failed_device]["result"]


async def test_charge_now_remains_explicit_unknown_price_override(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass)
    runtime.plan = {}
    runtime.charge_now = True
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "on"
    assert hass.states.get(runtime.mappings["battery_mode"]).state == "backup"
    assert "overrides" in writer.status
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)


async def test_departure_readiness_preserves_battery_before_ev_power_ramps(hass, monkeypatch):
    writer, runtime, snapshot, _ = fallback_controller(hass)
    runtime.config["fallback_ev"] = "Maintain departure readiness"
    snapshot["ev_busy"] = False  # No measured power yet, but charging is scheduled.
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "on"
    assert hass.states.get(runtime.mappings["battery_mode"]).state == "backup"
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)


async def test_missing_ev_feedback_is_not_reported_as_a_successful_pause(hass, monkeypatch):
    writer, runtime, snapshot, _ = fallback_controller(hass)
    hass.states.async_set(runtime.mappings["ev_charge"], "unavailable")
    snapshot.update(ev_kw=None, ev_busy=None)
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert writer.fallback_results["ev"]["result"].startswith("Failed")
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)


async def test_fallback_revokes_force_charge_mode_even_with_separate_permission(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass, has_ev=False)
    runtime.config["control_values"]["battery_charge"] = "force_charge"
    hass.states.async_set(runtime.mappings["battery_mode"], "force_charge",
                          {"options": ["backup", "self_consumption", "force_charge"]})
    calls = services(hass, monkeypatch)
    await writer.apply()
    options = [data["option"] for _, _, data in calls if "option" in data]
    assert options.index("backup") < options.index("self_consumption")
    assert hass.states.get(runtime.mappings["battery_grid_charge"]).state == "off"


async def test_fallback_cannot_authorize_normal_charge_or_serve(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass)
    services(hass, monkeypatch)
    for key, action in (("battery_mode", "serve"), ("battery_mode", "charge"), ("battery_grid_charge", "on"), ("ev_charge", "on")):
        with pytest.raises(RuntimeError, match="fallback"):
            await writer.set(key, action, runtime.revision)


async def test_control_change_between_commands_cancels_fallback_chain(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass)
    calls = services(hass, monkeypatch, lambda calls: runtime.config.update(mode="Observation"))
    await writer.apply()
    assert len(calls) == 1
    assert not any(data.get("option") == "self_consumption" for _, _, data in calls)


async def test_reserve_cannot_be_lowered_by_a_stale_fallback_command(hass, monkeypatch):
    writer, runtime, snapshot, _ = fallback_controller(hass, has_ev=False)
    snapshot["battery_native_reserve"] = 20  # Earlier snapshot, before the native setting changed.
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    services(hass, monkeypatch)
    with pytest.raises(RuntimeError, match="cannot lower"):
        await writer.set("battery_reserve", 20, runtime.revision, revoke=True)
    assert hass.states.get(runtime.mappings["battery_reserve"]).state == "80"


async def test_fallback_script_context_retains_reserve_and_caps_export_permission(hass, monkeypatch):
    writer, runtime, _, _ = fallback_controller(hass, has_ev=False)
    runtime._fallback_active = True
    runtime.config["export_policy"] = "Battery"
    runtime.config["command_scripts"]["battery_mode"] = "script.invented_mode"
    hass.states.async_set("script.invented_mode", "off")
    hass.states.async_set(runtime.mappings["battery_reserve"], 80, {"min": 0, "max": 100})
    calls = []
    async def call(self, domain, service, data, **kwargs):
        calls.append(data.copy())
    monkeypatch.setattr(type(hass.services), "async_call", call)
    await writer.adapters.write("battery_mode", "hold")
    assert calls[0]["reserve_soc"] == 80
    assert calls[0]["export_policy"] == "Solar only"
