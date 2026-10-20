"""Persistent model switches and an intentionally session-only charge-now override."""
from homeassistant.components.switch import SwitchEntity

from .const import SETTINGS
from .entity import NRGEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NRGSwitch(entry.runtime_data, key) for key, f in SETTINGS.items() if f.kind == "switch"]
                       + [NRGChargeNow(entry.runtime_data, "charge_now", "Charge now · ignore price", config=True, platform="switch")])


class NRGSwitch(NRGEntity, SwitchEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime, key, config=True)

    @property
    def is_on(self):
        return self.coordinator.config[self.key]

    async def async_turn_on(self, **kwargs):
        await self.change(True)

    async def async_turn_off(self, **kwargs):
        await self.change(False)


class NRGChargeNow(NRGEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.coordinator.charge_now

    async def async_turn_on(self, **kwargs):
        await self.coordinator.set_charge_now(True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.set_charge_now(False)
