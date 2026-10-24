"""Documentation coverage and source-derived references; no live instance/network."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import markdown
import pytest

from custom_components.nrg.const import SETTINGS, MAPPINGS, CONTROL_VALUES, COMMAND_SCRIPTS, VERSION, option_label
from tools.build_ui import HANDBOOK_CHAPTERS

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class DocumentLinks(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(markdown.markdown(text, extensions=["tables", "fenced_code", "toc"]))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a":
            self.links.append(attrs["href"])


def test_every_documentation_chapter_is_bundled_once():
    expected = {str(p.relative_to(ROOT)) for p in DOCS.glob("*.md")} | {"PRIVACY.md", "SECURITY.md"}
    sources = [name for name, _, _, _ in HANDBOOK_CHAPTERS]
    keys = [key for _, key, _, _ in HANDBOOK_CHAPTERS]
    assert set(sources) == expected
    assert all(count == 1 for count in Counter(sources).values())
    assert all(count == 1 for count in Counter(keys).values())
    handbook = (ROOT / "custom_components/nrg/assets/guide.html").read_text()
    for key in keys:
        assert f'<section id="{key}"' in handbook


def test_repository_markdown_links_and_fragments_resolve():
    paths = [ROOT / "README.md", ROOT / "PRIVACY.md", ROOT / "SECURITY.md", *DOCS.glob("*.md")]
    documents = {p.resolve(): DocumentLinks(p.read_text()) for p in paths}
    for source, parsed in documents.items():
        for target in parsed.links:
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            destination = (source.parent / unquote(parts.path)).resolve() if parts.path else source
            assert destination.exists(), f"Missing target in {source.name}: {target}"
            if parts.fragment and destination in documents:
                assert unquote(parts.fragment) in documents[destination].ids, f"Missing fragment in {source.name}: {target}"


def test_every_catalogue_setting_has_its_current_default_and_help():
    reference = (DOCS / "settings.md").read_text()
    keys = re.findall(r"Reference key: `([^`]+)`\.", reference)
    assert set(keys) == set(SETTINGS)
    assert all(count == 1 for count in Counter(keys).values())
    for key, field in SETTINGS.items():
        section = reference.split(f"### {field.name}\n", 1)[1].split(f"Reference key: `{key}`.", 1)[0]
        default = "On" if field.default is True else "Off" if field.default is False else "Unset" if field.default is None else str(option_label(key, field.default))
        if field.unit and field.default is not None:
            default += " " + field.unit
        assert f"Default: **{default}**." in section
        assert field.description in section
        for choice in field.choices:
            assert f"**{option_label(key, choice)}**" in section


def test_every_mapping_control_value_and_script_role_is_documented_from_catalogues():
    reference = (DOCS / "settings.md").read_text()
    mappings = reference.split("## Measurement and control entity mappings", 1)[1].split("## Control-state names and command scripts", 1)[0]
    for key, (name, domains, description) in MAPPINGS.items():
        row = next(line for line in mappings.splitlines() if line.startswith(f"| `{key}` |"))
        assert name in row and description in row
        for domain in domains if isinstance(domains, tuple) else (domains,):
            assert f"`{domain}`" in row
    controls = reference.split("## Control-state names and command scripts", 1)[1]
    for key, value in CONTROL_VALUES.items():
        assert f"| `{key}` | `{value}` |" in controls
    for key in COMMAND_SCRIPTS:
        assert f"| `{key}` | `script_{key}` |" in controls
    for key in ("supply_periods", "delivery_periods", "mappings", "solar_sources", "departure_override",
                "notification_targets", "control_values", "command_scripts"):
        assert f"`{key}`" in reference.split("## Configuration beyond catalogue fields", 1)[1]


@pytest.mark.parametrize("target", [
    "installation.md#updates-and-removal",
    "README.md#the-three-ideas-that-make-setup-easier",
    "pricing.md#editing-timed-periods-in-ha",
    "pricing.md#external-utility-price-integrations",
    "pricing.md#comed-price-sources-and-freshness",
    "pricing.md#comeds-new-hour-publication-window",
    "pricing.md#brief-comed-live-data-delays",
    "pricing.md#tentative-prices-for-the-end-of-day-cost-forecast",
    "operations.md#price-data-fallback",
    "operations.md#detection-and-recovery",
    "operations.md#notifications",
    "design.md#ev-candidates",
    "design.md#battery-search",
    "homeowner-guide.md#modeled-energy-plan-the-battery-line",
    "homeowner-guide.md#current-power-flow-the-sankey-diagram",
    "integrations.md#script-adapters",
    "integrations.md#solar-forecasts-and-alternatives",
    "learning.md#calibrate-battery-estimates",
    "learning.md#calibrate-ev-charging-estimates",
    "learning.md#solar-forecast-calibration",
    "learning.md#learn-household-demand",
    "learning.md#resetting-or-disabling-learning",
    "simulation.md",
    "accounting.md#observed-ledger",
    "accounting.md#different-money-figures",
    "accounting.md#built-in-ha-energy",
    "../PRIVACY.md",
    "../SECURITY.md",
])
def test_feature_index_links_original_and_subsequent_feature_areas(target):
    inventory = DocumentLinks((DOCS / "features.md").read_text())
    assert target in inventory.links


def test_feature_availability_and_retired_behavior_are_explicit():
    inventory = (DOCS / "features.md").read_text()
    assert "**0.1.0**" in inventory and "**0.2.0**" in inventory
    assert f"The latest numbered release is **{VERSION}**" in inventory
    assert f"| **{VERSION}** |" in inventory
    assert "**unreleased development**" in inventory
    assert "summer peak-import heuristic is retired" in inventory
    for filename in ("design.md", "accounting.md"):
        text = (DOCS / filename).read_text()
        assert "The optional seasonal" not in text
    for filename in ("README.md", "installation.md", "faq.md", "troubleshooting.md"):
        assert "features.md" in (DOCS / filename).read_text()
