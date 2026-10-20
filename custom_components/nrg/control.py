"""One guarded writer, independent of vehicle/battery manufacturer or integration."""
import asyncio
import logging
import time

from .adapters import Adapters
from .config import finite

_LOGGER = logging.getLogger(__name__)


class Controller:
    def __init__(self, runtime):
        self.runtime, self.hass = runtime, runtime.hass
        self.adapters = Adapters(runtime)
        self.lock, self.last = asyncio.Lock(), {}
        self.status = "Observation: no equipment commands"

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

    def price_known_now(self):
        known = self.runtime.current_price_known and self.plan_now().get("_slot_price_known", True)
        if self.runtime.config["supply_plan"] == "Hourly ComEd":
            known = known and int(getattr(self.runtime,"last_sample_at",time.time()) // 3600) == int(time.time() // 3600)
        return known

    def ev_busy(self, snapshot, plan):
        busy = snapshot["ev_busy"] is not False if "ev_busy" in snapshot else snapshot.get("ev_kw", 0) is None or snapshot.get("ev_kw", 0) > .2
        return self.runtime.config["has_ev"] and (busy or plan.get("ev_amps", 0) > 0)

    async def set(self, key, action, revision, *, revoke=False):
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
        if not revoke and not emergency and not self.valid_plan(revision):
            raise RuntimeError("Plan expired before command")
        active = self.plan_now()
        if not emergency and key == "ev_charge" and action == "on" and (not active.get("ev_amps") or (active.get("ev_stop_at") or 0) <= time.time()):
            raise RuntimeError("The current charging interval ended before the start command")
        if key == "battery_grid_charge" and action == "on" and (active.get("battery_action") != "charge" or not self.price_known_now()):
            raise RuntimeError("The current interval no longer permits battery grid charging")
        if key == "battery_mode" and action in ("serve", "charge") and (active.get("battery_action") != action or not self.price_known_now()):
            raise RuntimeError("The current interval no longer permits that battery action")
        if (key == "battery_grid_charge" and action == "on") or (key == "battery_mode" and action in ("serve", "charge")):
            config = self.runtime.config
            if not snapshot.get("battery_ready") or snapshot.get("battery_soc") is None:
                raise RuntimeError("Battery control/feedback is no longer ready")
            busy = self.ev_busy(snapshot, active)
            if action in ("on", "charge"):
                target = finite(active.get("battery_target_soc"))
                if (busy or not snapshot.get("can_grid_charge", True) or target is None
                        or snapshot["battery_soc"] >= target - .3):
                    raise RuntimeError("Battery grid charging is no longer permitted by current readings")
            elif snapshot["battery_soc"] <= config["backup_reserve"] + .3 or config["hold_battery_for_ev"] and busy:
                raise RuntimeError("Battery discharge is no longer permitted by current readings")
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
                self.status = "Observation: no equipment commands"
                return
            if not self.enabled("ev") and not self.enabled("battery"):
                self.status = "Monitoring: no device is enabled for NRG control"
                return
            revision, errors = self.runtime.revision, []
            if not self.runtime.snapshot()["native_ready"]:
                self.status = "Yielding to a configured protection guard or missing guard reading"
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

    async def _stop_ev_if_home(self, revision, snapshot):
        if (snapshot.get("connected") and time.time() - self.last.get("ev_charge", 0) >= 60
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
