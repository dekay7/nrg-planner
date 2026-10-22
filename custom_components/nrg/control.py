"""One guarded writer, independent of vehicle/battery manufacturer or integration."""
import asyncio
import logging
import time

from .adapters import Adapters
from .config import finite
from .const import option_label

_LOGGER = logging.getLogger(__name__)


class Controller:
    def __init__(self, runtime):
        self.runtime, self.hass = runtime, runtime.hass
        self.adapters = Adapters(runtime)
        self.lock, self.last = asyncio.Lock(), {}
        self.status = "Observation: no equipment commands"
        self.fallback_results = {}

    def owned(self):
        return not getattr(self.runtime, "_closing", False) and self.runtime.config["mode"] == "Control"

    def enabled(self, device):
        config = self.runtime.config
        return config["has_" + device] and config[device + "_control"]

    def valid_plan(self, revision):
        return self.owned() and revision == self.runtime.revision and self.runtime.plan.get("expires_at", 0) > time.time()

    def plan_now(self):
        planned = self.runtime.plan
        rows = planned.get("slots", [])
        row = next((s for s in rows if s["start"] <= time.time() < s["end"]), None)
        if row is None:
            return planned
        return planned | {"ev_amps":row["ev_amps"], "ev_stop_at":row.get("ev_stop_at"),
                          "battery_action":row["battery_action"], "battery_target_soc":row["battery_soc"],
                          "_slot_price_known":row["price_known"], "_slot_export_price":row["export_price"] if row.get("export_known",row["price_known"]) else None}

    def fallback_context(self):
        evaluate = getattr(self.runtime, "evaluate_fallback", None)
        return evaluate(publish=True) if evaluate else {}

    def price_known_now(self):
        context = self.fallback_context()
        current = context.get("price_known", self.runtime.current_price_known)
        known = current and self.plan_now().get("_slot_price_known", True)
        if self.runtime.config["supply_plan"] == "Hourly ComEd":
            known = known and int(getattr(self.runtime,"last_sample_at",time.time()) // 3600) == int(time.time() // 3600)
        return known

    def fallback_ev_plan(self):
        plan = self.plan_now()
        return plan | {"ev_amps": 0} if self.runtime.config["fallback_ev"] == "Pause scheduled charging" else plan

    def ev_busy(self, snapshot, plan):
        busy = snapshot["ev_busy"] is not False if "ev_busy" in snapshot else snapshot.get("ev_kw", 0) is None or snapshot.get("ev_kw", 0) > .2
        return self.runtime.config["has_ev"] and (busy or plan.get("ev_amps", 0) > 0
            or self.runtime.charge_now and snapshot.get("connected"))

    async def set(self, key, action, revision, *, revoke=False, fallback=False):
        context = self.fallback_context()
        if not self.owned() or revision != self.runtime.revision:
            raise RuntimeError("Controller ownership or plan changed during command")
        if not self.enabled("ev" if key.startswith("ev_") else "battery"):
            raise RuntimeError("Equipment control is no longer enabled")
        snapshot = self.runtime.snapshot()
        if not snapshot["native_ready"]:
            raise RuntimeError("Yielding to a configured grid/protection/ownership guard")
        emergency = (self.runtime.charge_now and self.enabled("ev") and snapshot.get("ev_ready")
                     and snapshot.get("ev_soc", 100) < snapshot.get("ev_limit", 0)
                     and (key in ("ev_current", "ev_charge") or key == "battery_mode" and action == "hold"))
        fallback_serve = (fallback and context.get("active") and key == "battery_mode" and action == "serve"
                          and self.runtime.config["fallback_battery"] == "Self-consumption")
        if context.get("active"):
            if key == "ev_charge" and action == "on" and not emergency:
                if self.runtime.config["fallback_ev"] == "Pause scheduled charging":
                    raise RuntimeError("Price-data fallback pauses scheduled EV charging")
            if (key == "battery_grid_charge" and action == "on"
                    or key == "battery_mode" and action in ("charge", "serve") and not fallback_serve):
                raise RuntimeError("Price-data fallback revoked that battery action")
        if context.get("active") and key == "battery_reserve":
            native = self.adapters.state(key)
            current_reserve = finite(native.state) if native else None
            if current_reserve is None or finite(action) is None or action < current_reserve:
                raise RuntimeError("Fallback cannot lower an existing or unknown battery reserve")
        if not revoke and not emergency and not fallback_serve and not self.valid_plan(revision):
            raise RuntimeError("Plan expired before command")
        active = self.plan_now()
        if not emergency and key == "ev_charge" and action == "on" and (not active.get("ev_amps") or (active.get("ev_stop_at") or 0) <= time.time()):
            raise RuntimeError("The current charging interval ended before the start command")
        if key == "battery_grid_charge" and action == "on" and (active.get("battery_action") != "charge" or not self.price_known_now()):
            raise RuntimeError("The current interval no longer permits battery grid charging")
        if key == "battery_mode" and action in ("serve", "charge") and not fallback_serve and (active.get("battery_action") != action or not self.price_known_now()):
            raise RuntimeError("The current interval no longer permits that battery action")
        if (key == "battery_grid_charge" and action == "on") or (key == "battery_mode" and action in ("serve", "charge")):
            config = self.runtime.config
            if not snapshot.get("battery_ready") or snapshot.get("battery_soc") is None:
                raise RuntimeError("Battery control/feedback is no longer ready")
            busy = self.ev_busy(snapshot, self.fallback_ev_plan() if fallback_serve else active)
            if action in ("on", "charge"):
                target = finite(active.get("battery_target_soc"))
                if (busy or not snapshot.get("can_grid_charge", True) or target is None
                        or snapshot["battery_soc"] >= target - .3):
                    raise RuntimeError("Battery grid charging is no longer permitted by current readings")
            elif snapshot["battery_soc"] <= config["backup_reserve"] + .3 or config["hold_battery_for_ev"] and busy:
                raise RuntimeError("Battery discharge is no longer permitted by current readings")
        if fallback_serve:
            reserve_state = self.adapters.state("battery_reserve")
            native_reserve = snapshot.get("battery_native_reserve", finite(reserve_state.state)) if reserve_state else None
            if reserve_state is not None and native_reserve is None:
                raise RuntimeError("Native battery reserve feedback is unavailable")
            if snapshot["battery_soc"] <= max(self.runtime.config["backup_reserve"], native_reserve or 0) + .3:
                raise RuntimeError("Battery is at its retained reserve")
        if self.adapters.matches(key, action):
            return
        await self.adapters.write(key, action)
        self.last[key] = time.time()
        for _ in range(15):
            if not self.owned() or revision != self.runtime.revision:
                raise RuntimeError("Ownership or plan changed while waiting for device readback")
            if self.adapters.matches(key, action):
                return
            await asyncio.sleep(1)
        raise RuntimeError(f"{key}: no matching readback within 15 seconds")

    async def revoke_battery(self, revision):
        if not self.enabled("battery"):
            return
        if self.adapters.can("battery_grid_charge", "off"):
            await self.set("battery_grid_charge", "off", revision, revoke=True)
        elif self.adapters.can("battery_mode", "hold"):
            # Devices with a distinct force-charge mode stop charging by leaving it.
            await self.set("battery_mode", "hold", revision, revoke=True)

    async def apply(self):
        if self.lock.locked():
            return
        async with self.lock:
            if not self.owned():
                self.fallback_results = {}
                self.status = "Observation: no equipment commands"
                return
            if not self.enabled("ev") and not self.enabled("battery"):
                self.status = "Monitoring: no device is enabled for NRG control"
                return
            context = self.fallback_context()
            revision, errors = self.runtime.revision, []
            self.fallback_results = {}
            if not self.runtime.snapshot()["native_ready"]:
                self.status = "Yielding to a configured protection guard or missing guard reading"
                return
            if context.get("active"):
                await self._fallback(revision)
                return
            if not self.valid_plan(revision):
                for device in ("battery", "ev"):
                    if not self.enabled(device):
                        continue
                    try:
                        if device == "battery":
                            await self.revoke_battery(revision)
                        elif self.runtime.charge_now:
                            await self._ev(revision, self.runtime.snapshot())
                        else:
                            await self._stop_ev_if_home(revision, self.runtime.snapshot())
                    except Exception as error:
                        errors.append(f"{device}: {error}")
                        _LOGGER.warning("NRG stale-plan handling (%s): %s", device, error)
                self.status = "; ".join(errors) if errors else (
                    "Charge-now request without price data" if self.runtime.charge_now else "Stale plan: previous charging requests revoked where supported")
                return
            for device, action in (("battery", self._battery), ("ev", self._ev)):
                if not self.enabled(device):
                    continue
                try:
                    await action(revision, self.runtime.snapshot())
                except (RuntimeError, ValueError, TimeoutError) as error:
                    errors.append(f"{device}: {error}")
                except Exception as error:
                    errors.append(f"{device}: service failed ({type(error).__name__})")
                    _LOGGER.exception("NRG %s service failed", device)
            self.status = "; ".join(errors) if errors else "Control: supported requests acknowledged; see measured response"

    async def _fallback(self, revision):
        """One writer; either device can fail without blocking the other's attempt."""
        self.fallback_results = {}
        for device in ("ev", "battery"):
            if not self.enabled(device):
                self.fallback_results[device] = {"requested": "None", "result": "Monitoring only / not installed"}
                continue
            policy = self.runtime.config["fallback_" + device]
            self.fallback_results[device] = {"requested": option_label("fallback_" + device, policy), "result": "Pending"}
            try:
                snapshot = self.runtime.snapshot()
                if device == "ev":
                    if self.runtime.charge_now or policy == "Maintain departure readiness":
                        if not self.runtime.charge_now and not self.valid_plan(revision):
                            await self._stop_ev_if_home(revision, snapshot)
                            result = "Waiting for a fresh departure plan"
                        else:
                            await self._ev(revision, snapshot)
                            result = "Charge now override; price may be unknown" if self.runtime.charge_now else "Following departure plan; price may be unknown"
                    else:
                        await self._stop_ev_if_home(revision, snapshot, force=True)
                        if snapshot.get("connected") and (not self.adapters.matches("ev_charge", "off")
                                or self.runtime.snapshot().get("ev_busy") is True):
                            raise RuntimeError("EV stop not yet acknowledged / charging still measured")
                        result = "Pause acknowledged" if snapshot.get("connected") else "Not connected at home; no command"
                else:
                    result = await self._fallback_battery(revision, snapshot)
                self.fallback_results[device]["result"] = result
            except Exception as error:
                self.fallback_results[device]["result"] = f"Failed: {type(error).__name__}: {error}"
        failures = [device for device, value in self.fallback_results.items() if value["result"].startswith("Failed")]
        self.status = "Price-data fallback active; " + (
            "failed devices: " + ", ".join(failures) if failures else "requests checked") + ". See Pricing health for device results."
        if self.runtime.charge_now:
            self.status += "; Charge now overrides the scheduled-charging pause"

    async def _fallback_battery(self, revision, snapshot):
        await self.revoke_battery(revision)
        # A separate permission switch does not necessarily exit force-charge mode.
        if self.adapters.matches("battery_mode", "charge") and not self.adapters.matches("battery_mode", "hold"):
            await self.set("battery_mode", "hold", revision, revoke=True)
        snapshot = self.runtime.snapshot()
        if not snapshot.get("battery_ready"):
            if self.adapters.can("battery_mode", "hold"):
                await self.set("battery_mode", "hold", revision, revoke=True)
            raise RuntimeError("Grid charging revoked where supported; battery feedback/control is not ready")
        config = self.runtime.config
        reserve = config["backup_reserve"]
        reserve_state = self.adapters.state("battery_reserve")
        if reserve_state is not None:
            current_reserve = snapshot.get("battery_native_reserve", finite(reserve_state.state))
            if current_reserve is None:
                await self.set("battery_mode", "hold", revision, revoke=True)
                raise RuntimeError("Cannot verify native battery reserve")
            reserve = max(reserve, current_reserve)
            if self.adapters.can("battery_reserve", reserve):
                await self.set("battery_reserve", reserve, revision, revoke=True)
            elif current_reserve < reserve:
                raise RuntimeError("Cannot establish configured battery reserve")
        busy = self.ev_busy(self.runtime.snapshot(), self.fallback_ev_plan())
        if self.fallback_results.get("ev", {}).get("result", "").startswith("Failed"):
            busy = True
        serve = (config["fallback_battery"] == "Self-consumption" and snapshot["battery_soc"] > reserve + .3
                 and not (config["hold_battery_for_ev"] and busy))
        export = "No exports" if config["export_policy"] == "No exports" else "Solar only"
        if self.adapters.can("battery_export", export):
            await self.set("battery_export", export, revision, revoke=True)
        await self.set("battery_mode", "serve" if serve else "hold", revision, revoke=not serve, fallback=serve)
        return "Self-consumption acknowledged; reserve retained" if serve else "Battery hold acknowledged; grid charging revoked where supported"

    async def _battery(self, revision, snapshot):
        config, plan = self.runtime.config, self.plan_now()
        if not snapshot["battery_ready"]:
            await self.revoke_battery(revision)
            raise RuntimeError("Battery control/feedback is not ready")
        busy = self.ev_busy(snapshot, plan)
        action = "hold" if config["has_ev"] and config["hold_battery_for_ev"] and busy else plan["battery_action"]
        if not self.price_known_now():
            action = "hold"
        if snapshot["battery_soc"] <= config["backup_reserve"] + .3 and action == "serve":
            action = "hold"
        target = plan["battery_target_soc"]
        grid = (action == "charge" and not busy and snapshot["battery_soc"] < target - .3
                and self.price_known_now() and snapshot.get("can_grid_charge", True))
        if not grid and self.adapters.can("battery_grid_charge", "off"):
            await self.set("battery_grid_charge", "off", revision)
        if not grid and self.adapters.matches("battery_mode", "charge") and not self.adapters.matches("battery_mode", "hold"):
            await self.set("battery_mode", "hold", revision)
        if time.time() - self.last.get("battery_attempt", 0) < 120:
            return
        self.last["battery_attempt"] = time.time()
        if self.adapters.can("battery_grid_charge", "off"):
            await self.set("battery_grid_charge", "off", revision)
        if self.adapters.can("battery_reserve", config["backup_reserve"]):
            await self.set("battery_reserve", config["backup_reserve"], revision)
        await self.set("battery_mode", "charge" if grid else "serve" if action == "serve" else "hold", revision)
        export_price = plan.get("_slot_export_price", self.runtime.live_export)
        export = "No exports" if export_price is not None and export_price < 0 else config["export_policy"]
        if self.adapters.can("battery_export", export):
            await self.set("battery_export", export, revision)
        if grid and self.adapters.can("battery_grid_charge", "on"):
            fresh = self.runtime.snapshot()
            if config["has_ev"] and (fresh.get("ev_busy") or self.runtime.plan.get("ev_amps", 0)):
                raise RuntimeError("EV became active before the battery charging request")
            if fresh.get("battery_soc") is not None and fresh["battery_soc"] < target - .3:
                await self.set("battery_grid_charge", "on", revision)

    async def _stop_ev_if_home(self, revision, snapshot, *, force=False):
        if (snapshot.get("connected") and (force or time.time() - self.last.get("ev_charge", 0) >= 60)
                and (self.adapters.matches("ev_charge", "on") or (snapshot.get("ev_kw") or 0) > .2)):
            await self.set("ev_charge", "off", revision, revoke=True)

    async def _ev(self, revision, snapshot):
        if not snapshot.get("connected"):
            return
        plan = self.plan_now()
        required = snapshot.get("ev_soc") is not None and snapshot.get("ev_limit") is not None and snapshot["ev_soc"] < snapshot["ev_limit"]
        active = (plan.get("ev_amps", 0) > 0 and (plan.get("ev_stop_at") or 0) > time.time()) or self.runtime.charge_now
        if not required or not active:
            await self._stop_ev_if_home(revision, snapshot)
            return
        if not snapshot["ev_ready"]:
            raise RuntimeError("EV needs its configured connection, SOC and control feedback")
        current = self.adapters.state("ev_current")
        desired = int(min(plan.get("ev_amps") or self.runtime.config["ev_max_amps"], self.runtime.config["ev_max_amps"], finite(current.attributes.get("max"), self.runtime.config["ev_max_amps"])))
        if desired < self.runtime.config["ev_min_amps"]:
            raise RuntimeError("Vehicle current limit is below the configured stable minimum")
        charging = self.adapters.matches("ev_charge", "on")
        if not charging and time.time() - self.last.get("ev_start", 0) < 300 and not self.runtime.charge_now:
            return
        if self.enabled("battery") and self.runtime.config["hold_battery_for_ev"] and snapshot["battery_ready"]:
            await self.revoke_battery(revision)
            await self.set("battery_mode", "hold", revision)
        if time.time() - self.last.get("ev_current", 0) >= 60 or finite(current.state, 0) >= desired:
            await self.set("ev_current", desired, revision)
        if not self.adapters.matches("ev_current", desired):
            return
        fresh = self.runtime.snapshot()
        if not fresh["ev_ready"] or fresh["ev_soc"] >= fresh["ev_limit"]:
            return
        await self.set("ev_charge", "on", revision)
        if not charging:
            self.last["ev_start"] = time.time()
