"""Invented dawn/dusk shapes: known darkness may complete, never replace, daylight."""
from datetime import datetime, timedelta
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.nrg.config import settings
from custom_components.nrg.forecast import aggregate_solar, known_nights, solar_response
from custom_components.nrg.planner import plan
from custom_components.nrg.runtime import NRGRuntime
from custom_components.nrg.statistics import Statistics, forecast_net_cost
from conftest import ZONE
from test_forecasts import source


def scenario(zone=ZONE, day="2026-10-20", start="07:15", end="17:45"):
    date = datetime.fromisoformat(day).date()
    def stamp(clock):
        return datetime.combine(date, datetime.strptime(clock, "%H:%M").time(), zone)
    first, last = stamp(start), stamp(end)
    points = [first] + [stamp(f"{hour:02}:00") for hour in range(8, 18)] + [last]
    raw = {"watts": {point.isoformat(): 0 if point in (first, last) else 500 for point in points},
           "wh_period": {last.isoformat(): 5000}}
    daylight = {day: (stamp("07:15").timestamp(), stamp("17:45").timestamp())}
    now = stamp("02:00").timestamp()
    return raw, daylight, now


def test_astronomy_recovers_dawn_and_dusk_energy_without_scaling_partial_hours():
    raw, daylight, now = scenario()
    without = solar_response(raw, ZONE, now)
    result = solar_response(raw, ZONE, now, daylight)
    rise, setting = next(iter(daylight.values()))
    dawn, dusk = str(int(rise // 3600) * 3600), str(int(setting // 3600) * 3600)
    assert dawn not in without["hours"] and dusk not in without["hours"]
    assert dawn in result["hours"] and dusk in result["hours"]
    assert 0 < result["hours"][dawn] < result["hours"][str(int(dawn) + 3600)]
    assert sum(result["hours"].values()) == pytest.approx(5)
    assert result["hours"][str(int(dawn) + 3600)] == without["hours"][str(int(dawn) + 3600)]
    assert solar_response(raw, ZONE, now, daylight) == result  # Deterministic, no input mutation.


@pytest.mark.parametrize("zone_name,day", [
    ("Asia/Kolkata", "2026-10-20"), ("Asia/Kathmandu", "2026-10-20"),
    ("Australia/Lord_Howe", "2026-10-04"), ("America/Chicago", "2026-03-08"),
    ("America/Chicago", "2026-11-01"),
])
def test_edge_completion_conserves_daily_energy_in_fractional_zones_and_dst(zone_name, day):
    zone = ZoneInfo(zone_name)
    raw, daylight, now = scenario(zone, day)
    result = solar_response(raw, zone, now, daylight)
    rise, setting = daylight[day]
    expected = {str(hour) for hour in range(int(rise // 3600) * 3600, math.ceil(setting / 3600) * 3600, 3600)}
    assert set(result["hours"]) == expected
    assert sum(result["hours"].values()) == pytest.approx(5)


@pytest.mark.parametrize("edge", ["dawn", "dusk"])
def test_zero_endpoint_during_daylight_cannot_complete_missing_daylight(edge):
    raw, daylight, now = scenario(start="07:30" if edge == "dawn" else "07:15",
                                   end="17:30" if edge == "dusk" else "17:45")
    result = solar_response(raw, ZONE, now, daylight)
    rise, setting = next(iter(daylight.values()))
    missing = rise if edge == "dawn" else setting
    assert str(int(missing // 3600) * 3600) not in result["hours"]
    covered = setting if edge == "dawn" else rise
    assert str(int(covered // 3600) * 3600) in result["hours"]


@pytest.mark.parametrize("events", [None, {}, {"2026-10-21": (0, 1)},
                                    {"2026-10-20": (float("nan"), float("inf"))},
                                    {"2026-10-20": (1, 0)}])
def test_missing_wrong_day_or_invalid_sun_events_leave_partial_edges_unknown(events):
    raw, _, now = scenario()
    assert solar_response(raw, ZONE, now, events)["hours"] == solar_response(raw, ZONE, now)["hours"]


def test_darkness_overlap_with_provider_samples_is_merged_not_double_counted():
    raw, daylight, now = scenario()
    raw["watts"]["2026-10-20T06:00:00-05:00"] = 0
    raw["watts"]["2026-10-20T19:00:00-05:00"] = 0
    original = solar_response(raw, ZONE, now)
    result = solar_response(raw, ZONE, now, daylight)
    assert result["hours"] == original["hours"]
    assert sum(result["hours"].values()) == pytest.approx(5)


def test_astronomy_cannot_cover_a_missing_midday_shape_or_partial_midday_edges():
    raw, daylight, now = scenario()
    midday = {stamp: value for stamp, value in raw["watts"].items()
              if datetime.fromisoformat(stamp).hour in (10, 11, 12)}
    midday["2026-10-20T10:15:00-05:00"] = midday.pop("2026-10-20T10:00:00-05:00")
    midday["2026-10-20T12:15:00-05:00"] = midday.pop("2026-10-20T12:00:00-05:00")
    partial = solar_response(raw | {"watts": midday}, ZONE, now, daylight)
    assert {datetime.fromtimestamp(int(hour), ZONE).hour for hour in partial["hours"]} == {11}
    broken = {stamp: value for stamp, value in raw["watts"].items()
              if not 9 <= datetime.fromisoformat(stamp).hour <= 15}
    with pytest.raises(ValueError, match="gap"):
        solar_response(raw | {"watts": broken}, ZONE, now, daylight)


def test_each_physical_array_needs_covered_edges_but_alternatives_can_fill_them():
    raw, daylight, now = scenario()
    broken, _, _ = scenario(start="07:30")
    caches = {"a": solar_response(raw, ZONE, now, daylight),
              "b": solar_response(broken, ZONE, now, daylight)}
    dawn = str(int(next(iter(daylight.values()))[0] // 3600) * 3600)
    result = aggregate_solar([source("a", "south"), source("b", "west")], caches, settings({}), now, ZONE)
    assert not result["known"][dawn] and dawn not in result["hours"]
    result = aggregate_solar([source("a", "roof"), source("b", "roof")], caches, settings({}), now, ZONE)
    assert result["known"][dawn]
    assert result["hours"][dawn] == caches["a"]["hours"][dawn]
    result = aggregate_solar([source("a", "roof")], caches, settings({}), now + 10801, ZONE)
    assert not result["known"][dawn]  # Completion never extends cache freshness.


@pytest.mark.parametrize("missing_daylight", [False, True])
def test_end_of_day_forecast_recovers_normal_sun_edges_but_rejects_missing_daylight(missing_daylight):
    raw, daylight, now = scenario(start="07:30" if missing_daylight else "07:15")
    config = settings({"has_solar": True, "has_ev": False, "has_battery": False,
                       "supply_plan": "Flat supply", "flat_supply_cents": 10, "delivery_cents": 0,
                       "house_kw": 2})
    cache = {"a": solar_response(raw, ZONE, now, daylight)}
    solar = aggregate_solar([source("a", "roof")], cache, config, now, ZONE)
    date = datetime.fromtimestamp(now, ZONE).date()
    first = datetime.combine(date, datetime.min.time(), ZONE).timestamp()
    last = datetime.combine(date + timedelta(days=1), datetime.min.time(), ZONE).timestamp()
    solar = known_nights(solar, list(daylight.values()), now, first, last)
    planned = plan(now, config, ZONE, {}, Statistics(), [], solar)
    result = forecast_net_cost(now, ZONE, {"coverage_hours": 2, "import_cost": .4, "export_credit": 0}, planned)
    if missing_daylight:
        assert result["net_cost"] is None
        assert result["missing_forecast_inputs"] == ["solar forecast"]
        assert "07:00" in result["reason"]
    else:
        # Independent oracle: 24h * 2kW - 5kWh solar, all at $0.10/kWh.
        assert result["net_cost"] == pytest.approx((24 * 2 - 5) * .1)
        assert result["status"] == "ready"
        assert result["forecast_until"] == last


@pytest.mark.parametrize("events", ["normal", "missing", "reversed"])
async def test_runtime_supplies_astronomy_to_the_existing_single_cached_service_read(events):
    raw, daylight, now = scenario()
    services = SimpleNamespace(async_call=AsyncMock(return_value=raw))
    runtime = SimpleNamespace(config=settings({"has_solar": True, "supply_plan": "Flat supply"}),
        entry=SimpleNamespace(options={"solar_sources": [source("a", "roof")]}),
        hass=SimpleNamespace(services=services, states=SimpleNamespace(get=lambda entity: SimpleNamespace(state="0"))),
        zone=ZONE, solar_caches={}, last_fetch=0)
    runtime.solar_daylight = lambda stamp: NRGRuntime.solar_daylight(runtime, stamp)
    def event(hass, kind, date):
        if events == "missing":
            return None
        clock = "07:15" if (kind == "sunrise") == (events != "reversed") else "17:45"
        return datetime.combine(date, datetime.strptime(clock, "%H:%M").time(), ZONE)
    with patch("custom_components.nrg.runtime.time.time", return_value=now), \
            patch("custom_components.nrg.runtime.get_astral_event_date", side_effect=event):
        await NRGRuntime.refresh_forecasts(runtime)
    dawn = str(int(next(iter(daylight.values()))[0] // 3600) * 3600)
    assert (dawn in runtime.solar_caches["a"]["hours"]) is (events == "normal")
    assert services.async_call.await_count == 1
    assert services.async_call.await_args.args[2] == {"config_entry": "a", "resolution": "raw"}
    assert runtime.last_fetch == now
