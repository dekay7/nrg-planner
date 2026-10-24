"""Release metadata and restoration of an invented 0.2.0-format HA store."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import time

import pytest
from homeassistant.config_entries import ConfigEntryState

from custom_components.nrg.const import VERSION

ROOT = Path(__file__).resolve().parents[1]


def test_release_versions_and_ha_baseline_are_aligned():
    manifest = json.loads((ROOT / "custom_components/nrg/manifest.json").read_text())
    hacs = json.loads((ROOT / "hacs.json").read_text())
    assert manifest["version"] == VERSION
    assert f"version {VERSION}." in (ROOT / "README.md").read_text()
    assert f"homeassistant=={hacs['homeassistant']}" in (ROOT / "requirements-dev.txt").read_text()
    assert f"Home Assistant **{hacs['homeassistant']} or newer**" in (ROOT / "README.md").read_text()


@pytest.mark.parametrize("mode,permission", [("Observation", False), ("Control", True)])
async def test_upgrade_restores_020_store_settings_learning_and_ledger(hass, installed, mode, permission):
    runtime = installed.runtime_data
    departure = (datetime.now(runtime.zone) + timedelta(days=3)).isoformat()
    await runtime.update_options({
        "mode": mode, "has_ev": True, "has_battery": True, "has_solar": False,
        "ev_control": permission, "battery_control": permission, "battery_learning": True,
        "battery_capacity": 17, "round_trip_efficiency": 91, "ev_kwh_per_percent": .65,
        "departure_override": departure,
        "mappings": {"ev_soc": "sensor.example_ev_soc", "battery_soc": "sensor.example_battery_soc"},
    })
    await hass.async_block_till_done()
    options = dict(installed.options)
    assert await hass.config_entries.async_unload(installed.entry_id)

    # These are the fields written by v0.2.0: no fallback/ComEd-continuity keys
    # or estimated-cost subsets. Keep all completed samples inside retention.
    now = time.time()
    hour = int(now // 3600) * 3600 - 3600
    day = datetime.fromtimestamp(now, runtime.zone).date().isoformat()
    statistics = {
        "hours": [{"start": hour, "house_kwh": 1.25, "solar_kwh": 0,
                   "solar_forecast": None, "supply": .06, "comed_hour": 12}],
        "ev_sessions": [{"kwh_per_percent": .7, "kw_per_amp": .23}],
        "battery": {
            "signature": runtime.stats.battery.signature,
            "cycles": [{"ended": now - 600, "charge_kwh": 5, "discharge_kwh": 4.4}],
            "powers": {"charge": [{"ended": now - 600, "kw": 3.5}],
                       "discharge": [{"ended": now - 600, "kw": 4}]},
        },
        "issued": {str(hour): .5},
        "ledger": {day: {"import_cost": 1.5, "export_credit": .2, "coverage_hours": 1}},
    }
    saved = {
        "statistics": statistics,
        "prices": [{"start": hour, "supply": .06, "fetched_at": now - 600}],
        "solar": {}, "solar_signature": runtime.solar_signature, "delivered": {},
    }
    await runtime.store.async_save(saved)
    assert await hass.config_entries.async_setup(installed.entry_id)
    await hass.async_block_till_done()

    restored = installed.runtime_data
    assert installed.state == ConfigEntryState.LOADED
    assert installed.options == options
    assert restored.config["mode"] == mode
    assert restored.config["ev_control"] is permission
    assert restored.config["battery_control"] is permission
    assert restored.config["battery_learning"] is True
    assert restored.config["comed_price_resilience"] == "Strict live pricing"
    assert restored.config["price_fallback"] == "Existing behavior"
    assert not restored.fallback.manual and not restored.fallback.automatic
    assert restored.comed_continuity == {}
    assert not restored.charge_now and restored.stats.session is None
    assert restored.stats.battery.previous is None and restored.stats.battery.cycle is None
    for key in ("hours", "ev_sessions", "battery", "ledger"):
        assert restored.stats.export()[key] == statistics[key]
    assert restored.stats.issued[str(hour)] == .5
    assert restored.prices == saved["prices"]
    assert restored.data["cost_forecast"]["observed_net_cost"] == 1.3
    assert hass.states.get("sensor.nrg_net_cost_eod") is not None
    assert restored.controller.last == {}
