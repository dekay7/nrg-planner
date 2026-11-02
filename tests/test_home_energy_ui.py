"""Execute generated chart code and render native details with invented plans."""
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time

import pytest
import yaml
from homeassistant.helpers.template import Template

from conftest import NOW, ZONE
from custom_components.nrg.hourly import hourly_plan
from test_hourly_plan import invented
from tools.build_ui import home_energy_chart, home_energy_details, home_energy_events, home_time_formatter

ROOT = Path(__file__).resolve().parents[1]


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def energy_series():
    return [series for charging in (False, True) for series in home_energy_chart(charging=charging)["series"]]


def run_node(script, data, **environment):
    result = subprocess.run(["node", "-e", script], input=json.dumps(data), text=True,
                            capture_output=True, check=True, env=os.environ | environment)
    return json.loads(result.stdout)


def test_new_chart_placement_and_existing_price_chart_move_preserve_both_outlooks():
    home = yaml.safe_load((ROOT / "custom_components/nrg/dashboards/nrg-home.yaml").read_text())
    views = {v["path"]: list(walk(v)) for v in home["views"]}
    charts = {key: [c["header"]["title"] for c in cards if c.get("type") == "custom:apexcharts-card"] for key, cards in views.items()}
    assert charts["now"] == ["Household flows · next 24 hours", "Charging & grid import · next 24 hours"]
    assert charts["why"] == ["Grid prices · suggested appliance window", "Modeled energy plan · next 48 hours"]
    assert any("Hourly plan details" in c.get("content", "") for c in views["now"])
    assert {s["name"] for s in home_energy_chart()["series"]} == {
        "House demand", "Solar generation", "Battery supply", "Grid export", "Solar curtailment"}
    assert [(s["name"], s["type"]) for s in home_energy_chart(charging=True)["series"]] == [
        ("Grid import (total)", "line"), ("EV charging", "column"), ("Battery charging", "column")]
    for charging in (False, True):
        chart = home_energy_chart(charging=charging)
        assert chart["stacked"] is False  # Total grid import must not be added to charging.
        axis = chart["apex_config"]["yaxis"]
        assert axis["min"] == 0
        assert axis["max"].startswith("EVAL:")  # Per-panel headroom, not a fixed/shared cap.
        assert not axis.get("logarithmic")
        assert chart["apex_config"]["chart"]["zoom"]["enabled"] is True
        assert chart["apex_config"]["tooltip"]["shared"] is True
        assert "touchstart" in chart["apex_config"]["chart"]["events"]["mounted"]


def test_linear_scales_leave_headroom_without_clipping_peaks():
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));
const maximum=eval('('+d.code.slice(5)+')');console.log(JSON.stringify(d.peaks.map(maximum)));"""
    for charging in (False, True):
        result = run_node(script, {"code": home_energy_chart(charging=charging)["apex_config"]["yaxis"]["max"],
                                   "peaks": [0, 1, 7, 50]})
        assert result == pytest.approx([1, 1.1, 7.7, 55])


def test_executable_generators_preserve_exact_positive_energy_alignment_absence_and_null_gaps():
    source = invented(solar=True, battery=True, ev=True)
    source["slots"][0].update(solar_kwh=1, import_kwh=.25, solar_charge_kwh=.25,
                               battery_discharge_kwh=.5, export_kwh=.2, curtailed_kwh=.1)
    hourly = hourly_plan(source, ZONE, NOW)
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8')); Date.now=()=>d.now*1000;
const start=new Date(d.now*1000),end=new Date((d.now+86400)*1000),entity={attributes:{plan:d.plan,hourly:d.hourly}};
const run=()=>d.codes.map(code=>new Function('entity','start','end',code)(entity,start,end));
const active=run(); entity.attributes.hourly.rows[1].complete=false; const gaps=run();
entity.attributes.plan.components={solar:false,battery:false,ev:false}; const absent=run();
entity.attributes.plan.expires_at=d.now; const expired=run(); delete entity.attributes.hourly; const old=run();
console.log(JSON.stringify({active,gaps,absent,expired,old}));"""
    result = run_node(script, {"now": NOW, "plan": source, "hourly": hourly,
                               "codes": [s["data_generator"] for s in energy_series()]})
    values = [points[0][1] for points in result["active"]]
    assert values == [1, 1, .5, .2, .1, 1, 0, .25]
    assert all(points[0][0] == (NOW + 1800) * 1000 for points in result["active"])
    assert all(points[1][1] is None for points in result["gaps"])
    assert all(all(point[1] == (None if n == 1 else 0) for n, point in enumerate(result["absent"][i])) for i in (1, 2, 3, 4, 6, 7))
    # Hidden series retain matching x values: empty arrays corrupt shared tooltip
    # labels/values in the pinned ApexCharts implementation.
    assert all([p[0] for p in points] == [p[0] for p in result["absent"][0]] for points in result["absent"])
    assert all(points == [] for points in result["expired"] + result["old"])


@pytest.mark.parametrize("ev,grid_charge,solar,imports", [(9, 0, 0, 10), (0, 5, 0, 6), (9, 0, 4, 6), (0, 0, 0, 1)])
def test_charging_peaks_stay_in_their_own_panel_without_reallocating_or_scaling_energy(ev, grid_charge, solar, imports):
    source = invented(solar=True, battery=True, ev=True)
    for slot in source["slots"][:4]:
        slot.update(ev_kwh=ev / 4, grid_charge_kwh=grid_charge / 4, solar_kwh=solar / 4,
                    import_kwh=imports / 4, ev_amps=40 if ev else 0, ev_stop_at=slot["end"] if ev else None)
    hourly = hourly_plan(source, ZONE, NOW)
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));Date.now=()=>d.now*1000;
const entity={attributes:{plan:d.plan,hourly:d.hourly}},before=JSON.stringify(entity);
const values=d.codes.map(code=>new Function('entity','start','end',code)(entity,new Date(d.now*1000),new Date((d.now+86400)*1000))[0][1]);
console.log(JSON.stringify({values,unchanged:before===JSON.stringify(entity)}));"""
    result = run_node(script, {"now": NOW, "plan": source, "hourly": hourly,
                               "codes": [s["data_generator"] for s in energy_series()]})
    assert result["unchanged"]
    assert result["values"] == [1, solar, 0, 0, 0, imports, ev, grid_charge]
    # The solar-assisted EV case must retain 6 kWh imports, not infer 9 kWh of grid EV charging.
    assert max(result["values"][:5]) <= 4
    assert sum(result["values"][1:3]) + imports == 1 + ev + grid_charge


def test_zero_export_and_curtailment_series_are_hidden_not_spurious_legend_entries():
    source = invented(solar=True)
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));Date.now=()=>d.now*1000;
console.log(JSON.stringify(d.codes.map(code=>new Function('entity','start','end',code)({attributes:d.attributes},new Date(d.now*1000),new Date((d.now+86400)*1000)))));"""
    result = run_node(script, {"now": NOW, "attributes": {"plan": source, "hourly": hourly_plan(source, ZONE, NOW)},
                               "codes": [s["data_generator"] for s in home_energy_chart()["series"][-2:]]})
    assert len(result) == 2
    assert all(len(points) == 24 and all(p[1] == 0 for p in points) for points in result)
    assert home_energy_chart()["apex_config"]["legend"]["showForZeroSeries"] is False


def test_chart_resize_observer_wraps_tooltips_redraws_only_for_width_and_disconnects():
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));
let callback,observations=0,disconnected=0,updates=[],styles=[],properties=[],plotWidth=200;
global.document={createElement:()=>({dataset:{},textContent:''})};
global.ResizeObserver=class{constructor(cb){callback=cb;}observe(){observations++;}disconnect(){disconnected++;}};
const el={isConnected:true,parentElement:{getBoundingClientRect:()=>({right:300})},closest:()=>null,append:style=>styles.push(style),
  style:{setProperty:(...args)=>properties.push(args)},
  querySelector:selector=>selector==='style[data-nrg-tooltip]'?styles[0]:selector==='.apexcharts-grid'?{getBoundingClientRect:()=>({width:plotWidth,left:40,right:plotWidth+40})}:null};
const ctx={el,updateOptions:(...a)=>updates.push(a)};
const mounted=eval('('+d.code.slice(5)+')');mounted(ctx);mounted(ctx);
callback([{contentRect:{width:400,height:340}}]);
callback([{contentRect:{width:400,height:450}}]);
callback([{contentRect:{width:600,height:450}}]);
// Reconfiguration can reuse the DOM element with a NEW chart instance.
plotWidth=350;mounted({el,updateOptions:(...a)=>updates.push(['replacement',...a])});
callback([{contentRect:{width:600,height:340}}]);callback([{contentRect:{width:700,height:340}}]);
el.isConnected=false;callback([{contentRect:{width:0,height:0}}]);
console.log(JSON.stringify({observations,updates,disconnected,styles,properties}));"""
    result = run_node(script, {"code": home_energy_events()})
    styles, properties = result.pop("styles"), result.pop("properties")
    assert len(styles) == 1  # Mounted/updated/replacement callbacks do not duplicate CSS.
    assert styles[0]["dataset"] == {"nrgTooltip": ""}
    assert "max-width:min(20rem,var(--nrg-tooltip-width,calc(100% - 16px)))" in styles[0]["textContent"]
    assert "white-space:normal" in styles[0]["textContent"]
    assert "overflow-wrap:anywhere" in styles[0]["textContent"]
    assert properties == [[name, value] for width, offset in (("184px", "0px"), ("184px", "0px"), ("244px", "-90px"))
                          for name, value in (("--nrg-tooltip-width", width), ("--nrg-tooltip-offset", offset))]
    assert result == {"observations": 2,
                      "updates": [[{"chart": {"width": 600}}, False, False], ["replacement", {"chart": {"width": 700}}, False, False]],
                      "disconnected": 2}


@pytest.mark.parametrize("now", [NOW, datetime.fromisoformat("2026-11-01T23:00:00-06:00").timestamp(),
                                 datetime.fromisoformat("2026-11-01T01:00:00-05:00").timestamp()])
def test_shared_tooltip_uses_the_same_exact_interval_label_as_native_details(now):
    source = invented(now)
    h = hourly_plan(source, ZONE, now + 300)
    row = h["rows"][0]
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));
global.document={querySelector:()=>({hass:{config:{time_zone:'America/Chicago'},locale:{time_zone:'local'},states:{'sensor.nrg_plan':{attributes:{hourly:d.hourly}}}}})};
const formatter=eval('('+d.code.slice(5)+')');console.log(JSON.stringify(formatter(d.stamp)));"""
    assert run_node(script, {"code": home_time_formatter(True), "hourly": h,
                              "stamp": (row["start"] + row["end"]) * 500}) == row["label"]


@pytest.mark.parametrize("profile", ["server", "local"])
@pytest.mark.parametrize("browser_zone", ["UTC", "Asia/Kathmandu", "America/Los_Angeles"])
def test_labels_use_ha_timezone_and_distinguish_dst_folds_in_both_profile_modes(profile, browser_zone):
    # Reproduce the pinned card's CURRENT server/browser offset adjustment, then
    # execute our actual formatter on both occurrences of Chicago's repeated hour.
    stamps = [datetime.fromisoformat(v).timestamp() for v in ("2026-11-01T01:30:00-05:00", "2026-11-01T01:30:00-06:00")]
    script = """const fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));
const RealDate=Date;global.Date=class extends RealDate{constructor(...a){super(...(a.length?a:[d.now*1000]));}static now(){return d.now*1000;}};
global.document={querySelector:()=>({hass:{config:{time_zone:'America/Chicago'},locale:{time_zone:d.profile}}})};
const now=new Date(), parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',timeZoneName:'longOffset'}).formatToParts(now);
const offset=parts.find(p=>p.type==='timeZoneName').value.match(/GMT([+-])(\\d{2}):(\\d{2})/);
const home=(offset[1]==='-'?-1:1)*(Number(offset[2])*60+Number(offset[3]));
const shift=d.profile==='server'?(-now.getTimezoneOffset()-home)*60000:0;
const formatter=eval('('+d.code.slice(5)+')');
console.log(JSON.stringify(d.stamps.map(t=>formatter(t*1000-shift))));"""
    labels = run_node(script, {"now": NOW, "code": home_time_formatter(True), "stamps": stamps, "profile": profile}, TZ=browser_zone)
    assert "01:30" in labels[0] or "1:30" in labels[0]
    assert "01:30" in labels[1] or "1:30" in labels[1]
    assert "GMT-5" in labels[0] and "GMT-6" in labels[1]


@pytest.mark.parametrize("scenario", ["ready", "partial", "fallback", "old", "expired", "missing"])
async def test_native_details_render_safely_and_have_keyboard_accessible_hourly_actions(hass, scenario):
    now = time.time()
    source = invented(now, solar=True, battery=True, ev=True)
    source["slots"][0].update(ev_amps=16, ev_stop_at=now+900, ev_kwh=.2, import_kwh=.45)
    source["slots"][1].update(battery_action="serve")  # zero flow must not become a claim of discharge
    source["economic_until"] = now + 1800
    if scenario == "partial":
        source.update(battery_forecast_available=False, battery_reason="Battery monitoring only; native controller decides.")
    if scenario == "fallback":
        source["fallback_active"] = True
    if scenario == "expired":
        source["expires_at"] = now - 1
    attributes = {"plan": source, "hourly": hourly_plan(source, ZONE, now), "operating_mode": "Observation"}
    if scenario == "old":
        attributes.pop("hourly")
    if scenario == "missing":
        attributes = {}
    hass.states.async_set("sensor.nrg_plan", "test", attributes)
    text = Template(home_energy_details()["content"], hass).async_render()
    if scenario in ("old", "expired", "missing"):
        assert "Waiting for a fresh home energy plan" in text
        assert "<details>" not in text
    else:
        assert "Observation, no commands sent" in text
        assert "<details><summary>" in text
        assert "Hourly plan details" in text
        assert "independent linear kWh scales" in text
        assert "not an extra amount to add to charging" in text
        assert "Save battery" in text if scenario != "partial" else "monitoring only" in text
        assert "EV charging at 16" in text
        if scenario == "partial":
            assert "grid Unknown" in text and "Incomplete outlook" in text
            assert "Modeled ending battery" not in text
        elif scenario == "fallback":
            assert "Price-data fallback baseline" in text
        else:
            assert "Conservative later outlook" in text
            assert "Supply home" in text
            assert "may deliver nothing" in text


async def test_sensor_projection_is_not_inserted_into_the_command_plan(hass, installed):
    runtime = installed.runtime_data
    assert "hourly" not in runtime.plan
    state = hass.states.get("sensor.nrg_plan")
    projection = state.attributes["hourly"]
    assert projection["rows"] and projection["status"] == "ready"
    assert projection["timezone"] == "America/Chicago"
    assert "hourly" not in state.attributes["plan"]
    package = yaml.safe_load((ROOT / "custom_components/nrg/dashboard-package.yaml").read_text())
    assert "sensor.nrg_plan" in package["recorder"]["exclude"]["entities"]
