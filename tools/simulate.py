"""Offline synthetic stress lab. Run: python -B tools/simulate.py --help.

Load only the integration's pure modules in a private package: importing its real
__init__ would load Home Assistant. No HA instance, store, network or writer is used.
The independent AC plant below deliberately does not call planner.transition.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import sys
from types import ModuleType
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CORE_NAME = "_nrg_synthetic_core"
if CORE_NAME not in sys.modules:
    package = ModuleType(CORE_NAME)
    package.__path__ = [str(ROOT / "custom_components/nrg")]
    sys.modules[CORE_NAME] = package
config_core = importlib.import_module(CORE_NAME + ".config")
planner = importlib.import_module(CORE_NAME + ".planner")
Statistics = importlib.import_module(CORE_NAME + ".statistics").Statistics

STEP = 900
ZONE = ZoneInfo("America/Chicago")
SCENARIOS = {
    "baseline": "Ordinary synthetic demand, solar and hourly prices",
    "volatile-prices": "Negative midday prices and unexpected evening spikes",
    "solar-miss": "Solar forecast is optimistic; actual afternoon cloud collapse",
    "demand-spike": "Unforecast evening household load",
    "price-gap": "Missing current and future supply intervals, then recovery",
    "solar-gap": "Missing solar coverage, never replaced by known zero",
    "slow-ev": "Charger delivers less power and needs more AC energy than configured",
    "battery-mismatch": "Lower real capacity, efficiency and power than configured",
    "no-grid-charge": "Battery has no supported grid-charge capability",
    "grid-only": "No EV, battery or solar",
    "dst-spring": "Real elapsed time across the Chicago spring clock jump",
    "dst-fall": "Real elapsed time across the Chicago repeated autumn hour",
}
LIMITS = [
    "Synthetic outcomes are not measured savings, a utility bill or a global-optimum benchmark.",
    "15-minute replanning and ideal immediate mode response; not HA's 5-minute/30-second execution timing.",
    "Does not exercise HA adapters, command guards/readbacks, provider parsing, outages or fallback recovery latches.",
    "Baseline is immediate EV charging plus battery self-consumption, not an optimized or deadline-equivalent policy.",
    "Advice outcomes replay the issued fixed plan, not the later rolling policy or actual appliance operation.",
]


@dataclass(frozen=True)
class Scenario:
    name: str
    start: float
    capacity: float = 12
    efficiency: float = .90
    charge_kw: float = 4
    discharge_kw: float = 4
    ev_kw: float = 7.2
    ev_kwh_per_percent: float = .6
    solar_bias: float = 1
    has_equipment: bool = True
    grid_charge: bool = True


def scenario(name):
    if name not in SCENARIOS:
        raise ValueError("Unknown scenario: " + name)
    day = {"dst-spring": "2026-03-07", "dst-fall": "2026-10-31"}.get(name, "2026-10-19")
    result = Scenario(name, datetime.fromisoformat(day + "T18:00:00").replace(tzinfo=ZONE).timestamp())
    if name == "slow-ev":
        result = replace(result, ev_kw=3.6, ev_kwh_per_percent=.8)
    if name == "battery-mismatch":
        result = replace(result, capacity=9, efficiency=.72, charge_kw=2, discharge_kw=2)
    return replace(result, solar_bias=1.6 if name == "solar-miss" else 1,
                   has_equipment=name != "grid-only", grid_charge=name != "no-grid-charge")


def model_config(spec, learning=True):
    # Permissions apply only to the simulated plant; defaults/live options are untouched.
    return config_core.settings({
        "has_ev": spec.has_equipment, "has_battery": spec.has_equipment,
        "has_solar": spec.has_equipment, "ev_control": spec.has_equipment,
        "battery_control": spec.has_equipment, "battery_capacity": 12,
        "battery_charge_kw": 4, "battery_discharge_kw": 4,
        "ev_max_amps": 32, "ev_kw_at_max": 7.2, "ev_kwh_per_percent": .6,
        "supply_plan": "External supply entity", "delivery_cents": 4,
        "export_rate": "Flat credit", "flat_export_cents": 3,
        "house_learning": learning, "solar_learning": learning,
        "ev_learning": learning, "battery_learning": learning,
    })


def noise(seed, stamp, stream):
    """Stateless streams: policy and forecast calls cannot change future reality."""
    return random.Random(f"{seed}:{int(stamp)}:{stream}").gauss(0, 1)


def shape(stamp):
    local = datetime.fromtimestamp(stamp, ZONE)
    hour = local.hour + local.minute / 60
    house = .55 + (.7 if 6 <= hour < 9 else 0) + (1.1 if 17 <= hour < 22 else 0)
    solar = 5 * max(math.sin(math.pi * (hour - 6) / 12), 0) if 6 <= hour <= 18 else 0
    supply = .055 if hour < 6 else .25 if 16 <= hour < 21 else .11
    return house, solar, supply


def truth(spec, seed, stamp):
    house, solar, supply = shape(stamp)
    hour = datetime.fromtimestamp(stamp, ZONE).hour
    house = max(.1, house + .12 * noise(seed, stamp, "house"))
    solar *= max(.1, 1 + .12 * noise(seed, int(stamp // 3600) * 3600, "cloud"))
    supply += .008 * noise(seed, int(stamp // 3600) * 3600, "price")
    if stamp >= spec.start:
        if spec.name == "demand-spike" and 18 <= hour < 21:
            house += 4
        if spec.name == "solar-miss" and 12 <= hour < 17:
            solar *= .15
        if spec.name == "volatile-prices":
            supply = -.12 if 11 <= hour < 14 else .8 if 18 <= hour < 20 else supply
    return {"house_kw": house, "solar_kw": solar if spec.has_equipment else 0,
            "supply_price": supply, "import_price": supply + .04, "export_price": .03}


def forecasts(spec, seed, now, stats, config):
    rows, hours, known = [], {}, {}
    first = int(now // 3600) * 3600
    for stamp in range(first, first + 49 * 3600, 3600):
        _, solar, supply = shape(stamp)
        lead = max((stamp - now) / 3600, 0)
        supply += .01 * (1 + lead / 24) * noise(seed, stamp, f"price-issue-{int(now)}")
        if spec.name == "volatile-prices" and 11 <= datetime.fromtimestamp(stamp, ZONE).hour < 14:
            supply = -.10
        # A repeatable outage is based on time of issue, not the future truth.
        elapsed = (now - spec.start) / 3600
        price_gap = spec.name == "price-gap" and 2 <= elapsed < 6
        solar_gap = spec.name == "solar-gap" and 14 <= elapsed < 20
        if not price_gap:
            rows.append({"start": stamp, "end": stamp + 3600, "price": supply})
        key = str(stamp)
        known[key] = not solar_gap
        if not solar_gap:
            hours[key] = solar * spec.solar_bias * max(.2, 1 + .08 * noise(seed, stamp, f"solar-issue-{int(now)}"))
    if not spec.has_equipment:
        hours = {key: 0.0 for key in known}
        known = {key: True for key in known}
    raw = {"hours": hours, "known": known}
    factor = stats.solar_quality()["factor"] if config["solar_learning"] else 1
    adjusted = raw | {"hours": {key: value * factor for key, value in hours.items()}}
    return config | {"_external_supply": rows, "zone": ZONE}, raw, adjusted


@dataclass
class Plant:
    energy: float
    ev_soc: float = 45
    connected: bool = True
    ev_energy: float = 0


def connection(plant, stamp, spec):
    """Daily departure and return; each invented commute resets SOC to 45%."""
    hour = datetime.fromtimestamp(stamp, ZONE).hour
    connected = spec.has_equipment and (hour >= 18 or hour < 8)
    departed = plant.connected and not connected
    shortfall = max(80 - plant.ev_soc, 0) * spec.ev_kwh_per_percent if departed else None
    if connected and not plant.connected:
        plant.ev_soc = 45
    plant.connected = connected
    return shortfall


def advance(plant, spec, actual, hours, action, ev_fraction, extra_kw=0):
    """Independent physical oracle, AC quantities; requests are ideal native modes."""
    before = plant.energy
    car = min(max(80 - plant.ev_soc, 0) * spec.ev_kwh_per_percent,
              spec.ev_kw * hours * max(min(ev_fraction, 1), 0)) if plant.connected else 0
    plant.ev_soc += car / spec.ev_kwh_per_percent
    plant.ev_energy += car
    load = (actual["house_kw"] + extra_kw) * hours + car
    sun = actual["solar_kw"] * hours
    direct = min(sun, load)
    deficit, surplus = load - direct, sun - direct
    eta = math.sqrt(spec.efficiency)
    solar_charge = grid_charge = discharge = 0.0
    if spec.has_equipment:
        solar_charge = min(surplus, spec.charge_kw * hours, max(spec.capacity - before, 0) / eta)
        plant.energy += solar_charge * eta
        surplus -= solar_charge
        if action == "charge" and spec.grid_charge and not car:
            grid_charge = min(max(spec.charge_kw * hours - solar_charge, 0),
                              max(spec.capacity - plant.energy, 0) / eta)
            plant.energy += grid_charge * eta
        elif action == "serve":
            discharge = min(deficit, spec.discharge_kw * hours, max(plant.energy - spec.capacity * .2, 0) * eta)
            plant.energy -= discharge / eta
            deficit -= discharge
    imports, exports = deficit + grid_charge, surplus
    cash = imports * actual["import_price"] - exports * actual["export_price"]
    residual = sun + imports + discharge - load - solar_charge - grid_charge - exports
    stored_residual = plant.energy - before - (solar_charge + grid_charge) * eta + discharge / eta
    checks = {
        "energy_balance": abs(residual) <= 1e-8,
        "storage_balance": abs(stored_residual) <= 1e-8,
        "capacity": -1e-8 <= plant.energy <= spec.capacity + 1e-8,
        "reserve": plant.energy >= min(before, spec.capacity * .2) - 1e-8,
        "charge_power": solar_charge + grid_charge <= spec.charge_kw * hours + 1e-8,
        "discharge_power": discharge <= spec.discharge_kw * hours + 1e-8,
        "no_battery_exports": exports <= max(sun - load, 0) + 1e-8,
        "no_joint_grid_charge": not (car > 1e-8 and grid_charge > 1e-8),
        "grid_charge_permission": spec.grid_charge or grid_charge <= 1e-8,
    }
    return {"cash_cost": cash, "import_kwh": imports, "export_kwh": exports,
            "ev_kwh": car, "solar_charge_kwh": solar_charge, "grid_charge_kwh": grid_charge,
            "discharge_kwh": discharge, "checks": checks}


def observe(stats, stamp, plant, before_soc, out, actual, action, spec, enabled, *, finish=False):
    """Feed real coverage/session learners at one-minute intervals, not fake hours."""
    ev_kw = out["ev_kwh"] * 4
    battery_kw = (out["discharge_kwh"] - out["solar_charge_kwh"] - out["grid_charge_kwh"]) * 4
    energy_before = plant.ev_energy - out["ev_kwh"]
    soc_before = plant.ev_soc - out["ev_kwh"] / spec.ev_kwh_per_percent
    # Shared edges belong to the next interval; only the final interval supplies
    # its endpoint, closing the last covered minute/hour without duplicating time.
    for minute in range(16 if finish else 15):
        fraction = minute / 15
        values = actual | {
            "ev_kw": ev_kw, "ev_soc": soc_before + fraction * (plant.ev_soc - soc_before),
            "ev_energy": energy_before + fraction * out["ev_kwh"], "ev_amps": 32 * ev_kw / spec.ev_kw,
            "battery_kw": battery_kw, "battery_soc": before_soc + fraction * (plant.energy / spec.capacity * 100 - before_soc),
            "battery_learning_valid": True,
            "battery_charge_opportunity": action == "charge" and 20 < before_soc < 80,
            "battery_discharge_opportunity": action == "serve" and actual["house_kw"] >= spec.discharge_kw and 20 < before_soc < 80,
        }
        stats.observe(stamp + minute * 60, values, ZONE)
        stats.battery.observe(stamp + minute * 60, values, enabled and spec.has_equipment)


def warmup(spec, seed, config, days):
    stats = Statistics()
    plant = Plant(spec.capacity * .6 if spec.has_equipment else 0, connected=False)
    for stamp in range(int(spec.start - days * 86400), int(spec.start), STEP):
        connection(plant, stamp, spec)
        actual = truth(spec, seed, stamp)
        _, raw, _ = forecasts(spec, seed, stamp, stats, config)
        stats.remember_forecast(raw, stamp)
        hour = datetime.fromtimestamp(stamp, ZONE).hour
        action = "charge" if hour < 3 else "serve"
        before_soc = plant.energy / spec.capacity * 100
        out = advance(plant, spec, actual, .25, action, 1 if plant.connected else 0)
        observe(stats, stamp, plant, before_soc, out, actual, action, spec, config["battery_learning"],
                finish=stamp + STEP == spec.start)
    # Start evaluation like a real restart: preserve completed learning, discard
    # ALL unfinished house/EV/battery cycles and power episodes before a new plant.
    return Statistics(stats.export())


class Errors:
    def __init__(self):
        self.count = self.missing = 0
        self.absolute = self.squared = self.signed = 0.0

    def add(self, predicted, actual):
        if predicted is None:
            self.missing += 1
            return
        error = predicted - actual
        self.count += 1
        self.absolute += abs(error)
        self.squared += error * error
        self.signed += error

    def report(self):
        return {"samples": self.count, "missing": self.missing,
                "mae": self.absolute / self.count if self.count else None,
                "rmse": math.sqrt(self.squared / self.count) if self.count else None,
                "bias": self.signed / self.count if self.count else None}


def ev_fraction(row, stamp):
    """Honor the dated fractional stop and current, not just the slot's average kW."""
    stop = row.get("ev_stop_at") or stamp
    active = max(min(row["end"], stamp + STEP, stop) - max(row["start"], stamp), 0)
    return row["ev_amps"] / 32 * active / STEP


def advice_outcome(issued, initial, spec, seed, end, config):
    """Post-hoc independent replay, never fed into the planning policy."""
    advice = issued["household"]
    start, later = issued["generated_at"], advice.get("best_start")
    duration = config["flexible_load_minutes"] * 60
    boundary = min(issued["economic_until"], end)
    if later is None or later <= start or later + duration > boundary:
        return None
    scores = []
    for task in (start, later):
        plant = replace(initial)
        cash = 0.0
        for row in issued["slots"]:
            stamp = row["start"]
            if row["end"] > boundary:
                break
            connection(plant, stamp, spec)
            overlap = max(min(row["end"], task + duration) - max(stamp, task), 0)
            extra = config["flexible_load_kwh"] * overlap / duration / row["hours"]
            out = advance(plant, spec, truth(spec, seed, stamp), row["hours"], row["battery_action"],
                          ev_fraction(row, stamp), extra)
            cash += out["cash_cost"]
        scores.append(cash + (initial.energy - plant.energy) * issued["terminal_value"])
    return {"issued_at": start, "best_start": later, "confidence": advice.get("confidence"),
            "predicted_saving": advice["saving"], "fixed_plan_realized_saving": scores[0] - scores[1]}


def audit_request(row, config, spec):
    """Check the request as well as the constrained physical outcome."""
    checks = {
        "supported_mode": row["battery_action"] in ("hold", "serve", "charge"),
        "current_bounds": row["ev_amps"] == 0 or config["ev_min_amps"] <= row["ev_amps"] <= config["ev_max_amps"],
        "battery_soc_bounds": row["battery_soc"] is None or config["backup_reserve"] - .01 <= row["battery_soc"] <= 100,
        "grid_charge_permission": spec.grid_charge or row["battery_action"] != "charge",
        "no_joint_grid_charge": not (row["battery_action"] == "charge" and row["ev_kwh"] > 1e-8),
        "no_battery_for_ev": not (row["battery_action"] == "serve" and row["ev_kwh"] > 1e-8),
        "dependable_battery": row["battery_action"] == "hold" or (row["price_known"] and row["solar_known"]),
    }
    return ["requested_" + key for key, passed in checks.items() if not passed]


def simulate(name="baseline", *, seed=1, days=1, warmup_days=7, learning=True, trace=False):
    if not 1 <= days <= 30 or not 0 <= warmup_days <= 28:
        raise ValueError("days must be 1–30 and warmup_days 0–28")
    spec = scenario(name)
    config = model_config(spec, learning)
    stats = warmup(spec, seed, config, warmup_days)
    initial_learning = learning_report(stats, config, spec.start)
    plant = Plant(spec.capacity * .6 if spec.has_equipment else 0, connected=spec.has_equipment)
    baseline = replace(plant)
    end = spec.start + days * 86400
    totals = {policy: {"cash_cost": 0.0, "import_kwh": 0.0, "export_kwh": 0.0,
                       "ev_kwh": 0.0, "discharge_kwh": 0.0, "departure_shortfalls_kwh": []}
              for policy in ("planner", "baseline")}
    errors = {f"{key}_{lead}h": Errors() for lead in (1, 6, 24)
              for key in ("house_kw", "solar_kw", "supply_usd_per_kwh")}
    current_errors = {key: Errors() for key in ("house_kw", "fallback_house_kw", "raw_solar_kw", "solar_kw", "battery_soc")}
    pending = {}
    previous = None
    violations, decisions, advice_results = [], [], []
    counts = {"decisions": 0, "battery_action_changes": 0, "ev_on_off_changes": 0,
              "limited_advice": 0, "missing_current_price": 0, "missing_current_solar": 0}
    last_action = last_ev_on = None
    for stamp in range(int(spec.start), int(end), STEP):
        for policy, state in (("planner", plant), ("baseline", baseline)):
            missed = connection(state, stamp, spec)
            if missed is not None:
                totals[policy]["departure_shortfalls_kwh"].append(missed)
        actual = truth(spec, seed, stamp)
        for key, predicted in pending.pop(stamp, []):
            actual_key = "supply_price" if key.startswith("supply_") else key.rsplit("_", 1)[0]
            errors[key].add(predicted, actual[actual_key])
        effective, raw, solar = forecasts(spec, seed, stamp, stats, config)
        # Current price is an observation; a gap removes it as well as the forecast.
        live = actual["supply_price"] if effective["_external_supply"] else None
        telemetry = {"connected": plant.connected, "ev_soc": plant.ev_soc, "ev_limit": 80,
                     "battery_soc": plant.energy / spec.capacity * 100, "battery_ready": True,
                     "can_grid_charge": spec.grid_charge}
        issued = planner.plan(stamp, effective, ZONE, telemetry, stats, [], solar, live, previous)
        first = issued["slots"][0]
        # Freeze the actual production model's future predictions before outcomes.
        for lead in (1, 6, 24):
            target = stamp + lead * 3600
            if target >= end:
                continue
            row = next(s for s in issued["slots"] if s["start"] <= target < s["end"])
            for key, value in (("house_kw", row["house_kwh"] / row["hours"]),
                               ("solar_kw", row["solar_kwh"] / row["hours"] if row["solar_known"] else None),
                               ("supply_usd_per_kwh", row["supply_price"] if row["price_known"] else None)):
                pending.setdefault(target, []).append((f"{key}_{lead}h", value))
        current_errors["house_kw"].add(first["house_kwh"] / first["hours"], actual["house_kw"])
        current_errors["fallback_house_kw"].add(config["house_kw"], actual["house_kw"])
        hour = str(int(stamp // 3600) * 3600)
        current_errors["raw_solar_kw"].add(raw["hours"].get(hour), actual["solar_kw"])
        current_errors["solar_kw"].add(first["solar_kwh"] / first["hours"] if first["solar_known"] else None, actual["solar_kw"])
        state_at_issue = replace(plant)
        before_soc = plant.energy / spec.capacity * 100
        out = advance(plant, spec, actual, .25, first["battery_action"], ev_fraction(first, stamp))
        base_out = advance(baseline, spec, actual, .25, "serve", 1)
        for policy, outcome in (("planner", out), ("baseline", base_out)):
            for key in totals[policy]:
                if key != "departure_shortfalls_kwh":
                    totals[policy][key] += outcome[key]
            for check, passed in outcome["checks"].items():
                if not passed:
                    violations.append({"time": stamp, "policy": policy, "check": check})
        # Audit requests separately: a clamping physical plant must not hide an invalid plan.
        for check in audit_request(first, config, spec):
            violations.append({"time": stamp, "policy": "planner_request", "check": check})
        current_errors["battery_soc"].add(first["battery_soc"], plant.energy / spec.capacity * 100)
        action, ev_on = first["battery_action"], first["ev_kwh"] > 1e-8
        counts["decisions"] += 1
        counts["battery_action_changes"] += last_action is not None and action != last_action
        counts["ev_on_off_changes"] += last_ev_on is not None and ev_on != last_ev_on
        counts["limited_advice"] += issued["household"].get("confidence") != "forecast"
        counts["missing_current_price"] += not first["price_known"]
        counts["missing_current_solar"] += not first["solar_known"]
        last_action, last_ev_on = action, ev_on
        if stamp % 3600 == 0:
            outcome = advice_outcome(issued, state_at_issue, spec, seed, end, config)
            if outcome:
                advice_results.append(outcome)
        if trace:
            decisions.append({"time": datetime.fromtimestamp(stamp, ZONE).isoformat(),
                              "candidate": issued["selected_candidate"], "battery_action": action,
                              "ev_amps": first["ev_amps"], "ev_stop_at": first["ev_stop_at"],
                              "deadline": issued["deadline"],
                              "predicted_shortfall_kwh": issued["ev_shortfall_kwh"],
                              "coverage": {key: first[key] for key in ("price_known", "solar_known", "export_known")},
                              "forecast": {"house_kw": first["house_kwh"] / first["hours"],
                                           "solar_kw": first["solar_kwh"] / first["hours"] if first["solar_known"] else None,
                                           "supply_price": first["supply_price"], "import_price": first["import_price"]},
                              "predicted_battery_soc": first["battery_soc"], "actual_battery_soc": plant.energy / spec.capacity * 100,
                              "actual_ev_soc": plant.ev_soc, "economic_until": issued["economic_until"],
                              "advice": {key: issued["household"].get(key) for key in
                                         ("category", "confidence", "best_start", "saving")},
                              "actual": actual, "outcome": out})
        stats.remember_forecast(raw, stamp)
        observe(stats, stamp, plant, before_soc, out, actual, action, spec, config["battery_learning"],
                finish=stamp + STEP == end)
        previous = issued
    for policy, state in (("planner", plant), ("baseline", baseline)):
        totals[policy]["final_battery_kwh"] = state.energy
        totals[policy]["final_ev_soc"] = state.ev_soc if spec.has_equipment else None
        totals[policy]["missed_departures"] = sum(v > .1 for v in totals[policy]["departure_shortfalls_kwh"])
    return {"scenario": name, "seed": seed, "days": days, "warmup_days": warmup_days,
            "learning_enabled": learning, "start": datetime.fromtimestamp(spec.start, ZONE).isoformat(),
            "end": datetime.fromtimestamp(end, ZONE).isoformat(), "truth_parameters": asdict(spec),
            "model_assumptions": {key: config[key] for key in
                                  ("mode", "battery_capacity", "round_trip_efficiency", "battery_charge_kw",
                                   "battery_discharge_kw", "backup_reserve", "ev_kw_at_max", "ev_kwh_per_percent")},
            "forecast_units": {"house_kw": "kW", "solar_kw": "kW", "supply_usd_per_kwh": "USD/kWh",
                               "battery_soc": "percentage points"},
            "policies": totals, "decisions": counts, "invariant_violations": violations,
            "forecast_errors": {key: value.report() for key, value in errors.items()},
            "one_step_errors": {key: value.report() for key, value in current_errors.items()},
            "learning_before": initial_learning, "learning_after": learning_report(stats, config, end),
            "advice": {"evaluated_waits": len(advice_results),
                       "harmful_fixed_plan_waits": sum(r["fixed_plan_realized_saving"] < -.001 for r in advice_results),
                       "evaluations": advice_results}, "trace": decisions}


def learning_report(stats, config, now):
    return {"house_hours": sum(h.get("house_kwh") is not None for h in stats.hours),
            "solar": stats.solar_quality(), "ev_sessions": len(stats.ev_sessions),
            "ev_kwh_per_percent": stats.ev_estimate(config["ev_kwh_per_percent"]) if config["ev_learning"] else config["ev_kwh_per_percent"],
            "ev_kw_at_max": stats.ev_power(config["ev_kw_at_max"], 32) if config["ev_learning"] else config["ev_kw_at_max"],
            "battery": stats.battery.quality(config, now)}


def source_fingerprint():
    paths = [Path(__file__), *(ROOT / "custom_components/nrg" / (name + ".py") for name in
                              ("const", "config", "forecast", "tariffs", "statistics", "battery_learning", "planner"))]
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return {"sha256": digest.hexdigest(), "python": sys.version.split()[0],
            "integration_version": importlib.import_module(CORE_NAME + ".const").VERSION}


def bounded_int(low, high):
    def parse(value):
        number = int(value)
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f"must be between {low} and {high}")
        return number
    return parse


def format_mae(errors, key, scale=1):
    value = errors[key + "_1h"]["mae"]
    return f"{value * scale:.3f}" if value is not None else "n/a"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="baseline")
    parser.add_argument("--list", action="store_true", help="describe the synthetic scenarios and exit")
    parser.add_argument("--seed", type=int, default=1, help="reproducible seed (default: 1)")
    parser.add_argument("--runs", type=bounded_int(1, 100), default=1, help="repeat with consecutive seeds")
    parser.add_argument("--days", type=bounded_int(1, 30), default=1, help="real 24-hour periods (default: 1)")
    parser.add_argument("--warmup-days", type=bounded_int(0, 28), default=7, help="synthetic learning history (default: 7)")
    parser.add_argument("--no-learning", action="store_true", help="use configured assumptions; keep the same truth/seed")
    parser.add_argument("--trace", action="store_true", help="include every 15-minute decision in JSON")
    parser.add_argument("--output", type=Path, help="write a JSON report (use local/ to keep runs out of git)")
    args = parser.parse_args(argv)
    if args.list:
        for name, description in SCENARIOS.items():
            print(f"{name:20} {description}")
        return 0
    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = []
    print("Synthetic planning stress test — USD cash costs, not proven savings")
    print(f"{'Scenario / seed':27} {'Planner $':>10} {'Baseline $':>11} {'Missed EV':>10} {'Violations':>11}")
    for name in names:
        for seed in range(args.seed, args.seed + args.runs):
            result = simulate(name, seed=seed, days=args.days, warmup_days=args.warmup_days,
                              learning=not args.no_learning, trace=args.trace)
            results.append(result)
            p, b = result["policies"]["planner"], result["policies"]["baseline"]
            print(f"{name + ' / ' + str(seed):27} {p['cash_cost']:10.3f} {b['cash_cost']:11.3f} "
                  f"{p['missed_departures']:10} {len(result['invariant_violations']):11}")
            errors = result["forecast_errors"]
            print(f"  1h MAE: house {format_mae(errors, 'house_kw')} kW, "
                  f"solar {format_mae(errors, 'solar_kw')} kW, "
                  f"supply {format_mae(errors, 'supply_usd_per_kwh', 100)} cents/kWh; "
                  f"end battery {p['final_battery_kwh']:.2f}/{b['final_battery_kwh']:.2f} kWh (planner/baseline)")
    report = {"schema_version": 1, "synthetic_only": True, "source": source_fingerprint(),
              "limits": LIMITS, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
        print(f"Report: {args.output}")
    print("Review forecast errors, final stored energy and deadline shortfalls together; lower cash cost alone is not a better plan.")
    return 1 if any(r["invariant_violations"] for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
