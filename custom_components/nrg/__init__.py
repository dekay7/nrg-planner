"""Native UI configuration, observable planning, and one guarded writer."""
from datetime import timedelta
from pathlib import Path

import probatio as vol
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .const import DOMAIN, PLATFORMS, STATIC_URL
from .runtime import NRGRuntime

CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): dict}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass, config):
    # Only generic bundled documentation is exposed, never user settings/storage.
    if (http := getattr(hass, "http", None)) is not None:
        from homeassistant.components.http import StaticPathConfig
        await http.async_register_static_paths([
            StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "assets"), cache_headers=False)
        ])
    # Optional first-install bootstrap. An existing entry is never overwritten by
    # YAML on restart: UI options become the durable source of truth.
    if DOMAIN in config:
        hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN,
            context={"source": SOURCE_IMPORT}, data=config[DOMAIN]))
    return True


async def async_setup_entry(hass, entry):
    runtime = NRGRuntime(hass, entry)
    entry.runtime_data = runtime
    await runtime.load()
    await runtime.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def execute(now):
        await runtime.controller.apply()

    async def options_updated(hass, updated_entry):
        runtime.revision += 1
        runtime.plan = {}
        runtime.last_fetch = 0
        runtime.force_plan = True
        # Source mappings can change through options; replace watched entity IDs.
        register_watch()
        await runtime.async_request_refresh()

    stop_watch = None

    @callback
    def important_changed(event):
        source_ids = {s["entity_id"] for s in entry.options.get("solar_sources", [])}
        forecast_ids = {runtime.mappings.get(k) for k in ("supply_forecast", "delivery_forecast")}
        new, old = event.data.get("new_state"), event.data.get("old_state")
        if (event.data.get("entity_id") not in source_ids | forecast_ids and new and old and new.state == old.state
                and new.attributes.get("unit_of_measurement") == old.attributes.get("unit_of_measurement")):
            return  # GPS/report-attribute jitter is not a new charging decision.
        if event.data.get("entity_id") in source_ids and new and new.state not in ("unknown", "unavailable"):
            runtime.last_fetch = 0  # Read the newly available provider cache after startup/update.
        runtime.force_plan = True
        hass.async_create_task(runtime.async_request_refresh())

    @callback
    def register_watch():
        nonlocal stop_watch
        if stop_watch:
            stop_watch()
        keys = ["grid_connected"]
        if runtime.config["has_ev"]:
            keys += ["ev_connected", "ev_location", "ev_soc", "ev_limit", "ev_charge"]
        if runtime.config["has_battery"]:
            keys += ["storm_watch", "grid_services", "grid_services_enabled"]
        if runtime.config["supply_plan"] in ("Hourly ComEd", "External supply entity"):
            keys += ["live_supply", "supply_forecast"]
        if runtime.config["delivery_plan"] == "External delivery entity":
            keys += ["live_delivery", "delivery_forecast"]
        ids = [runtime.mappings.get(k) for k in keys]
        ids.extend(s["entity_id"] for s in entry.options.get("solar_sources", []) if runtime.config["has_solar"])
        stop_watch = async_track_state_change_event(hass, [i for i in ids if i], important_changed)

    register_watch()
    entry.async_on_unload(lambda: stop_watch() if stop_watch else None)
    entry.async_on_unload(entry.add_update_listener(options_updated))
    entry.async_on_unload(async_track_time_interval(hass, execute, timedelta(seconds=30)))
    async def stopping(event):
        await runtime.close()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stopping))
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        entry.runtime_data.revision += 1
        await entry.runtime_data.close()
        return True
    return False
