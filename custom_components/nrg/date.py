"""Installation dates are editable from native date controls."""
from datetime import date
from homeassistant.components.date import DateEntity

from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGDate(entry.runtime_data, key) for key, f in SETTINGS.items() if f.kind == "date")


class NRGDate(NRGEntity, DateEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)

    @property
    def native_value(self):
        value = self.coordinator.config[self.key]
        return date.fromisoformat(value) if value else None

    async def async_set_value(self, value):
        await self.change(value.isoformat())
