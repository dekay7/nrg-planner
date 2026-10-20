"""Invented deterministic scenarios and a real HA runtime; no household exports."""
from datetime import datetime
from pathlib import Path
import sys
import time
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.nrg.config import settings
from custom_components.nrg.statistics import Statistics

ZONE = ZoneInfo("America/Chicago")
NOW = datetime(2026, 10, 19, 18, tzinfo=ZONE).timestamp()


def fixture(**overrides):
    config = settings({"has_ev": True, "has_battery": True, "has_solar": True, "ev_control": True, "battery_control": True,
                       "battery_capacity": 12, "ev_max_amps": 32, "ev_kw_at_max": 7.2,
                       "ev_kwh_per_percent": .6, "departure_time": "08:00:00",
                       "supply_plan": "Hourly ComEd", "delivery_cents": 4, "export_rate": "Supply plus adder", "export_adder_cents": 2,
                       "summer_guard": False, **overrides})
    prices = [{"start": NOW + i * 3600, "supply": (.005 if i in (7, 8) else .15), "fetched_at": NOW} for i in range(48)]
    solar = {"hours": {str(int(NOW + i * 3600)): 0 for i in range(49)},
             "known": {str(int(NOW + i * 3600)): True for i in range(49)}}
    telemetry = {"battery_soc": 60, "battery_ready": True, "connected": True, "ev_soc": 70, "ev_limit": 80}
    return config, prices, solar, telemetry, Statistics()


@pytest.fixture
async def hass(tmp_path):
    from homeassistant.core import HomeAssistant
    from homeassistant.config_entries import ConfigEntries
    from homeassistant.loader import async_setup as setup_loader
    instance = HomeAssistant(str(tmp_path))
    await instance.config.async_set_time_zone("America/Chicago")
    instance.config_entries = ConfigEntries(instance, {})
    (tmp_path / "custom_components").symlink_to(Path(__file__).resolve().parents[1] / "custom_components", target_is_directory=True)
    setup_loader(instance)
    from homeassistant.helpers import entity_registry, device_registry, area_registry, floor_registry, label_registry
    for registry in (floor_registry, area_registry, label_registry, device_registry, entity_registry):
        if hasattr(registry, "async_setup"):
            registry.async_setup(instance)
        await registry.async_load(instance)
    yield instance
    await instance.async_stop(force=True)


@pytest.fixture
async def installed(hass):
    from homeassistant.setup import async_setup_component
    from custom_components.nrg.runtime import NRGRuntime
    async def no_network(self):
        self.last_fetch = time.time()
    with patch.object(NRGRuntime, "refresh_forecasts", no_network):
        assert await async_setup_component(hass, "nrg", {"nrg": {"supply_plan": "Flat supply", "flat_supply_cents": 10, "delivery_cents": 4}})
        await hass.async_block_till_done()
        entry = next(e for e in hass.config_entries.async_entries("nrg"))
        assert entry.runtime_data is not None
        yield entry
        await hass.config_entries.async_unload(entry.entry_id)
