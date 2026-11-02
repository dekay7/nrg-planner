"""Release metadata and restoration of invented previous-release HA stores."""
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


async def test_fresh_release_setup_keeps_conservative_defaults(installed):
    runtime = installed.runtime_data
    assert runtime.config["mode"] == "Observation"
    for key in ("ev_control", "battery_control", "notifications", "fallback_notifications", "battery_learning"):
        assert runtime.config[key] is False
    assert runtime.config["comed_price_resilience"] == "Strict live pricing"
    assert runtime.config["price_fallback"] == "Existing behavior"
    assert runtime.controller.last == {}


@pytest.mark.parametrize("store_version", ["0.2.0", "0.3.0"])
@pytest.mark.parametrize("mode,permission", [("Observation", False), ("Control", True)])
async def test_upgrade_restores_previous_store_settings_learning_and_ledger(hass, installed, mode, permission, store_version):
    runtime = installed.runtime_data
    previous_release = store_version == "0.3.0"
    departure = (datetime.now(runtime.zone) + timedelta(days=3)).isoformat()
    previous_options = {
        "supply_plan": "Hourly ComEd", "price_fallback": "Custom fallback",
        "comed_price_resilience": "Allow brief published estimates",
        "fallback_ev": "Maintain departure readiness", "fallback_battery": "Self-consumption",
    } if previous_release else {}
    await runtime.update_options({
        "mode": mode, "has_ev": True, "has_battery": True, "has_solar": False,
        "ev_control": permission, "battery_control": permission, "battery_learning": True,
        "battery_capacity": 17, "round_trip_efficiency": 91, "ev_kwh_per_percent": .65,
        "departure_override": departure,
        "mappings": {"ev_soc": "sensor.example_ev_soc", "battery_soc": "sensor.example_battery_soc",
                     **({"live_supply": "sensor.example_supply"} if previous_release else {})},
        **previous_options,
    })
    await hass.async_block_till_done()
    options = dict(installed.options)
    assert await hass.config_entries.async_unload(installed.entry_id)

    # v0.2.0 has no fallback/ComEd-continuity keys or estimated-cost subsets.
    # v0.3.0 adds those without changing the storage version. Keep samples recent.
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
    if previous_release:
        statistics["ledger"][day].update({
            "estimated_coverage_hours": .5, "estimated_import_cost": .6, "estimated_export_credit": .1,
        })
        saved.update({
            "manual_fallback": True, "automatic_fallback": True,
            "comed_continuity": {"source": "sensor.example_supply", "last_live": now - 1800},
            "delivered": {"notify.example": "invented-notification-key"},
        })
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
    assert restored.config["comed_price_resilience"] == ("Allow brief published estimates" if previous_release else "Strict live pricing")
    assert restored.config["price_fallback"] == ("Custom fallback" if previous_release else "Existing behavior")
    assert restored.fallback.manual is previous_release
    assert restored.fallback.automatic is previous_release
    assert restored.comed_continuity == saved.get("comed_continuity", {})
    assert restored.delivered == saved["delivered"]
    for key, value in previous_options.items():
        assert restored.config[key] == value
    assert not restored.charge_now and restored.stats.session is None
    assert restored.stats.battery.previous is None and restored.stats.battery.cycle is None
    for key in ("hours", "ev_sessions", "battery", "ledger"):
        assert restored.stats.export()[key] == statistics[key]
    assert restored.stats.issued[str(hour)] == .5
    assert restored.prices == saved["prices"]
    assert restored.data["cost_forecast"]["observed_net_cost"] == 1.3
    assert hass.states.get("sensor.nrg_net_cost_eod") is not None
    hourly = hass.states.get("sensor.nrg_plan").attributes["hourly"]
    assert isinstance(hourly["rows"], list)
    assert hourly["timezone"] == str(restored.zone)
    assert restored.controller.last == {}
