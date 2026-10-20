"""Tariff, export and controller choices."""
from homeassistant.components.select import SelectEntity

from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGSelect(entry.runtime_data, key) for key, f in SETTINGS.items() if f.kind == "select")


class NRGSelect(NRGEntity, SelectEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)
        self._attr_options = list(SETTINGS[key].choices)

    @property
    def current_option(self):
        return self.coordinator.config[self.key]

    async def async_select_option(self, option):
        await self.change(option)
