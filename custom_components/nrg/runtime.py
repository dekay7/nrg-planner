"""Home Assistant boundary: sampling, cached forecasts, persistence and execution."""
from datetime import datetime, timedelta, time as local_time
import logging
import time
import json
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientTimeout
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .config import effective_capacity, finite, settings, validate, cents_rate
from .const import DOMAIN, MAPPINGS
from .adapters import Adapters
from .tariffs import usd_price, external_intervals
from .control import Controller
from .forecast import aggregate_solar, parse_comed, price_at, solar_response, known_nights, comed_publication_window
from .fallback import PriceFallback, KNOWN_SOURCES, live_valid
from .planner import plan
from .statistics import Statistics

_LOGGER = logging.getLogger(__name__)
COMED = "https://hourlypricing.comed.com/rrtp/ServletFeed"


class NRGRuntime(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, config_entry=entry, name="NRG Planner", update_interval=timedelta(minutes=1))
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.stats = Statistics()
        self.prices = []
        self.solar_caches = {}
        self.live_cache = None
        self.plan = {}
        self.revision = 0
        self.last_fetch = 0
        self.forecast_status = {}
        self.charge_now = False
        self.fallback = PriceFallback()
        self.fallback_notice = None
        self.last_fallback_notice = None
        self.last_valid_prices = {}
        self.force_plan = True
        self.current_price_known = False
        self.live_export = None
        self.controller = Controller(self)
        self._closing = False
        self.solar_signature = None
        self.delivered = {}
        self.pending_advice = None
        self.last_save = time.time()
        self.last_sample_at = 0

    @property
    def config(self):
        return settings(dict(self.entry.options)) | {"departure_override": self.entry.options.get("departure_override")}

    @property
    def mappings(self):
        return dict(self.entry.options.get("mappings", {}))

    @property
    def zone(self):
        return ZoneInfo(self.hass.config.time_zone)

    async def load(self):
        saved = await self.store.async_load() or {}
        self.stats = Statistics(saved.get("statistics"))
        self.prices = saved.get("prices", [])
        self.solar_caches = saved.get("solar", {})
        self.solar_signature = saved.get("solar_signature")
        self.delivered = saved.get("delivered", {})
        self.fallback.manual = saved.get("manual_fallback") is True

    def persisted(self):
        return {"statistics": self.stats.export(), "prices": self.prices, "solar": self.solar_caches,
                "solar_signature": self.solar_signature, "delivered": self.delivered,
                "manual_fallback": self.fallback.manual}

    async def close(self):
        self._closing = True
        await self.store.async_save(self.persisted())

    async def update_options(self, changes):
        options = validate(dict(self.entry.options) | changes, datetime.now(self.zone).date())
        self.plan = {}  # Invalidate before publishing changed assumptions.
        self.revision += 1
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.force_plan = True
        await self.async_request_refresh()

    def state(self, key, age=180):
        entity_id = self.mappings.get(key)
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in ("unknown", "unavailable", ""):
            return None
        if not entity_id.startswith("input_") and age is not None and not 0 <= time.time() - state.last_reported.timestamp() <= age:
            return None
        return state

    def numeric(self, key, age=180, unit=None, low=None, high=None):
        state = self.state(key, age)
        if state is None or (unit and state.attributes.get("unit_of_measurement") != unit):
            return None
        value = finite(state.state)
        if value is None or (low is not None and value < low) or (high is not None and value > high):
            return None
        return value

    def power(self, key):
        state = self.state(key)
        value = self.numeric(key)
        if state is None or value is None or state.attributes.get("unit_of_measurement") not in ("W", "kW"):
            return None
        value /= 1000 if state.attributes["unit_of_measurement"] == "W" else 1
        if key == "grid_power" and self.config["grid_power_inverted"] or key == "battery_power" and self.config["battery_power_inverted"]:
            value = -value
        if abs(value) > 250:
            return None
        if key == "solar_power":
            return max(value, 0) if value >= -.05 else None
        return value if key in ("grid_power", "battery_power") or value >= 0 else None

    def snapshot(self):
        config = self.config
        adapters = Adapters(self)
        def is_state(key, wanted, age=180):
            state = self.state(key, age)
            return state is not None and state.state == wanted
        solar = self.power("solar_power") if config["has_solar"] else 0.0
        battery = self.power("battery_power") if config["has_battery"] else 0.0
        ev = self.power("ev_power") if config["has_ev"] else 0.0
        plugged = (True if is_state("ev_connected", "on") else False if is_state("ev_connected", "off") else None) if config["has_ev"] else False
        saved = config["ev_allow_saved_readings"] and plugged is True
        vehicle_age, control_age = (None, None) if saved else (3600, 300)
        charge_feedback = self.state("ev_charge", control_age)
        ev_busy = ev > .2 if ev is not None else False if plugged is False else True if charge_feedback and adapters.matches("ev_charge", "on") else False if charge_feedback and adapters.matches("ev_charge", "off") else None
        if config["has_ev"] and ev is None and ev_busy is False:
            ev = 0.0
        home, grid = self.power("home_power"), self.power("grid_power")
        house_meter = home if not config["home_includes_ev"] else None
        if house_meter is not None and config["has_ev"]:
            home = house_meter + ev if ev is not None else None
        home_basis = "meter"
        if home is None and all(v is not None for v in (solar, grid, battery)):
            home = max(solar + grid + battery, 0)
            home_basis = "calculated from site meters"
        grid_basis = "meter"
        if grid is None and all(v is not None for v in (solar, home, battery)):
            grid = home - solar - battery
            grid_basis = "calculated from site meters"
        balance = solar + grid + battery - home if all(v is not None for v in (solar, grid, battery, home)) else None
        balance_ok = balance is None or abs(balance) <= max(.3, (home or 0) * .05)
        ev_valid = ev is not None and (home is None or ev <= home + .2) and balance_ok
        house_valid = house_meter is not None or home is not None and ev_valid
        quality = ("Some home/site measurements are unavailable" if home is None or ev is None else
                   "Meters disagree; inconsistent learning paused" if not balance_ok or not ev_valid else "Measurements consistent")
        guard_roles = [("grid_connected", "on")]
        if config["has_battery"]:
            guard_roles += [("storm_watch", "off"), ("grid_services", "off"), ("grid_services_enabled", "off")]
        guard_issues = []
        for key, expected in guard_roles:
            if not (entity_id := self.mappings.get(key)) or is_state(key, expected):
                continue
            raw = self.hass.states.get(entity_id)
            actual = raw.state if raw else "missing"
            if raw and actual not in ("unknown", "unavailable") and self.state(key) is None:
                actual = "stale"
            guard_issues.append({"role": key, "name": MAPPINGS[key][0].removesuffix(" (optional)"),
                                 "entity_id": entity_id, "state": actual, "expected": expected})
        native = not guard_issues
        battery_soc = self.numeric("battery_soc", unit="%", low=0, high=100) if config["has_battery"] else None
        ev_soc = self.numeric("ev_soc", vehicle_age, "%", 0, 100) if config["has_ev"] else None
        ev_limit = self.numeric("ev_limit", vehicle_age, "%", 0, 100) if config["has_ev"] else None
        location = self.state("ev_location", vehicle_age)
        home_location = not self.mappings.get("ev_location") or location is not None and location.state in ("home", "on")
        connected = config["has_ev"] and plugged is True and home_location
        current = self.state("ev_current", control_age)
        current_min = finite(current.attributes.get("min"), config["ev_min_amps"]) if current else None
        current_max = finite(current.attributes.get("max"), config["ev_max_amps"]) if current else None
        ev_bounds = (current_min is not None and current_max is not None
                     and current_min <= self.config["ev_max_amps"] and current_max >= self.config["ev_min_amps"])
        battery_controls = self.state("battery_mode") is not None and adapters.can("battery_mode", "hold") and adapters.can("battery_mode", "serve")
        grid_switch = self.state("battery_grid_charge") is not None and adapters.can("battery_grid_charge", "on") and adapters.can("battery_grid_charge", "off")
        can_grid_charge = (battery_controls and adapters.can("battery_mode", "charge")
                           and (grid_switch or config["control_values"]["battery_charge"] != config["control_values"]["battery_hold"]))
        ev_controls = adapters.can("ev_current", config["ev_max_amps"]) and charge_feedback is not None and adapters.can("ev_charge", "on") and adapters.can("ev_charge", "off")
        # Deriving a home/grid meter makes balance tautological. Only independent
        # site readings can establish spare solar or unmet household demand.
        independent = home_basis == grid_basis == "meter" and all(v is not None for v in (home, grid, solar))
        middle_soc = battery_soc is not None and max(10, config["backup_reserve"] + 5) <= battery_soc <= 85
        force_charge = (self.state("battery_mode") is not None
                        and config["control_values"]["battery_charge"] != config["control_values"]["battery_hold"]
                        and adapters.matches("battery_mode", "charge"))
        battery_valid = config["has_battery"] and battery is not None and battery_soc is not None and balance_ok and native
        return {"solar_kw": solar, "home_kw": home, "ev_kw": ev,
                "house_kw": house_meter if house_meter is not None else max(home - ev, 0) if house_valid else None,
                "grid_kw": grid, "battery_kw": battery, "balance_kw": balance,
                "measurement_quality": quality, "ev_learning_valid": ev_valid,
                "battery_learning_valid": battery_valid,
                "battery_charge_opportunity": bool(independent and middle_soc and battery_valid and battery <= -.5
                                                   and (grid <= -.5 or grid >= .5 and force_charge)),
                "battery_discharge_opportunity": bool(independent and middle_soc and battery_valid and battery >= .5 and grid >= .5),
                "battery_energy_counters": any(key in self.mappings for key in ("battery_charge_energy", "battery_discharge_energy")),
                "battery_charge_energy": self.numeric("battery_charge_energy", 180, "kWh", 0),
                "battery_discharge_energy": self.numeric("battery_discharge_energy", 180, "kWh", 0),
                "battery_soc": battery_soc, "ev_soc": ev_soc, "ev_limit": ev_limit,
                "ev_energy": self.numeric("ev_energy", 180, "kWh", 0),
                "ev_amps": self.numeric("ev_measured_current", 180, "A", 0, 100)
                or self.numeric("ev_current", control_age, "A", 0, 100),
                "native_ready": native, "guard_issues": guard_issues, "battery_controls_ready": battery_controls,
                "battery_ready": config["has_battery"] and config["battery_control"] and native and battery_soc is not None and battery_controls,
                "can_grid_charge": can_grid_charge, "can_set_export": adapters.can("battery_export", config["export_policy"]),
                "battery_reserve_mapped": bool(self.mappings.get("battery_reserve")),
                "battery_native_reserve": self.numeric("battery_reserve", low=0, high=100),
                "local_connected": plugged, "ev_busy": ev_busy,
                "home_basis": home_basis, "grid_basis": grid_basis,
                "ev_data_basis": "Saved readings allowed while connected" if saved else "Recent reports required",
                "connected": connected,
                "ev_ready": config["has_ev"] and config["ev_control"] and native and connected and ev_soc is not None and ev_limit is not None
                and current is not None and current.attributes.get("unit_of_measurement") == "A" and ev_bounds and ev_controls}

    def live_supply(self):
        if self.config["supply_plan"] == "Flat supply":
            return cents_rate(self.config, "flat_supply_cents")
        if self.mappings.get("live_supply"):
            state = self.state("live_supply", 900)
            value = finite(state.state) if state else None
            unit = state.attributes.get("unit_of_measurement") if state else None
            hourly = self.config["supply_plan"] == "Hourly ComEd"
            if (value is not None and live_valid(state.last_reported.timestamp(), time.time(), hourly=hourly)
                    and unit in ("¢/kWh", "c/kWh", "cents/kWh", "USD/kWh", "$/kWh")):
                supply = value / 100 if unit in ("¢/kWh", "c/kWh", "cents/kWh") else value
                return supply if -10 <= supply <= 5 else None
            return None
        if (self.config["supply_plan"] == "Hourly ComEd" and self.live_cache
                and live_valid(self.live_cache["time"], time.time(), hourly=True)):
            return self.live_cache["supply"]
        return None

    def evaluate_fallback(self, *, publish=False, allow_recovery=False):
        """Recompute current prices even when a coordinator fetch/plan has stalled."""
        now, config = time.time(), self.rate_context()
        live = self.live_supply()
        current = price_at(now, now, config, self.prices, live, self.stats.price_prior)
        missing = [kind for kind in ("supply", "delivery")
                   if current[kind + "_source"] not in KNOWN_SOURCES
                   or kind == "supply" and config["supply_plan"] == "Hourly ComEd" and live is None
                   and not current["comed_publication_bridge"]]
        observations = {}
        token = []
        for kind in ("supply", "delivery"):
            source_key = kind + "_forecast" if current[kind + "_source"] == "external_forecast" and self.mappings.get(kind + "_forecast") else "live_" + kind
            state = self.state(source_key, None)
            external = config[kind + "_plan"].startswith("External") or config[kind + "_plan"] == "Hourly ComEd"
            stamp = (state.last_reported.timestamp() if state else (
                self.live_cache["time"] if kind == "supply" and config["supply_plan"] == "Hourly ComEd" and self.live_cache else None)) if external else None
            if kind == "supply" and current["comed_publication_bridge"]:
                stamp = next(r["fetched_at"] for r in self.prices if r["start"] <= now < r["start"] + 3600
                             and 0 <= now - r["fetched_at"] <= 36 * 3600)
            identity = (kind, config[kind + "_plan"], self.mappings.get("live_" + kind), self.mappings.get(kind + "_forecast"))
            if kind not in missing and stamp is not None:
                self.last_valid_prices[identity] = stamp
            valid_stamp = self.last_valid_prices.get(identity)
            observations[kind] = {"source": current[kind + "_source"], "last_observation": stamp,
                                  "last_valid_observation": valid_stamp,
                                  "age_seconds": max(now - valid_stamp, 0) if valid_stamp is not None else None}
            if current[kind + "_source"] in ("running_average", "external_live"):
                token.append(stamp)
        old_active = getattr(self, "_fallback_active", False)
        enabled = config["price_fallback"] == "Custom fallback"
        degraded = bool(config["supply_plan"] == "Hourly ComEd" and not self.mappings.get("live_supply")
                        and self.forecast_status.get("live_price"))
        # A publication bridge prevents a healthy system entering fallback; it
        # must not count as fresh live evidence for an already active outage.
        recovery_known = current["price_known"] and not (current["comed_publication_bridge"] and self.fallback.automatic)
        active = self.fallback.update(now, enabled=enabled, known=recovery_known,
                                      degraded=degraded, observation=tuple(token) if token else now,
                                      allow_recovery=allow_recovery)
        self._fallback_active = active
        if active != old_active:
            self.plan = {}
            self.revision += 1
            self.force_plan = True
            self.fallback_notice = (active, "Price-data fallback activated" if active else "Price-data fallback released; a fresh plan is required")
        result = {"state": self.fallback.state, "active": active, "enabled": enabled, "price_known": current["price_known"],
                  "manual": self.fallback.manual, "missing": missing, "observations": observations,
                  "comed_publication_bridge": current["comed_publication_bridge"],
                  "recovery_since": self.fallback.recovery_since,
                  "ev_policy": config["fallback_ev"], "battery_policy": config["fallback_battery"],
                  "charge_now_override": active and self.charge_now,
                  "reason": "Manual activation" if self.fallback.manual and active else
                            "Missing, stale or invalid current pricing: " + ", ".join(missing) if missing else
                            "Waiting for fresh ComEd live pricing before releasing automatic fallback" if active and current["comed_publication_bridge"] else
                            "Confirming stable fresh pricing" if active else
                            "Live fetch failed; the published current-hour forecast is still usable" if degraded and current["comed_publication_bridge"] else
                            "Live fetch failed; the current cached observation is still usable" if degraded else
                            "Using the published current-hour forecast while ComEd live pricing is being published" if current["comed_publication_bridge"] else
                            "Current import pricing is usable"}
        if publish:
            # Publishing a command-time check must not reset the coordinator's
            # polling timer: the writer runs more often than the price poll.
            self.data = (self.data or {}) | {"fallback": result, "plan": self.plan,
                "price": current if current["price_known"] else None, "price_components": current}
            self.async_update_listeners()
            if active != old_active:
                self.hass.async_create_task(self.async_request_refresh())
        return result

    async def set_manual_fallback(self, enabled):
        if enabled and self.config["price_fallback"] != "Custom fallback":
            raise HomeAssistantError("Choose Use my fallback actions in Configure → Price-data fallback before starting a manual request")
        self.fallback.manual = enabled
        # A manual release with usable prices still requires a fresh normal plan.
        self.revision += 1
        self.plan = {}
        self.force_plan = True
        await self.store.async_save(self.persisted())
        self.evaluate_fallback(publish=True)
        self.hass.async_create_task(self.async_request_refresh())
        await self.controller.apply()
        self.async_update_listeners()

    def rate_context(self):
        config = self.config | {"zone": self.zone}
        delivery = self.state("live_delivery", 900)
        config["_delivery_live"] = (usd_price(delivery.state, delivery.attributes.get("unit_of_measurement"))
                                    if delivery and live_valid(delivery.last_reported.timestamp(), time.time()) else None)
        for component in ("supply", "delivery"):
            key = component + "_forecast"
            source = self.state(key, 36 * 3600) or self.state("live_" + component, 36 * 3600)
            try:
                config["_external_" + component] = external_intervals(source.attributes.get(config["external_" + component + "_attribute"], []), source.attributes.get("unit_of_measurement")) if source else []
                self.forecast_status.pop("external_" + component, None)
            except ValueError as error:
                config["_external_" + component] = []
                self.forecast_status["external_" + component] = str(error)
        return config

    async def get_text(self, url, params=None):
        async with async_get_clientsession(self.hass).get(url, params=params, timeout=ClientTimeout(total=15)) as response:
            response.raise_for_status()
            return await response.text()

    async def refresh_forecasts(self):
        now = time.time()
        if self.config["supply_plan"] == "Hourly ComEd":
            merged = {r["start"]: r for r in self.prices if 0 <= now - r["fetched_at"] <= 36 * 3600}
            errors = []
            today = datetime.fromtimestamp(now, ZoneInfo("America/Chicago")).strftime("%Y%m%d")
            try:
                text = await self.get_text(COMED, {"type": "daynexttoday", "date": today})
                merged.update({r["start"]: r for r in parse_comed(text, now)})
            except (ClientError, TimeoutError, ValueError, TypeError) as error:
                errors.append(f"Today: {error}")
            try:
                available = await self.get_text(COMED, {"type": "hasdaynexttomorrow"})
                if available.strip().lower() == "true":
                    text = await self.get_text(COMED, {"type": "daynexttomorrow"})
                    merged.update({r["start"]: r for r in parse_comed(text, now)})
            except (ClientError, TimeoutError, ValueError, TypeError) as error:
                errors.append(f"Tomorrow: {error}")
            self.prices = sorted(merged.values(), key=lambda r: r["start"])
            self.forecast_status["comed"] = "; ".join(errors) if errors else "Published forecast loaded"
        for source in self.entry.options.get("solar_sources", []) if self.config["has_solar"] else []:
            key = source["config_entry_id"]
            old = self.solar_caches.get(key, {})
            try:
                state = self.hass.states.get(source["entity_id"])
                if state is None or state.state in ("unavailable", "unknown"):
                    raise ValueError("Selected Forecast.Solar entity is unavailable")
                response = await self.hass.services.async_call("forecast_solar", "get_forecast",
                    {"config_entry": key, "resolution": "raw"}, blocking=True, return_response=True)
                self.solar_caches[key] = solar_response(response, self.zone, now)
            except (HomeAssistantError, ClientError, TimeoutError, ValueError, TypeError, KeyError) as error:
                self.solar_caches[key] = old | {"error": str(error)}
        self.last_fetch = now

    async def _async_update_data(self):
        if self._closing:
            return self.data or {}
        revision = self.revision
        failed_source = self.config["has_solar"] and any(not self.solar_caches.get(s["config_entry_id"], {}).get("days")
                            or self.solar_caches.get(s["config_entry_id"], {}).get("error")
                            for s in self.entry.options.get("solar_sources", []))
        if time.time() - self.last_fetch >= (300 if failed_source else 1800):
            await self.refresh_forecasts()
        if self.config["supply_plan"] == "Hourly ComEd" and not self.mappings.get("live_supply"):
            if (not self.live_cache or not live_valid(self.live_cache["time"], time.time(), hourly=True)
                    or time.time() - self.live_cache["time"] >= 300):
                try:
                    rows = json.loads(await self.get_text("https://hourlypricing.comed.com/api", {"type": "currenthouraverage"}))
                    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
                        raise ValueError("Invalid ComEd live response")
                    row = rows[0]
                    stamp, cents = finite(row.get("millisUTC")), finite(row.get("price"))
                    if stamp is None or cents is None or not -1000 <= cents <= 500:
                        raise ValueError("Invalid ComEd live price")
                    observed, received = stamp / 1000, time.time()
                    if live_valid(observed, received, hourly=True):
                        self.live_cache = {"time": observed, "supply": cents / 100}
                    elif (comed_publication_window(received)
                          and int(observed // 3600) == int(received // 3600) - 1):
                        # A normal publication delay, not a current-hour live price.
                        # Only a separately valid current-hour forecast can bridge it.
                        pass
                    else:
                        raise ValueError("Invalid or stale ComEd live price")
                    self.forecast_status.pop("live_price", None)
                except (ClientError, TimeoutError, ValueError, TypeError, KeyError, IndexError) as error:
                    self.forecast_status["live_price"] = f"Live ComEd unavailable ({type(error).__name__})"
        if revision != self.revision:
            return self.data or {}  # Options/ownership changed during network I/O.
        fallback = self.evaluate_fallback(allow_recovery=True)
        revision = self.revision
        now = time.time()
        config, snapshot, live = self.rate_context(), self.snapshot(), self.live_supply()
        config["_fallback_active"] = fallback["active"]
        if config.get("departure_override"):
            override = datetime.fromisoformat(config["departure_override"])
            if override.tzinfo is None:
                override = override.replace(tzinfo=self.zone)
            reached = snapshot["ev_soc"] is not None and snapshot["ev_limit"] is not None and snapshot["ev_soc"] >= snapshot["ev_limit"]
            if override.timestamp() <= now and (not snapshot["connected"] or reached):
                self.hass.config_entries.async_update_entry(self.entry, options=dict(self.entry.options) | {"departure_override": None})
                config["departure_override"] = None
        # Never calibrate a changed forecast system against the previous system's
        # residuals. Preserve measurements, house learning and the cost ledger.
        signature = json.dumps({"sources": list(self.entry.options.get("solar_sources", [])),
                                "enabled": config["has_solar"],
                                "date": config["solar_install_date"], "rate": config["solar_degradation"],
                                "measurement": self.mappings.get("solar_power")}, sort_keys=True)
        if signature != self.solar_signature:
            for hour in self.stats.hours:
                hour["solar_forecast"] = None
            self.stats.issued = {}
            self.solar_signature = signature
        current = price_at(now, now, config, self.prices, live, self.stats.price_prior)
        previous_rate = (self.data or {}).get("price") or {}
        if any(previous_rate.get(key) != current.get(key)
               for key in ("supply_period", "delivery_period", "price_known", "comed_publication_bridge")):
            self.force_plan = True
        self.current_price_known = current["price_known"]
        self.last_sample_at = now
        self.live_export = current["export_price"] if current["export_known"] else None
        values = snapshot | {"supply": live if config["supply_plan"] == "Hourly ComEd" else None,
                             "import_price": current["import_price"] if self.current_price_known else None,
                             "export_price": self.live_export,
                             "supply_price": current["supply_price"] if current["comed_publication_bridge"] or current["supply_source"] in ("flat","time_of_use","running_average","external_live","external_forecast") else None,
                             "delivery_price": current["delivery_price"] if current["delivery_source"] in ("flat","time_of_use","external_live","external_forecast") else None,
                             "_tariffs": {key:config[key] for key in ("supply_plan","delivery_plan","supply_periods","delivery_periods","export_rate","export_adder_cents","flat_export_cents")}}
        if not snapshot["ev_learning_valid"]:
            values["ev_kw"] = None
        self.stats.observe(now, values, self.zone)
        self.stats.battery.configure(config, self.mappings)
        self.stats.battery.observe(now, snapshot, config["has_battery"] and config["battery_learning"])
        battery_quality = self.stats.battery.quality(config, now)
        if self.stats.battery.model(config, now) != self.plan.get("battery_model"):
            self.force_plan = True
        if config["has_solar"]:
            raw_solar = self.with_nights(aggregate_solar(list(self.entry.options.get("solar_sources", [])), self.solar_caches, config, now, self.zone), now)
        else:
            hours = {str(hour): 0.0 for hour in range(int(now // 3600) * 3600, (int(now // 3600) + 49) * 3600, 3600)}
            raw_solar = {"hours": hours, "known": {key: True for key in hours}, "partial": hours, "sources": [], "groups": 0}
        self.stats.remember_forecast(raw_solar, now)
        quality = self.stats.solar_quality()
        solar = self.with_nights(aggregate_solar(list(self.entry.options.get("solar_sources", [])), self.solar_caches, config, now, self.zone,
                                quality["factor"] if config["solar_learning"] else 1), now) if config["has_solar"] else raw_solar
        if not snapshot["connected"] or (snapshot["ev_soc"] is not None and snapshot["ev_limit"] is not None and snapshot["ev_soc"] >= snapshot["ev_limit"]):
            self.charge_now = False
        current_control = self.state("ev_current", None if config["ev_allow_saved_readings"] and snapshot["local_connected"] else 300)
        model_config = dict(config)
        if current_control:
            ceiling = finite(current_control.attributes.get("max"))
            if ceiling is not None and 0 < ceiling < config["ev_max_amps"]:
                model_config["ev_kw_at_max"] *= ceiling / config["ev_max_amps"]
                model_config["ev_max_amps"] = ceiling
        if self.force_plan or now - self.plan.get("generated_at", 0) >= 300:
            self.force_plan = False
            # Planner works on snapshots off the event loop. A changed configuration
            # cannot publish an obsolete result when this worker completes.
            # Use the same effective hardware ceiling for prediction and commands.
            result = await self.hass.async_add_executor_job(plan, now, model_config, self.zone, snapshot, Statistics(self.stats.export()),
                                                           list(self.prices), solar, live, self.plan, self.charge_now)
            if revision == self.revision:
                self.plan = result
                self.revision += 1  # Revoke command chains using the previous plan.
        day = datetime.fromtimestamp(now, self.zone).date().isoformat()
        ledger = self.stats.ledger.get(day, {})
        today_start = datetime.combine(datetime.fromtimestamp(now, self.zone).date(), datetime.min.time(), self.zone).timestamp()
        coverage = ledger.get("coverage_hours", 0) / max((now - today_start) / 3600, 1e-9) * 100
        data = {"snapshot": snapshot, "plan": self.plan, "solar": solar, "solar_quality": quality,
                "fallback": fallback,
                "observations": list(self.stats.hours),
                "price": current if self.current_price_known else None, "price_components": current, "ledger": ledger,
                "cost_coverage": min(coverage, 100), "forecast_status": dict(self.forecast_status),
                "capacity": effective_capacity(config, datetime.fromtimestamp(now, self.zone).date()) if config["has_battery"] else None,
                "components": {"ev": config["has_ev"], "battery": config["has_battery"], "solar": config["has_solar"],
                               "ev_control": config["has_ev"] and config["ev_control"], "battery_control": config["has_battery"] and config["battery_control"]},
                "house_observations": sum(h.get("house_kwh") is not None for h in self.stats.hours),
                "ev_sessions": len(self.stats.ev_sessions), "controller": self.controller.status,
                "battery_calibration": battery_quality,
                "ev_energy_estimate": self.stats.ev_estimate(config["ev_kwh_per_percent"]) if config["ev_learning"] else config["ev_kwh_per_percent"],
                "ev_power_estimate": self.stats.ev_power(model_config["ev_kw_at_max"], model_config["ev_max_amps"]) if config["ev_learning"] else model_config["ev_kw_at_max"],
                "mode": config["mode"], "charge_now": self.charge_now,
                "departure_override": self.entry.options.get("departure_override")}
        if now - self.last_save >= 300:
            self.store.async_delay_save(self.persisted, 1)
            self.last_save = now
        await self.notify(now)
        await self.notify_fallback(now)
        return data

    def with_nights(self, forecast, now):
        today = datetime.fromtimestamp(now, self.zone).date()
        daylight = []
        for offset in range(3):
            day = today + timedelta(days=offset)
            rising, setting = get_astral_event_date(self.hass, "sunrise", day), get_astral_event_date(self.hass, "sunset", day)
            if rising is None or setting is None:
                return forecast  # Polar/event calculation uncertainty: do not guess.
            daylight.append((rising.timestamp(), setting.timestamp()))
        first = datetime.combine(today, datetime.min.time(), self.zone).timestamp()
        last = datetime.combine(today + timedelta(days=3), datetime.min.time(), self.zone).timestamp()
        return known_nights(forecast, daylight, now, first, last)

    async def notify(self, now):
        config, advice = self.config, self.plan.get("household", {})
        if (not config["notifications"] or self.plan.get("expires_at", 0) <= now or advice.get("category") != "wait"
                or advice.get("confidence") != "forecast"
                or (advice.get("saving") or 0) * 100 < config["notification_saving_cents"]):
            self.pending_advice = None
            return
        current = datetime.fromtimestamp(now, self.zone).time().replace(tzinfo=None)
        start, end = local_time.fromisoformat(config["quiet_start"]), local_time.fromisoformat(config["quiet_end"])
        quiet = start <= current < end if start < end else current >= start or current < end if start > end else False
        if quiet:
            return
        key = str(advice["best_start"])
        if not self.pending_advice or self.pending_advice[0] != key:
            self.pending_advice = (key, now)
            return
        if now - self.pending_advice[1] < 120:
            return
        message = f"{advice['summary']}. Estimated benefit: {advice['saving'] * 100:.0f} cents for {config['flexible_load_kwh']:g} kWh. "
        basis = {"grid": "Grid-supplied use", "solar": "Direct solar use", "battery": "Battery-backed use", "mixed": "Mixed energy sources"}
        message += basis.get(advice.get("cost_basis"), "Modeled appliance cost") + "; not necessarily the cheapest grid-price window. "
        message += "Proposed schedule (Observation)." if config["mode"] == "Observation" else "Solar, battery and car outlook considered."
        for target in self.entry.options.get("notification_targets", []):
            if not isinstance(target, str) or not target.startswith("notify.") or self.delivered.get(target) == key:
                continue
            service = target.split(".", 1)[1]
            if self.hass.services.has_service("notify", service):
                try:
                    await self.hass.services.async_call("notify", service, {"title": "Home energy", "message": message}, blocking=True)
                    self.delivered[target] = key
                    self.store.async_delay_save(self.persisted, 1)
                except Exception as error:
                    self.forecast_status["notification"] = f"Notification failed ({type(error).__name__})"
                    _LOGGER.exception("NRG notification delivery failed")

    async def notify_fallback(self, now):
        if not self.config["fallback_notifications"] or not self.fallback_notice:
            return
        current = datetime.fromtimestamp(now, self.zone).time().replace(tzinfo=None)
        start, end = local_time.fromisoformat(self.config["quiet_start"]), local_time.fromisoformat(self.config["quiet_end"])
        quiet = start <= current < end if start < end else current >= start or current < end if start > end else False
        if quiet or self.last_fallback_notice is not None and now - self.last_fallback_notice < 300:
            return
        notice = self.fallback_notice
        message = notice[1] + ". See NRG pricing health and control status for device results."
        if self.config["mode"] == "Observation":
            message += " Observation only: no equipment commands."
        for target in self.entry.options.get("notification_targets", []):
            if isinstance(target, str) and target.startswith("notify.") and self.hass.services.has_service("notify", target.split(".", 1)[1]):
                try:
                    await self.hass.services.async_call("notify", target.split(".", 1)[1],
                        {"title": "Energy pricing", "message": message}, blocking=True)
                except Exception as error:
                    self.forecast_status["fallback_notification"] = f"Delivery failed ({type(error).__name__})"
        if self.fallback_notice == notice:
            self.fallback_notice = None
        self.last_fallback_notice = now

    async def refresh(self):
        self.last_fetch = 0
        self.force_plan = True
        await self.async_request_refresh()

    async def set_charge_now(self, enabled):
        self.charge_now = enabled
        self.force_plan = True
        self.revision += 1
        self.plan = {}
        self.async_set_updated_data((self.data or {}) | {"charge_now": enabled, "plan": {}})
        self.hass.async_create_task(self.async_request_refresh())
        self.hass.async_create_task(self.controller.apply())

    async def reset_learning(self):
        self.stats = Statistics({"ledger": self.stats.ledger})
        self.force_plan = True
        await self.async_request_refresh()
