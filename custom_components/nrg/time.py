"""Persistent local departure and charging-window times."""
from datetime import time
from homeassistant.components.time import TimeEntity

from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGTime(entry.runtime_data, key) for key, f in SETTINGS.items() if f.kind == "time")


class NRGTime(NRGEntity, TimeEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)

    @property
    def native_value(self):
        return time.fromisoformat(self.coordinator.config[self.key])

    async def async_set_value(self, value):
        await self.change(value.isoformat())
