"""Allowlisted support summary; never export household configuration or plans."""
from .const import VERSION


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = entry.runtime_data
    config = runtime.config
    sources = (runtime.data or {}).get("solar", {}).get("sources", [])
    return {
        "schema_version": 1,
        "integration_version": VERSION,
        "mode": config["mode"] if config["mode"] in ("Observation", "Control") else "unknown",
        "components": {key: bool(config.get("has_" + key)) for key in ("ev", "battery", "solar")},
        "control_enabled": {key: bool(config.get("has_" + key) and config.get(key + "_control")) for key in ("ev", "battery")},
        "source_counts": {"total": len(sources), "ready": sum(bool(s.get("ready")) for s in sources)},
        "statistics_counts": {"house_hours": len(runtime.stats.hours), "ev_sessions": len(runtime.stats.ev_sessions)},
        "plan_available": bool(runtime.plan),
        "current_price_known": bool(runtime.current_price_known),
    }
