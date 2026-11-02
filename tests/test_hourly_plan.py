"""Independent invented energy/time oracles for the read-only dashboard projection."""
from copy import deepcopy
from datetime import datetime
import json
from zoneinfo import ZoneInfo

import pytest

from conftest import NOW, ZONE, fixture
from custom_components.nrg.hourly import FLOWS, hourly_plan
from custom_components.nrg.planner import plan, transition


def invented(start=NOW, hours=48, **components):
    rows = []
    for i in range(hours * 4):
        a = start + i * 900
        rows.append({"start": a, "end": a + 900, "house_kwh": .25, "solar_kwh": 0,
                     "solar_known": True, "import_kwh": .25, "export_kwh": 0,
                     "solar_charge_kwh": 0, "grid_charge_kwh": 0, "battery_discharge_kwh": 0,
                     "curtailed_kwh": 0, "ev_kwh": 0, "ev_amps": 0, "ev_stop_at": None,
                     "battery_action": "hold", "battery_soc": 60})
    return {"generated_at": start, "expires_at": start + 420, "slots": rows,
            "economic_until": start + 48 * 3600, "battery_initial_soc": 60,
            "battery_forecast_available": True, "ev_forecast_available": True,
            "components": {"solar": False, "battery": False, "ev": False, **components}}


def balanced(row):
    assert row["import_kwh"] + row["solar_kwh"] + row["battery_discharge_kwh"] == pytest.approx(
        row["house_kwh"] + row["ev_kwh"] + row["battery_charge_kwh"] + row["export_kwh"] + row["curtailed_kwh"])


def test_read_only_clipped_grid_only_projection_and_bounded_payload():
    source = invented()
    before = deepcopy(source)
    result = hourly_plan(source, ZONE, NOW + 300)
    assert source == before
    assert result["status"] == "ready"
    assert len(result["rows"]) == 25
    assert result["rows"][0]["minutes"] == 55
    assert result["rows"][0]["import_kwh"] == pytest.approx(55 / 60)
    assert result["rows"][-1]["minutes"] == 5
    assert sum(r["import_kwh"] for r in result["rows"]) == pytest.approx(24)
    for row in result["rows"]:
        balanced(row)
        assert row["battery_soc"] is None
    assert len(json.dumps(result)) < 40000
    assert hourly_plan(source, ZONE, NOW + 420)["rows"] == []


@pytest.mark.parametrize("flows, action", [
    ({"solar_kwh": 3, "solar_charge_kwh": 1, "export_kwh": 1}, "hold"),
    ({"solar_kwh": 3, "curtailed_kwh": 2}, "hold"),
    ({"solar_kwh": 3, "ev_kwh": 2}, "hold"),
    ({"import_kwh": 1, "solar_kwh": 2, "solar_charge_kwh": 1, "grid_charge_kwh": 1}, "charge"),
    ({"import_kwh": .4, "solar_kwh": .2, "battery_discharge_kwh": .4}, "serve"),
])
def test_independent_ac_balance_for_solar_storage_exports_curtailment_and_ev(flows, action):
    source = invented(solar=True, battery=True, ev=True)
    for i, slot in enumerate(source["slots"][:4]):
        slot.update({key: 0 for key in FLOWS})
        slot.update({key: value / 4 for key, value in ({"house_kwh": 1} | flows).items()})
        slot["battery_action"] = action
        delta = flows.get("solar_charge_kwh", 0) + flows.get("grid_charge_kwh", 0) - flows.get("battery_discharge_kwh", 0)
        slot["battery_soc"] = 60 + delta * 10 * (i + 1) / 4
    row = hourly_plan(source, ZONE, NOW)["rows"][0]
    assert row["complete"]
    for key, value in flows.items():
        assert row[key] == pytest.approx(value)
    balanced(row)
    assert row["periods"][0]["battery"] == action


def test_charge_discharge_and_import_export_are_not_netted_and_soc_is_endpoint():
    source = invented(battery=True, solar=True)
    first, second = source["slots"][:2]
    first.update(import_kwh=1.25, grid_charge_kwh=1, battery_action="charge", battery_soc=70)
    second.update(import_kwh=0, battery_discharge_kwh=.25, battery_action="serve", battery_soc=67.5)
    source["slots"][2].update(solar_kwh=.75, import_kwh=0, export_kwh=.5)
    source["slots"][3].update(battery_soc=67.5)
    result = hourly_plan(source, ZONE, NOW)
    row = result["rows"][0]
    assert row["import_kwh"] == 1.5
    assert row["export_kwh"] == .5
    assert row["grid_charge_kwh"] == 1
    assert row["battery_discharge_kwh"] == .25
    assert row["battery_soc"] == 67.5
    assert [p["battery"] for p in row["periods"]] == ["charge", "serve", "hold"]
    balanced(row)
    # SOC at a clipped final edge uses endpoints, not the average of slot SOCs.
    short = deepcopy(source)
    short["slots"] = short["slots"][:1]
    short["slots"][0]["end"] = NOW + 900
    short["slots"][0]["battery_soc"] = 70
    clipped = hourly_plan(short, ZONE, NOW + 300)["rows"][0]
    assert clipped["battery_soc"] == 70


@pytest.mark.parametrize("mode", ["Observation", "Control"])
def test_published_flows_are_the_selected_transition_outputs_without_new_decisions(mode):
    config, prices, solar, telemetry, stats = fixture(mode=mode)
    selected = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .15)
    initial = telemetry["battery_soc"] * selected["effective_capacity_kwh"] / 100
    for slot in selected["slots"]:
        expected = transition(slot, initial, slot["ev_kwh"], slot["battery_action"], config,
                              selected["effective_capacity_kwh"])
        for key in ("solar_charge_kwh", "grid_charge_kwh", "battery_discharge_kwh", "curtailed_kwh"):
            assert slot[key] == expected[key]
        initial = expected["energy"]
    original = deepcopy(selected)
    result = hourly_plan(selected, ZONE, NOW)
    assert selected == original
    assert result["status"] == "ready"
    assert len(json.dumps(result)) < 50000
    for row in result["rows"]:
        balanced(row)


@pytest.mark.parametrize("case, reason", [
    ("battery", "Monitoring only"), ("ev", "EV charging outlook"),
    ("solar", "Solar forecast coverage"), ("old", "Energy-flow details"),
    ("negative", "Energy-flow details"), ("nan", "Energy-flow details"),
    ("action", "Battery action unavailable"),
])
def test_unavailable_is_not_zero_and_independent_house_demand_remains(case, reason):
    source = invented(battery=True, solar=True, ev=True)
    if case == "battery":
        source.update(battery_forecast_available=False, battery_reason="Monitoring only")
    elif case == "ev":
        source["ev_forecast_available"] = False
    elif case == "solar":
        source["slots"][0]["solar_known"] = False
    elif case == "old":
        del source["slots"][0]["grid_charge_kwh"]
    elif case == "negative":
        source["slots"][0]["grid_charge_kwh"] = -1
    elif case == "nan":
        source["slots"][0]["import_kwh"] = float("nan")
    else:
        source["slots"][0]["battery_action"] = "unsupported"
    row = hourly_plan(source, ZONE, NOW)["rows"][0]
    assert not row["complete"]
    assert any(reason in r for r in row["reasons"])
    assert row["import_kwh"] is None and row["battery_soc"] is None
    assert row["house_kwh"] == 1
    assert row["solar_kwh"] is None if case == "solar" else row["solar_kwh"] == 0


def test_unknown_earlier_solar_invalidates_later_battery_but_not_grid_only_future():
    source = invented(battery=True, solar=True)
    source["slots"][0]["solar_known"] = False
    result = hourly_plan(source, ZONE, NOW)
    assert all(not r["complete"] for r in result["rows"])
    source["components"]["battery"] = False
    result = hourly_plan(source, ZONE, NOW)
    assert not result["rows"][0]["complete"]
    assert all(r["complete"] for r in result["rows"][1:])


def test_fallback_and_economic_boundary_remain_explanations_not_dispatch_changes():
    source = invented(battery=True)
    source["economic_until"] = NOW + 700
    result = hourly_plan(source, ZONE, NOW)
    first = result["rows"][0]
    assert [p["coverage"] for p in first["periods"]] == ["economic", "outlook"]
    assert first["periods"][0]["end"] == NOW + 700
    source["fallback_active"] = True
    fallback = hourly_plan(source, ZONE, NOW)
    assert fallback["fallback_active"]
    assert all(p["coverage"] == "fallback" for r in fallback["rows"] for p in r["periods"])
    assert first["import_kwh"] == fallback["rows"][0]["import_kwh"]


def test_ev_current_windows_fractional_stop_and_monitor_only_basis():
    source = invented(ev=True)
    first = source["slots"][0]
    first.update(ev_amps=16, ev_stop_at=NOW + 420, ev_kwh=.4, import_kwh=.65)
    result = hourly_plan(source, ZONE, NOW)
    window = result["rows"][0]["ev_windows"][0]
    assert window["start"] == NOW and window["end"] == NOW + 420 and window["amps"] == 16
    assert not result["rows"][1]["ev_windows"]
    assert any("16 A" in a["text"] for a in result["next_actions"])
    balanced(result["rows"][0])
    source["ev_status"] = "monitor_only"
    source["slots"][0].update(ev_amps=0, ev_stop_at=None)
    result = hourly_plan(source, ZONE, NOW)
    assert result["ev_basis"] == "Observed EV charging extrapolation"
    assert result["rows"][0]["ev_kwh"] == .4
    assert not result["rows"][0]["ev_windows"]


@pytest.mark.parametrize("zone, day", [
    ("America/Chicago", (2026, 11, 1)), ("America/Chicago", (2026, 3, 8)),
    ("Australia/Lord_Howe", (2026, 10, 4)), ("Australia/Lord_Howe", (2026, 4, 5)),
    ("Asia/Kathmandu", (2026, 10, 19)),
])
def test_ha_clock_hours_are_distinct_real_instants_including_dst_and_fractional_zones(zone, day):
    zone = ZoneInfo(zone)
    start = datetime(*day, tzinfo=zone).timestamp()
    result = hourly_plan(invented(start), zone, start)
    rows = result["rows"]
    assert sum(r["minutes"] for r in rows) == 1440
    assert all(a["end"] == b["start"] for a, b in zip(rows, rows[1:]))
    assert len({r["start"] for r in rows}) == len(rows)
    assert sum(r["house_kwh"] for r in rows) == pytest.approx(24)
    assert all(r["complete"] for r in rows)
    if str(zone) == "America/Chicago" and day[1] == 11:
        repeated = [r for r in rows if datetime.fromtimestamp(r["start"], zone).hour == 1]
        assert len(repeated) == 2
        assert "-0500" in repeated[0]["label"] and "-0600" in repeated[1]["label"]
    if str(zone) == "America/Chicago" and day[1] == 3:
        assert not any(datetime.fromtimestamp(r["start"], zone).hour == 2 for r in rows)
    if str(zone) == "Australia/Lord_Howe":
        assert any(r["minutes"] == 30 for r in rows)


def test_missing_expired_old_overlapping_and_gapped_payloads():
    assert hourly_plan({}, ZONE, NOW)["status"] == "waiting"
    source = invented()
    source["components"] = {}
    assert not hourly_plan(source, ZONE, NOW)["rows"]
    source = invented()
    source["slots"][1]["start"] -= 1
    assert not hourly_plan(source, ZONE, NOW)["rows"]
    source = invented()
    del source["slots"][1]
    row = hourly_plan(source, ZONE, NOW)["rows"][0]
    assert not row["complete"]
    assert all(row[key] is None for key in FLOWS)


def test_hourly_ev_windows_keep_the_real_stop_not_each_hour_boundary():
    source = invented(ev=True)
    for i in range(6):
        source["slots"][i].update(ev_amps=16, ev_stop_at=NOW + (i + 1) * 900, ev_kwh=.5, import_kwh=.75)
    source["slots"][6].update(ev_amps=16, ev_stop_at=NOW + 5700, ev_kwh=.15, import_kwh=.4)
    result = hourly_plan(source, ZONE, NOW)
    first, second = result["rows"][:2]
    assert first["ev_windows"][0]["end"] == NOW + 3600
    assert second["ev_windows"][0]["end"] == NOW + 5700
    assert first["ev_windows"][0]["stop_label"] == second["ev_windows"][0]["stop_label"]
    assert "19:35" in first["ev_windows"][0]["stop_label"]
    for row in result["rows"]:
        balanced(row)


def test_absent_ev_never_publishes_actions_from_old_slot_fields():
    source = invented()
    source["slots"][0].update(ev_amps=16, ev_stop_at=NOW + 120, ev_kwh=.2)
    result = hourly_plan(source, ZONE, NOW + 60)
    assert result["status"] == "ready"
    assert result["next_actions"] == []
    assert all(r["ev_kwh"] == 0 and r["ev_windows"] == [] for r in result["rows"])


def test_fractional_ev_clipping_does_not_claim_a_completed_charge_as_future_energy():
    source = invented(ev=True)
    source["slots"][0].update(ev_amps=16, ev_stop_at=NOW + 120, ev_kwh=.2, import_kwh=.45)
    row = hourly_plan(source, ZONE, NOW + 180)["rows"][0]
    assert row["ev_kwh"] == 0
    assert row["import_kwh"] is None and not row["complete"]
    assert any("Partial EV completion" in r for r in row["reasons"])
    assert row["ev_windows"] == []
    # Before its stop, exact remaining EV energy can be shown independently, but
    # whole-site allocation around that stop is unknown, not reoptimized in UI.
    row = hourly_plan(source, ZONE, NOW + 60)["rows"][0]
    assert row["ev_kwh"] == pytest.approx(.1)
    assert not row["complete"]


def test_soc_interpolates_the_clipped_final_edge_instead_of_averaging_percentages():
    source = invented(battery=True)
    source["slots"][96].update(battery_soc=45)
    # The display ends five minutes into a 15-minute 60% -> 45% interval.
    last = hourly_plan(source, ZONE, NOW + 300)["rows"][-1]
    assert last["end"] == NOW + 86400 + 300
    assert last["battery_soc"] == 55
