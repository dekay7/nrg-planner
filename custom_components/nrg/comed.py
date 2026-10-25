"""Pure, read-only ComEd five-minute normalization and hourly reconstruction.

Not connected to runtime, storage, learning or command authorization. Provider
retention permission must be resolved before activating a persisted cache; see
docs/plans/comed-source-verification.md. All rates here are public-data estimates,
never certified utility settlement prices. Timestamps identify interval STARTS.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math

INTERVAL_SECONDS = 300
HOUR_SECONDS = 3600
RECHECK_SECONDS = 48 * HOUR_SECONDS
MAX_RESPONSE_ROWS = RECHECK_SECONDS // INTERVAL_SECONDS + 1  # Inclusive endpoints.
MAX_RESPONSE_BYTES = 128 * 1024
SOURCE = "comed_five_minute_public"
CENTS_UNITS = {"¢/kWh", "c/kWh", "cents/kWh"}


def _number(value) -> Decimal:
    # Decimal JSON decoding avoids rounding the provider's decimal text to float.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)) or len(str(value)) > 64:
        raise ValueError("Invalid ComEd number")
    try:
        result = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid ComEd number") from error
    if not result.is_finite():
        raise ValueError("Non-finite ComEd number")
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate ComEd object field")
        result[key] = value
    return result


def _time(value):
    try:
        valid = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("Invalid ComEd observation time")
    return value


def _boundary(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value % INTERVAL_SECONDS:
        raise ValueError("ComEd boundaries must be aligned UTC epoch seconds")
    return value


@dataclass(frozen=True)
class FiveMinutePrice:
    start: int
    cents_per_kwh: Decimal
    fetched_at: float


@dataclass(frozen=True)
class HourlyPrice:
    start: int
    supply_usd_per_kwh: Decimal | None
    state: str
    interval_count: int
    revision: str | None
    last_observed_at: float | None
    # The oldest observation of the contributing points: not every successful
    # poll necessarily rechecks all twelve intervals.
    all_observed_since: float | None
    source: str = SOURCE


def parse_five_minute_feed(text: str, *, start: int, end: int, fetched_at: float) -> tuple[FiveMinutePrice, ...]:
    """Validate an inclusive UTC-label range, atomically, without timezone guesses.

    The HTTP adapter must translate its Central query bounds separately. A UTC
    timestamp from the response is never reinterpreted as a wall-clock label.
    Identical duplicate rows collapse; conflicting duplicates reject the response
    because ordering within one response does not establish revision precedence.
    Missing intervals remain missing. A response can legitimately be empty.
    """
    start, end, fetched_at = _boundary(start), _boundary(end), _time(fetched_at)
    if not start <= end <= fetched_at or end - start > RECHECK_SECONDS:
        raise ValueError("Invalid or oversized ComEd query range")
    if (not isinstance(text, str) or len(text) > MAX_RESPONSE_BYTES
            or len(text.encode("utf-8")) > MAX_RESPONSE_BYTES):
        raise ValueError("Oversized or invalid ComEd response")
    try:
        rows = json.loads(text, parse_float=Decimal, parse_int=Decimal, object_pairs_hook=_object)
    except (ValueError, TypeError, RecursionError) as error:
        raise ValueError("Invalid ComEd JSON") from error
    if not isinstance(rows, list) or len(rows) > MAX_RESPONSE_ROWS:
        raise ValueError("ComEd response must be a bounded interval list")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not {"millisUTC", "price"} <= row.keys():
            raise ValueError("Invalid ComEd interval object")
        # The documented feed has a fixed cents/kWh contract, not a unit field.
        # If supplied, contradictory units must not silently be divided by 100.
        for key in ("unit", "unit_of_measurement"):
            if key in row and (not isinstance(row[key], str) or row[key] not in CENTS_UNITS):
                raise ValueError("Unexpected ComEd price unit")
        millis, cents = _number(row["millisUTC"]), _number(row["price"])
        if not -1000 <= cents <= 500 or cents.as_tuple().exponent < -12:
            raise ValueError("ComEd price outside supported bounds or precision")
        if (not start * 1000 <= millis <= end * 1000 or millis != millis.to_integral_value()
                or int(millis) % (INTERVAL_SECONDS * 1000)):
            raise ValueError("ComEd timestamp outside query or not interval-aligned")
        stamp = int(millis) // 1000
        point = FiveMinutePrice(stamp, cents, fetched_at)
        if stamp in result and result[stamp].cents_per_kwh != cents:
            raise ValueError("Conflicting duplicate ComEd interval")
        result[stamp] = point
    return tuple(result[key] for key in sorted(result))


class HourlyPriceCache:
    """Bounded in-memory reconstruction, intentionally without Store/export APIs.

    Keeps the preceding 48 physical hours plus the current hour. Later fetches
    may correct individual intervals; older responses cannot overwrite them.
    Revision identity depends on interval content, not row order or poll count.
    No elapsed settlement timer upgrades public data to billing-final/reconciled.
    As-of reads filter retained observations, not a historical revision archive
    suitable for forecast backtests; overwritten older revisions are not retained.
    """

    def __init__(self):
        self._intervals: dict[int, FiveMinutePrice] = {}
        self._latest_seen = 0.0

    def __len__(self):
        return len(self._intervals)

    def update(self, text: str, *, start: int, end: int, fetched_at: float) -> frozenset[int]:
        """Return physical hours with changed price content, not refreshed ages.

        Parse and check ALL conflicts before mutating. Transport/parse failures
        therefore cannot clear previously usable observations.
        """
        points = parse_five_minute_feed(text, start=start, end=end, fetched_at=fetched_at)
        for point in points:
            old = self._intervals.get(point.start)
            if (old and old.fetched_at == point.fetched_at
                    and old.cents_per_kwh != point.cents_per_kwh):
                raise ValueError("Conflicting ComEd observations at the same fetch time")
        changed = set()
        for point in points:
            old = self._intervals.get(point.start)
            if old is not None and old.fetched_at > point.fetched_at:
                continue
            if old is None or old.cents_per_kwh != point.cents_per_kwh:
                changed.add(point.start // HOUR_SECONDS * HOUR_SECONDS)
            self._intervals[point.start] = point
        self.prune(fetched_at)
        retained_hours = {key // HOUR_SECONDS * HOUR_SECONDS for key in self._intervals}
        return frozenset(changed & retained_hours)

    def prune(self, now: float) -> None:
        # Out-of-order responses/clock rollback must not resurrect expired data.
        self._latest_seen = max(self._latest_seen, _time(now))
        cutoff = int(self._latest_seen // HOUR_SECONDS) * HOUR_SECONDS - RECHECK_SECONDS
        self._intervals = {key: point for key, point in self._intervals.items() if key >= cutoff}

    def hour(self, start: int, *, as_of: float) -> HourlyPrice:
        start, as_of = _boundary(start), _time(as_of)
        if start % HOUR_SECONDS:
            raise ValueError("ComEd hour must be aligned to a physical UTC hour")
        cutoff = int(as_of // HOUR_SECONDS) * HOUR_SECONDS - RECHECK_SECONDS
        points = [self._intervals[key] for key in range(start, start + HOUR_SECONDS, INTERVAL_SECONDS)
                  if key in self._intervals and self._intervals[key].fetched_at <= as_of and start >= cutoff]
        if not points:
            return HourlyPrice(start, None, "unavailable", 0, None, None, None)
        # Equal-duration market intervals, NEVER energy weights or running means.
        # Preserve decimal input; use 36 significant digits for recurring division.
        with localcontext() as context:
            context.prec = 36
            supply = sum(p.cents_per_kwh for p in points) / len(points) / 100
            content = ";".join(f"{p.start}:{p.cents_per_kwh.normalize() if p.cents_per_kwh else 0}" for p in points)
        revision = hashlib.sha256(content.encode("ascii")).hexdigest()
        complete = len(points) == 12 and as_of >= start + HOUR_SECONDS
        return HourlyPrice(start, supply, "complete_public_data" if complete else "provisional",
                           len(points), revision, max(p.fetched_at for p in points),
                           min(p.fetched_at for p in points))
