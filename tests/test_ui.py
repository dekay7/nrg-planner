from pathlib import Path
from collections import Counter
from html.parser import HTMLParser
import json
import subprocess
import hashlib
from urllib.parse import unquote, urlsplit

import yaml

from custom_components.nrg.const import SETTINGS
from tools.build_ui import price_generator, timeline

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components/nrg"


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def test_homeowner_dashboard_contains_only_read_metrics_and_accessible_links():
    home = yaml.safe_load((INTEGRATION / "dashboards/nrg-home.yaml").read_text())
    for item in walk(home):
        if "entity" in item:
            assert item["entity"].startswith(("sensor.", "binary_sensor."))
        assert item.get("tap_action", {}).get("action") not in ("toggle", "perform-action", "call-service")
    package = yaml.safe_load((INTEGRATION / "dashboard-package.yaml").read_text())
    assert package["lovelace"]["dashboards"]["nrg-home"]["require_admin"] is False
    assert package["lovelace"]["dashboards"]["nrg-settings"]["require_admin"] is True


async def test_dashboard_entities_exist_and_all_tuning_has_help(hass, installed):
    admin = yaml.safe_load((INTEGRATION / "dashboards/nrg-settings.yaml").read_text())
    entities = [item["entity"] for item in walk(admin) if "entity" in item]
    for item in walk(admin):
        entities.extend(e for e in item.get("entities", []) if isinstance(e, str))
    assert all(hass.states.get(e) is not None for e in entities)
    translations = json.loads((ROOT / "custom_components/nrg/translations/en.json").read_text())
    for key, field in SETTINGS.items():
        assert translations["options"]["step"][field.section]["data_description"][key]


def test_actual_chart_generator_converts_once_and_expires():
    script = """const fs=require('fs'), input=JSON.parse(fs.readFileSync(0,'utf8'));
const now=Date.now(), start=new Date(now),end=new Date(now+3600000);
const entity={attributes:{plan:{expires_at:now/1000+60,slots:[{start:now/1000,end:now/1000+3600,import_price:-.02,price_source:'flat',price_known:true}]}}};
const run=new Function('entity','start','end',input.code);
const active=run(entity,start,end); entity.attributes.plan.expires_at=0;
console.log(JSON.stringify({active,expired:run(entity,start,end)}));"""
    result = subprocess.run(["node", "-e", script], input=json.dumps({"code": price_generator("live")}), text=True, capture_output=True, check=True)
    values = json.loads(result.stdout)
    assert values["active"][0][1] == -2
    assert values["expired"] == []


def test_battery_chart_uses_observation_plan_but_does_not_invent_unready_soc():
    from conftest import fixture, NOW, ZONE
    from custom_components.nrg.planner import plan

    config, prices, solar, telemetry, stats = fixture(mode="Observation")
    telemetry["connected"] = False
    ready = plan(NOW, config, ZONE, telemetry, stats, prices, solar, .15)
    blocked = plan(NOW, config, ZONE, telemetry | {"battery_ready": False}, stats, prices, solar, .15)
    battery = next(series for series in timeline()["series"] if series["yaxis_id"] == "soc")
    script = """const fs=require('fs'), input=JSON.parse(fs.readFileSync(0,'utf8'));
Date.now=()=>input.now*1000;
const run=new Function('entity',input.code);
console.log(JSON.stringify(input.plans.map(plan=>run({attributes:{plan}}))));"""
    result = subprocess.run(["node", "-e", script], input=json.dumps({
        "code": battery["data_generator"], "now": NOW, "plans": [ready, blocked],
    }), text=True, capture_output=True, check=True)
    ready_points, blocked_points = json.loads(result.stdout)
    assert len(ready_points) == len(ready["slots"])
    assert all(20 <= point[1] <= 100 for point in ready_points)
    assert blocked_points == []


def test_handbook_links_bypass_ha_month_long_static_cache_after_updates():
    digest=hashlib.sha256((INTEGRATION/"assets/guide.html").read_bytes()).hexdigest()[:12]
    for filename in ("nrg-home.yaml","nrg-settings.yaml"):
        text=(INTEGRATION/"dashboards"/filename).read_text()
        assert "/nrg-planner/guide.html?v="+digest in text


class HandbookParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.tags = []
        self.tables = []
        self.headers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs["href"])
        if tag == "div" and attrs.get("class") == "table-scroll":
            self.tables.append(attrs)
        if tag == "th":
            self.headers.append(attrs)


def test_handbook_is_self_contained_and_every_local_link_resolves():
    page = HandbookParser()
    page.feed((INTEGRATION / "assets/guide.html").read_text())
    assert not {"script", "link", "img", "iframe", "object", "embed", "form"}.intersection(page.tags)
    assert not [key for key, count in Counter(page.ids).items() if count > 1]
    for target in page.links:
        parts = urlsplit(target)
        if not parts.scheme and not parts.netloc:
            assert not parts.path, f"Link would leave the bundled handbook: {target}"
            assert unquote(parts.fragment) in page.ids, f"Missing handbook target: {target}"
    # In particular, root-level privacy and its relative links must work locally.
    assert "#privacy-diagnostics-and-support" in page.links
    assert "#installation-optional-dashboards" in page.links


def test_handbook_has_accessible_navigation_and_complete_user_help():
    page = HandbookParser()
    page.feed((INTEGRATION / "assets/guide.html").read_text())
    assert page.tags.count("h1") == 1
    assert page.tags.count("main") == 1
    assert "#content" in page.links
    assert {"overview", "installation", "quick-start", "homeowner-guide", "operations",
            "faq", "pricing", "integrations", "learning", "settings", "troubleshooting",
            "glossary", "privacy", "security", "design", "accounting", "alternatives", "review"} <= set(page.ids)
    assert page.tables
    assert all(table.get("role") == "region" and table.get("aria-label")
               and table.get("tabindex") == "0" for table in page.tables)
    assert page.headers and all(header.get("scope") == "col" for header in page.headers)
