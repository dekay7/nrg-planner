"""Passive AC battery calibration; no capacity inference or equipment commands.

Only compact, completed cycle/opportunity summaries survive a restart. Power is
an observed sustained operating capability, not a certified hardware maximum.
"""
import hashlib
import json
from statistics import median

from .config import finite

HISTORY = 12
MAX_AGE = 30 * 86400
MIN_SAMPLES = 3
POWER_WINDOW = 600


class BatteryLearning:
    def __init__(self, saved=None):
        saved = saved or {}
        self.signature = saved.get("signature")
        self.cycles = [{"ended": finite(r["ended"]), "charge_kwh": used, "discharge_kwh": out}
                       for r in saved.get("cycles", []) if isinstance(r, dict)
                       and finite(r.get("ended")) is not None
                       and (used := finite(r.get("charge_kwh"), 0)) >= .5
                       and (out := finite(r.get("discharge_kwh"), 0)) > 0
                       and .5 <= out / used <= 1][-HISTORY:]
        self.powers = {direction: [{"ended": finite(r["ended"]), "kw": finite(r["kw"])}
                                  for r in saved.get("powers", {}).get(direction, [])
                                  if isinstance(r, dict) and finite(r.get("ended")) is not None
                                  and .5 <= finite(r.get("kw"), 0) <= 30][-HISTORY:]
                       for direction in ("charge", "discharge")}
        self.previous = None
        self.cycle = None
        self.episodes = {"charge": None, "discharge": None}
        self.status = "Waiting for battery measurements"

    def export(self):
        return {"signature": self.signature, "cycles": [r.copy() for r in self.cycles],
                "powers": {key: [r.copy() for r in rows] for key, rows in self.powers.items()}}

    def configure(self, config, mappings):
        # Manual capacity/efficiency/power assumptions are deliberately absent:
        # efficiency is measured without converting SOC to assumed stored kWh.
        roles = ("battery_soc", "battery_power", "battery_charge_energy", "battery_discharge_energy",
                 "home_power", "grid_power", "solar_power", "battery_mode")
        identity = {"mappings": {key: mappings.get(key) for key in roles},
                    "conventions": {key: config[key] for key in
                                    ("battery_power_inverted", "grid_power_inverted", "home_includes_ev")},
                    "charge_mode": config["control_values"]["battery_charge"],
                    "hold_mode": config["control_values"]["battery_hold"]}
        signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        if signature != self.signature:
            self.__init__()
            self.signature = signature

    def _break(self):
        self.cycle = None
        self.episodes = {"charge": None, "discharge": None}

    @staticmethod
    def _recent(rows, now):
        return [r for r in rows if 0 <= now - r["ended"] <= MAX_AGE]

    def quality(self, config, now):
        cycles = self._recent(self.cycles, now)
        if cycles:
            center = median(r["discharge_kwh"] / r["charge_kwh"] for r in cycles)
            cycles = [r for r in cycles if abs(r["discharge_kwh"] / r["charge_kwh"] - center) <= .05]
        efficiency = (100 * sum(r["discharge_kwh"] for r in cycles) / sum(r["charge_kwh"] for r in cycles)
                      if len(cycles) >= MIN_SAMPLES else None)
        rows = {"round_trip_efficiency": (efficiency, cycles)}
        for direction in ("charge", "discharge"):
            samples = self._recent(self.powers[direction], now)
            power = median(r["kw"] for r in samples) if len(samples) >= MIN_SAMPLES else None
            rows["battery_" + direction + "_kw"] = power, samples
        enabled = config["has_battery"] and config["battery_learning"]
        estimates = {key: {"effective": value if enabled and value is not None else config[key],
                           "learned": value, "samples": len(samples),
                           "last_observed": max((r["ended"] for r in samples), default=None),
                           "source": "learned" if enabled and value is not None else "configured"}
                     for key, (value, samples) in rows.items()}
        used = sum(row["source"] == "learned" for row in estimates.values())
        status = ("Not installed" if not config["has_battery"] else "Off" if not enabled else
                  "Using learned estimates" if used == 3 else "Using partial calibration" if used else
                  "Collecting observations")
        return {"status": status, "observation_status": self.status, "estimates": estimates,
                "basis": "AC measurements; sustained operating power, not a hardware rating or battery health estimate"}

    def model(self, config, now):
        return {key: row["effective"] for key, row in self.quality(config, now)["estimates"].items()}

    def observe(self, now, values, enabled):
        power, soc = finite(values.get("battery_kw")), finite(values.get("battery_soc"))
        if (not enabled or not values.get("battery_learning_valid") or power is None or soc is None
                or not -30 <= power <= 30 or not 0 <= soc <= 100):
            self.previous = None
            self._break()
            self.status = "Learning disabled" if not enabled else "Waiting for consistent battery measurements and protection inputs"
            return
        values = values | {"battery_kw": power, "battery_soc": soc}
        previous, self.previous = self.previous, (now, values)
        self.cycles = self._recent(self.cycles, now)
        self.powers = {key: self._recent(rows, now) for key, rows in self.powers.items()}
        self.status = "Waiting for qualified cycles and sustained-power opportunities"
        if previous is None:
            return
        start, old = previous
        elapsed = now - start
        if not 0 < elapsed <= 180:
            self._break()
            self.status = "Observation gap; incomplete calibration discarded"
            return
        # Reject SOC motion inconsistent with even the smallest supported 1 kWh
        # system, allowing one percentage point of display rounding. This does
        # not use the user's capacity or turn capacity errors into learned losses.
        charge = max(-old["battery_kw"], 0) * elapsed / 3600
        discharge = max(old["battery_kw"], 0) * elapsed / 3600
        delta = soc - old["battery_soc"]
        if delta > charge * 100 + 1.1 or -delta > discharge * 100 / .5 ** .5 + 1.1:
            self._break()
            self.status = "Unexplained battery percentage change; incomplete calibration discarded"
            return
        self._power(now, old, values, elapsed)
        if values.get("battery_energy_counters"):
            pairs = [(finite(old.get(key)), finite(values.get(key)))
                     for key in ("battery_charge_energy", "battery_discharge_energy")]
            if any(a is None or b is None or a < 0 or b < a for a, b in pairs):
                self.cycle = None
                self.status = "Efficiency paused: both increasing AC energy counters must be available"
                return
            charge, discharge = [b - a for a, b in pairs]
            if charge + discharge > 30 * elapsed / 3600 + .02:
                self.cycle = None
                self.status = "Efficiency paused: implausible energy-counter change"
                return
        self._efficiency(now, start, old, values, charge, discharge, elapsed)

    def _power(self, now, old, values, elapsed):
        for direction, sign in (("charge", -1), ("discharge", 1)):
            key = "battery_" + direction + "_opportunity"
            low = min(sign * old["battery_kw"], sign * values["battery_kw"])
            high = max(sign * old["battery_kw"], sign * values["battery_kw"])
            if not old.get(key) or not values.get(key) or low < .5:
                episode, self.episodes[direction] = self.episodes[direction], None
                if episode and episode["best"] is not None:
                    self.powers[direction].append({"kw": episode["best"], "ended": now})
                    self.powers[direction] = self.powers[direction][-HISTORY:]
                continue
            episode = self.episodes[direction]
            if episode is None:
                episode = self.episodes[direction] = {"seconds": 0, "low": low, "high": high, "best": None}
            episode["seconds"] += elapsed
            episode["low"] = min(episode["low"], low)
            episode["high"] = max(episode["high"], high)
            if episode["seconds"] >= POWER_WINDOW:
                if episode["high"] <= episode["low"] * 1.1:
                    episode["best"] = max(episode["best"] or 0, episode["low"])
                episode.update(seconds=0, low=low, high=high)
            # One summary per continuous opportunity, not one 'independent'
            # sample per minute or per ten-minute block of the same event.

    def _efficiency(self, now, start, old, values, charge, discharge, elapsed):
        if self.cycle is None:
            if abs(old["battery_kw"]) < .2:
                return
            self.cycle = {"start": start, "soc": old["battery_soc"],
                          "direction": 1 if old["battery_kw"] < 0 else -1,
                          "excursion": 0, "charge_kwh": 0, "discharge_kwh": 0, "idle": 0}
        cycle = self.cycle
        before = cycle["direction"] * (old["battery_soc"] - cycle["soc"])
        after = cycle["direction"] * (values["battery_soc"] - cycle["soc"])
        cycle["excursion"] = max(cycle["excursion"], after)
        closing = before > 0 and after <= 0
        # Interpolate a crossing rather than include energy beyond the starting
        # reported SOC. SOC rounding still limits field-measurement accuracy.
        fraction = before / (before - after) if closing else 1
        cycle["charge_kwh"] += charge * fraction
        cycle["discharge_kwh"] += discharge * fraction
        cycle["idle"] += elapsed * fraction if abs(old["battery_kw"]) < .2 else 0
        if now - cycle["start"] > 86400 or cycle["idle"] > 7200 or after < -1.1 and not closing:
            self.cycle = None
            return
        if closing:
            self.cycle = None
            used, out = cycle["charge_kwh"], cycle["discharge_kwh"]
            if (cycle["excursion"] >= 30 and now - cycle["start"] >= 600 and used >= .5
                    and .5 <= out / used <= 1):
                self.cycles.append({"charge_kwh": used, "discharge_kwh": out, "ended": now})
                self.cycles = self.cycles[-HISTORY:]
