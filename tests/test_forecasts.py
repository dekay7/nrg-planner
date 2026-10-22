from datetime import date, datetime
import json

import pytest

from custom_components.nrg.config import age_factor, effective_capacity, settings, validate, validate_sources
from custom_components.nrg.forecast import aggregate_solar, parse_comed, price_at, solar_response, known_nights
from conftest import NOW, ZONE


def response(kwh=1):
    return {"watts": {"2026-10-20T11:00:00-05:00": 0, "2026-10-20T12:00:00-05:00": kwh * 1000, "2026-10-20T13:00:00-05:00": 0},
            "wh_period": {"2026-10-20T12:00:00-05:00": kwh * 1000}}


def source(entry, group, weight=1):
    return {"config_entry_id": entry, "entity_id": "sensor." + entry, "group": group, "weight": weight, "apply_age": True}


def test_import_flat_works_without_comed_and_negative_supply_is_not_free_import():
    flat = price_at(NOW, NOW, settings({"supply_plan": "Flat supply", "flat_supply_cents": 10, "delivery_cents": 6}), [], None)
    assert flat["import_price"] == .16
    assert flat["price_source"] == "flat"
    hourly = price_at(NOW, NOW, settings({"supply_plan":"Hourly ComEd", "delivery_cents": 6}), [], -.02)
    assert hourly["import_price"] == pytest.approx(.04)


@pytest.mark.parametrize("basis, expected", [("Flat credit", .03), ("No credit", 0), ("Supply plus adder", .07)])
def test_export_is_independent_of_import_delivery(basis, expected):
    price = price_at(NOW, NOW, settings({"supply_plan":"Hourly ComEd", "export_rate": basis, "flat_export_cents": 3, "export_adder_cents": 5, "delivery_cents": 19}), [], .02)
    assert price["export_price"] == pytest.approx(expected)


def test_comed_hour_ending_dates_and_cache_age():
    text = " ".join(f"Date.UTC(2026,9,20,{h},0,0),{h}" for h in range(24))
    rows = parse_comed(text, NOW)
    assert datetime.fromtimestamp(rows[0]["start"], ZONE).hour == 23
    assert datetime.fromtimestamp(rows[0]["start"], ZONE).day == 19
    assert rows[3]["supply"] == .03
    old = [{"start": NOW + 3600, "supply": 8, "fetched_at": NOW - 37 * 3600}]
    result = price_at(NOW + 3600, NOW, settings({"supply_plan":"Hourly ComEd"}), old, None)
    assert result["price_source"] == "missing" and result["supply_price"] is None


def test_current_day_ahead_outlook_does_not_replace_missing_live_price_after_publication_window():
    rows = [{"start": NOW, "supply": .02, "fetched_at": NOW}]
    result = price_at(NOW + 600, NOW + 600, settings({"supply_plan":"Hourly ComEd", "delivery_cents": 4}), rows, None)
    assert result["price_source"] == "day_ahead"
    assert result["price_known"] is False
    assert not result["comed_publication_bridge"]


@pytest.mark.parametrize("offset,bridge", [(0, True), (300, True), (599.99, True), (600, False), (900, False)])
def test_comed_publication_bridge_is_bounded_and_explicit(offset, bridge):
    rows = [{"start": NOW, "supply": -.02, "fetched_at": NOW - 3600}]
    config = settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4,
                       "export_rate": "Supply plus adder", "export_adder_cents": 1})
    result = price_at(NOW + offset, NOW + offset, config, rows, None)
    assert result["comed_publication_bridge"] is bridge
    assert result["price_known"] is bridge
    assert result["export_known"] is bridge
    assert result["supply_source"] == "day_ahead"  # Never relabel a forecast as live.
    assert result["import_price"] == pytest.approx(.02)


@pytest.mark.parametrize("rows", [[], [{"start": NOW - 3600, "supply": .02, "fetched_at": NOW}],
                                  [{"start": NOW, "supply": .02, "fetched_at": NOW - 36 * 3600 - 1}],
                                  [{"start": NOW, "supply": .02, "fetched_at": NOW + 1}]])
def test_comed_publication_bridge_requires_a_valid_published_current_hour(rows):
    result = price_at(NOW, NOW, settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4}),
                      rows, None, lambda hour: (.05, 10))
    assert not result["comed_publication_bridge"]
    assert not result["price_known"]  # Learned estimates cannot bridge a missing publication.


@pytest.mark.parametrize("hour", [datetime(2026, 3, 8, 3, tzinfo=ZONE),
                                 datetime(2026, 11, 1, 1, tzinfo=ZONE, fold=0),
                                 datetime(2026, 11, 1, 1, tzinfo=ZONE, fold=1)])
def test_comed_publication_window_uses_real_hours_across_dst(hour):
    start = hour.timestamp()
    config = settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4})
    rows = [{"start": start, "supply": .03, "fetched_at": start - 3600}]
    for offset, bridge in ((0, True), (599.99, True), (600, False)):
        result = price_at(start + offset, start + offset, config, rows, None)
        assert result["comed_publication_bridge"] is bridge
        assert result["price_known"] is bridge
    previous_hour = [{"start": start - 3600, "supply": .03, "fetched_at": start - 3600}]
    assert not price_at(start, start, config, previous_hour, None)["comed_publication_bridge"]


def test_current_comed_live_price_takes_priority_over_publication_bridge():
    result = price_at(NOW, NOW, settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4}),
                      [{"start": NOW, "supply": .02, "fetched_at": NOW}], .07)
    assert result["supply_source"] == "running_average"
    assert result["supply_price"] == .07
    assert result["price_known"] and not result["comed_publication_bridge"]


def test_comed_rejects_partial_wrong_date_and_ambiguous_dst():
    for text in ("", " ".join(f"Date.UTC(2026,9,28,{h},0,0),4" for h in range(24))):
        with pytest.raises(ValueError):
            parse_comed(text, NOW)
    text = " ".join(f"Date.UTC(2026,10,1,{h},0,0),4" for h in range(24))
    with pytest.raises(ValueError, match="DST"):
        parse_comed(text, datetime(2026, 10, 31, 18, tzinfo=ZONE).timestamp())


def test_age_is_compounded_fractional_and_does_not_double_apply():
    today = date(2026, 10, 19)
    factor = age_factor("2025-10-19", 2, today)
    assert factor == pytest.approx(.98, abs=.0001)
    assert age_factor(None, 2, today) == 1
    assert effective_capacity(settings({"battery_capacity": 12, "battery_install_date": "2025-10-19"}), today) == pytest.approx(12 * .98, abs=.002)
    with pytest.raises(ValueError):
        validate({"solar_install_date": "2027-01-01"}, today)
    with pytest.raises(ValueError):
        validate({"ev_min_amps": 12, "ev_max_amps": 6})


def test_distinct_arrays_sum_alternatives_average_and_duplicates_reject():
    sources = [source("a", "south"), source("b", "south", 3), source("c", "west")]
    caches = {key: solar_response(response(value), ZONE, NOW) for key, value in (("a", 1), ("b", 2), ("c", 3))}
    result = aggregate_solar(sources, caches, settings({}), NOW, ZONE)
    assert sum(result["hours"].values()) == pytest.approx(4.75)
    assert result["groups"] == 2
    with pytest.raises(ValueError, match="already selected"):
        validate_sources([source("a", "south"), source("a", "west")])
    with pytest.raises(ValueError, match="Overlapping"):
        validate_sources([source("a", "south,west"), source("b", "south")])


def test_failed_array_is_unknown_but_alternative_can_cover_same_array():
    sources = [source("a", "south"), source("b", "west")]
    cache = {"a": solar_response(response(), ZONE, NOW)}
    result = aggregate_solar(sources, cache, settings({}), NOW, ZONE)
    assert not result["hours"]
    assert any(v > 0 for v in result["partial"].values())
    result = aggregate_solar([source("a", "south"), source("b", "south")], cache, settings({}), NOW, ZONE)
    assert sum(result["hours"].values()) == pytest.approx(1)
    result = aggregate_solar([source("a", "south")], cache, settings({}), NOW + 4 * 3600, ZONE)
    assert not result["hours"]


def test_source_age_toggle_and_unknown_days():
    config = settings({"solar_install_date": "2020-10-19", "solar_degradation": .7})
    cache = {"a": solar_response(response(), ZONE, NOW)}
    a = source("a", "south")
    aged = aggregate_solar([a], cache, config, NOW, ZONE)
    assert sum(aged["hours"].values()) < 1
    a["apply_age"] = False
    unaged = aggregate_solar([a], cache, config, NOW, ZONE)
    assert sum(unaged["hours"].values()) == pytest.approx(1)
    assert unaged["known"][str(int(NOW))] is False
    assert json.loads(json.dumps(unaged)) == unaged


def test_known_darkness_fills_night_not_missing_daylight_forecasts():
    first = int(NOW)
    empty = {"hours": {}, "partial": {}, "known": {str(first + i * 3600): False for i in range(24)}}
    sunrise, sunset = first + 13 * 3600, first + 24 * 3600
    result = known_nights(empty, [(first - 11 * 3600, first), (sunrise, sunset)], NOW, first, sunset)
    assert result["known"][str(first + 3600)] is True
    assert result["hours"][str(first + 3600)] == 0
    assert result["known"][str(first + 14 * 3600)] is False
    assert str(first + 14 * 3600) not in result["hours"]
