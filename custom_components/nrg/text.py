"""Persistent text options for provider-specific forecast attribute names."""
from homeassistant.components.text import TextEntity, TextMode
from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGText(entry.runtime_data, key) for key, field in SETTINGS.items() if field.kind == "text")


class NRGText(NRGEntity, TextEntity):
    _attr_native_min = 1
    _attr_native_max = 100
    _attr_mode = TextMode.TEXT

    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)

    @property
    def native_value(self):
        return self.coordinator.config[self.key]

    async def async_set_value(self, value):
        await self.change(value)
