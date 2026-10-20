from pathlib import Path
import json
import subprocess
import hashlib

import yaml

from custom_components.nrg.const import SETTINGS
from tools.build_ui import price_generator

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


def test_handbook_links_bypass_ha_month_long_static_cache_after_updates():
    digest=hashlib.sha256((INTEGRATION/"assets/guide.html").read_bytes()).hexdigest()[:12]
    for filename in ("nrg-home.yaml","nrg-settings.yaml"):
        text=(INTEGRATION/"dashboards"/filename).read_text()
        assert "/nrg-planner/guide.html?v="+digest in text
