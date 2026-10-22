"""Explicit admin actions; learning reset preserves the measured-cost ledger."""
from homeassistant.components.button import ButtonEntity

from .entity import NRGEntity

ACTIONS = {"refresh": "Refresh energy forecasts", "reset_learning": "Reset learned estimates", "clear_departure": "Clear one-off departure",
           "activate_fallback": "Start manual price-data fallback", "release_fallback": "End manual price-data fallback"}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGButton(entry.runtime_data, key, name, config=True, platform="button") for key, name in ACTIONS.items())


class NRGButton(NRGEntity, ButtonEntity):
    @property
    def available(self):
        if not super().available:
            return False
        if self.key == "activate_fallback":
            return self.coordinator.config["price_fallback"] == "Custom fallback" and not self.coordinator.fallback.manual
        if self.key == "release_fallback":
            return self.coordinator.fallback.manual
        return True

    async def async_press(self):
        if self.key == "refresh":
            await self.coordinator.refresh()
        elif self.key in ("activate_fallback", "release_fallback"):
            await self.coordinator.set_manual_fallback(self.key == "activate_fallback")
        elif self.key == "reset_learning":
            await self.coordinator.reset_learning()
        else:
            await self.coordinator.update_options({"departure_override": None})
