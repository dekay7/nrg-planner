"""Invented ComEd wall-hour feeds; UTC expectations are independent DST oracles."""
from datetime import datetime, timezone

import pytest

from custom_components.nrg.forecast import parse_comed
from conftest import ZONE


def wall_feed(day, hours=range(24)):
    return " ".join(
        f"Date.UTC({day.year},{day.month - 1},{day.day},{hour},0,0),{hour - 8}"
        for hour in hours
    )


def test_fall_back_keeps_unambiguous_hour_ending_prices():
    now = datetime(2026, 11, 1, 10, 15, tzinfo=ZONE).timestamp()
    rows = parse_comed(wall_feed(datetime(2026, 11, 1)), now)
    # HE 01 has two possible UTC endpoints, so neither candidate is invented.
    # HE 02 is unambiguous: its preceding real hour is the SECOND 01:00.
    first = datetime(2026, 11, 1, 4, tzinfo=timezone.utc).timestamp()
    after_gap = datetime(2026, 11, 1, 7, tzinfo=timezone.utc).timestamp()
    assert [row["start"] for row in rows] == [first] + [after_gap + hour * 3600 for hour in range(22)]
    assert [row["supply"] for row in rows] == pytest.approx([-.08] + [(hour - 8) / 100 for hour in range(2, 24)])
    assert all(row["source"] == "day_ahead" and row["fetched_at"] == now for row in rows)


def test_spring_forward_omits_nonexistent_endpoint_without_shifting_later_prices():
    now = datetime(2026, 3, 8, 10, 15, tzinfo=ZONE).timestamp()
    rows = parse_comed(wall_feed(datetime(2026, 3, 8)), now)
    first = datetime(2026, 3, 8, 5, tzinfo=timezone.utc).timestamp()
    assert [row["start"] for row in rows] == [first + hour * 3600 for hour in range(23)]
    assert [row["supply"] for row in rows] == pytest.approx([(hour - 8) / 100 for hour in range(24) if hour != 2])


@pytest.mark.parametrize("hours", [
    list(range(23)), list(range(24)) + [1],
    [0, 0] + list(range(2, 24)), [0, 1, 1] + list(range(3, 24)),
])
def test_dst_does_not_excuse_partial_or_duplicate_wall_labels(hours):
    now = datetime(2026, 11, 1, 10, 15, tzinfo=ZONE).timestamp()
    with pytest.raises(ValueError):
        parse_comed(wall_feed(datetime(2026, 11, 1), hours), now)


@pytest.mark.parametrize("replacement", [
    "Date.UTC(2026,10,1,1,0,0),501",
    "Date.UTC(2026,10,1,1,30,0),-7",
    "Date.UTC(2026,10,1,1,0,1),-7",
    "Date.UTC(2026,10,2,1,0,0),-7",
])
def test_omitted_dst_label_must_still_have_valid_price_time_and_date(replacement):
    now = datetime(2026, 11, 1, 10, 15, tzinfo=ZONE).timestamp()
    text = wall_feed(datetime(2026, 11, 1)).replace("Date.UTC(2026,10,1,1,0,0),-7", replacement)
    with pytest.raises(ValueError):
        parse_comed(text, now)


def test_fall_back_omissions_do_not_become_control_prices():
    from custom_components.nrg.config import settings
    from custom_components.nrg.forecast import price_at

    now = datetime(2026, 10, 31, 18, tzinfo=ZONE).timestamp()
    rows = parse_comed(wall_feed(datetime(2026, 11, 1)), now)
    config = settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4,
                       "export_rate": "Supply plus adder", "export_adder_cents": 2})
    for utc_hour in (5, 6):
        stamp = datetime(2026, 11, 1, utc_hour, tzinfo=timezone.utc).timestamp()
        missing = price_at(stamp, now, config, rows, None)
        assert missing["supply_price"] is None and not missing["price_known"]
        estimated = price_at(stamp, now, config, rows, None, lambda hour: (.33, 2))
        assert estimated["supply_source"] == "recorded_estimate"
        assert not estimated["price_known"] and not estimated["export_known"]
    second_one = datetime(2026, 11, 1, 7, tzinfo=timezone.utc).timestamp()
    known = price_at(second_one, now, config, rows, None)
    assert known["price_known"] and known["supply_price"] == pytest.approx(-.06)
