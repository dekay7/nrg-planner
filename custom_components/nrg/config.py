"""Configuration and age calculations without Home Assistant dependencies."""
from datetime import date, time
import math
from typing import Any

from .const import DEFAULTS, SETTINGS, CONTROL_VALUES, COMMAND_SCRIPTS, OPTIONAL_RATES

# Accepted only to clean saved options from older releases; never used for planning.
RETIRED_SETTINGS = frozenset({"summer_guard"})


def finite(value: Any, default=None):
    if isinstance(value, bool):
        return default
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (ValueError, TypeError):
        return default


def settings(options: dict) -> dict:
    result = DEFAULTS | {k: v for k, v in options.items() if k in SETTINGS}
    mappings = options.get("mappings", {})
    # Mapped equipment can be monitored; mapping alone never enables commands.
    inferred = {"has_ev": any(k in mappings for k in ("ev_soc", "ev_connected", "ev_power")),
                "has_battery": any(k in mappings for k in ("battery_soc", "battery_power", "battery_mode")),
                 "has_solar": bool(options.get("solar_sources")) or "solar_power" in mappings}
    for key, value in inferred.items():
        if key not in options:
            result[key] = value
    for key in ("supply_periods", "delivery_periods"):
        result[key] = list(options.get(key, []))
    result["control_values"] = CONTROL_VALUES | dict(options.get("control_values", {}))
    result["command_scripts"] = dict(options.get("command_scripts", {}))
    return result


def validate(options: dict, today: date | None = None) -> dict:
    """Reject bad settings rather than silently clamping a user's inputs."""
    result = {key: value for key, value in options.items() if key not in RETIRED_SETTINGS}
    for key, value in result.items():
        if key not in SETTINGS:
            if key not in {"mappings", "solar_sources", "departure_override", "notification_targets", "supply_periods", "delivery_periods", "control_values", "command_scripts"}:
                raise ValueError("Unknown NRG setting: " + key)
            continue
        field = SETTINGS[key]
        if field.kind == "number":
            if key in OPTIONAL_RATES and value is None:
                continue
            number = finite(value)
            if number is None or not field.low <= number <= field.high:
                raise ValueError(f"{field.name} must be between {field.low} and {field.high}")
            result[key] = number
        elif field.kind == "select" and value not in field.choices:
            raise ValueError(f"Unsupported {field.name}")
        elif field.kind == "switch" and not isinstance(value, bool):
            raise ValueError(f"{field.name} must be on or off")
        elif field.kind == "date" and value:
            parsed = date.fromisoformat(value)
            if parsed > (today or date.today()):
                raise ValueError(f"{field.name} cannot be in the future")
            result[key] = parsed.isoformat()
        elif field.kind == "time":
            result[key] = time.fromisoformat(value).isoformat()
        elif field.kind == "text":
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
                raise ValueError(f"{field.name} needs 1–100 characters")
            result[key] = value.strip()
    merged = settings(result)
    if merged["ev_min_amps"] > merged["ev_max_amps"]:
        raise ValueError("Minimum EV current cannot exceed maximum EV current")
    validate_sources(options.get("solar_sources", []))
    from .tariffs import validate_periods
    for key in ("supply_periods", "delivery_periods"):
        validate_periods(options.get(key, []))
    for key, value in options.get("control_values", {}).items():
        if key not in CONTROL_VALUES or not isinstance(value, str) or not value.strip():
            raise ValueError("Control option names must be nonempty device states")
    for key, script in options.get("command_scripts", {}).items():
        if key not in COMMAND_SCRIPTS or not isinstance(script, str) or not script.startswith("script."):
            raise ValueError("Command adapters must select HA script entities")
    return result


def cents_rate(config: dict, key: str):
    """Convert an explicitly configured rate; absence is never an implicit zero."""
    value = finite(config.get(key))
    return value / 100 if value is not None else None


def export_price(config: dict, supply):
    if config["export_rate"] == "No credit":
        return 0.0
    if config["export_rate"] == "Flat credit":
        return cents_rate(config, "flat_export_cents")
    adder = cents_rate(config, "export_adder_cents")
    return supply + adder if supply is not None and adder is not None else None


def age_factor(installed: str | None, annual_percent: float, today: date) -> float:
    if not installed:
        return 1.0
    years = max((today - date.fromisoformat(installed)).days, 0) / 365.2425
    return (1 - annual_percent / 100) ** years


def effective_capacity(config: dict, today: date) -> float:
    return config["battery_capacity"] * age_factor(
        config["battery_install_date"], config["battery_degradation"], today)


def source_scope(source: dict) -> frozenset[str]:
    """Comma-separated physical coverage, e.g. 'south,west' for a combined source."""
    return frozenset(p.strip().casefold() for p in source.get("group", "").split(",") if p.strip())


def validate_sources(sources: list[dict]) -> None:
    entries, scopes = set(), []
    for source in sources:
        if finite(source.get("weight"), 0) <= 0:
            raise ValueError("A solar source needs a finite positive weight")
        entry = source.get("config_entry_id") or source.get("entity_id")
        if entry in entries:
            raise ValueError("This Forecast.Solar entry is already selected; its sensors share one forecast")
        entries.add(entry)
        scope = source_scope(source)
        if not scope:
            raise ValueError("Enter the physical arrays covered by this source")
        if any(scope & previous and scope != previous for previous in scopes):
            raise ValueError("Overlapping forecasts must cover the same arrays to be alternatives")
        scopes.append(scope)
