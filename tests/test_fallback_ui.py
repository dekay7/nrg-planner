"""Settings organization and user-facing fallback states, using invented fixtures."""
from itertools import product
from pathlib import Path
import json

import pytest
import yaml
from homeassistant.helpers.template import Template

from custom_components.nrg.config_flow import fields
from custom_components.nrg.const import option_label
from tools.build_ui import pricing_health_note

ROOT = Path(__file__).resolve().parents[1]


def dashboard():
    return yaml.safe_load((ROOT / "custom_components/nrg/dashboards/nrg-settings.yaml").read_text())


def visible_items(value, states):
    """Evaluate the simple state conditions used by these generated pages."""
    if isinstance(value, dict):
        conditions = value.get("visibility", [])
        if value.get("type") == "conditional":
            conditions += value.get("conditions", [])
        if any(states.get(c["entity"], "off") != c["state"] for c in conditions):
            return
        yield value
        for key, child in value.items():
            if key not in ("visibility", "conditions"):
                yield from visible_items(child, states)
    elif isinstance(value, list):
        for child in value:
            yield from visible_items(child, states)


def field_names(schema):
    return {marker.schema for marker in schema.schema}


def test_everyday_operation_and_fallback_are_separate_and_labels_keep_saved_values():
    assert field_names(fields("operation", {})) == {"mode"}
    assert field_names(fields("fallback", {})) == {"price_fallback"}
    selector = next(iter(fields("fallback", {}).schema.values()))
    assert selector.config["options"] == [
        {"value": "Existing behavior", "label": "Standard protection (default)"},
        {"value": "Custom fallback", "label": "Use my fallback actions"},
    ]
    views = {view["path"]: view for view in dashboard()["views"]}
    operation_entities = {item.get("entity") for item in visible_items(views["operation"], {})}
    assert "select.nrg_price_fallback" not in operation_entities
    assert {view["title"] for view in dashboard()["views"]}.issuperset({"Operation", "Price-data fallback", "Notifications"})
    assert "Configure → Price-data fallback" in str(views["fallback"])
    assert "Saving can apply them immediately" in str(views["fallback"])


@pytest.mark.parametrize("custom,has_ev,ev_control,has_battery,battery_control", list(product((False, True), repeat=5)))
def test_fallback_dashboard_hides_unused_device_actions(custom, has_ev, ev_control, has_battery, battery_control):
    states = {
        "binary_sensor.nrg_fallback_enabled": "on" if custom else "off",
        "binary_sensor.nrg_has_ev": "on" if has_ev else "off",
        "binary_sensor.nrg_ev_control": "on" if has_ev and ev_control else "off",
        "binary_sensor.nrg_has_battery": "on" if has_battery else "off",
        "binary_sensor.nrg_battery_control": "on" if has_battery and battery_control else "off",
    }
    view = next(view for view in dashboard()["views"] if view["path"] == "fallback")
    entities = {item.get("entity") for item in visible_items(view, states)}
    assert ("select.nrg_fallback_ev" in entities) == (custom and has_ev and ev_control)
    assert ("select.nrg_fallback_battery" in entities) == (custom and has_battery and battery_control)
    assert "select.nrg_price_fallback" not in entities  # Policy changes use the guided review, not an immediate dropdown.
    assert "select.nrg_price_fallback" in str(view)


@pytest.mark.parametrize("custom,manual", list(product((False, True), repeat=2)))
def test_manual_buttons_only_offer_applicable_confirmed_action(custom, manual):
    states = {"binary_sensor.nrg_fallback_enabled": "on" if custom else "off",
              "binary_sensor.nrg_fallback_manual": "on" if manual else "off"}
    view = next(view for view in dashboard()["views"] if view["path"] == "fallback")
    buttons = {item["entity"]: item for item in visible_items(view, states)
               if item.get("type") == "button" and item.get("entity", "").startswith("button.nrg_")}
    assert ("button.nrg_activate_fallback" in buttons) == (custom and not manual)
    assert ("button.nrg_release_fallback" in buttons) == manual
    for button in buttons.values():
        assert button["tap_action"]["perform_action"] == "button.press"
        assert button["tap_action"]["confirmation"]["text"]


@pytest.mark.parametrize("advice", [False, True])
def test_notification_benefit_is_only_visible_with_household_advice(advice):
    view = next(view for view in dashboard()["views"] if view["path"] == "notifications")
    entities = {item.get("entity") for item in visible_items(view, {"switch.nrg_notifications": "on" if advice else "off"})}
    assert ("number.nrg_notification_saving_cents" in entities) == advice
    assert "switch.nrg_fallback_notifications" in entities
    assert "time.nrg_quiet_start" in entities and "time.nrg_quiet_end" in entities
    headings = [group["cards"][0]["heading"] for group in view["sections"]]
    assert headings == ["Household advice messages", "Price-data fallback alerts", "Shared delivery and quiet hours"]


async def test_observation_banner_cannot_be_mistaken_for_executed_actions(hass):
    hass.states.async_set("sensor.nrg_pricing_health", "Fallback", {
        "active": True, "operating_mode": "Observation", "reason": "Invented price outage"})
    rendered = Template(pricing_health_note()["content"], hass).async_render(parse_result=False)
    assert "Observation only" in rendered
    assert "No equipment commands are sent" in rendered
    assert "verify device results" not in rendered
    hass.states.async_set("sensor.nrg_pricing_health", "Recovering", {
        "active": True, "operating_mode": "Control", "reason": "Invented recovery"})
    rendered = Template(pricing_health_note()["content"], hass).async_render(parse_result=False)
    assert "verify device results" in rendered
    assert "fallback remains active" in rendered


@pytest.mark.parametrize("has_ev,ev_control,has_battery,battery_control", list(product((False, True), repeat=4)))
async def test_guided_flow_shows_only_controlled_devices_and_preserves_hidden_choices(hass, installed, has_ev, ev_control, has_battery, battery_control):
    runtime = installed.runtime_data
    await runtime.update_options({"has_ev": has_ev, "ev_control": ev_control,
                                  "has_battery": has_battery, "battery_control": battery_control,
                                  "fallback_ev": "Maintain departure readiness", "fallback_battery": "Self-consumption"})
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(installed.entry_id)
    assert ("fallback" in result["menu_options"]) == (has_ev or has_battery)
    if not (has_ev or has_battery):
        return
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "fallback"})
    assert field_names(result["data_schema"]) == {"price_fallback"}
    assert result["last_step"] is False
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"price_fallback": "Custom fallback"})
    expected = ({"fallback_ev"} if has_ev and ev_control else set()) | ({"fallback_battery"} if has_battery and battery_control else set())
    if expected:
        assert result["step_id"] == "fallback_actions"
        assert result["last_step"] is True
        assert field_names(result["data_schema"]) == expected
        assert runtime.config["price_fallback"] == "Existing behavior"  # No change before confirmation.
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    assert runtime.config["price_fallback"] == "Custom fallback"
    assert runtime.config["fallback_ev"] == "Maintain departure readiness"
    assert runtime.config["fallback_battery"] == "Self-consumption"
    assert runtime.config["has_ev"] == has_ev and runtime.config["ev_control"] == ev_control
    assert runtime.config["mode"] == "Observation" and not runtime.fallback.manual
    assert runtime.controller.last == {}


async def test_native_selects_use_friendly_labels_without_changing_stored_policy(hass, installed):
    runtime = installed.runtime_data
    assert hass.states.get("select.nrg_price_fallback").state == "Standard protection (default)"
    await hass.services.async_call("select", "select_option", {
        "entity_id": "select.nrg_price_fallback", "option": "Use my fallback actions"}, blocking=True)
    await hass.async_block_till_done()
    assert installed.options["price_fallback"] == "Custom fallback"
    assert hass.states.get("select.nrg_price_fallback").state == "Use my fallback actions"
    assert hass.states.get("button.nrg_activate_fallback").state != "unavailable"
    assert hass.states.get("button.nrg_release_fallback").state == "unavailable"
    await runtime.set_manual_fallback(True)
    await hass.async_block_till_done()
    assert hass.states.get("button.nrg_activate_fallback").state == "unavailable"
    assert hass.states.get("button.nrg_release_fallback").state != "unavailable"
    await runtime.update_options({"price_fallback": "Existing behavior"})
    await hass.async_block_till_done()
    assert hass.states.get("button.nrg_release_fallback").state != "unavailable"  # Saved request can still be ended.
    assert runtime.fallback.manual


async def test_returning_to_standard_protection_keeps_device_choices(hass, installed):
    runtime = installed.runtime_data
    await runtime.update_options({"has_ev": True, "ev_control": True, "price_fallback": "Custom fallback",
                                  "fallback_ev": "Maintain departure readiness", "fallback_battery": "Self-consumption"})
    await hass.async_block_till_done()
    flow = await hass.config_entries.options.async_init(installed.entry_id)
    flow = await hass.config_entries.options.async_configure(flow["flow_id"], {"next_step_id": "fallback"})
    result = await hass.config_entries.options.async_configure(flow["flow_id"], {"price_fallback": "Existing behavior"})
    await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert runtime.config["price_fallback"] == "Existing behavior"
    assert runtime.config["fallback_ev"] == "Maintain departure readiness"
    assert runtime.config["fallback_battery"] == "Self-consumption"
    assert runtime.config["ev_control"] and runtime.config["mode"] == "Observation"


def test_generated_help_uses_user_visible_labels_and_explains_shared_alert_delivery():
    text = (ROOT / "docs/settings.md").read_text()
    assert "**Existing behavior**" not in text and "**Custom fallback**" not in text
    for key, value in (("price_fallback", "Existing behavior"), ("fallback_ev", "Maintain departure readiness"),
                       ("fallback_battery", "Self-consumption")):
        assert option_label(key, value) in text
    translations = json.loads((ROOT / "custom_components/nrg/translations/en.json").read_text())
    description = translations["options"]["step"]["notifications"]["description"]
    assert "Two independent message types" in description
    assert "minimum benefit applies only to household advice" in description
