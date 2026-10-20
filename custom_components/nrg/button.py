"""Explicit admin actions; learning reset preserves the measured-cost ledger."""
from homeassistant.components.button import ButtonEntity

from .entity import NRGEntity

ACTIONS = {"refresh": "Refresh energy forecasts", "reset_learning": "Reset learned estimates", "clear_departure": "Clear one-off departure"}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGButton(entry.runtime_data, key, name, config=True, platform="button") for key, name in ACTIONS.items())


class NRGButton(NRGEntity, ButtonEntity):
    async def async_press(self):
        if self.key == "refresh":
            await self.coordinator.refresh()
        elif self.key == "reset_learning":
            await self.coordinator.reset_learning()
        else:
            await self.coordinator.update_options({"departure_override": None})
