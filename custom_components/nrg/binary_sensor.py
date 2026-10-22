"""Separate writer authorization from per-device operational readiness."""
from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGReady(entry.runtime_data, key, name, platform="binary_sensor") for key, name in (
        ("writer_authorized", "Writer authorized"), ("battery_ready", "Battery telemetry and native state ready"),
        ("ev_ready", "EV ready for commands"), ("native_ready", "Configured protection guards clear"),
        ("has_ev", "EV installed"), ("has_battery", "Home battery installed"), ("has_solar", "Solar installed"),
        ("ev_control", "EV control enabled"), ("battery_control", "Battery control enabled"),
        ("fallback_enabled", "Custom price-data fallback selected"),
        ("fallback_manual", "Manual price-data fallback requested"),
        ("cost_metered", "Energy cost is metered")))


class NRGReady(NRGEntity, BinarySensorEntity):
    @property
    def extra_state_attributes(self):
        if self.key in ("native_ready", "battery_ready", "ev_ready"):
            return {"guard_issues": (self.coordinator.data or {}).get("snapshot", {}).get("guard_issues", [])}
        return super().extra_state_attributes

    @property
    def is_on(self):
        if self.key == "writer_authorized":
            return self.coordinator.controller.owned()
        if self.key.startswith("has_"):
            return self.coordinator.config[self.key]
        if self.key in ("ev_control", "battery_control"):
            return self.coordinator.config[self.key] and self.coordinator.config["has_" + self.key.removesuffix("_control")]
        if self.key == "fallback_enabled":
            return self.coordinator.config["price_fallback"] == "Custom fallback"
        if self.key == "fallback_manual":
            return self.coordinator.fallback.manual
        if self.key == "cost_metered":
            return (self.coordinator.data or {}).get("snapshot", {}).get("grid_kw") is not None
        return (self.coordinator.data or {}).get("snapshot", {}).get(self.key, False)
