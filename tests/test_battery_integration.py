"""Real HA switch, read-only calibration, measurement gates and lifecycle."""
import time
from datetime import UTC, datetime, timedelta

import pytest

from homeassistant.core import State


async def setup_battery(hass, runtime, **changes):
    mappings = {key: "sensor.example_" + key for key in
                ("battery_soc", "battery_power", "home_power", "grid_power", "solar_power")}
    for key, value in (("battery_soc", 50), ("battery_power", 3), ("home_power", 4), ("grid_power", 1), ("solar_power", 0)):
        hass.states.async_set(mappings[key], value, {"unit_of_measurement": "%" if key.endswith("soc") else "kW"})
    await runtime.update_options({"has_battery": True, "has_solar": True, "battery_learning": True,
                                  "mappings": mappings, **changes})
    await hass.async_block_till_done()
    await runtime.async_refresh()
    return mappings


async def test_single_opt_in_switch_effective_sensors_and_no_control_permissions(hass, installed):
    runtime = installed.runtime_data
    assert hass.states.get("switch.nrg_battery_learning").state == "off"
    assert hass.states.get("switch.nrg_battery_learning").attributes["friendly_name"].endswith("Calibrate battery estimates")
    await setup_battery(hass, runtime)
    now = time.time()
    runtime.stats.battery.cycles = [{"charge_kwh": 5, "discharge_kwh": 4.4, "ended": now}] * 3
    runtime.stats.battery.powers["charge"] = [{"kw": 3.5, "ended": now}] * 3
    runtime.stats.battery.powers["discharge"] = [{"kw": 4, "ended": now}] * 3
    await runtime.async_refresh()
    assert float(hass.states.get("sensor.nrg_battery_efficiency_estimate").state) == pytest.approx(88)
    assert float(hass.states.get("sensor.nrg_battery_charge_estimate").state) == 3.5
    assert float(hass.states.get("sensor.nrg_battery_discharge_estimate").state) == 4
    assert hass.states.get("sensor.nrg_battery_charge_estimate").attributes["source"] == "learned"
    assert hass.states.get("sensor.nrg_battery_calibration").state == "Using learned estimates"
    assert runtime.plan["battery_model"]["battery_charge_kw"] == 3.5
    assert not runtime.config["battery_control"] and runtime.config["mode"] == "Observation"
    assert runtime.controller.last == {}
    assert runtime.config["battery_charge_kw"] == 5 and runtime.config["round_trip_efficiency"] == 90
    for entity in ("number.nrg_battery_charge_kw", "number.nrg_battery_discharge_kw"):
        assert float(hass.states.get(entity).state) == 5

    saved = runtime.stats.battery.export()
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.nrg_battery_learning"}, blocking=True)
    await hass.async_block_till_done()
    await runtime.async_refresh()
    assert runtime.stats.battery.export() == saved
    assert runtime.stats.battery.previous is None
    assert float(hass.states.get("sensor.nrg_battery_efficiency_estimate").state) == 90
    assert float(hass.states.get("sensor.nrg_battery_charge_estimate").state) == 5
    assert hass.states.get("sensor.nrg_battery_calibration").state == "Off"
    assert runtime.plan["battery_model"]["round_trip_efficiency"] == 90

    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()
    restored = installed.runtime_data
    assert not restored.config["battery_learning"]
    assert restored.stats.battery.export() == saved
    assert restored.stats.battery.previous is None and restored.stats.battery.cycle is None
    await restored.update_options({"battery_learning": True})
    await restored.async_refresh()
    assert restored.data["battery_calibration"]["estimates"]["round_trip_efficiency"]["source"] == "learned"


async def test_snapshot_power_opportunities_require_independent_headroom_and_mid_soc(hass, installed):
    runtime = installed.runtime_data
    mappings = await setup_battery(hass, runtime)
    snapshot = runtime.snapshot()
    assert snapshot["battery_learning_valid"] and snapshot["battery_discharge_opportunity"]
    assert not snapshot["battery_charge_opportunity"]
    # Meeting a small load does not establish the battery's maximum.
    hass.states.async_set(mappings["home_power"], 3, {"unit_of_measurement": "kW"})
    hass.states.async_set(mappings["grid_power"], 0, {"unit_of_measurement": "kW"})
    assert not runtime.snapshot()["battery_discharge_opportunity"]
    # An independently observed 1 kW surplus remains after 3 kW battery charging.
    for key, value in (("battery_power", -3), ("solar_power", 7), ("home_power", 3), ("grid_power", -1)):
        hass.states.async_set(mappings[key], value, {"unit_of_measurement": "kW"})
    assert runtime.snapshot()["battery_charge_opportunity"]
    hass.states.async_set(mappings["battery_soc"], 95, {"unit_of_measurement": "%"})
    assert not runtime.snapshot()["battery_charge_opportunity"]
    hass.states.async_set(mappings["battery_soc"], 50, {"unit_of_measurement": "%"})
    # Calculating home from the other meters does not independently prove balance.
    await runtime.update_options({"mappings": {key: value for key, value in mappings.items() if key != "home_power"}})
    snapshot = runtime.snapshot()
    assert snapshot["home_basis"] == "calculated from site meters"
    assert snapshot["battery_learning_valid"] and not snapshot["battery_charge_opportunity"]


async def test_distinct_force_charge_feedback_not_permission_alone_qualifies(hass, installed):
    runtime = installed.runtime_data
    mappings = await setup_battery(hass, runtime)
    mappings |= {"battery_mode": "sensor.example_battery_mode", "battery_grid_charge": "switch.example_grid_charge"}
    hass.states.async_set(mappings["battery_mode"], "backup")
    hass.states.async_set(mappings["battery_grid_charge"], "on")
    for key, value in (("battery_power", -3), ("home_power", 1), ("grid_power", 4)):
        hass.states.async_set(mappings[key], value, {"unit_of_measurement": "kW"})
    await runtime.update_options({"mappings": mappings})
    assert not runtime.snapshot()["battery_charge_opportunity"]
    await runtime.update_options({"control_values": {"battery_charge": "force_charge"}})
    hass.states.async_set(mappings["battery_mode"], "force_charge")
    assert runtime.snapshot()["battery_charge_opportunity"]
    hass.states.async_set(mappings["battery_mode"], "unavailable")
    assert not runtime.snapshot()["battery_charge_opportunity"]


async def test_stale_invalid_units_inconsistent_flows_and_guards_pause_learning(hass, installed, monkeypatch):
    runtime = installed.runtime_data
    mappings = await setup_battery(hass, runtime)
    old_get = hass.states.get
    aged = State(mappings["battery_power"], 3, {"unit_of_measurement": "kW"},
                 last_reported=datetime.now(UTC) - timedelta(minutes=10))
    with monkeypatch.context() as patch:
        patch.setattr(type(hass.states), "get", lambda self, entity: aged if entity == aged.entity_id else old_get(entity))
        assert not runtime.snapshot()["battery_learning_valid"]
    hass.states.async_set(mappings["battery_power"], 3, {"unit_of_measurement": "A"})
    assert not runtime.snapshot()["battery_learning_valid"]
    hass.states.async_set(mappings["battery_power"], 3000, {"unit_of_measurement": "W"})
    assert runtime.snapshot()["battery_learning_valid"]
    hass.states.async_set(mappings["home_power"], 20, {"unit_of_measurement": "kW"})
    assert not runtime.snapshot()["battery_learning_valid"]
    hass.states.async_set(mappings["home_power"], 4, {"unit_of_measurement": "kW"})
    hass.states.async_set("binary_sensor.example_protection", "on")
    await runtime.update_options({"mappings": mappings | {"storm_watch": "binary_sensor.example_protection"}})
    assert not runtime.snapshot()["battery_learning_valid"]


async def test_mapping_change_and_reset_preserve_other_learning_and_cost_ledger(hass, installed):
    runtime = installed.runtime_data
    mappings = await setup_battery(hass, runtime)
    runtime.stats.ev_sessions = [{"kwh_per_percent": .7}]
    runtime.stats.ledger = {"example-day": {"import_cost": 2}}
    runtime.stats.battery.cycles = [{"charge_kwh": 5, "discharge_kwh": 4.4, "ended": time.time()}] * 3
    hass.states.async_set("sensor.example_replacement_soc", 50, {"unit_of_measurement": "%"})
    await runtime.update_options({"mappings": mappings | {"battery_soc": "sensor.example_replacement_soc"}})
    await runtime.async_refresh()
    assert runtime.stats.battery.cycles == []
    assert runtime.stats.ev_sessions == [{"kwh_per_percent": .7}]
    assert runtime.stats.ledger["example-day"] == {"import_cost": 2}
    runtime.stats.battery.cycles = [{"charge_kwh": 5, "discharge_kwh": 4.4, "ended": time.time()}] * 3
    await runtime.reset_learning()
    await runtime.async_refresh()
    assert runtime.stats.battery.cycles == [] and runtime.stats.ev_sessions == []
    assert runtime.stats.ledger["example-day"] == {"import_cost": 2}
    assert runtime.config["battery_learning"] and runtime.config["round_trip_efficiency"] == 90


async def test_optional_counters_are_fresh_kwh_and_mapping_flow_exposes_one_learning_switch(hass, installed):
    runtime = installed.runtime_data
    mappings = await setup_battery(hass, runtime)
    assert not runtime.snapshot()["battery_energy_counters"]
    mappings |= {"battery_charge_energy": "sensor.example_lifetime_ac_charge",
                 "battery_discharge_energy": "sensor.example_lifetime_ac_discharge"}
    hass.states.async_set(mappings["battery_charge_energy"], 100, {"unit_of_measurement": "kWh"})
    hass.states.async_set(mappings["battery_discharge_energy"], 200, {"unit_of_measurement": "Wh"})
    await runtime.update_options({"mappings": mappings})
    snapshot = runtime.snapshot()
    assert snapshot["battery_energy_counters"]
    assert snapshot["battery_charge_energy"] == 100 and snapshot["battery_discharge_energy"] is None
    result = await hass.config_entries.options.async_init(installed.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "battery"})
    fields = {marker.schema for marker in result["data_schema"].schema}
    assert [key for key in fields if "learning" in key or "calibration" in key] == ["battery_learning"]
