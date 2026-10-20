"""Privacy boundaries: unknown tariffs, hostile diagnostics, and Git ancestry."""
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from custom_components.nrg.config import settings, validate
from custom_components.nrg.const import OPTIONAL_RATES
from custom_components.nrg.diagnostics import async_get_config_entry_diagnostics
from custom_components.nrg.forecast import price_at
from custom_components.nrg.planner import plan
from custom_components.nrg.statistics import Statistics
from tools.check_privacy import check_file, check_text, scan
from conftest import NOW, ZONE, fixture


def test_unconfigured_tariffs_stay_unknown_and_explicit_zero_is_valid():
    config = settings({})
    assert all(config[key] is None for key in OPTIONAL_RATES)
    assert not any(config[key] for key in ("ev_control", "battery_control", "has_ev", "has_battery", "has_solar"))
    missing = price_at(NOW, NOW, config, [], None)
    assert missing["import_price"] is None and not missing["price_known"]
    assert validate({key: None for key in OPTIONAL_RATES}) == {key: None for key in OPTIONAL_RATES}
    free = price_at(NOW, NOW, settings({"flat_supply_cents": 0, "delivery_cents": 0}), [], None)
    assert free["import_price"] == 0 and free["price_known"]


def test_no_historical_price_profile_is_bundled_and_local_estimates_are_tentative():
    stats = Statistics()
    config = settings({"supply_plan": "Hourly ComEd", "delivery_cents": 4})
    missing = price_at(NOW + 3600, NOW, config, [], None, stats.price_prior)
    assert missing["supply_price"] is None and missing["import_price"] is None
    stats.hours = [{"comed_hour": 19, "supply": .07}]
    learned = price_at(NOW + 3600, NOW, config, [], None, stats.price_prior)
    assert learned["supply_price"] == .07 and learned["supply_source"] == "recorded_estimate"
    assert not learned["price_known"]


def test_missing_rates_never_publish_free_prices_or_authorize_battery_arbitrage():
    config, _, solar, telemetry, stats = fixture(supply_plan="Flat supply", flat_supply_cents=None, delivery_cents=None)
    result = plan(NOW, config, ZONE, telemetry, stats, [], solar)
    assert all(row["import_price"] is None and row["cost"] is None for row in result["slots"])
    assert all(row["battery_action"] == "hold" for row in result["slots"])
    assert not any(key.startswith("_model_") for row in result["slots"] for key in row)
    assert result["modeled_cost"] is None
    assert result["household"]["windows"] == []


def test_missing_export_rate_is_unknown_independently_of_known_import_prices():
    config, _, solar, telemetry, stats = fixture(supply_plan="Flat supply", flat_supply_cents=10,
                                               export_rate="Flat credit", flat_export_cents=None)
    result = plan(NOW, config, ZONE, telemetry, stats, [], solar)
    assert all(row["price_known"] and not row["export_known"] for row in result["slots"])
    assert all(row["export_price"] is None and row["battery_action"] == "hold" for row in result["slots"])
    assert result["household"]["windows"] == []
    assert result["modeled_cost"] is None


async def test_diagnostics_cannot_export_nested_identifiers_rates_errors_or_schedules():
    private = {"tariff": 123.456, "email": "owner@example.invalid", "label": "private-marker",
               "entity_id": "sensor.private_marker", "departure": "2030-01-02T03:04:05",
               "ip": ".".join(("10", "99", "88", "77")), "credential": "ghp_" + "A" * 36}
    config = settings({"has_solar": True, "delivery_cents": private["tariff"],
                       "command_scripts": {"ev_start": "script.private_marker"}}) | private
    runtime = SimpleNamespace(config=config, data={"solar": {"sources": [private | {"ready": True}]}},
                              plan=private, forecast_status=private,
                              controller=SimpleNamespace(status=private), current_price_known=False,
                              stats=SimpleNamespace(hours=[private], ev_sessions=[private]))
    result = await async_get_config_entry_diagnostics(None, SimpleNamespace(runtime_data=runtime))
    serialized = json.dumps(result)
    assert all(str(value) not in serialized for value in private.values())
    assert result["source_counts"] == {"total": 1, "ready": 1}
    assert set(result) == {"schema_version", "integration_version", "mode", "components", "control_enabled",
                           "source_counts", "statistics_counts", "plan_available", "current_price_known"}


async def test_blank_rate_survives_restart_and_can_be_cleared_through_options(hass, installed):
    runtime = installed.runtime_data
    await runtime.update_options({"delivery_cents": None})
    await hass.async_block_till_done()
    assert hass.states.get("number.nrg_delivery_cents").state == "unknown"
    assert hass.states.get("sensor.nrg_import_price").state == "unknown"
    assert await hass.config_entries.async_reload(installed.entry_id)
    await hass.async_block_till_done()
    assert installed.runtime_data.config["delivery_cents"] is None
    result = await hass.config_entries.options.async_init(installed.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "tariff"})
    await hass.config_entries.options.async_configure(result["flow_id"], {"supply_plan": "Flat supply"})
    await hass.async_block_till_done()
    assert installed.runtime_data.config["flat_supply_cents"] is None
    assert installed.runtime_data.controller.last == {}


async def test_fresh_ui_setup_with_no_rates_loads_in_observation(hass):
    from homeassistant.setup import async_setup_component
    assert await async_setup_component(hass, "nrg", {})
    result = await hass.config_entries.flow.async_init("nrg", context={"source": "user"})
    for values in ({}, {}, {}):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], values)
    await hass.async_block_till_done()
    entry = result["result"]
    assert all(entry.runtime_data.config[key] is None for key in OPTIONAL_RATES)
    assert entry.runtime_data.config["mode"] == "Observation"
    assert hass.states.get("sensor.nrg_import_price").state == "unknown"
    assert not entry.runtime_data.controller.last
    await hass.config_entries.async_unload(entry.entry_id)


def test_mapping_a_command_path_does_not_enable_control():
    config = settings({"mappings": {"ev_current": "number.example", "ev_charge": "switch.example",
                                     "battery_mode": "select.example"}})
    assert not config["ev_control"] and not config["battery_control"]


@pytest.mark.parametrize("name", ["bill.pdf", "readings.csv", "docs/history.csv", "prod/config.yaml",
                                  ".session/state.json", "custom_components/other/__init__.py", "docs/photo.png",
                                  "docs/usage.json", "custom_components/nrg/measurements.json"])
def test_publication_gate_rejects_private_files_even_in_otherwise_valid_directories(name):
    assert check_file(name, b"invented contents")


def test_security_policy_and_dependabot_are_reviewed_publication_assets():
    assert check_file("SECURITY.md", b"# Security policy\n") == []
    assert check_file(".github/dependabot.yml", b"version: 2\nupdates: []\n") == []
    assert check_file(".github/settings/private.yml", b"not publishable")


def test_publication_gate_detects_credentials_and_personal_metadata_without_values_in_report():
    credential = "ghp_" + "A" * 36
    email = "owner" + "@" + "mail.invalid"
    findings = check_text(credential + "\n" + email)
    assert {label for _, label in findings} == {"GitHub credential", "non-placeholder email address"}
    assert credential not in repr(findings) and email not in repr(findings)


@pytest.fixture
def publication_repo(tmp_path):
    env = os.environ | {"GIT_AUTHOR_NAME": "review-test", "GIT_COMMITTER_NAME": "review-test",
                        "GIT_AUTHOR_EMAIL": "test@users.noreply.github.com", "GIT_COMMITTER_EMAIL": "test@users.noreply.github.com"}

    def run(*args, **changes):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True, env=env | changes)

    run("init", "-b", "main")
    (tmp_path / "README.md").write_text("Generic test project\n")
    run("add", "README.md")
    run("commit", "-m", "Generic initial snapshot")
    return tmp_path, run


def test_publication_gate_finds_deleted_files_and_old_metadata_in_history(publication_repo):
    tmp_path, run = publication_repo
    (tmp_path / "old.csv").write_text("invented,private,data\n")
    run("add", "README.md", "old.csv")
    private_email = "old" + "@" + "mail.invalid"
    run("commit", "-m", "Initial test snapshot", GIT_AUTHOR_EMAIL=private_email)
    run("rm", "old.csv")
    run("commit", "-m", "Remove test data")
    assert scan(tmp_path)[1] == []
    findings = scan(tmp_path, history=True)[1]
    assert any(name == "history:old.csv" for name, _, _ in findings)
    assert any(label == "non-placeholder email address" for _, _, label in findings)


def test_publication_gate_checks_staged_content_even_when_working_copy_is_clean(publication_repo):
    root, run = publication_repo
    private_email = "staged" + "@" + "mail.invalid"
    (root / "README.md").write_text(private_email)
    run("add", "README.md")
    (root / "README.md").write_text("Generic test project\n")
    findings = scan(root)[1]
    assert any(name == "index:README.md" and label == "non-placeholder email address"
               for name, _, label in findings)
    assert private_email not in repr(findings)


def test_publication_gate_checks_annotated_tag_metadata(publication_repo):
    root, run = publication_repo
    private_email = "tagger" + "@" + "mail.invalid"
    run("tag", "-a", "review-test", "-m", "Generic tag", GIT_COMMITTER_EMAIL=private_email)
    findings = scan(root, history=True)[1]
    assert any(name.startswith("tag ") and label == "non-placeholder email address"
               for name, _, label in findings)
    assert private_email not in repr(findings)


def test_history_scan_handles_github_dependabot_release_notes_without_ignoring_secrets(publication_repo):
    root, run = publication_repo
    (root / "README.md").write_text("Generic Dependabot test project\n")
    run("add", "README.md")
    contact = "maintainer" + "@" + "package.invalid"
    run("commit", "-m", f"Update package\n\nUpstream contact: {contact}\nPrivate marker: local-secret-marker",
        GIT_AUTHOR_NAME="dependabot[bot]", GIT_AUTHOR_EMAIL="49699333+dependabot[bot]@users.noreply.github.com",
        GIT_COMMITTER_NAME="dependabot[bot]", GIT_COMMITTER_EMAIL="49699333+dependabot[bot]@users.noreply.github.com")
    assert scan(root, history=True)[1] == []
    assert any(label == "owner-supplied private indicator" for _, _, label in
               scan(root, history=True, indicators=["local-secret-marker"])[1])


def test_history_scan_rejects_incomplete_or_missing_history(publication_repo):
    root, run = publication_repo
    clone = root / "shallow"
    run("clone", "--depth=1", root.as_uri(), str(clone))
    assert any(label == "shallow Git history; fetch full history before publication"
               for _, _, label in scan(clone, history=True)[1])
    archive = root / "archive"
    archive.mkdir()
    (archive / "README.md").write_text("Generic test project\n")
    # An exported tree outside a repository cannot substantiate a history check.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CEILING_DIRECTORIES", str(root))
        assert any(label == "Git history unavailable" for _, _, label in scan(archive, history=True)[1])


def test_dashboard_package_and_handbook_are_shipped_inside_integration():
    import yaml
    integration = Path(__file__).resolve().parents[1] / "custom_components/nrg"
    package = yaml.safe_load((integration / "dashboard-package.yaml").read_text())
    for dashboard in package["lovelace"]["dashboards"].values():
        relative = Path(dashboard["filename"]).relative_to("custom_components/nrg")
        assert (integration / relative).is_file()
    assert (integration / "assets/guide.html").is_file()


async def test_http_registration_exposes_only_generic_bundled_assets():
    from unittest.mock import AsyncMock
    from custom_components.nrg import async_setup
    http = SimpleNamespace(async_register_static_paths=AsyncMock())
    assert await async_setup(SimpleNamespace(http=http), {})
    paths = http.async_register_static_paths.call_args.args[0]
    assert len(paths) == 1
    assert paths[0].url_path == "/nrg-planner"
    directory = Path(paths[0].path)
    assert directory.name == "assets" and directory.parent.name == "nrg"
    assert {p.name for p in directory.iterdir()} == {"guide.html"}


async def test_real_http_serves_handbook_but_not_configuration_or_parent_files(hass):
    from aiohttp.test_utils import TestClient, TestServer
    from homeassistant.components.http import HomeAssistantHTTP, SSL_MODERN
    from homeassistant.components.http.cors import setup_cors
    from custom_components.nrg import async_setup

    server = HomeAssistantHTTP(hass, None, None, None, None, 0, [], SSL_MODERN)
    setup_cors(server.app, [])
    hass.http = server
    assert await async_setup(hass, {})

    async with TestClient(TestServer(server.app)) as client:
        response = await client.get("/nrg-planner/guide.html?v=review")
        assert response.status == 200
        assert response.content_type == "text/html"
        bundled = Path(__file__).resolve().parents[1] / "custom_components/nrg/assets/guide.html"
        assert await response.read() == bundled.read_bytes()
        assert "max-age" not in response.headers.get("Cache-Control", "")
        for path in ("configuration.yaml", ".storage/core.config_entries", "manifest.json",
                     "%2e%2e/manifest.json", "%2e%2e/%2e%2e/configuration.yaml"):
            response = await client.get("/nrg-planner/" + path)
            assert response.status in (403, 404)
