"""Dated ComEd and Forecast.Solar adapters. Missing energy is never a zero forecast."""
from datetime import datetime, timedelta
import re
from zoneinfo import ZoneInfo

from .config import age_factor, finite, source_scope, validate_sources, cents_rate, export_price
from .tariffs import period_at, external_at

COMED_ZONE = ZoneInfo("America/Chicago")
COMED_PUBLICATION_SECONDS = 600
COMED_ESTIMATE_SECONDS = 3600
PRICE_PATTERN = re.compile(r"Date\.UTC\((\d{4}),\s*(\d{1,2}),\s*(\d{1,2}),\s*(\d{1,2}),\s*(\d{1,2}),\s*(\d{1,2})\),\s*([+-]?\d+(?:\.\d+)?)")


def comed_estimate_deadline(now: float, config: dict):
    """A fixed deadline, never renewed by a successful fetch of old data."""
    if (config.get("supply_plan") != "Hourly ComEd"
            or config.get("comed_price_resilience") != "Allow brief published estimates"):
        return None
    observed = finite(config.get("_comed_last_live"))
    if observed is None:
        return int(now // 3600) * 3600 + COMED_PUBLICATION_SECONDS
    # A future anchor/clock rollback cannot create an allowance.
    return observed + COMED_ESTIMATE_SECONDS if observed <= now else now


def comed_publication_window(now: float) -> bool:
    """Bound the normal new-hour live publication gap in real elapsed time."""
    return now % 3600 < COMED_PUBLICATION_SECONDS


def parse_comed(text: str, now: float) -> list[dict]:
    """Website Date.UTC fields are CENTRAL HOUR-ENDING labels, not UTC.

    Ambiguous/nonexistent DST labels are rejected, rather than guessed. A valid
    existing cache/live price and locally learned estimates remain available.
    """
    rows = PRICE_PATTERN.findall(text)
    if len(rows) != 24:
        raise ValueError("ComEd did not return 24 complete forecast rows")
    today = datetime.fromtimestamp(now, COMED_ZONE).date()
    result, dates = [], set()
    for row in rows:
        y, m, d, h, minute, second = map(int, row[:6])
        value = finite(row[6])
        end = datetime(y, m + 1, d, h, minute, second, tzinfo=COMED_ZONE)
        if end.replace(fold=0).utcoffset() != end.replace(fold=1).utcoffset():
            raise ValueError("Ambiguous or nonexistent ComEd DST hour label")
        if value is None or not -1000 <= value <= 500 or minute or second:
            raise ValueError("Invalid ComEd price or hour label")
        dates.add(end.date())
        result.append({"start": end.timestamp() - 3600, "supply": value / 100,
                       "source": "day_ahead", "fetched_at": now})
    starts = sorted(r["start"] for r in result)
    if len(dates) != 1 or not dates <= {today, today + timedelta(days=1)} or any(b - a != 3600 for a, b in zip(starts, starts[1:])):
        raise ValueError("Wrong ComEd forecast date or incomplete real-hour coverage")
    return result


def price_at(stamp: float, now: float, config: dict, cache: list[dict], live: float | None,
             prior=None) -> dict:
    zone = config.get("zone", COMED_ZONE)
    if config["supply_plan"] == "Flat supply":
        supply = cents_rate(config, "flat_supply_cents")
        source = "flat" if supply is not None else "missing"
    elif config["supply_plan"] == "Time-of-use supply":
        supply, label = period_at(stamp, config.get("supply_periods", []), zone)
        source = "time_of_use" if supply is not None else "missing"
    elif config["supply_plan"] == "External supply entity":
        supply, source = external_at(stamp, now, live, config.get("_external_supply", []))
    elif int(stamp // 3600) == int(now // 3600) and live is not None:
        supply, source = live, "running_average"
    else:
        row = next((r for r in cache if r["start"] <= stamp < r["start"] + 3600
                    and 0 <= now - r["fetched_at"] <= 36 * 3600), None)
        if row:
            supply, source = row["supply"], "day_ahead"
        else:
            hour = datetime.fromtimestamp(stamp, COMED_ZONE).hour
            supply, count = prior(hour) if prior else (None, 0)
            source = "recorded_estimate" if count and supply is not None else "missing"
    if config["delivery_plan"] == "Flat delivery":
        delivery = cents_rate(config, "delivery_cents")
        delivery_source = "flat" if delivery is not None else "missing"
    elif config["delivery_plan"] == "Time-of-use delivery":
        delivery, delivery_label = period_at(stamp, config.get("delivery_periods", []), zone)
        delivery_source = "time_of_use" if delivery is not None else "missing"
    else:
        delivery, delivery_source = external_at(stamp, now, config.get("_delivery_live"), config.get("_external_delivery", []))
    export = export_price(config, supply)
    current_comed = config["supply_plan"] == "Hourly ComEd" and int(stamp // 3600) == int(now // 3600)
    estimate_until = comed_estimate_deadline(now, config)
    estimate_usable = estimate_until is not None and now <= stamp < estimate_until
    publication_bridge = (current_comed and live is None and source == "day_ahead"
                          and comed_publication_window(now)
                          and (estimate_until is None or estimate_usable))
    estimated = (current_comed and live is None and source == "day_ahead" and estimate_usable)
    current_unknown = current_comed and live is None and not (publication_bridge or estimated)
    known_sources = ("flat", "running_average", "day_ahead", "time_of_use", "external_live", "external_forecast")
    known = not current_unknown and source in known_sources and delivery_source in known_sources
    combined = "missing" if supply is None or delivery is None else source
    if (source in ("flat", "time_of_use") and delivery_source not in ("flat", "time_of_use")
            or source == "flat" and delivery_source == "time_of_use"):
        combined = delivery_source
    return {"supply_price": supply, "delivery_price": delivery,
            "import_price": supply + delivery if supply is not None and delivery is not None else None,
            "export_price": export, "price_source": combined, "supply_source": source,
            "delivery_source": delivery_source, "price_known": known,
            "comed_publication_bridge": publication_bridge, "comed_estimated_price": estimated,
            "comed_estimate_until": estimate_until,
             "export_known": export is not None and (config["export_rate"] != "Supply plus adder" or not current_unknown and source in known_sources),
            "supply_period": label if config["supply_plan"] == "Time-of-use supply" else None,
            "delivery_period": delivery_label if config["delivery_plan"] == "Time-of-use delivery" else None}


def solar_response(response: dict, zone: ZoneInfo, fetched_at: float) -> dict:
    """Normalize the power shape to daily totals, exposing only covered hours.

    Forecast.Solar's service already reads its cache; this causes no extra provider
    polling. Normalizing daily energy avoids assuming ambiguous raw Wh boundaries.
    Partial edge hours remain unknown; only astronomy can establish missing night.
    """
    if (not isinstance(response, dict) or not isinstance(response.get("watts"), dict)
            or not isinstance(response.get("wh_period"), dict)):
        raise ValueError("Solar forecast needs power and energy time-series objects")
    points, totals = [], {}
    for stamp, raw in response.get("watts", {}).items():
        parsed, watts = datetime.fromisoformat(stamp), finite(raw)
        if parsed.tzinfo is None or watts is None or not 0 <= watts <= 250000:
            raise ValueError("Invalid timestamp or power in solar forecast")
        points.append((parsed.timestamp(), watts / 1000))
    for stamp, raw in response.get("wh_period", {}).items():
        parsed, wh = datetime.fromisoformat(stamp), finite(raw)
        if parsed.tzinfo is None or wh is None or wh < 0:
            raise ValueError("Invalid timestamp or energy in solar forecast")
        day = parsed.astimezone(zone).date().isoformat()
        totals[day] = totals.get(day, 0) + wh / 1000
    if len(points) < 2 or not totals:
        raise ValueError("A full time-series forecast, not a daily scalar, is required")
    for day, energy in totals.items():
        start = datetime.fromisoformat(day).replace(tzinfo=zone)
        elapsed_hours = ((start + timedelta(days=1)).timestamp() - start.timestamp()) / 3600
        if not 0 <= energy <= 250 * elapsed_hours:
            raise ValueError("Invalid daily solar energy")
    points.sort()
    if any(a[0] == b[0] for a, b in zip(points, points[1:])):
        raise ValueError("Duplicate solar timestamp")
    pieces = {}

    def integrate(start, end, pa, pb):
        cursor = start
        while cursor < end:
            day = datetime.fromtimestamp(cursor, zone).date()
            midnight = datetime.combine(day + timedelta(days=1), datetime.min.time(), zone).timestamp()
            boundary = min(end, (int(cursor) // 3600 + 1) * 3600, midnight)
            a = pa + (pb - pa) * (cursor - start) / (end - start)
            b = pa + (pb - pa) * (boundary - start) / (end - start)
            key = (int(cursor) // 3600 * 3600, day.isoformat())
            energy, covered = pieces.get(key, (0, 0))
            pieces[key] = (energy + (a + b) / 2 * (boundary - cursor) / 3600,
                           covered + boundary - cursor)
            cursor = boundary

    for (start, pa), (end, pb) in zip(points, points[1:]):
        if end - start > 14400:
            # A zero-ended overnight gap is not a missing daylight shape. A
            # broken daytime shape must not concentrate a daily total elsewhere.
            if pa or pb or datetime.fromtimestamp(start, zone).date() == datetime.fromtimestamp(end, zone).date():
                raise ValueError("Uncovered gap in solar power shape")
            continue
        integrate(start, end, pa, pb)
    shapes = {}
    for (_, day), (energy, _) in pieces.items():
        shapes[day] = shapes.get(day, 0) + energy
    if any(energy > 0 and shapes.get(day, 0) <= 0 for day, energy in totals.items()):
        raise ValueError("Positive daily solar energy has no usable power shape")
    normalized, coverage = {}, {}
    for (stamp, day), (energy, covered) in pieces.items():
        if day not in totals:
            continue
        key = str(stamp)
        normalized[key] = normalized.get(key, 0) + (energy * totals[day] / shapes[day] if shapes[day] > 0 else 0)
        coverage[key] = coverage.get(key, 0) + covered
    # A partial edge hour is not a full known forecast, including in half-hour
    # timezones where a UTC bin straddles two independently normalized days.
    normalized = {key: energy for key, energy in normalized.items() if abs(coverage[key] - 3600) < .001}
    return {"hours": normalized, "days": list(totals), "fetched_at": fetched_at}


def aggregate_solar(sources: list[dict], caches: dict, config: dict, now: float,
                    zone: ZoneInfo, bias: float = 1) -> dict:
    validate_sources(sources)
    groups, health = {}, []
    for source in sources:
        entry = source["config_entry_id"]
        cache = caches.get(entry, {})
        valid = 0 <= now - cache.get("fetched_at", 0) <= 3 * 3600 and bool(cache.get("days"))
        health.append({"name": source.get("label") or source["entity_id"],
                       "entity_id": source["entity_id"], "group": source["group"],
                       "ready": valid, "fetched_at": cache.get("fetched_at"),
                       "error": cache.get("error")})
        groups.setdefault(source_scope(source), []).append((source, cache if valid else None))
    hours, known, partial = {}, {}, {}
    first = int(now // 3600) * 3600
    factor = age_factor(config["solar_install_date"], config["solar_degradation"], datetime.fromtimestamp(now, zone).date())
    for stamp in range(first, first + 49 * 3600, 3600):
        day = datetime.fromtimestamp(stamp, zone).date().isoformat()
        total, all_known = 0.0, bool(groups)
        for alternatives in groups.values():
            usable = [(s, c) for s, c in alternatives if c and day in c["days"] and str(stamp) in c["hours"]]
            if not usable:
                all_known = False
                continue
            # Relative weights avoid overflow even for large finite user inputs.
            scale = max(finite(s["weight"]) for s, _ in usable)
            weights = [(s, c, finite(s["weight"]) / scale) for s, c in usable]
            total += sum(c["hours"][str(stamp)] * weight *
                         (factor if s.get("apply_age", True) else 1) for s, c, weight in weights) / sum(w for _, _, w in weights)
        partial[str(stamp)] = total * bias
        known[str(stamp)] = all_known
        if all_known:
            hours[str(stamp)] = total * bias
    return {"hours": hours, "known": known, "partial": partial, "sources": health,
            "age_factor": factor, "calibration": bias, "groups": len(groups)}


def known_nights(forecast: dict, daylight: list[tuple[float, float]], now: float,
                 coverage_start: float, coverage_end: float) -> dict:
    """Astronomical darkness is known zero even if a provider drops today's data.

    Only complete remaining hour portions outside all daylight intervals are
    filled. Missing daylight/cloud forecasts are never inferred to be zero.
    """
    result = forecast | {k: dict(forecast[k]) for k in ("hours", "known", "partial")}
    for hour in result["known"]:
        start, end = max(float(hour), now), float(hour) + 3600
        if coverage_start <= start < end <= coverage_end and all(end <= rise or start >= setting for rise, setting in daylight):
            result["known"][hour] = True
            result["hours"][hour] = result["partial"][hour] = 0.0
    result["night_basis"] = "HA astronomical sunrise/sunset; missing daylight remains unknown"
    return result
