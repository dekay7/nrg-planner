"""Invented offline worlds, independent physical oracles and closed-loop regressions."""
from dataclasses import replace
from datetime import datetime
import json
import math
from pathlib import Path
import random
import subprocess
import sys

import pytest

from tools import simulate as lab

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def runs():
    return {name: lab.simulate(name, seed=13, warmup_days=0, learning=False, trace=True)
            for name in ("baseline", "price-gap", "solar-gap", "slow-ev", "grid-only")}


def test_cli_needs_only_stdlib_and_never_imports_ha(tmp_path):
    script = ROOT / "tools/simulate.py"
    code = (
        "import runpy, sys; "
        f"m = runpy.run_path({str(script)!r}, run_name='offline_lab'); "
        "assert not any(k.startswith('homeassistant') for k in sys.modules); "
        "assert 'custom_components.nrg' not in sys.modules; "
        "assert not any(k.endswith(('.runtime', '.control')) for k in sys.modules); "
        "m['main'](['--list'])"
    )
    done = subprocess.run([sys.executable, "-S", "-B", "-c", code], cwd=tmp_path,
                          capture_output=True, text=True, check=True)
    assert all(name in done.stdout for name in lab.SCENARIOS)


def test_cli_json_report_and_validation(tmp_path):
    report = tmp_path / "runs/report.json"
    command = [sys.executable, "-S", "-B", str(ROOT / "tools/simulate.py")]
    done = subprocess.run([*command, "--scenario", "grid-only", "--warmup-days", "0",
                           "--output", str(report)], cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    data = json.loads(report.read_text())
    assert data["schema_version"] == 1 and data["synthetic_only"]
    assert len(data["source"]["sha256"]) == 64
    assert data["limits"] and data["results"][0]["trace"] == []
    bad = subprocess.run([*command, "--days", "0"], capture_output=True, text=True)
    assert bad.returncode == 2 and "between 1 and 30" in bad.stderr


def test_exact_reproducibility_and_default_permissions_are_unchanged(runs):
    again = lab.simulate("baseline", seed=13, warmup_days=0, learning=False, trace=True)
    assert json.dumps(again, sort_keys=True, allow_nan=False) == json.dumps(runs["baseline"], sort_keys=True, allow_nan=False)
    defaults = lab.config_core.settings({})
    assert defaults["mode"] == "Observation"
    assert not defaults["ev_control"] and not defaults["battery_control"] and not defaults["battery_learning"]
    assert not defaults["notifications"] and not defaults["fallback_notifications"]


def test_closed_loop_outcomes_and_forecast_coverage(runs):
    for result in runs.values():
        assert result["invariant_violations"] == []
        assert result["decisions"]["decisions"] == 96
        assert len(result["trace"]) == 96
        for key in ("house_kw", "solar_kw", "supply_usd_per_kwh"):
            one = result["forecast_errors"][key + "_1h"]
            six = result["forecast_errors"][key + "_6h"]
            assert one["samples"] + one["missing"] == 92
            assert six["samples"] + six["missing"] == 72
            assert result["forecast_errors"][key + "_24h"]["mae"] is None
        assert result["policies"]["planner"]["missed_departures"] <= 1
    assert runs["baseline"]["policies"]["planner"]["missed_departures"] == 0
    # Unlearned optimistic power/energy assumptions should visibly miss readiness.
    assert runs["slow-ev"]["policies"]["planner"]["missed_departures"] == 1
    assert runs["slow-ev"]["policies"]["planner"]["departure_shortfalls_kwh"][0] > 1


@pytest.mark.parametrize("name,field,error_key", [
    ("price-gap", "missing_current_price", "supply_usd_per_kwh_1h"),
    ("solar-gap", "missing_current_solar", "solar_kw_1h"),
])
def test_missing_forecasts_are_unknown_and_recover(runs, name, field, error_key):
    result = runs[name]
    assert result["decisions"][field] > 0
    assert result["forecast_errors"][error_key]["missing"] > 0
    gaps = [row for row in result["trace"] if row["economic_until"] == datetime.fromisoformat(row["time"]).timestamp()]
    assert gaps and all(row["battery_action"] == "hold" for row in gaps)
    assert all(row["advice"]["confidence"] == "limited" for row in gaps)
    assert result["trace"][-1]["economic_until"] > datetime.fromisoformat(result["trace"][-1]["time"]).timestamp()


def test_grid_only_is_not_an_invented_battery_or_ev(runs):
    result = runs["grid-only"]
    p, b = result["policies"]["planner"], result["policies"]["baseline"]
    assert p["cash_cost"] == b["cash_cost"]
    assert p["final_battery_kwh"] == p["ev_kwh"] == 0
    assert p["final_ev_soc"] is None and p["departure_shortfalls_kwh"] == []
    assert result["one_step_errors"]["raw_solar_kw"]["mae"] == 0
    assert all(row["ev_amps"] == 0 and row["battery_action"] == "hold" for row in result["trace"])


def test_real_learners_use_only_synthetic_observations():
    spec = lab.scenario("slow-ev")
    config = lab.model_config(spec)
    stats = lab.warmup(spec, 7, config, 3)
    before = lab.learning_report(stats, config, spec.start)
    assert before["house_hours"] == 72
    assert stats.previous is None and stats.session is None and stats.bucket is None
    assert stats.battery.previous is None and stats.battery.cycle is None
    assert all(episode is None for episode in stats.battery.episodes.values())
    assert before["ev_sessions"] >= 3
    assert before["ev_kw_at_max"] == pytest.approx(spec.ev_kw)
    assert before["ev_kwh_per_percent"] == pytest.approx(spec.ev_kwh_per_percent)
    assert before["solar"]["samples"] >= 6
    predicted, count = stats.demand(spec.start, lab.ZONE, config["house_kw"], True)
    assert count > 0 and predicted > config["house_kw"]
    assert config["ev_kw_at_max"] == 7.2 and config["ev_kwh_per_percent"] == .6
    # Calibration is data-gated, not filled in from the ground-truth parameters.
    assert before["battery"]["estimates"]["round_trip_efficiency"]["source"] == "configured"


def test_forecast_generation_never_reads_the_future_actuals(monkeypatch):
    spec = lab.scenario("solar-miss")
    stats = lab.Statistics()
    config = lab.model_config(spec)
    expected = lab.forecasts(spec, 20, spec.start, stats, config)
    monkeypatch.setattr(lab, "truth", lambda *args: pytest.fail("forecast consulted future reality"))
    assert lab.forecasts(spec, 20, spec.start, stats, config) == expected
    assert lab.forecasts(spec, 21, spec.start, stats, config) != expected
    # Forecast and truth streams do not depend on how many policy calls were made.
    assert lab.noise(1, spec.start, "house") == lab.noise(1, spec.start, "house")


@pytest.mark.parametrize("name,offsets", [
    ("dst-spring", ["-06:00", "-05:00"]),
    ("dst-fall", ["-05:00", "-06:00"]),
])
def test_dst_world_uses_real_elapsed_quarters(name, offsets):
    spec = lab.scenario(name)
    times = [datetime.fromtimestamp(spec.start + i * lab.STEP, lab.ZONE) for i in range(96)]
    assert times[0].isoformat().endswith(offsets[0])
    assert times[-1].isoformat().endswith(offsets[1])
    assert len({t.timestamp() for t in times}) == 96
    if name == "dst-fall":
        assert sum(t.hour == 1 for t in times) == 8
    else:
        assert not any(t.hour == 2 for t in times)


def test_independent_plant_matches_hand_calculated_ac_energy_and_cost():
    spec = replace(lab.scenario("baseline"), efficiency=.81, charge_kw=4, discharge_kw=4)
    actual = {"house_kw": 2, "solar_kw": 0, "import_price": .2, "export_price": .03}
    plant = lab.Plant(6, connected=False)
    out = lab.advance(plant, spec, actual, .25, "serve", 0)
    assert out["discharge_kwh"] == .5
    assert plant.energy == pytest.approx(6 - .5 / .9)
    assert out["cash_cost"] == 0
    out = lab.advance(plant, spec, actual, .25, "charge", 0)
    assert out["grid_charge_kwh"] == 1
    assert plant.energy == pytest.approx(6 - .5 / .9 + .9)
    assert out["cash_cost"] == pytest.approx(1.5 * .2)


def test_random_plant_conservation_bounds_and_permissions():
    rng = random.Random(720)
    for _ in range(400):
        spec = replace(lab.scenario("baseline"), capacity=rng.uniform(1, 100),
                       efficiency=rng.uniform(.5, 1), charge_kw=rng.uniform(.5, 30),
                       discharge_kw=rng.uniform(.5, 30), grid_charge=rng.choice([True, False]))
        state = lab.Plant(rng.uniform(0, spec.capacity), rng.uniform(0, 80), rng.choice([True, False]))
        before = state.energy
        actual = {"house_kw": rng.uniform(0, 50), "solar_kw": rng.uniform(0, 30),
                  "import_price": rng.uniform(-.2, 1), "export_price": rng.uniform(0, .3)}
        hours = rng.uniform(.001, 1)
        out = lab.advance(state, spec, actual, hours, rng.choice(["hold", "serve", "charge"]), rng.random())
        charge = out["solar_charge_kwh"] + out["grid_charge_kwh"]
        assert state.energy == pytest.approx(before + charge * math.sqrt(spec.efficiency) - out["discharge_kwh"] / math.sqrt(spec.efficiency))
        assert all(out["checks"].values())
        assert out["cash_cost"] == pytest.approx(out["import_kwh"] * actual["import_price"] - out["export_kwh"] * actual["export_price"])


def test_invalid_requests_are_visible_even_when_plant_clamps_them():
    spec = lab.scenario("no-grid-charge")
    config = lab.model_config(spec)
    row = {"battery_action": "charge", "ev_amps": 90, "ev_kwh": 1,
           "price_known": False, "solar_known": False, "battery_soc": 110}
    failures = lab.audit_request(row, config, spec)
    for key in ("grid_charge_permission", "no_joint_grid_charge", "dependable_battery", "current_bounds", "battery_soc_bounds"):
        assert "requested_" + key in failures
    actual = lab.truth(spec, 1, spec.start)
    out = lab.advance(lab.Plant(6), spec, actual, .25, "charge", 1)
    assert out["grid_charge_kwh"] == 0 and all(out["checks"].values())


def test_fractional_stop_is_not_a_full_interval_of_charging():
    spec = lab.scenario("baseline")
    row = {"start": spec.start, "end": spec.start + 900, "ev_amps": 16, "ev_stop_at": spec.start + 300}
    assert lab.ev_fraction(row, spec.start) == pytest.approx(1 / 6)
    assert lab.ev_fraction(row, spec.start + 900) == 0


def test_grid_only_advice_replay_has_an_independent_known_answer(monkeypatch):
    spec = lab.scenario("grid-only")
    now = spec.start
    config = lab.model_config(spec)
    config["flexible_load_minutes"] = 15
    issued = {"generated_at": now, "economic_until": now + 1800, "terminal_value": 0,
              "household": {"best_start": now + 900, "saving": .2, "confidence": "forecast"},
              "slots": [{"start": now + i * 900, "end": now + (i + 1) * 900, "hours": .25,
                         "battery_action": "hold", "ev_amps": 0, "ev_stop_at": None} for i in range(2)]}
    monkeypatch.setattr(lab, "truth", lambda spec, seed, stamp: {
        "house_kw": 1, "solar_kw": 0, "import_price": .3 if stamp == now else .1, "export_price": 0})
    initial = lab.Plant(0, connected=False)
    result = lab.advice_outcome(issued, initial, spec, 1, now + 1800, config)
    assert result["fixed_plan_realized_saving"] == pytest.approx(.2)
    assert initial.energy == 0  # Counterfactual replay cannot mutate the policy state.
    assert lab.advice_outcome(issued, initial, spec, 1, now + 900, config) is None


def test_error_metrics_keep_missing_separate_from_zero():
    errors = lab.Errors()
    for predicted, actual in ((None, 2), (0, 2), (4, 2)):
        errors.add(predicted, actual)
    assert errors.report() == {"samples": 2, "missing": 1, "mae": 2, "rmse": 2, "bias": 0}


def test_batch_seeds_and_failure_exit_code(monkeypatch, tmp_path):
    calls = []
    def fake(name, **kwargs):
        calls.append((name, kwargs["seed"]))
        return {"policies": {"planner": {"cash_cost": 0, "missed_departures": 0, "final_battery_kwh": 0},
                             "baseline": {"cash_cost": 1, "final_battery_kwh": 0}},
                "forecast_errors": {key + "_1h": {"mae": None} for key in
                                    ("house_kw", "solar_kw", "supply_usd_per_kwh")},
                "invariant_violations": ["invented failure"]}
    monkeypatch.setattr(lab, "simulate", fake)
    path = tmp_path / "batch.json"
    assert lab.main(["--scenario", "all", "--seed", "9", "--runs", "2", "--output", str(path)]) == 1
    assert calls == [(name, seed) for name in lab.SCENARIOS for seed in (9, 10)]
    assert len(json.loads(path.read_text())["results"]) == 2 * len(lab.SCENARIOS)
