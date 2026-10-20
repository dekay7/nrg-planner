"""Shared entity identity; settings have one persistent source of truth."""
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN, SETTINGS, VERSION


class NRGEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, runtime, key, name=None, config=False, platform=None):
        super().__init__(runtime)
        self.key = key
        self._attr_unique_id = f"{runtime.entry.unique_id}_{key}"
        # An explicit integration suggestion keeps packaged dashboards independent
        # of display labels/translations. Registry/user-renamed IDs still win.
        domain = platform or SETTINGS[key].kind
        self.entity_id = f"{domain}.nrg_{key}"
        self._attr_name = name or SETTINGS[key].name
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, runtime.entry.entry_id)},
            name="NRG Planner", manufacturer="NRG", model="Explainable energy planner", sw_version=VERSION)
        if config:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def suggested_object_id(self):
        return "nrg_" + self.key

    @property
    def extra_state_attributes(self):
        if self.key in SETTINGS:
            return {"description": SETTINGS[self.key].description}
        return None

    async def change(self, value):
        try:
            await self.coordinator.update_options({self.key: value})
        except ValueError as error:
            raise HomeAssistantError(str(error)) from error
