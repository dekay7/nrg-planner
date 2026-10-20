"""One-off departure override using a standard HA date/time picker."""
from datetime import datetime
from homeassistant.components.datetime import DateTimeEntity

from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NRGDeparture(entry.runtime_data, "departure_override", "One-off EV departure", config=True, platform="datetime")])


class NRGDeparture(NRGEntity, DateTimeEntity):
    @property
    def native_value(self):
        value = self.coordinator.entry.options.get("departure_override")
        return datetime.fromisoformat(value) if value else None

    async def async_set_value(self, value):
        await self.change(value.isoformat())
