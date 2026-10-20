import time
from types import SimpleNamespace

import pytest
from homeassistant.helpers import entity_registry as er

from custom_components.nrg.config import settings
from custom_components.nrg.control import Controller


def controller(hass, mode="Control", provider="tessie", has_ev=True, has_battery=True):
    config = settings({"mode": mode, "has_ev": has_ev, "has_battery": has_battery, "has_solar": True, "ev_control": True, "battery_control": True})
    snapshot = {"native_ready": True, "battery_ready": True, "battery_soc": 60,
                "connected": True, "ev_ready": True, "ev_soc": 70, "ev_limit": 80, "ev_kw": 0}
    mappings = {}
    for key, domain, state, attributes in (
        ("battery_mode", "select", "backup", {"options": ["backup", "self_consumption", "autonomous"]}),
        ("battery_export", "select", "pv_only", {"options": ["never", "pv_only", "battery_ok"]}),
        ("battery_grid_charge", "switch", "on", {}), ("battery_reserve", "number", "20", {"min": 0, "max": 100}),
        ("ev_current", "number", "40", {"min": 0, "max": 40, "unit_of_measurement": "A"}),
        ("ev_charge", "switch", "off", {})):
        registered = er.async_get(hass).async_get_or_create(domain, provider, "fixture_" + key, suggested_object_id="fixture_" + key)
        hass.states.async_set(registered.entity_id, state, attributes)
        mappings[key] = registered.entity_id
    runtime = SimpleNamespace(hass=hass, config=config, mappings=mappings, revision=1,
        plan={"expires_at": time.time() + 600, "battery_action": "hold", "battery_target_soc": 60,
              "ev_amps": 40, "ev_stop_at": time.time() + 600},
        snapshot=lambda: snapshot.copy(), current_price_known=True, live_export=.1, charge_now=False)
    return Controller(runtime), runtime, snapshot


def services(hass, monkeypatch, after=None):
    calls = []
    async def call(self, domain, service, data, **kwargs):
        calls.append((domain, service, data.copy()))
        old = hass.states.get(data["entity_id"])
        state = data.get("value", data.get("option", "on" if service == "turn_on" else "off"))
        hass.states.async_set(old.entity_id, state, dict(old.attributes))
        if after:
            after(calls)
    monkeypatch.setattr(type(hass.services), "async_call", call)
    return calls


async def test_observation_and_configured_ownership_guard_issue_no_commands(hass, monkeypatch):
    writer, runtime, snapshot = controller(hass, "Observation")
    calls = services(hass, monkeypatch)
    await writer.apply()
    runtime.config["mode"] = "Control"
    snapshot["native_ready"] = False
    await writer.apply()
    assert calls == []


async def test_expired_plan_revokes_grid_grant_without_battery_soc(hass, monkeypatch):
    writer, runtime, snapshot = controller(hass)
    snapshot.update(battery_ready=False, battery_soc=None)
    runtime.plan["expires_at"] = 0
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert any(service == "turn_off" and data["entity_id"] == runtime.mappings["battery_grid_charge"] for _, service, data in calls)
    assert not any(service == "turn_on" for _, service, _ in calls)


async def test_ownership_change_between_commands_prevents_ev_start(hass, monkeypatch):
    writer, runtime, _ = controller(hass)
    def changed(calls):
        runtime.config["mode"] = "Observation"
    calls = services(hass, monkeypatch, changed)
    await writer.apply()
    assert len(calls) == 1
    assert calls[0][1] == "turn_off"


async def test_new_plan_cancels_earlier_command_chain(hass, monkeypatch):
    writer, runtime, _ = controller(hass)
    def replaced(calls):
        runtime.revision += 1
    calls = services(hass, monkeypatch, replaced)
    await writer.apply()
    assert not any(service == "turn_on" for _, service, _ in calls)


async def test_charge_now_does_not_require_price_solar_or_a_plan(hass, monkeypatch):
    writer, runtime, _ = controller(hass)
    runtime.plan = {}
    runtime.charge_now = True
    runtime.current_price_known = False
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert any(service == "turn_on" and data["entity_id"] == runtime.mappings["ev_charge"] for _, service, data in calls)
    assert hass.states.get(runtime.mappings["battery_grid_charge"]).state == "off"


@pytest.mark.parametrize("policy,expected", [("Solar only", "pv_only"), ("Battery", "battery_ok"), ("No exports", "never")])
async def test_export_policy_and_ev_selected_limit_never_written(hass, monkeypatch, policy, expected):
    writer, runtime, _ = controller(hass)
    runtime.config["export_policy"] = policy
    calls = services(hass, monkeypatch)
    await writer.apply()
    assert hass.states.get(runtime.mappings["battery_export"]).state == expected
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "on"
    assert not any("limit" in data["entity_id"] for _, _, data in calls)


async def test_native_event_and_negative_credit_priority(hass, monkeypatch):
    writer, runtime, snapshot = controller(hass)
    calls = services(hass, monkeypatch)
    snapshot["native_ready"] = False
    await writer.apply()
    assert calls == []
    snapshot["native_ready"] = True
    runtime.live_export = -.02
    await writer.apply()
    assert hass.states.get(runtime.mappings["battery_export"]).state == "never"


async def test_variable_current_and_readback_before_start(hass, monkeypatch):
    writer, runtime, _ = controller(hass)
    runtime.plan["ev_amps"] = 12
    calls = services(hass, monkeypatch)
    await writer.apply()
    current = next(i for i, (_, _, data) in enumerate(calls) if data["entity_id"] == runtime.mappings["ev_current"])
    start = next(i for i, (_, service, data) in enumerate(calls) if service == "turn_on" and data["entity_id"] == runtime.mappings["ev_charge"])
    assert current < start
    assert calls[current][2]["value"] == 12


async def test_failed_current_readback_does_not_start_car(hass, monkeypatch):
    import asyncio
    writer, runtime, _ = controller(hass)
    runtime.plan["ev_amps"] = 12
    calls = []
    async def call(self, domain, service, data, **kwargs):
        calls.append((service, data.copy()))
        if data["entity_id"] != runtime.mappings["ev_current"]:
            old = hass.states.get(data["entity_id"])
            hass.states.async_set(old.entity_id, "off", dict(old.attributes))
    async def no_delay(seconds):
        pass
    monkeypatch.setattr(type(hass.services), "async_call", call)
    monkeypatch.setattr(asyncio, "sleep", no_delay)
    await writer.apply()
    assert not any(service == "turn_on" for service, _ in calls)
    assert "readback" in writer.status


async def test_teslemetry_ev_only_controls_need_no_battery(hass, monkeypatch):
    writer,runtime,_=controller(hass,provider="teslemetry",has_battery=False)
    runtime.plan["ev_amps"]=16
    calls=services(hass,monkeypatch)
    await writer.apply()
    assert float(hass.states.get(runtime.mappings["ev_current"]).state) == 16
    assert hass.states.get(runtime.mappings["ev_charge"]).state == "on"
    assert all("battery" not in data["entity_id"] for _,_,data in calls)


async def test_generic_inverter_with_distinct_charge_mode_and_no_optional_controls(hass,monkeypatch):
    writer,runtime,snapshot=controller(hass,provider="other_inverter",has_ev=False)
    for key in ("battery_export","battery_reserve","battery_grid_charge"):
        runtime.mappings.pop(key)
    runtime.config["control_values"].update(battery_hold="Standby",battery_serve="Self use",battery_charge="Grid charge")
    mode=runtime.mappings["battery_mode"]
    hass.states.async_set(mode,"Standby",{"options":["Standby","Self use","Grid charge"]})
    runtime.plan.update(battery_action="charge",battery_target_soc=80,ev_amps=0)
    calls=services(hass,monkeypatch)
    await writer.apply()
    assert hass.states.get(mode).state == "Grid charge"
    assert len(calls)==1 and calls[0][0]=="select"


async def test_readonly_mqtt_feedback_can_use_user_command_scripts(hass,monkeypatch):
    writer,runtime,_=controller(hass,provider="mqtt",has_battery=False)
    runtime.mappings.update(ev_current="sensor.mqtt_current_setting",ev_charge="sensor.mqtt_charge_state")
    hass.states.async_set(runtime.mappings["ev_current"],40,{"unit_of_measurement":"A"})
    hass.states.async_set(runtime.mappings["ev_charge"],"Stopped")
    runtime.config["control_values"].update(ev_on="Charging",ev_off="Stopped")
    runtime.config["command_scripts"]={"ev_current":"script.set_ev_current","ev_start":"script.start_ev","ev_stop":"script.stop_ev"}
    for script in runtime.config["command_scripts"].values():
        hass.states.async_set(script,"off")
    runtime.plan["ev_amps"]=12
    calls=[]
    async def call(self,domain,service,data,**kwargs):
        calls.append((domain,service,data.copy()))
        if service=="set_ev_current":
            hass.states.async_set(runtime.mappings["ev_current"],data["value"],{"unit_of_measurement":"A"})
        elif service=="start_ev":
            hass.states.async_set(runtime.mappings["ev_charge"],"Charging")
    monkeypatch.setattr(type(hass.services),"async_call",call)
    await writer.apply()
    assert [(d,s) for d,s,_ in calls] == [("script","set_ev_current"),("script","start_ev")]
    assert calls[0][2]["value"] == 12
    assert calls[1][2]["value"] == "Charging"


async def test_executor_uses_current_interval_instead_of_first_slot(hass,monkeypatch):
    writer,runtime,_=controller(hass,has_battery=False)
    now=time.time()
    runtime.plan.update(ev_amps=0,ev_stop_at=None,slots=[
        {"start":now-100,"end":now-1,"ev_amps":0,"ev_stop_at":None,"battery_action":"hold","battery_soc":60,"price_known":True,"export_price":0},
        {"start":now-1,"end":now+100,"ev_amps":16,"ev_stop_at":now+100,"battery_action":"hold","battery_soc":60,"price_known":True,"export_price":0}])
    calls=services(hass,monkeypatch)
    await writer.apply()
    assert float(hass.states.get(runtime.mappings["ev_current"]).state)==16
    assert any(service=="turn_on" for _,service,_ in calls)
