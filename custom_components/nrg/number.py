"""Persistent numeric tuning, exposed as standard number entities."""
from homeassistant.components.number import NumberEntity, NumberMode

from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGNumber(entry.runtime_data, key) for key, f in SETTINGS.items() if f.kind == "number")


class NRGNumber(NRGEntity, NumberEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)
        field = SETTINGS[key]
        self._attr_native_min_value, self._attr_native_max_value = field.low, field.high
        self._attr_native_step, self._attr_native_unit_of_measurement = field.step, field.unit
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self.coordinator.config[self.key]

    async def async_set_native_value(self, value):
        await self.change(value)
