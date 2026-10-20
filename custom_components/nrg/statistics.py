"""Small coverage-gated statistics and measured-cost ledger, persisted by HA Store.

No raw house history, location history or credentials are retained. Restart breaks
the integration interval: the unobserved gap is never learned or billed as zero.
"""
from datetime import datetime, timedelta
from statistics import mean, median

from .config import export_price
from .tariffs import boundaries, period_at


class Statistics:
    def __init__(self, saved: dict | None = None):
        saved = saved or {}
        self.hours = saved.get("hours", [])[-24 * 28:]
        self.ev_sessions = saved.get("ev_sessions", [])[-12:]
        self.issued = saved.get("issued", {})
        self.ledger = saved.get("ledger", {})
        self.previous = None
        self.bucket = None
        self.session = None

    def export(self) -> dict:
        return {"hours": self.hours, "ev_sessions": self.ev_sessions,
                "issued": self.issued, "ledger": self.ledger}

    def demand(self, stamp: float, zone, fallback: float, enabled: bool) -> tuple[float, int]:
        target = datetime.fromtimestamp(stamp, zone)
        values = [h["house_kwh"] for h in self.hours if h.get("house_kwh") is not None
                  and datetime.fromtimestamp(h["start"], zone).hour == target.hour]
        matching = [h["house_kwh"] for h in self.hours if h.get("house_kwh") is not None
                    and datetime.fromtimestamp(h["start"], zone).hour == target.hour
                    and (datetime.fromtimestamp(h["start"], zone).weekday() < 5) == (target.weekday() < 5)]
        values = matching if len(matching) >= 3 else values
        if not enabled or not values:
            return fallback, 0
        # Recent hours carry more weight, but a single spike cannot dominate forever.
        weights = [.9 ** i for i in range(len(values) - 1, -1, -1)]
        return sum(v * w for v, w in zip(values, weights)) / sum(weights), len(values)

    def price_prior(self, hour: int) -> tuple[float | None, int]:
        values = [h["supply"] for h in self.hours if h.get("supply") is not None and h.get("comed_hour") == hour]
        return (median(values), len(values)) if values else (None, 0)

    def solar_quality(self) -> dict:
        samples = [h for h in self.hours if h.get("solar_kwh") is not None and (h.get("solar_forecast") or 0) > .1]
        if len(samples) < 6:
            return {"factor": 1, "samples": len(samples), "mae_kwh": None}
        recent = samples[-168:]
        factor = max(.5, min(1.5, sum(h["solar_kwh"] for h in recent) / sum(h["solar_forecast"] for h in recent)))
        return {"factor": factor, "samples": len(recent),
                "mae_kwh": mean(abs(h["solar_kwh"] - h["solar_forecast"]) for h in recent)}

    def ev_estimate(self, fallback: float) -> float:
        values = sorted(s["kwh_per_percent"] for s in self.ev_sessions)
        return values[min(len(values) - 1, int(len(values) * .8))] if values else fallback

    def ev_power(self, fallback: float, maximum_amps: float) -> float:
        values = sorted(s["kw_per_amp"] * maximum_amps for s in self.ev_sessions if s.get("kw_per_amp"))
        return values[int((len(values) - 1) * .2)] if values else fallback

    def remember_forecast(self, forecast: dict, now: float) -> None:
        # Freeze the latest uncalibrated, age-adjusted outlook BEFORE each hour.
        for stamp, energy in forecast.get("hours", {}).items():
            if float(stamp) >= (int(now // 3600) + 1) * 3600:
                self.issued[stamp] = energy
        self.issued = {k: v for k, v in self.issued.items() if now - 2 * 3600 <= float(k) <= now + 49 * 3600}

    def observe(self, now: float, values: dict, zone) -> None:
        previous, self.previous = self.previous, (now, values.copy())
        if previous is None or not 0 < now - previous[0] <= 180:
            self.bucket = None
            self.session = None
            return
        start, old = previous
        self._ev_session(now, values, old, now - start)
        cuts = sorted(boundaries(start, now, old["_tariffs"], zone)) if old.get("_tariffs") else []
        # Integrate previous sample only; split at real hours and local midnight.
        while start < now:
            hour = int(start // 3600) * 3600
            local_day = datetime.fromtimestamp(start, zone).date()
            midnight = datetime.combine(local_day + timedelta(days=1), datetime.min.time(), zone).timestamp()
            end = min([now, hour + 3600, midnight] + [t for t in cuts if t > start])
            duration = end - start
            if self.bucket is None or self.bucket["start"] != hour:
                if self.bucket:
                    self._finish(zone)
                self.bucket = {"start": hour, "house_kwh": 0, "house_seconds": 0,
                               "solar_kwh": 0, "solar_seconds": 0, "supply_values": []}
            b = self.bucket
            for key in ("house", "solar"):
                if old.get(key + "_kw") is not None:
                    b[key + "_kwh"] += old[key + "_kw"] * duration / 3600
                    b[key + "_seconds"] += duration
            if old.get("supply") is not None:
                b["supply_values"].append(old["supply"])
            day = datetime.fromtimestamp(start, zone).date().isoformat()
            ledger = self.ledger.setdefault(day, {"import_cost": 0, "export_credit": 0, "coverage_hours": 0,
                                                 "import_kwh": 0, "export_kwh": 0, "solar_kwh": 0, "home_kwh": 0, "ev_kwh": 0})
            buying, selling = old.get("import_price"), old.get("export_price")
            if tariff := old.get("_tariffs"):
                supply = period_at(start, tariff["supply_periods"], zone)[0] if tariff["supply_plan"] == "Time-of-use supply" else old.get("supply_price")
                delivery = period_at(start, tariff["delivery_periods"], zone)[0] if tariff["delivery_plan"] == "Time-of-use delivery" else old.get("delivery_price")
                buying = supply + delivery if supply is not None and delivery is not None else None
                selling = export_price(tariff, supply)
            if old.get("grid_kw") is not None and buying is not None and selling is not None:
                bought, sold = max(old["grid_kw"], 0) * duration / 3600, max(-old["grid_kw"], 0) * duration / 3600
                ledger["import_cost"] += bought * buying
                ledger["export_credit"] += sold * selling
                ledger["coverage_hours"] += duration / 3600
                ledger["import_kwh"] += bought
                ledger["export_kwh"] += sold
            for key in ("solar", "home", "ev"):
                if old.get(key + "_kw") is not None:
                    ledger[key + "_kwh"] += old[key + "_kw"] * duration / 3600
            start = end
            if end == hour + 3600:
                self._finish(zone)
                self.bucket = None
        self.ledger = dict(sorted(self.ledger.items())[-62:])

    def _finish(self, zone) -> None:
        b = self.bucket
        from .forecast import COMED_ZONE
        row = {"start": b["start"], "comed_hour": datetime.fromtimestamp(b["start"], COMED_ZONE).hour}
        for key in ("house", "solar"):
            # Only use complete enough hours; scale the covered observation to an hour.
            row[key + "_kwh"] = b[key + "_kwh"] * 3600 / b[key + "_seconds"] if b[key + "_seconds"] >= 2880 else None
        row["supply"] = b["supply_values"][-1] if b["supply_values"] else None
        row["solar_forecast"] = self.issued.get(str(b["start"]))
        self.hours.append(row)
        self.hours = self.hours[-24 * 28:]

    def _ev_session(self, now: float, values: dict, old: dict, elapsed: float) -> None:
        soc, energy = values.get("ev_soc"), values.get("ev_energy")
        if soc is None or energy is None or values.get("ev_kw") is None:
            self.session = None
            return
        if values.get("ev_kw", 0) is not None and values.get("ev_kw", 0) > .2:
            if self.session is None:
                self.session = {"start": now, "soc": soc, "energy": energy, "normalized_energy": 0, "active_hours": 0}
            amps = old.get("ev_amps")
            if amps and amps > 0 and old.get("ev_kw") is not None and old["ev_kw"] > .2:
                self.session["normalized_energy"] += old["ev_kw"] / amps * elapsed / 3600
                self.session["active_hours"] += elapsed / 3600
        elif self.session:
            session, self.session = self.session, None
            delta, used = soc - session["soc"], energy - session["energy"]
            if delta >= 5 and now - session["start"] >= 300 and .1 <= used / delta <= 3:
                rate = session["normalized_energy"] / session["active_hours"] if session["active_hours"] >= (now - session["start"]) / 3600 * .8 else None
                self.ev_sessions.append({"kwh_per_percent": used / delta, "ended": now,
                                         "kw_per_amp": rate if rate and .08 <= rate <= .5 else None})
                self.ev_sessions = self.ev_sessions[-12:]
