"""Render generated homeowner advice with real HA templates and invented data."""
from pathlib import Path

import pytest
import yaml
from homeassistant.helpers.template import Template

from conftest import NOW

ROOT = Path(__file__).resolve().parents[1]


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


@pytest.mark.parametrize("advice", [
    {},
    {"category": "limited", "forecast_until": NOW},
    # An old integration plan should not break an independently updated dashboard.
    {"best_cost": .12, "forecast_until": NOW + 3600},
    {"category": "wait", "cost_basis": "battery", "best_cost": .12,
     "saving": .03, "grid_import_price": .3, "reference_kwh": 1,
     "reference_minutes": 60, "forecast_until": NOW + 7200},
    {"category": "wait", "cost_basis": "battery", "best_cost": .12, "confidence": "limited",
     "saving": .03, "grid_import_price": .3, "reference_kwh": 1, "reference_minutes": 60,
     "forecast_until": NOW + 7200, "battery_valuation": {"comparison_limited": True, "usable_stored_kwh": 5}},
])
async def test_generated_advice_templates_handle_new_old_and_missing_attributes(hass, advice):
    hass.states.async_set("sensor.nrg_plan", "household", {"plan": {"household": advice}})
    hass.states.async_set("sensor.nrg_advice", "Test advice", advice)
    dashboard = yaml.safe_load((ROOT / "custom_components/nrg/dashboards/nrg-home.yaml").read_text())
    cards = [item for item in walk(dashboard) if item.get("type") == "markdown"]
    explanation = next(c["content"] for c in cards if "### Selected appliance window" in c["content"])
    rendered = Template(explanation, hass).async_render()
    if "grid_import_price" in advice:
        assert "**Modeled appliance cost:** 12.0¢" in rendered
        assert "**Grid buying price during the window:** 30.0¢/kWh" in rendered
        assert "1 kWh over 60 minutes" in rendered or "1.0 kWh over 60 minutes" in rendered
        assert "Dependable comparison coverage ends" in rendered
        summary = next(c["content"] for c in cards if "## {{ states('sensor.nrg_advice') }}" in c["content"])
        text = Template(summary, hass).async_render()
        assert "Battery-backed use" in text
        assert "not necessarily the cheapest grid-price window" in text
        if advice.get("battery_valuation", {}).get("comparison_limited"):
            assert "Limited battery estimate" in text
            assert "not a promised refill" in text
            assert "Savings notifications are withheld" in text
            assert "Limited — conservative known-price reference" in rendered
    else:
        assert "Grid buying price during the window" not in rendered


def test_chart_and_admin_cost_labels_distinguish_prices_from_appliance_costs():
    home = yaml.safe_load((ROOT / "custom_components/nrg/dashboards/nrg-home.yaml").read_text())
    chart = next(c for c in walk(home) if c.get("type") == "custom:apexcharts-card"
                 and c.get("header", {}).get("title") == "Grid prices · suggested appliance window")
    assert any(s["name"] == "Suggested appliance window" for s in chart["series"])
    admin = (ROOT / "custom_components/nrg/dashboards/nrg-settings.yaml").read_text()
    assert "Modeled cost through dependable coverage" in admin
    assert "economic_until" in admin
