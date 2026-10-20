"""Independent utility-agnostic supply/delivery schedules and external intervals."""
from datetime import datetime, timedelta, time

from .config import finite
from .const import WEEKDAYS

WEEK = 7 * 86400


def seconds(value):
    parsed = time.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError("Pricing-period times use the configured home timezone")
    return parsed.hour * 3600 + parsed.minute * 60 + parsed.second


def week_intervals(periods):
    """Overnight periods belong to the weekday on which they start."""
    result = []
    for index, row in enumerate(periods):
        start, end = seconds(row["start"]), seconds(row["end"])
        length = (end - start) % 86400 or 86400
        for day in row.get("days", WEEKDAYS):
            a = WEEKDAYS.index(day) * 86400 + start
            b = a + length
            result.append((a, min(b, WEEK), index))
            if b > WEEK:
                result.append((0, b - WEEK, index))
    return sorted(result)


def validate_periods(periods):
    if not isinstance(periods, list) or len(periods) > 80:
        raise ValueError("A pricing schedule must be a list of at most 80 periods")
    for row in periods:
        if not isinstance(row, dict) or not str(row.get("label", "")).strip():
            raise ValueError("Each pricing period needs a name")
        try:
            seconds(row["start"]); seconds(row["end"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Each pricing period needs valid start/end times") from error
        rate = finite(row.get("rate_cents"))
        if row.get("rate_cents") is not None and (rate is None or not -1000 <= rate <= 1000):
            raise ValueError("Period rates must be finite cents/kWh between −1000 and 1000")
        days = row.get("days", list(WEEKDAYS))
        if not isinstance(days, (list, tuple)) or not days or len(set(days)) != len(days) or any(d not in WEEKDAYS for d in days):
            raise ValueError("Choose valid, distinct weekdays for each period")
    intervals = week_intervals(periods)
    for previous, current in zip(intervals, intervals[1:]):
        if current[0] < previous[1]:
            raise ValueError("Pricing periods overlap. Each instant must have at most one rate.")


def schedule_complete(periods):
    rows = week_intervals(periods)
    return (bool(rows) and rows[0][0] == 0 and rows[-1][1] == WEEK
            and all(a[1] == b[0] for a, b in zip(rows, rows[1:]))
            and all(finite(row.get("rate_cents")) is not None for row in periods))


def period_at(stamp, periods, zone):
    local = datetime.fromtimestamp(stamp, zone)
    point = local.weekday() * 86400 + local.hour * 3600 + local.minute * 60 + local.second
    match = next((periods[i] for a, b, i in week_intervals(periods) if a <= point < b), None)
    return (finite(match.get("rate_cents")) / 100 if finite(match.get("rate_cents")) is not None else None, match["label"]) if match else (None, None)


def boundaries(now, end, config, zone):
    """Include exact non-quarter-hour tariff changes, with real elapsed DST time."""
    result = set()
    first = datetime.fromtimestamp(now, zone).date() - timedelta(days=1)
    periods = []
    if config["supply_plan"] == "Time-of-use supply":
        periods += config.get("supply_periods", [])
    if config["delivery_plan"] == "Time-of-use delivery":
        periods += config.get("delivery_periods", [])
    for offset in range(5):
        day = first + timedelta(days=offset)
        for period in periods:
            if WEEKDAYS[day.weekday()] not in period.get("days", WEEKDAYS):
                continue
            a = datetime.combine(day, time.fromisoformat(period["start"]), zone)
            # This is a wall-clock boundary; each interval is still integrated in UTC.
            b = datetime.combine(day + timedelta(days=1 if seconds(period["end"]) <= seconds(period["start"]) else 0), time.fromisoformat(period["end"]), zone)
            for stamp in (a.timestamp(), b.timestamp()):
                if now < stamp < end:
                    result.add(stamp)
    for key in ("_external_supply", "_external_delivery"):
        for row in config.get(key, []):
            result.update(t for t in (row["start"], row["end"]) if now < t < end)
    return result


def usd_price(value, unit):
    value = finite(value)
    if value is None:
        return None
    if unit in ("¢/kWh", "c/kWh", "cents/kWh"):
        value /= 100
    elif unit not in ("USD/kWh", "$/kWh"):
        return None
    return value if -10 <= value <= 10 else None


def external_intervals(raw, unit):
    """Read explicit dated intervals; recognize common HA provider field aliases.

    No guesses about timestamps, missing end times, unit conversion or overlaps.
    """
    if not isinstance(raw, list):
        return []
    result = []
    for row in raw:
        if not isinstance(row, dict):
            raise ValueError("Price forecast must contain interval objects")
        start = row.get("start", row.get("valid_from", row.get("start_time")))
        end = row.get("end", row.get("valid_to", row.get("end_time")))
        price = row.get("price", row.get("value_inc_vat", row.get("value", row.get("per_kwh"))))
        try:
            a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
        except (ValueError, TypeError) as error:
            raise ValueError("External forecast intervals need ISO start/end timestamps") from error
        value = usd_price(price, row.get("unit", row.get("unit_of_measurement", unit)))
        if a.tzinfo is None or b.tzinfo is None or a >= b or value is None:
            raise ValueError("External price intervals need timezones, increasing times and explicit recognized units")
        result.append({"start": a.timestamp(), "end": b.timestamp(), "price": value})
    result.sort(key=lambda r: r["start"])
    if any(a["end"] > b["start"] for a, b in zip(result, result[1:])):
        raise ValueError("External price forecast intervals overlap")
    return result


def external_at(stamp, now, live, rows):
    # A current sensor is one observation, not a forecast for the rest of an hour.
    if abs(stamp - now) < .001 and live is not None:
        return live, "external_live"
    row = next((row for row in rows if row["start"] <= stamp < row["end"]), None)
    return (row["price"], "external_forecast") if row else (None, "missing")
