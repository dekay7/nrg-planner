import pytest

from homeassistant.config_entries import ConfigEntryState


async def test_actual_ha_setup_entities_persisted_settings_and_no_commands(hass, installed):
    assert installed.state == ConfigEntryState.LOADED
    assert hass.states.get("sensor.nrg_import_price").state == "14.0"
    assert hass.states.get("select.nrg_mode").state == "Observation"
    assert hass.states.get("binary_sensor.nrg_writer_authorized").state == "off"
    await hass.services.async_call("number", "set_value", {"entity_id": "number.nrg_delivery_cents", "value": 7.5}, blocking=True)
    await hass.async_block_till_done()
    assert installed.options["delivery_cents"] == 7.5
    assert hass.states.get("sensor.nrg_import_price").state == "17.5"
    assert installed.runtime_data.controller.last == {}


async def test_reload_keeps_ui_edits(hass, installed):
    await installed.runtime_data.update_options({"battery_capacity": 30})
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("number.nrg_battery_capacity").state == "30.0"
    assert installed.runtime_data.config["mode"] == "Observation"


async def test_reload_restores_learning_and_ledger_without_resuming_charge_now(hass, installed):
    import time

    runtime = installed.runtime_data
    hour = int(time.time() // 3600) * 3600 - 3600
    runtime.stats.hours = [{"start": hour, "house_kwh": 1.25, "solar_kwh": None, "solar_forecast": None}]
    runtime.stats.ev_sessions = [{"kwh_per_percent": .7, "kw_per_amp": .23}]
    runtime.stats.ledger = {"2026-10-19": {"import_cost": 1.5, "export_credit": .2, "coverage_hours": 1}}
    runtime.charge_now = True

    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()

    restored = installed.runtime_data
    assert restored is not runtime
    assert runtime._closing
    assert restored.stats.hours == runtime.stats.hours
    assert restored.stats.ev_sessions == runtime.stats.ev_sessions
    assert restored.stats.ledger["2026-10-19"] == runtime.stats.ledger["2026-10-19"]
    assert restored.stats.session is None
    assert not restored.charge_now


@pytest.mark.parametrize("unload_first", [False, True])
async def test_removal_deletes_private_storage_and_entities(hass, unload_first):
    from homeassistant.helpers.storage import Store
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "nrg", {"nrg": {
        "supply_plan": "Flat supply", "flat_supply_cents": 10, "delivery_cents": 4,
    }})
    await hass.async_block_till_done()
    entry = next(iter(hass.config_entries.async_entries("nrg")))
    runtime = entry.runtime_data
    runtime.stats.ev_sessions = [{"kwh_per_percent": .7}]
    await runtime.store.async_save(runtime.persisted())
    assert await Store(hass, 1, f"nrg.{entry.entry_id}").async_load() is not None

    if unload_first:
        assert await hass.config_entries.async_unload(entry.entry_id)
    result = await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert not result["require_restart"]
    assert not hass.config_entries.async_entries("nrg")
    assert hass.states.get("sensor.nrg_import_price") is None
    assert runtime._closing
    assert await Store(hass, 1, f"nrg.{entry.entry_id}").async_load() is None


async def test_energy_dashboard_usd_prices_preserve_negative_export_and_unknown_rates(hass, installed):
    await installed.runtime_data.update_options({"export_rate": "Flat credit", "flat_export_cents": -2.5})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nrg_export_price_usd").state == "-0.025"
    assert hass.states.get("sensor.nrg_import_price_usd").state == "0.14"
    await installed.runtime_data.update_options({"export_rate": "Supply plus adder", "supply_plan": "External supply entity"})
    await installed.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nrg_export_price_usd").state == "unknown"


async def test_flow_rejects_duplicate_bootstrap_and_settings_descriptions(hass, installed):
    result = await hass.config_entries.flow.async_init("nrg", context={"source": "import"}, data={})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
    result = await hass.config_entries.options.async_init(installed.entry_id)
    assert result["type"] == "menu"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "tariff"})
    assert result["type"] == "form"
    assert result["step_id"] == "tariff"


async def test_real_state_event_replans_on_the_event_loop(hass, installed):
    await installed.runtime_data.update_options({"mappings": {"ev_connected": "binary_sensor.test_plug"}})
    await hass.async_block_till_done()
    before = installed.runtime_data.plan["generated_at"]
    installed.runtime_data._debounced_refresh.async_cancel()  # Exercise the event, not HA's ten-second cooldown.
    hass.states.async_set("binary_sensor.test_plug", "on")
    await hass.async_block_till_done()
    assert installed.runtime_data.plan["generated_at"] > before


async def test_inconsistent_local_flows_do_not_become_zero_house_learning(hass, installed):
    mappings = {key: "sensor.test_" + key for key in ("solar_power", "home_power", "grid_power", "battery_power", "ev_power")}
    await installed.runtime_data.update_options({"mappings": mappings})
    await hass.async_block_till_done()
    for key, value in (("solar_power", 0), ("home_power", 12), ("grid_power", 12), ("battery_power", 0), ("ev_power", 5)):
        hass.states.async_set(mappings[key], value, {"unit_of_measurement": "kW"})
    assert installed.runtime_data.snapshot()["house_kw"] == 7
    hass.states.async_set(mappings["ev_power"], 15, {"unit_of_measurement": "kW"})
    snapshot = installed.runtime_data.snapshot()
    assert snapshot["house_kw"] is None
    assert snapshot["ev_learning_valid"] is False
    assert "disagree" in snapshot["measurement_quality"]


async def test_ev_readiness_works_without_powerwall_or_tessie(hass,installed):
    mappings={"ev_connected":"binary_sensor.mqtt_plug","ev_soc":"sensor.mqtt_soc","ev_limit":"sensor.mqtt_limit",
              "ev_current":"number.any_provider_current","ev_charge":"switch.any_provider_charge"}
    for entity,state,attributes in (
        (mappings["ev_connected"],"on",{}),(mappings["ev_soc"],60,{"unit_of_measurement":"%"}),
        (mappings["ev_limit"],80,{"unit_of_measurement":"%"}),
        (mappings["ev_current"],40,{"unit_of_measurement":"A","min":0,"max":40}),
        (mappings["ev_charge"],"off",{})):
        hass.states.async_set(entity,state,attributes)
    await installed.runtime_data.update_options({"has_ev":True,"has_battery":False,"has_solar":False,"ev_control":True,"mappings":mappings})
    await hass.async_block_till_done()
    snapshot=installed.runtime_data.snapshot()
    assert snapshot["ev_ready"] and snapshot["native_ready"] and snapshot["connected"]
    assert snapshot["solar_kw"]==0 and snapshot["battery_kw"]==0


async def test_pricing_period_options_flow_template_and_validation(hass,installed):
    async def begin():
        result=await hass.config_entries.options.async_init(installed.entry_id)
        result=await hass.config_entries.options.async_configure(result["flow_id"],{"next_step_id":"pricing_periods"})
        return await hass.config_entries.options.async_configure(result["flow_id"],{"component":"delivery"})
    result=await begin()
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"next_step_id":"template_periods"})
    await hass.async_block_till_done()
    assert result["type"]=="create_entry"
    periods=installed.options["delivery_periods"]
    assert len(periods)==4 and all(p["rate_cents"] is None for p in periods)
    result=await begin()
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"next_step_id":"edit_period"})
    result=await hass.config_entries.options.async_configure(result["flow_id"],{"period":"0"})
    result=await hass.config_entries.options.async_configure(result["flow_id"],dict(periods[0])|{"rate_cents":4})
    await hass.async_block_till_done()
    assert result["type"]=="create_entry" and installed.options["delivery_periods"][0]["rate_cents"]==4


async def test_real_ha_script_adapter_receives_variables_and_updates_feedback(hass,installed):
    from homeassistant.setup import async_setup_component
    from custom_components.nrg.adapters import Adapters
    assert await async_setup_component(hass,"input_number",{"input_number":{"adapter_feedback":{"min":0,"max":40,"initial":40,"unit_of_measurement":"A"}}})
    assert await async_setup_component(hass,"script",{"script":{"adapter_current":{"sequence":[
        {"action":"input_number.set_value","target":{"entity_id":"input_number.adapter_feedback"},"data":{"value":"{{ value }}"}}]}}})
    await hass.async_block_till_done()
    await installed.runtime_data.update_options({"mappings":{"ev_current":"input_number.adapter_feedback"},"command_scripts":{"ev_current":"script.adapter_current"}})
    await hass.async_block_till_done()
    adapter=Adapters(installed.runtime_data)
    await adapter.write("ev_current",12)
    assert float(hass.states.get("input_number.adapter_feedback").state)==12
    assert adapter.matches("ev_current",12)


async def test_external_missing_supply_keeps_known_delivery_visible(hass,installed):
    await installed.runtime_data.update_options({"supply_plan":"External supply entity","delivery_cents":4})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.nrg_import_price").state == "unknown"
    assert float(hass.states.get("sensor.nrg_delivery_price").state)==4


async def test_meter_conventions_normalize_other_inverters_and_house_only_meter(hass,installed):
    mappings={key:"sensor.convention_"+key for key in ("home_power","grid_power","battery_power","ev_power")}
    for key,value in (("home_power",3),("grid_power",-5),("battery_power",-2),("ev_power",4)):
        hass.states.async_set(mappings[key],value,{"unit_of_measurement":"kW"})
    await installed.runtime_data.update_options({"has_ev":True,"has_battery":True,"has_solar":False,"mappings":mappings,
        "home_includes_ev":False,"grid_power_inverted":True,"battery_power_inverted":True})
    await hass.async_block_till_done()
    data=installed.runtime_data.snapshot()
    assert data["home_kw"]==7 and data["house_kw"]==3
    assert data["grid_kw"]==5 and data["battery_kw"]==2 and data["balance_kw"]==0


async def test_flat_pricing_without_solar_never_fetches_comed(hass,installed):
    from unittest.mock import AsyncMock
    runtime=installed.runtime_data
    runtime.get_text=AsyncMock(side_effect=AssertionError("A flat plan must not fetch ComEd"))
    runtime.last_fetch=0
    await runtime.async_refresh()
    runtime.get_text.assert_not_called()


async def test_new_user_can_select_monitoring_without_implicitly_enabling_commands(hass):
    from homeassistant.setup import async_setup_component
    from unittest.mock import patch
    from custom_components.nrg.runtime import NRGRuntime
    import time
    async def no_network(self):
        self.last_fetch=time.time()
    assert await async_setup_component(hass,"nrg",{})
    with patch.object(NRGRuntime,"refresh_forecasts",no_network):
        result=await hass.config_entries.flow.async_init("nrg",context={"source":"user"})
        result=await hass.config_entries.flow.async_configure(result["flow_id"],{"has_ev":True})
        assert result["step_id"]=="tariff"
        result=await hass.config_entries.flow.async_configure(result["flow_id"],{"supply_plan":"Flat supply","flat_supply_cents":10})
        result=await hass.config_entries.flow.async_configure(result["flow_id"],{"ev_current":"number.other_current","ev_charge":"switch.other_charge"})
        await hass.async_block_till_done()
        assert result["type"]=="create_entry"
        entry=result["result"]
        assert entry.options["has_ev"] is True and entry.options["ev_control"] is False
        assert entry.runtime_data.plan["ev_status"]=="monitor_only"
        await hass.config_entries.async_unload(entry.entry_id)


async def test_retained_vehicle_feeds_are_optional_and_still_need_home_connection(hass,installed,monkeypatch):
    from datetime import datetime,timedelta,UTC
    from homeassistant.core import State
    mappings={"ev_connected":"binary_sensor.retained_plug","ev_soc":"sensor.retained_soc","ev_limit":"sensor.retained_target",
              "ev_current":"number.retained_current","ev_charge":"switch.retained_charging"}
    old=datetime.now(UTC)-timedelta(hours=4)
    aged={
        mappings["ev_soc"]:State(mappings["ev_soc"],60,{"unit_of_measurement":"%"},last_reported=old),
        mappings["ev_limit"]:State(mappings["ev_limit"],80,{"unit_of_measurement":"%"},last_reported=old),
        mappings["ev_current"]:State(mappings["ev_current"],40,{"unit_of_measurement":"A","min":0,"max":40},last_reported=old),
        mappings["ev_charge"]:State(mappings["ev_charge"],"off",last_reported=old)}
    original=hass.states.get
    def get(self,entity_id):
        return aged.get(entity_id) or original(entity_id)
    monkeypatch.setattr(type(hass.states),"get",get)
    hass.states.async_set(mappings["ev_connected"],"on")
    await installed.runtime_data.update_options({"has_ev":True,"ev_control":True,"mappings":mappings})
    await hass.async_block_till_done()
    assert not installed.runtime_data.snapshot()["ev_ready"]
    await installed.runtime_data.update_options({"ev_allow_saved_readings":True})
    await hass.async_block_till_done()
    assert installed.runtime_data.snapshot()["ev_ready"]
    hass.states.async_set(mappings["ev_connected"],"off")
    assert not installed.runtime_data.snapshot()["ev_ready"]
