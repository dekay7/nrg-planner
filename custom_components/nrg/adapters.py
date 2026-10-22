"""Provider-neutral HA entity/script command adapters and explicit readback values."""
from homeassistant.helpers import entity_registry as er

from .config import finite

COMMANDS = {"ev_current", "ev_charge", "battery_mode", "battery_export", "battery_reserve", "battery_grid_charge"}


class Adapters:
    def __init__(self, runtime):
        self.runtime, self.hass = runtime, runtime.hass

    def state(self, key):
        entity_id = self.runtime.mappings.get(key)
        return self.hass.states.get(entity_id) if entity_id else None

    def script(self, key, action):
        script_key = ("ev_start" if action == "on" else "ev_stop") if key == "ev_charge" else (
            "grid_charge_on" if action == "on" else "grid_charge_off") if key == "battery_grid_charge" else key
        return self.runtime.config["command_scripts"].get(script_key)

    def value(self, key, action):
        values = self.runtime.config["control_values"]
        state = self.state(key)
        domain = state.entity_id.split(".")[0] if state else None
        if key == "battery_mode":
            return values["battery_" + action]
        if key == "battery_export":
            return values[{"Solar only": "export_solar", "Battery": "export_battery", "No exports": "export_none"}[action]]
        if key in ("ev_charge", "battery_grid_charge") and domain not in ("switch", "input_boolean"):
            return values[("ev_" if key == "ev_charge" else "grid_charge_") + action]
        return action

    def can(self, key, action=None):
        state = self.state(key)
        if key not in COMMANDS or state is None or state.state in ("unknown", "unavailable", ""):
            return False
        record = er.async_get(self.hass).async_get(state.entity_id)
        if record is not None and record.disabled_by is not None:
            return False
        script_id = self.script(key, action)
        if script_id:
            script = self.hass.states.get(script_id)
            return script is not None and script.state not in ("unavailable", "unknown")
        domain = state.entity_id.split(".")[0]
        if key in ("ev_current", "battery_reserve"):
            return domain in ("number", "input_number")
        if key in ("ev_charge", "battery_grid_charge"):
            return domain in ("switch", "input_boolean")
        value = self.value(key, action) if action is not None else None
        return domain in ("select", "input_select") and (value is None or value in state.attributes.get("options", []))

    def matches(self, key, action):
        state = self.state(key)
        expected = self.value(key, action)
        if not state:
            return False
        if key in ("ev_current", "battery_reserve"):
            return finite(state.state) is not None and abs(float(state.state) - float(expected)) < .01
        return state.state == expected

    async def write(self, key, action):
        if not self.can(key, action):
            raise RuntimeError(f"{key}: map a supported control entity or an available command script")
        state = self.state(key)
        value = self.value(key, action)
        if key in ("ev_current", "battery_reserve"):
            low = self.runtime.config["ev_min_amps"] if key == "ev_current" else 0
            high = self.runtime.config["ev_max_amps"] if key == "ev_current" else 100
            low, high = max(low, finite(state.attributes.get("min"), low)), min(high, finite(state.attributes.get("max"), high))
            if finite(value) is None or not low <= float(value) <= high:
                raise RuntimeError(f"{key}: requested value is outside configured/device bounds")
        script = self.script(key, action)
        if script:
            reserve, export = self.runtime.config["backup_reserve"], self.runtime.config["export_policy"]
            if getattr(self.runtime, "_fallback_active", False) or getattr(self.runtime, "_comed_estimated", False):
                native = self.state("battery_reserve")
                if native is not None:
                    current = finite(native.state)
                    reserve = max(reserve, current) if current is not None else None
                export = "No exports" if export == "No exports" else "Solar only"
            await self.hass.services.async_call("script", script.split(".", 1)[1],
                {"value": value, "action": action, "target_soc": self.runtime.plan.get("battery_target_soc"),
                 "reserve_soc": reserve, "export_policy": export}, blocking=True)
            return
        domain = state.entity_id.split(".")[0]
        if domain in ("number", "input_number"):
            service, data = "set_value", {"value": value}
        elif domain in ("select", "input_select"):
            service, data = "select_option", {"option": value}
        else:
            service, data = ("turn_on" if action == "on" else "turn_off"), {}
        await self.hass.services.async_call(domain, service, {"entity_id": state.entity_id, **data}, blocking=True)
