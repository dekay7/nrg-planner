"""Invented interval data only: no network, HA state or recorded provider feed."""
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
from zoneinfo import ZoneInfo

import pytest

from custom_components.nrg.comed import HourlyPriceCache, parse_five_minute_feed, RECHECK_SECONDS
from conftest import NOW, ZONE

HOUR = int(NOW)


def feed(prices=(2,) * 6 + (10,) * 6, *, start=HOUR):
    return [{"millisUTC": str((start + i * 300) * 1000), "price": str(price)}
            for i, price in enumerate(prices)]


def update(cache, rows=None, *, start=HOUR, end=HOUR + 3300, fetched_at=HOUR + 3600):
    return cache.update(json.dumps(feed() if rows is None else rows), start=start, end=end, fetched_at=fetched_at)


def test_twelve_distinct_intervals_mean_not_consumption_weights_or_averaged_averages():
    cache = HourlyPriceCache()
    update(cache)
    result = cache.hour(HOUR, as_of=HOUR + 3600)
    assert result.supply_usd_per_kwh == Decimal("0.06")
    assert result.state == "complete_public_data"
    assert result.interval_count == 12
    assert result.source == "comed_five_minute_public"
    assert not hasattr(result, "billing_final")
    # An independent energy placement oracle: 1 kWh entirely early or late must
    # cost 6 cents. Pricing consumption at the individual 5-minute rates is wrong.
    for energy in ([Decimal(1)] + [Decimal(0)] * 11,
                   [Decimal(0)] * 11 + [Decimal(1)]):
        assert sum(energy) * result.supply_usd_per_kwh == Decimal(".06")
    # Averaging the twelve successive running averages gives a different answer.
    prices = [Decimal(row["price"]) for row in feed()]
    running_means = [sum(prices[:n]) / n for n in range(1, 13)]
    assert sum(running_means) / 12 / 100 != result.supply_usd_per_kwh


def test_partial_polling_deduplicates_without_averaging_running_averages():
    cache = HourlyPriceCache()
    rows = feed()
    for count in range(1, 13):
        update(cache, rows[:count], end=HOUR + (count - 1) * 300, fetched_at=HOUR + count * 300)
        result = cache.hour(HOUR, as_of=HOUR + count * 300)
        assert result.interval_count == count
        assert result.state == ("complete_public_data" if count == 12 else "provisional")
    assert result.supply_usd_per_kwh == Decimal(".06")


def test_interval_starts_and_inclusive_midnight_endpoint_belong_to_separate_hours():
    start = int(datetime(2026, 10, 19, 23, tzinfo=ZONE).timestamp())
    cache = HourlyPriceCache()
    rows = feed(start=start) + feed([99], start=start + 3600)
    update(cache, rows, start=start, end=start + 3600, fetched_at=start + 3900)
    assert cache.hour(start, as_of=start + 3900).supply_usd_per_kwh == Decimal(".06")
    next_hour = cache.hour(start + 3600, as_of=start + 3900)
    assert next_hour.interval_count == 1
    assert next_hour.supply_usd_per_kwh == Decimal(".99")
    assert next_hour.state == "provisional"
    # A single-label inclusive query is also valid.
    parsed = parse_five_minute_feed(json.dumps(rows[-1:]), start=start + 3600,
                                  end=start + 3600, fetched_at=start + 3900)
    assert parsed[0].start == start + 3600


def test_out_of_order_identical_duplicates_do_not_inflate_completeness_or_revisions():
    cache = HourlyPriceCache()
    rows = feed()
    rows.pop(4)
    random.Random(719).shuffle(rows)
    update(cache, rows + [rows[0]])  # Twelve rows, but only eleven physical intervals.
    before = cache.hour(HOUR, as_of=HOUR + 3600)
    assert before.interval_count == 11 and before.state == "provisional"
    assert update(cache, rows * 2, fetched_at=HOUR + 7200) == frozenset()
    assert cache.hour(HOUR, as_of=HOUR + 7200).revision == before.revision
    assert update(cache, feed()[4:5], fetched_at=HOUR + 7300) == {HOUR}
    assert cache.hour(HOUR, as_of=HOUR + 7300).state == "complete_public_data"


def test_revisions_are_idempotent_newer_wins_and_not_billing_final_after_24_hours():
    cache = HourlyPriceCache()
    update(cache)
    before = cache.hour(HOUR, as_of=HOUR + 3600)
    revised = feed([14], start=HOUR + 3300)
    assert update(cache, revised, fetched_at=HOUR + 25 * 3600) == {HOUR}
    after = cache.hour(HOUR, as_of=HOUR + 25 * 3600)
    assert after.supply_usd_per_kwh == Decimal(".0633333333333333333333333333333333333")
    assert after.revision != before.revision
    assert after.state == "complete_public_data"  # Elapsed time is not settlement proof.
    assert after.last_observed_at == HOUR + 25 * 3600
    assert after.all_observed_since == HOUR + 3600
    assert update(cache, revised, fetched_at=HOUR + 26 * 3600) == frozenset()
    assert update(cache, fetched_at=HOUR + 7200) == frozenset()  # Late older response.
    assert cache.hour(HOUR, as_of=HOUR + 26 * 3600).revision == after.revision


def test_decimal_precision_survives_json_numbers_and_cosmetic_representations():
    cache = HourlyPriceCache()
    # Numeric JSON fields, not just strings, retain decimal text exactly.
    text = '[' + ','.join('{"millisUTC":%d,"price":1.123456789123}' % ((HOUR + i * 300) * 1000)
                          for i in range(12)) + ']'
    cache.update(text, start=HOUR, end=HOUR + 3300, fetched_at=HOUR + 3600)
    result = cache.hour(HOUR, as_of=HOUR + 3600)
    assert result.supply_usd_per_kwh == Decimal(".01123456789123")
    zeros = HourlyPriceCache()
    update(zeros, feed(["0.0"] * 12))
    before = zeros.hour(HOUR, as_of=HOUR + 3600)
    assert update(zeros, feed(["-0.000"] * 12), fetched_at=HOUR + 7200) == frozenset()
    assert zeros.hour(HOUR, as_of=HOUR + 7200).revision == before.revision
    # A caller's decimal context must not round accounting or revision identity.
    with localcontext() as context:
        context.prec = 4
        assert cache.hour(HOUR, as_of=HOUR + 7200) == result
        assert update(cache, feed(["1.123456789123"] * 12), fetched_at=HOUR + 7200) == frozenset()
        assert cache.hour(HOUR, as_of=HOUR + 7200).revision == result.revision


@pytest.mark.parametrize("cents,usd", [(0, "0"), (-5, "-.05"), (-1000, "-10"), (500, "5")])
def test_zero_negative_and_source_boundaries_are_valid(cents, usd):
    cache = HourlyPriceCache()
    update(cache, feed([cents] * 12))
    assert cache.hour(HOUR, as_of=HOUR + 3600).supply_usd_per_kwh == Decimal(usd)


@pytest.mark.parametrize("fault", [
    "object", "null", "html", "truncated", "row_scalar", "missing_price", "missing_time",
    "bool_price", "bool_time", "nan", "infinity", "bad_price", "high", "low", "precision",
    "seconds_not_millis", "fractional_millis", "misaligned", "outside", "usd", "bad_unit", "unit_alias",
    "conflict", "duplicate_key", "too_many", "too_large",
])
def test_invalid_response_is_rejected_atomically_and_preserves_prior_hour(fault):
    cache = HourlyPriceCache()
    update(cache)
    before = cache.hour(HOUR, as_of=HOUR + 7200)
    rows = feed([4] * 12)  # Ensure a rejected response cannot partly apply new data.
    bad = rows[-1]
    special = {"object": "{}", "null": "null", "html": "<html>outage</html>",
               "truncated": '[{"millisUTC":', "too_large": " " * (128 * 1024 + 1),
               "duplicate_key": '[{"millisUTC":"%d","price":"2","price":"3"}]' % (HOUR * 1000)}
    if fault == "row_scalar": rows[-1] = 3
    elif fault == "missing_price": bad.pop("price")
    elif fault == "missing_time": bad.pop("millisUTC")
    elif fault == "bool_price": bad["price"] = True
    elif fault == "bool_time": bad["millisUTC"] = True
    elif fault == "nan": bad["price"] = float("nan")
    elif fault == "infinity": bad["price"] = "Infinity"
    elif fault == "bad_price": bad["price"] = "not a price"
    elif fault == "high": bad["price"] = "500.0001"
    elif fault == "low": bad["price"] = "-1000.0001"
    elif fault == "precision": bad["price"] = "0.0000000000001"
    elif fault == "seconds_not_millis": bad["millisUTC"] = str(HOUR + 3300)
    elif fault == "fractional_millis": bad["millisUTC"] = str((HOUR + 3300) * 1000) + ".1"
    elif fault == "misaligned": bad["millisUTC"] = str((HOUR + 3301) * 1000)
    elif fault == "outside": bad["millisUTC"] = str((HOUR - 300) * 1000)
    elif fault == "usd": bad["unit"] = "USD/kWh"
    elif fault == "bad_unit": bad["unit"] = []
    elif fault == "unit_alias": bad["unit_of_measurement"] = "USD/kWh"
    elif fault == "conflict": rows.append(rows[0] | {"price": "9"})
    elif fault == "too_many": rows *= 100
    with pytest.raises(ValueError):
        cache.update(special.get(fault, json.dumps(rows)), start=HOUR, end=HOUR + 3300,
                     fetched_at=HOUR + 7200)
    assert cache.hour(HOUR, as_of=HOUR + 7200) == before


def test_equal_timestamp_conflict_also_rejects_the_whole_batch():
    cache = HourlyPriceCache()
    update(cache)
    before = cache.hour(HOUR, as_of=HOUR + 3600)
    with pytest.raises(ValueError, match="same fetch time"):
        update(cache, feed([4] * 12))
    assert cache.hour(HOUR, as_of=HOUR + 3600) == before


@pytest.mark.parametrize("bounds", [
    {"start": HOUR + 1}, {"start": True}, {"end": HOUR - 300},
    {"end": HOUR + 48 * 3600 + 300, "fetched_at": HOUR + 49 * 3600},
    {"fetched_at": HOUR + 3000}, {"fetched_at": float("nan")}, {"fetched_at": True},
    {"fetched_at": 10 ** 400},
])
def test_invalid_query_bounds_are_not_guessed(bounds):
    with pytest.raises(ValueError):
        parse_five_minute_feed("[]", **({"start": HOUR, "end": HOUR + 3300,
                                          "fetched_at": HOUR + 3600} | bounds))


def test_empty_feed_expiry_and_clock_rollback_never_invent_prices():
    cache = HourlyPriceCache()
    assert cache.hour(HOUR, as_of=HOUR).state == "unavailable"
    update(cache)
    # Future observations do not leak into an as-of query after clock rollback.
    assert cache.hour(HOUR, as_of=HOUR + 3599).supply_usd_per_kwh is None
    assert update(cache, [], fetched_at=HOUR + 7200) == frozenset()
    assert cache.hour(HOUR, as_of=HOUR + 7200).state == "complete_public_data"
    assert cache.hour(HOUR, as_of=HOUR + 49 * 3600).state == "unavailable"
    cache.prune(HOUR + 49 * 3600)
    assert len(cache) == 0
    update(cache)  # A late old response cannot resurrect pruned intervals.
    assert len(cache) == 0
    with pytest.raises(ValueError, match="physical UTC hour"):
        cache.hour(HOUR + 300, as_of=HOUR + 3600)


def test_all_twelve_rows_before_hour_end_are_still_provisional():
    cache = HourlyPriceCache()
    update(cache, fetched_at=HOUR + 3300)
    assert cache.hour(HOUR, as_of=HOUR + 3599).state == "provisional"
    assert cache.hour(HOUR, as_of=HOUR + 3600).state == "complete_public_data"


@pytest.mark.parametrize("date,hours", [(datetime(2026, 3, 8), 23), (datetime(2026, 11, 1), 25)])
def test_physical_hours_survive_23_and_25_hour_central_days_and_other_display_zones(date, hours):
    start = int(date.replace(tzinfo=ZONE).timestamp())
    end = int((date + timedelta(days=1)).replace(tzinfo=ZONE).timestamp())
    assert (end - start) // 3600 == hours
    cache = HourlyPriceCache()
    rows = feed(range(hours * 12), start=start)
    # Keep invented cents within accepted price bounds on the 25-hour day.
    update(cache, rows, start=start, end=end - 300, fetched_at=end)
    for index in range(hours):
        stamp = start + index * 3600
        result = cache.hour(stamp, as_of=end)
        assert result.interval_count == 12 and result.state == "complete_public_data"
        assert result.supply_usd_per_kwh == Decimal(12 * index + 5.5) / 100
        # HA's display zone does not participate in physical interval identity.
        displayed = datetime.fromtimestamp(stamp, ZoneInfo("Asia/Kolkata"))
        assert int(displayed.timestamp()) == result.start
    repeated = [start + i * 3600 for i in range(hours)
                if datetime.fromtimestamp(start + i * 3600, ZONE).hour == 1]
    assert len(repeated) == (2 if hours == 25 else 1)
    if hours == 25:
        assert cache.hour(repeated[0], as_of=end).revision != cache.hour(repeated[1], as_of=end).revision


def test_rolling_cache_is_bounded_with_inclusive_overlap_and_long_downtime():
    cache = HourlyPriceCache()
    for index in range(72):
        start = HOUR + index * 3600
        update(cache, feed([1] * 13, start=start), start=start, end=start + 3600,
               fetched_at=start + 3600)
        assert len(cache) <= 49 * 12
    assert cache.hour(HOUR, as_of=HOUR + 72 * 3600).state == "unavailable"
    cache.prune(HOUR + 10 * RECHECK_SECONDS)
    assert len(cache) == 0


def test_randomized_hourly_means_match_independent_rational_arithmetic():
    rng = random.Random(62019)
    for _ in range(200):
        microcents = [rng.randrange(-100000000, 50000001) for _ in range(12)]
        rows = feed([Decimal(value).scaleb(-6) for value in microcents])
        rows += [rows[rng.randrange(12)]] * 3
        rng.shuffle(rows)
        cache = HourlyPriceCache()
        update(cache, rows)
        expected = Fraction(sum(microcents), 12 * 100 * 1000000)
        assert float(cache.hour(HOUR, as_of=HOUR + 3600).supply_usd_per_kwh) == pytest.approx(float(expected), abs=1e-15)


def test_foundation_has_no_persistence_api_or_runtime_import():
    import ast
    path = Path(importlib.util.find_spec("custom_components.nrg.comed").origin)
    for name in ("runtime.py", "statistics.py", "forecast.py", "planner.py", "control.py"):
        imports = [node.module for node in ast.walk(ast.parse(path.with_name(name).read_text()))
                   if isinstance(node, ast.ImportFrom)]
        assert "comed" not in imports  # Explicit inactive-stage review boundary.
    assert not hasattr(HourlyPriceCache(), "export")


def test_module_can_load_using_only_the_standard_library_without_ha(tmp_path):
    path = Path(importlib.util.find_spec("custom_components.nrg.comed").origin)
    script = """import importlib.util, sys
spec = importlib.util.spec_from_file_location('standalone_comed', sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert module.HourlyPriceCache().hour(0, as_of=3600).state == 'unavailable'
assert not any(name.startswith('homeassistant') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-B", "-c", script, str(path)], cwd=tmp_path, check=True)
