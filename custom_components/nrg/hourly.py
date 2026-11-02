"""Read-only hourly presentation of selected slots; no dispatch or price decisions.

Energy is prorated using the planner's interval-average model. Action windows retain
exact boundaries (including fractional EV stops); they are not power measurements.
"""
from datetime import datetime, timedelta, time

from .config import finite
from .tariffs import clock_changes, wall_instants

FLOWS = ("import_kwh", "solar_kwh", "battery_discharge_kwh", "house_kwh", "ev_kwh",
         "solar_charge_kwh", "grid_charge_kwh", "export_kwh", "curtailed_kwh")
BATTERY_FLOWS = ("battery_discharge_kwh", "solar_charge_kwh", "grid_charge_kwh")
SITE_FLOWS = ("import_kwh", "export_kwh", "curtailed_kwh", *BATTERY_FLOWS)
ACTIONS = {"hold": "Save battery", "serve": "Supply home", "charge": "Charge from grid"}


def interval_label(start, end, zone):
    """Both dates and offsets matter across midnight and repeated clock hours."""
    a, b = (datetime.fromtimestamp(t, zone) for t in (start, end))
    if a.date() == b.date() and a.utcoffset() == b.utcoffset():
        return f"{a:%a %d %b %Y %H:%M}–{b:%H:%M %Z %z}"
    return f"{a:%a %d %b %Y %H:%M %Z %z} – {b:%a %d %b %Y %H:%M %Z %z}"


def hour_boundaries(start, end, zone):
    points = {start, end} | clock_changes(start, end, zone)
    first = datetime.fromtimestamp(start, zone).date()
    last = datetime.fromtimestamp(end, zone).date()
    for offset in range((last - first).days + 1):
        day = first + timedelta(days=offset)
        for hour in range(24):
            points.update(t for t in wall_instants(datetime.combine(day, time(hour)), zone) if start < t < end)
    return sorted(points)


def append_period(periods, start, end, **values):
    """Coalesce equal adjacent actions without erasing real changes or gaps."""
    if periods and periods[-1]["end"] == start and all(periods[-1][k] == v for k, v in values.items()):
        periods[-1]["end"] = end
    else:
        periods.append({"start": start, "end": end, **values})


def hourly_plan(plan, zone, now):
    """A bounded projection for sensor attributes, chart columns and native details.

    Never mutate the command plan. Incomplete whole-site forecasts have null site
    flows, while independent demand/solar values remain inspectable in details.
    """
    empty = {"status": "waiting", "timezone": str(zone), "rows": [], "next_actions": []}
    if not isinstance(plan, dict):
        return empty | {"reason": "Waiting for a fresh home energy plan."}
    expires = finite(plan.get("expires_at"))
    generated = finite(plan.get("generated_at"))
    if expires is None or generated is None or expires <= now:
        return empty | {"reason": "Waiting for a fresh home energy plan."}
    slots = plan.get("slots")
    if not isinstance(slots, list) or not slots:
        return empty | {"reason": "Waiting for dated energy intervals."}
    # Older/malformed payloads must not turn missing component metadata into zeros.
    components = plan.get("components", {})
    if not isinstance(components, dict) or any(not isinstance(components.get(k), bool) for k in ("solar", "battery", "ev")):
        return empty | {"reason": "Energy-plan details unavailable; update the integration and dashboard together."}
    previous_end = None
    dated = []
    for slot in slots:
        if not isinstance(slot, dict):
            return empty | {"reason": "Energy intervals unavailable."}
        a, b = finite(slot.get("start")), finite(slot.get("end"))
        if a is None or b is None or b <= a or (previous_end is not None and a < previous_end):
            return empty | {"reason": "Energy intervals unavailable or overlapping."}
        previous_end = b
        dated.append(slot | {"start": a, "end": b})
    slots = dated
    start, end = max(now, generated, slots[0]["start"]), min(now + 86400, slots[-1]["end"])
    if end <= start:
        return empty | {"reason": "Waiting for future energy intervals."}
    battery_ok = not components["battery"] or plan.get("battery_forecast_available") is True
    ev_ok = not components["ev"] or plan.get("ev_forecast_available") is True
    fallback = plan.get("fallback_active") is True
    economic_until = finite(plan.get("economic_until"), start)
    rows, battery_events, ev_events = [], [], []
    # Build complete EV runs before slicing hours: an hour boundary is NOT a
    # charging stop. Retain the actual selected run end even beyond the graph.
    if components["ev"] and ev_ok:
        for slot in slots:
            amps, stop = finite(slot.get("ev_amps")), finite(slot.get("ev_stop_at"))
            left = max(start, slot["start"])
            if amps is not None and amps > 0 and stop is not None and min(slot["end"], stop) > left:
                append_period(ev_events, left, min(slot["end"], stop), amps=amps)
    edges = hour_boundaries(start, end, zone)
    # Unknown solar earlier in the plan also invalidates later stored-energy flows.
    solar_gap = None
    if components["battery"] and components["solar"]:
        solar_gap = next((s["start"] for s in slots if s.get("solar_known") is not True), None)
    for a, b in zip(edges, edges[1:]):
        row = {"start": a, "end": b, "label": interval_label(a, b, zone),
               "minutes": (b - a) / 60, **{key: 0.0 for key in FLOWS}, "battery_soc": None,
               "periods": [], "reasons": []}
        covered = 0.0
        for index, slot in enumerate(slots):
            left, right = max(a, slot["start"]), min(b, slot["end"])
            if right <= left:
                continue
            duration = slot["end"] - slot["start"]
            weight = (right - left) / duration
            covered += right - left
            reasons = []
            if not battery_ok:
                reasons.append(plan.get("battery_reason") or "Battery forecast unavailable.")
            if not ev_ok:
                reasons.append("EV charging outlook unavailable; check connection, target, power and controls.")
            solar_ok = not components["solar"] or slot.get("solar_known") is True
            if not solar_ok:
                reasons.append("Solar forecast coverage is missing.")
            if solar_gap is not None and right > solar_gap:
                reasons.append("Battery trajectory crosses missing solar coverage.")
            stop, amps = finite(slot.get("ev_stop_at")), finite(slot.get("ev_amps"))
            clipped_ev = (components["ev"] and ev_ok and amps is not None and amps > 0 and stop is not None
                          and slot["start"] < stop < slot["end"]
                          and (left > slot["start"] or right < slot["end"]))
            if clipped_ev:
                # The selected whole-slot balance does not locate its non-EV
                # flows around a fractional stop. Don't fabricate that split.
                reasons.append("Partial EV completion interval; remaining site flows await a new plan.")
            for key in FLOWS:
                absent = ((key in BATTERY_FLOWS and not components["battery"])
                          or (key in ("solar_kwh", "solar_charge_kwh", "export_kwh", "curtailed_kwh") and not components["solar"])
                          or (key == "ev_kwh" and not components["ev"]))
                value = 0.0 if absent else finite(slot.get(key))
                if value is None or value < 0:
                    row[key] = None
                    reasons.append("Energy-flow details unavailable; refresh the integration and dashboard together.")
                elif row[key] is not None:
                    fraction = max(min(right, stop) - left, 0) / (stop - slot["start"]) if key == "ev_kwh" and clipped_ev else weight
                    row[key] += value * fraction
            if not solar_ok:
                row["solar_kwh"] = None
            if not ev_ok:
                row["ev_kwh"] = None
            if reasons:
                for key in SITE_FLOWS:
                    row[key] = None
                row["reasons"].extend(r for r in reasons if r not in row["reasons"])
            action = slot.get("battery_action") if components["battery"] and battery_ok and not reasons else None
            if components["battery"] and battery_ok and not reasons and action not in ACTIONS:
                row["reasons"].append("Battery action unavailable.")
                for key in SITE_FLOWS:
                    row[key] = None
                action = None
            # SOC is end-of-slot. Interpolate between modeled endpoints, never average.
            if action is not None:
                initial_soc = plan.get("battery_initial_soc") if index == 0 else slots[index - 1].get("battery_soc")
                initial_soc, final_soc = finite(initial_soc), finite(slot.get("battery_soc"))
                row["battery_soc"] = (initial_soc + (final_soc - initial_soc) * (right - slot["start"]) / duration
                                      if initial_soc is not None and final_soc is not None else None)
                append_period(battery_events, left, right, action=action)
            else:
                row["battery_soc"] = None
            coverage = "fallback" if fallback else "economic" if right <= economic_until else "outlook"
            # Split the explanation at the economic boundary even for older slots.
            cut = economic_until if not fallback and left < economic_until < right else right
            append_period(row["periods"], left, cut, battery=action, coverage="economic" if cut < right else coverage)
            if cut < right:
                append_period(row["periods"], cut, right, battery=action, coverage="outlook")
        if abs(covered - (b - a)) > .001:
            row["reasons"].append("Dated plan coverage is incomplete.")
            for key in FLOWS:
                row[key] = None
            row["battery_soc"] = None
        row["complete"] = not row["reasons"]
        if not row["complete"]:
            row["battery_soc"] = None
        row["battery_charge_kwh"] = (row["solar_charge_kwh"] + row["grid_charge_kwh"]
                                     if row["solar_charge_kwh"] is not None and row["grid_charge_kwh"] is not None else None)
        for period in row["periods"]:
            period["label"] = interval_label(period["start"], period["end"], zone)
        rows.append(row)
    for row in rows:
        row["ev_windows"] = [{**event, "start": max(row["start"], event["start"]), "end": min(row["end"], event["end"]),
                              "label": interval_label(max(row["start"], event["start"]), min(row["end"], event["end"]), zone),
                              "stop_label": datetime.fromtimestamp(event["end"], zone).strftime("%a %d %b %Y %H:%M %Z %z")}
                             for event in ev_events if event["start"] < row["end"] and event["end"] > row["start"]]
    next_actions = [{"start": e["start"], "text": interval_label(e["start"], e["end"], zone) + ": " + ACTIONS[e["action"]]} for e in battery_events[:2]]
    next_actions += [{"start": e["start"], "text": interval_label(e["start"], e["end"], zone) + f": EV charging at {e['amps']:g} A"} for e in ev_events[:1] if e["start"] < end]
    return {"status": "ready" if all(r["complete"] for r in rows) else "partial", "timezone": str(zone),
            "start": start, "end": end, "as_of": now, "generated_at": generated, "rows": rows,
            "ev_basis": "Observed EV charging extrapolation" if plan.get("ev_status") == "monitor_only" else "Selected EV schedule",
            "next_actions": sorted(next_actions, key=lambda e: e["start"]),
            "fallback_active": fallback}
