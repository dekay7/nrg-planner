"""Native HA capability feedback must agree with refill valuation."""
import pytest


@pytest.mark.parametrize("charge_mode,options,grid_switch,expected", [
    ("backup", ["backup", "self_consumption"], True, True),
    ("backup", ["backup", "self_consumption"], False, False),
    ("force_charge", ["backup", "self_consumption", "force_charge"], False, True),
    ("force_charge", ["backup", "self_consumption"], True, False),
    ("force_charge", ["backup", "self_consumption"], False, False),
])
async def test_charge_mode_and_permission_switch_are_both_checked(hass, installed, charge_mode, options, grid_switch, expected):
    runtime = installed.runtime_data
    mappings = {"battery_soc": "sensor.example_stationary_soc", "battery_mode": "select.example_stationary_mode"}
    hass.states.async_set(mappings["battery_soc"], 50, {"unit_of_measurement": "%"})
    hass.states.async_set(mappings["battery_mode"], "backup", {"options": options})
    if grid_switch:
        mappings["battery_grid_charge"] = "switch.example_grid_permission"
        hass.states.async_set(mappings["battery_grid_charge"], "off")
    await runtime.update_options({"has_battery": True, "battery_control": True, "mappings": mappings,
                                  "control_values": {"battery_charge": charge_mode}})
    await runtime.async_refresh()
    snapshot = runtime.snapshot()
    assert snapshot["battery_ready"]
    assert snapshot["can_grid_charge"] == expected
    valuation = runtime.plan["battery_valuation"]
    assert (valuation["refill_sources_stored_kwh"]["grid"] > 0) == expected
    if not expected:
        assert valuation["comparison_limited"]
        assert runtime.plan["household"]["confidence"] == "limited"
    assert runtime.config["mode"] == "Observation"
    assert runtime.controller.last == {}
