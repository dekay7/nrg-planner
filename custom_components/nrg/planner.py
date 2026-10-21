"""Explainable rolling-horizon planning; no networking, HA objects or commands.

Four EV candidates share one chronological battery/cost model. Battery search is
bounded to ~80 energy bins and three native actions, carrying exact physical energy
inside each bin. This is an approximate feasible search, not a global-optimum claim.
"""
from datetime import datetime, timedelta, time
import math

from .config import effective_capacity, cents_rate
from .forecast import price_at
from .tariffs import boundaries as tariff_boundaries


def deadline(now, config, zone, telemetry, previous):
    override = config.get("departure_override")
    if override:
        parsed = datetime.fromisoformat(override)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        if parsed.timestamp() > now or previous.get("departure_override") == override:
            return parsed.timestamp()
    local = datetime.fromtimestamp(now, zone)
    due = datetime.combine(local.date(), time.fromisoformat(config["departure_time"]), zone)
    if due.timestamp() <= now:
        due = datetime.combine(local.date() + timedelta(days=1), time.fromisoformat(config["departure_time"]), zone)
    # Do not move an incomplete connected morning session to tomorrow.
    if (previous.get("connected") and telemetry.get("connected")
            and previous.get("ev_status") not in ("ready", "unplugged", "telemetry_missing", "monitor_only", "not_installed")
            and previous.get("departure_setting") == config["departure_time"]
            and previous.get("departure_override") == override
            and previous.get("deadline", now + 1) <= now):
        return previous["deadline"]
    return due.timestamp()


def in_window(stamp, config, zone):
    current = datetime.fromtimestamp(stamp, zone).time().replace(tzinfo=None)
    start, end = time.fromisoformat(config["ev_start_time"]), time.fromisoformat(config["departure_time"])
    return start <= current < end if start < end else current >= start or current < end


def make_slots(now, config, zone, stats, prices, solar, live, due):
    end = (int(now // 3600) + 48) * 3600
    boundaries = {now, end}
    boundaries.update(range((int(now) // 900 + 1) * 900, end, 900))
    boundaries.update(t for t in (due, due - config["completion_buffer"] * 60) if now < t < end)
    boundaries.update(tariff_boundaries(now, end, config, zone))
    # Include non-quarter-hour configured availability boundaries exactly.
    local = datetime.fromtimestamp(now, zone)
    for day in range(3):
        for key in ("ev_start_time", "departure_time"):
            t = datetime.combine(local.date() + timedelta(days=day), time.fromisoformat(config[key]), zone).timestamp()
            if now < t < end:
                boundaries.add(t)
    boundaries = sorted(boundaries)
    rows = []
    for start, end in zip(boundaries, boundaries[1:]):
        duration = (end - start) / 3600
        house, count = stats.demand(start, zone, config["house_kw"], config["house_learning"])
        hour = str(int(start // 3600) * 3600)
        solar_known = not config["has_solar"] or solar.get("known", {}).get(hour, False)
        price = price_at(start, now, config, prices, live, stats.price_prior)
        # Numerical placeholders keep deadline feasibility calculable. They are
        # separate from actual rates, never displayed as known prices, and cannot
        # authorize discretionary battery moves or price advice.
        model_rates = {}
        for key, flat in (("supply_price", "flat_supply_cents"), ("delivery_price", "delivery_cents")):
            model_rates[key] = price[key]
            if model_rates[key] is None:
                component = "supply" if key == "supply_price" else "delivery"
                rates = [p["rate_cents"] / 100 for p in config.get(component + "_periods", []) if p.get("rate_cents") is not None]
                rates += [p["price"] for p in config.get("_external_" + component, [])]
                fallback = cents_rate(config, flat)
                model_rates[key] = sum(rates) / len(rates) if rates else fallback if fallback is not None else 0.0
        model_import = model_rates["supply_price"] + model_rates["delivery_price"]
        model_export = price["export_price"] if price["export_price"] is not None else 0.0
        rows.append({"start": start, "end": end, "hours": duration,
                     "house_kwh": house * duration, "house_samples": count,
                     "solar_kwh": solar.get("hours", {}).get(hour, 0) * duration if config["has_solar"] else 0,
                     "solar_known": solar_known,
                     "ev_available": start < due and in_window(start, config, zone),
                      "display_import_price": price["import_price"], **price,
                      "_model_import_price": model_import, "_model_export_price": model_export})
    return rows


def allocate(slots, need, power, cutoff, config, kind, all_time=False):
    """A fractional final interval stops at the selected vehicle limit."""
    result = [0.0] * len(slots)
    amps = [0] * len(slots)
    eligible = [i for i, s in enumerate(slots) if s["start"] < cutoff and (all_time or s["ev_available"])]
    if kind == "cheapest":
        eligible.sort(key=lambda i: (not slots[i]["price_known"], slots[i].get("_model_import_price", slots[i]["import_price"]), slots[i]["start"]))
    elif kind == "solar":
        # Direct surplus has the opportunity cost of foregone exports, not zero.
        eligible.sort(key=lambda i: (not slots[i]["price_known"], min(slots[i].get("_model_import_price", slots[i]["import_price"]), max(slots[i].get("_model_export_price", slots[i]["export_price"]), 0))
                                    if slots[i]["solar_known"] and slots[i]["solar_kwh"] > slots[i]["house_kwh"]
                                     else slots[i].get("_model_import_price", slots[i]["import_price"]), slots[i]["start"]))
    elif kind == "latest":
        eligible.reverse()
    for i in eligible:
        slot = slots[i]
        hours = max(min(slot["end"], cutoff) - slot["start"], 0) / 3600
        current = config["ev_max_amps"]
        if kind == "solar" and slot["solar_known"]:
            surplus_kw = max(slot["solar_kwh"] - slot["house_kwh"], 0) / slot["hours"]
            solar_amps = math.floor(surplus_kw / power * config["ev_max_amps"])
            if solar_amps >= config["ev_min_amps"]:
                current = min(current, solar_amps)
        energy = min(need, hours * power * current / config["ev_max_amps"])
        if energy > 1e-8:
            result[i], amps[i] = energy, current
            need = max(need - energy, 0)
    # Solar-current matching must not make the candidate miss a feasible deadline.
    if need > .001 and kind == "solar":
        for i in eligible:
            hours = max(min(slots[i]["end"], cutoff) - slots[i]["start"], 0) / 3600
            extra = min(need, hours * power - result[i])
            if extra > 0:
                result[i] += extra
                amps[i] = config["ev_max_amps"]
                need -= extra
    return result, amps, max(need, 0)


def transition(slot, energy, ev, action, config, capacity, battery_available=True,
               extra=0, target=None):
    """Exact energy balance for one feasible native mode, at the modeled power."""
    eta = (config["round_trip_efficiency"] / 100) ** .5
    reserve = capacity * config["backup_reserve"] / 100
    load = slot["house_kwh"] + ev + extra
    direct = min(slot["solar_kwh"], load)
    deficit, surplus = load - direct, slot["solar_kwh"] - direct
    charge_limit = config["battery_charge_kw"] * slot["hours"]
    solar_charge = min(surplus, charge_limit, max(capacity - energy, 0) / eta) if battery_available and (action != "hold" or config["battery_solar_while_held"]) else 0
    energy += solar_charge * eta
    surplus -= solar_charge
    grid_charge = discharge = 0.0
    if battery_available and action == "charge":
        ceiling = capacity if target is None else min(capacity, target)
        grid_charge = min(max(charge_limit - solar_charge, 0), max(ceiling - energy, 0) / eta)
        energy += grid_charge * eta
    elif battery_available and action == "serve":
        discharge = min(deficit, config["battery_discharge_kw"] * slot["hours"], max(energy - reserve, 0) * eta)
        energy -= discharge / eta
        deficit -= discharge
    # Permissions cannot force battery exports. Native solar curtailment is modeled
    # when exports are disabled/unprofitable; actual dispatch is separately observed.
    export_rate = slot.get("_model_export_price", slot["export_price"])
    import_rate = slot.get("_model_import_price", slot["import_price"])
    exports = surplus if config["export_policy"] != "No exports" and export_rate >= 0 else 0
    imports = deficit + grid_charge
    import_cost, credit = imports * import_rate, exports * export_rate
    wear = discharge * config["battery_wear_cents"] / 100
    return {"energy": energy, "import_kwh": imports, "export_kwh": exports,
            "curtailed_kwh": surplus - exports, "solar_charge_kwh": solar_charge,
            "grid_charge_kwh": grid_charge, "battery_discharge_kwh": discharge,
            "import_cost": import_cost, "export_credit": credit, "wear_cost": wear,
            "cost": import_cost - credit + wear, "action": action}


def replacement_value(slots, config, capacity=None):
    """Value a usable battery's refill, not an unlimited tiny cheap opportunity."""
    eta = (config["round_trip_efficiency"] / 100) ** .5
    opportunities, rates = [], []
    for slot in slots:
        if not slot["price_known"] or not slot.get("export_known", True):
            continue
        quota = config["battery_charge_kw"] * slot["hours"]
        solar = min(max(slot["solar_kwh"] - slot["house_kwh"], 0), quota) if slot["solar_known"] else 0
        credit = max(slot["export_price"], 0) if config["export_policy"] != "No exports" else 0
        if solar:
            opportunities.append((credit / eta, solar * eta))
        grid_rate = max(slot["import_price"], 0) / eta
        rates.append(grid_rate)
        if quota > solar:
            opportunities.append((grid_rate, (quota - solar) * eta))
    need = (config["battery_capacity"] if capacity is None else capacity) * (1 - config["backup_reserve"] / 100)
    if need <= 0:
        return 0
    remaining, cost = need, 0.0
    for rate, amount in sorted(opportunities):
        used = min(remaining, amount)
        cost += used * rate
        remaining -= used
        if remaining <= 1e-8:
            break
    fallback = sum(rates) / len(rates) if rates else 0
    return (cost + remaining * fallback) / need


def battery_search(slots, ev, initial, config, capacity, terminal, available):
    # Node = (cash cost, exact stored energy, parent, transition). Bins only bound
    # search width; no stored energy is ever rounded upwards or created for free.
    step = max(.5, capacity / 80)
    root = (0.0, initial, None, None, 0.0)
    nodes = {int(initial / step): root}
    for slot, car in zip(slots, ev):
        modes = ["hold"]
        if available and slot["solar_known"] and slot["price_known"] and slot.get("export_known", True):
            if not car or not config["hold_battery_for_ev"]:
                modes.append("serve")
            if not car and config.get("allow_grid_charge", True):
                modes.append("charge")
        next_nodes = {}
        for node in nodes.values():
            for action in modes:
                row = transition(slot, node[1], car, action, config, capacity, available)
                key = int((row["energy"] + 1e-9) / step)
                candidate = (node[0] + row["cost"], row["energy"], node, row,
                             node[4] + row["grid_charge_kwh"] + row["battery_discharge_kwh"])
                prior = next_nodes.get(key)
                if prior is None or (round(candidate[0] - candidate[1] * terminal, 9), candidate[4]) < (round(prior[0] - prior[1] * terminal, 9), prior[4]):
                    next_nodes[key] = candidate
        nodes = next_nodes
    winner = min(nodes.values(), key=lambda node: (round(node[0] + (initial - node[1]) * terminal, 9), node[4]))
    score = winner[0] + (initial - winner[1]) * terminal
    rows = []
    while winner[2] is not None:
        rows.append(winner[3])
        winner = winner[2]
    return score, list(reversed(rows))


def replay(slots, ev, actions, initial, config, capacity, terminal, available,
           load_start=None):
    energy, cost = initial, 0.0
    duration = config["flexible_load_minutes"] * 60
    for slot, car, planned in zip(slots, ev, actions):
        overlap = max(min(slot["end"], load_start + duration) - max(slot["start"], load_start), 0) if load_start is not None else 0
        extra = config["flexible_load_kwh"] * overlap / duration
        row = transition(slot, energy, car, planned["action"], config, capacity, available, extra,
                         planned["energy"] if planned["action"] == "charge" else None)
        energy, cost = row["energy"], cost + row["cost"]
    return cost + (initial - energy) * terminal


def household_advice(slots, ev, actions, initial, config, capacity, terminal, available, now):
    duration = config["flexible_load_minutes"] * 60
    # Compare only the contiguous trusted horizon; estimates remain charted but do
    # not compete with published windows or authorize discretionary battery moves.
    end = now
    for slot in slots:
        if not slot["price_known"] or not slot.get("export_known", True):
            break
        end = slot["end"]
    windows = []
    base = replay(slots, ev, actions, initial, config, capacity, terminal, available)
    solar_complete = all(s["solar_known"] for s in slots if s["start"] < end)
    for slot in slots:
        start = slot["start"]
        if start > now + 24 * 3600 or start + duration > end:
            continue
        cost = replay(slots, ev, actions, initial, config, capacity, terminal, available, start) - base
        windows.append({"start": start, "end": start + duration, "cost": round(cost, 6)})
    if not windows:
        return {"category": "limited", "summary": "Waiting for dependable price coverage",
                "reason": "No complete known-price window is available. Configure supply, delivery and export compensation. Locally learned estimates are tentative only.", "windows": []}
    best = min(windows, key=lambda w: (w["cost"], w["start"]))
    current = windows[0] if windows[0]["start"] == now else None
    saving = max(current["cost"] - best["cost"], 0) if current else None
    threshold = config["minimum_saving_cents"] / 100
    category = "wait" if saving is not None and saving > threshold else "normal"
    if category == "normal":
        best = current or best
        if max(w["cost"] for w in windows) - best["cost"] > threshold:
            category = "good"
    summary = ("Wait until " + datetime.fromtimestamp(best["start"], config["zone"]).strftime("%a %-I:%M %p")
               if category == "wait" else "Good time to use energy" if category == "good" else "Use energy as usual")
    trusted = solar_complete and (not config["has_battery"] or available) and not config.get("_ev_duration_unknown")
    included = ["grid prices", "typical home demand"]
    if config["has_solar"]:
        included.append("solar forecast" if solar_complete else "limited solar information")
    if config["has_battery"]:
        included.append("battery plan" if available else "battery's own controller (not scheduled by NRG)")
    if config["has_ev"]:
        included.append("unknown EV charging duration" if config.get("_ev_duration_unknown") else "EV schedule" if config["ev_control"] else "observed EV charging")
    basis = ", ".join(included).capitalize() + " considered"
    accounting = " Export credits are included." if config["has_solar"] else ""
    accounting += " Remaining battery energy is valued, not treated as free." if available else ""
    return {"category": category, "summary": summary,
            "reason": f"{basis}. Compare {config['flexible_load_kwh']:g} kWh over {config['flexible_load_minutes']:g} minutes.{accounting}",
            "best_start": best["start"], "best_end": best["end"], "now_cost": current["cost"] if current else None,
            "best_cost": best["cost"], "saving": saving, "confidence": "forecast" if trusted else "limited",
            "windows": windows, "forecast_until": end}


def plan(now, config, zone, telemetry, stats, prices, solar, live=None, previous=None, charge_now=False):
    battery_model = stats.battery.model(config, now)
    config = config | battery_model | {"zone": zone}
    previous = previous or {}
    managed_ev = config["has_ev"] and config["ev_control"]
    due = deadline(now, config, zone, telemetry, previous) if managed_ev else now + 48 * 3600
    slots = make_slots(now, config, zone, stats, prices, solar, live, due)
    capacity = effective_capacity(config, datetime.fromtimestamp(now, zone).date()) if config["has_battery"] else 0
    soc = telemetry.get("battery_soc") if config["has_battery"] else None
    available = config["has_battery"] and config["battery_control"] and soc is not None and telemetry.get("battery_ready", False)
    config["allow_grid_charge"] = telemetry.get("can_grid_charge", True)
    initial = capacity * soc / 100 if soc is not None else 0
    ev_soc, limit = telemetry.get("ev_soc"), telemetry.get("ev_limit")
    energy_per_point = stats.ev_estimate(config["ev_kwh_per_percent"]) if config["ev_learning"] else config["ev_kwh_per_percent"]
    need = max(limit - ev_soc, 0) * energy_per_point if config["has_ev"] and ev_soc is not None and limit is not None else None
    config["_ev_duration_unknown"] = config["has_ev"] and need is None and (telemetry.get("ev_busy") is True or (telemetry.get("ev_kw") or 0) > .2)
    if config["_ev_duration_unknown"] and config["hold_battery_for_ev"]:
        available = False
    connected = config["has_ev"] and telemetry.get("connected", False)
    power = stats.ev_power(config["ev_kw_at_max"], config["ev_max_amps"]) if config["ev_learning"] else config["ev_kw_at_max"]
    cutoff = due - config["completion_buffer"] * 60
    normal_hours = sum(s["hours"] for s in slots if s["ev_available"] and s["end"] <= cutoff)
    if need is not None and normal_hours * power < need:
        cutoff = due
    all_time = bool(charge_now or due <= now or (need is not None and normal_hours * power < need))
    urgent = bool(need and now + need / power * 3600 >= due - config["completion_buffer"] * 60)
    forced = charge_now or urgent or due <= now
    candidates = []
    if not managed_ev:
        # Extrapolate only an already observed charge to its known target. This
        # is a background load, not permission to command the vehicle.
        remaining = need or 0
        observed = max(telemetry.get("ev_kw") or 0, 0) if config["has_ev"] else 0
        ev = []
        for slot in slots:
            amount = min(remaining, observed * slot["hours"])
            ev.append(amount)
            remaining -= amount
        candidates.append(("observed EV" if any(ev) else "household", ev, [0] * len(slots), 0))
    elif not connected or need is None or need <= .001:
        candidates.append(("none", [0.0] * len(slots), [0] * len(slots), need or 0))
    else:
        for kind in (["earliest"] if forced else ["cheapest", "solar", "earliest", "latest"]):
            ev, amps, missing = allocate(slots, need, power, max(due, slots[-1]["end"]) if charge_now or due <= now else cutoff, config, kind, all_time)
            candidates.append((kind, ev, amps, missing))
        # Previous schedule competes only after revalidating deadline, availability,
        # current limits and needed energy against today's telemetry.
        old = previous.get("slots", [])
        if not forced and old and previous.get("deadline") == due:
            ev, amps = [], []
            remaining = need
            for slot in slots:
                prior = next((s for s in old if s["start"] <= slot["start"] < s["end"]), {})
                current = min(prior.get("ev_amps", 0), config["ev_max_amps"])
                usable = slot["ev_available"] and slot["end"] <= cutoff and current >= config["ev_min_amps"]
                amount = min(remaining, slot["hours"] * power * current / config["ev_max_amps"]) if usable else 0
                ev.append(amount); amps.append(current if amount else 0)
                remaining -= amount
            if remaining <= .001:
                candidates.append(("previous", ev, amps, 0))
    terminal = replacement_value(slots, config, capacity)
    outcomes = []
    for name, ev, amps, missing in candidates:
        score, actions = battery_search(slots, ev, initial, config, capacity, terminal, available)
        unknown = sum(e for e, slot in zip(ev, slots) if not slot["price_known"])
        outcomes.append({"name": name, "ev": ev, "amps": amps, "missing": missing, "unknown": unknown, "score": score, "actions": actions})
    best = min(outcomes, key=lambda o: (round(o["missing"], 3), round(o["unknown"], 3), o["score"]))
    old = next((o for o in outcomes if o["name"] == "previous" and o["missing"] <= best["missing"] + .001), None)
    if old and old["unknown"] <= best["unknown"] + .001 and old["score"] - best["score"] <= config["minimum_saving_cents"] / 100:
        best = old
    for slot, ev, amps, action in zip(slots, best["ev"], best["amps"], best["actions"]):
        slot.update(ev_kwh=ev, ev_amps=amps, battery_action=action["action"],
                     battery_soc=round(action["energy"] / capacity * 100, 2) if capacity and available else None,
                    import_kwh=action["import_kwh"], export_kwh=action["export_kwh"],
                      cost=action["import_cost"] - action["export_credit"] if slot["price_known"] and slot["export_known"] else None)
        slot["ev_stop_at"] = slot["start"] + ev / (power * amps / config["ev_max_amps"]) * 3600 if amps else None
    active = [s for s in slots if s["ev_kwh"] > .001]
    ev_status = ("not_installed" if not config["has_ev"] else "monitor_only" if not managed_ev else "unplugged" if not connected else "telemetry_missing" if need is None else "ready" if need <= .001
                 else "blocked" if not telemetry.get("ev_ready", True)
                 else "charge_now" if charge_now else "deadline" if urgent or due <= now
                 else "charging" if slots[0]["ev_kwh"] else "waiting")
    first = slots[0]
    next_charge = active[0]["start"] if active and managed_ev else None
    completion = active[-1]["start"] + active[-1]["ev_kwh"] / (power * active[-1]["ev_amps"] / config["ev_max_amps"]) * 3600 if active and managed_ev else None
    advice = household_advice(slots, best["ev"], best["actions"], initial, config, capacity, terminal, available, now)
    reasons = {"charge": "Buy lower-cost energy for later use after losses and export credits are considered.",
               "serve": "Use stored energy for the home rather than buy at this hour's price.",
               "hold": "Keep stored energy for a more valuable hour or preserve backup reserve."}
    battery_reason = reasons[first["battery_action"]]
    if not config["has_battery"]:
        battery_reason = "No home battery is configured; use the grid/solar outlook."
    elif not config["battery_control"]:
        battery_reason = "Battery monitoring only; its own controller decides when it charges or supplies the home."
    elif not available:
        issues = telemetry.get("guard_issues", [])
        if issues:
            battery_reason = "Battery forecast unavailable: " + "; ".join(
                f"{issue['name']} ({issue['entity_id']}) is {issue['state']}; expected {issue['expected']}" for issue in issues) + "."
        elif soc is None:
            battery_reason = "Battery forecast unavailable: battery charge percentage is missing, invalid or stale."
        elif telemetry.get("battery_controls_ready") is False:
            battery_reason = "Battery forecast unavailable: battery mode feedback or compatible hold/serve options are missing."
        elif config["_ev_duration_unknown"] and config["hold_battery_for_ev"]:
            battery_reason = "Battery forecast unavailable: an active EV session has unknown charging duration."
        else:
            battery_reason = "Battery telemetry or native-event readiness is incomplete; no discretionary battery action."
    elif first["ev_kwh"] and config["hold_battery_for_ev"]:
        battery_reason = "Ask the home battery to save its energy while the EV charges."
    if available and (not first["price_known"] or not first["export_known"] or not first["solar_known"]):
        battery_reason = "Current forecast coverage is incomplete; keep discretionary grid charging off."
    # Do not publish feasibility-only numerical placeholders as tariff data.
    for slot in slots:
        slot.pop("_model_import_price", None)
        slot.pop("_model_export_price", None)
    has_known_cost = any(s["price_known"] and s["export_known"] for s in slots)
    return {"version": 2, "generated_at": now, "expires_at": now + 420,
            "deadline": due if managed_ev else None, "departure_setting": config["departure_time"],
            "departure_override": config.get("departure_override"), "connected": connected,
            "ev_status": ev_status, "ev_needed_kwh": need, "ev_shortfall_kwh": best["missing"] if managed_ev else None,
            "next_charge": next_charge, "completion": completion,
            "ev_amps": first["ev_amps"],
            "ev_stop_at": first["start"] + first["ev_kwh"] / (power * first["ev_amps"] / config["ev_max_amps"]) * 3600 if first["ev_amps"] else None,
            "battery_action": first["battery_action"], "battery_reason": battery_reason, "battery_forecast_available": available,
            "battery_target_soc": first["battery_soc"], "effective_capacity_kwh": capacity,
            "battery_model": battery_model,
            "terminal_value": terminal, "selected_candidate": best["name"],
             "candidate_costs": [{"name": o["name"], "modeled_cost": round(o["score"], 4) if has_known_cost else None, "shortfall_kwh": o["missing"]} for o in outcomes],
             "modeled_cost": best["score"] if has_known_cost else None, "household": advice, "slots": slots,
            "components": {"solar": config["has_solar"], "battery": config["has_battery"], "ev": config["has_ev"]},
             "cost_includes_estimates": any(not s["price_known"] or not s["export_known"] for s in slots),
            "export_capability": "Permission only; timed stored-battery exports are not commanded or credited in the model."}
