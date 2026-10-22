"""Read-only household metrics and inspectable planning diagnostics."""
from datetime import datetime, timezone
import time

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from .entity import NRGEntity

# key: (name, units, device class). Price displays use cents; Energy uses USD alias.
METRICS = {
    "import_price": ("Grid price now · supply + delivery", "¢/kWh", None),
    "import_price_usd": ("Grid buying price USD", "USD/kWh", None),
    "export_price_usd": ("Grid export credit USD", "USD/kWh", None),
    "supply_price": ("Supply price now", "¢/kWh", None),
    "delivery_price": ("Delivery price now", "¢/kWh", None),
    "export_price": ("Export credit now", "¢/kWh", None),
    "solar_power": ("Solar power", "kW", SensorDeviceClass.POWER),
    "home_power": ("Whole-home power", "kW", SensorDeviceClass.POWER),
    "house_power": ("House power without car", "kW", SensorDeviceClass.POWER),
    "grid_power": ("Grid power · import positive", "kW", SensorDeviceClass.POWER),
    "battery_power": ("Battery power · discharge positive", "kW", SensorDeviceClass.POWER),
    "ev_power": ("Car charging power", "kW", SensorDeviceClass.POWER),
    "power_balance": ("Power balance residual", "kW", SensorDeviceClass.POWER),
    "measurement_quality": ("Local measurement quality", None, None),
    "battery_soc": ("Home battery charge", "%", SensorDeviceClass.BATTERY),
    "ev_soc": ("Car charge", "%", SensorDeviceClass.BATTERY),
    "ev_limit": ("Car selected limit", "%", None),
    "capacity": ("Estimated full battery capacity", "kWh", SensorDeviceClass.ENERGY_STORAGE),
    "available_energy": ("Battery energy above reserve", "kWh", SensorDeviceClass.ENERGY_STORAGE),
    "ev_needed": ("Car energy still needed", "kWh", None),
    "ev_shortfall": ("Car departure energy shortfall", "kWh", None),
    "net_cost_today": ("Net energy cost today", "USD", SensorDeviceClass.MONETARY),
    "import_cost_today": ("Energy purchases today", "USD", SensorDeviceClass.MONETARY),
    "export_credit_today": ("Export credits today", "USD", SensorDeviceClass.MONETARY),
    "cost_coverage": ("Today's cost data coverage", "%", None),
    "estimated_pricing_hours": ("Today's forecast-priced coverage", "h", None),
    "solar_today": ("Solar energy observed today", "kWh", None),
    "home_today": ("Home energy observed today", "kWh", None),
    "ev_today": ("Car energy observed today", "kWh", None),
    "house_observations": ("Covered house-demand hours", "h", None),
    "ev_sessions": ("Calibrated charging sessions", None, None),
    "ev_energy_estimate": ("Effective EV energy per percentage point", "kWh/%", None),
    "ev_power_estimate": ("Effective EV power at maximum current", "kW", SensorDeviceClass.POWER),
    "battery_efficiency_estimate": ("Effective battery round-trip efficiency", "%", None),
    "battery_charge_estimate": ("Effective battery charging power", "kW", SensorDeviceClass.POWER),
    "battery_discharge_estimate": ("Effective battery discharging power", "kW", SensorDeviceClass.POWER),
    "battery_calibration": ("Battery calibration", None, None),
    "solar_error": ("Solar forecast mean absolute error", "kWh", None),
    "advice": ("Household advice", None, None),
    "battery_action": ("Planned battery action", None, None),
    "ev_status": ("Car charging status", None, None),
    "ev_actual_status": ("Observed car charging status", None, None),
    "next_charge": ("Next car charging", None, SensorDeviceClass.TIMESTAMP),
    "completion": ("Expected car readiness", None, SensorDeviceClass.TIMESTAMP),
    "deadline": ("Car departure", None, SensorDeviceClass.TIMESTAMP),
    "control_status": ("Control status", None, None),
    "plan": ("Energy plan", None, None),
    "source_health": ("Forecast source health", None, None),
    "pricing_health": ("Pricing health", None, None),
    "observations": ("Forecast observations", None, None),
    "components": ("Configured components", None, None),
    "tariff_status": ("Pricing schedule coverage", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(NRGSensor(entry.runtime_data, key, *values) for key, values in METRICS.items())


class NRGSensor(NRGEntity, SensorEntity):
    def __init__(self, runtime, key, name, unit, device):
        super().__init__(runtime, key, name, platform="sensor")
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device
        if unit and device != SensorDeviceClass.MONETARY and key not in ("ev_needed", "ev_shortfall", "solar_today", "home_today", "ev_today"):
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 2 if unit else None

    @property
    def fresh_plan(self):
        value = self.coordinator.plan
        return value if value.get("expires_at", 0) > time.time() else {}

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        snapshot, price = data.get("snapshot", {}), data.get("price")
        planned, key = self.fresh_plan, self.key
        if key in ("import_price", "supply_price", "delivery_price", "export_price", "import_price_usd", "export_price_usd"):
            if key in ("supply_price", "delivery_price", "export_price", "export_price_usd"):
                components = data.get("price_components", {})
                source = components.get("supply_source" if key == "supply_price" else "delivery_source")
                known = components.get("export_known") if key.startswith("export_price") else source in ("flat","time_of_use","running_average","external_live","external_forecast")
                if key == "supply_price" and (components.get("comed_publication_bridge") or components.get("comed_estimated_price")):
                    known = True
                value = components.get(key.removesuffix("_usd"))
                return round(value * (1 if key.endswith("_usd") else 100), 5) if known and value is not None else None
            return round(price[key.replace("_usd", "")] * (1 if key.endswith("usd") else 100), 5) if price else None
        if key.endswith("_power"):
            return snapshot.get(key.replace("_power", "_kw"))
        if key == "power_balance":
            return snapshot.get("balance_kw")
        if key == "measurement_quality":
            return snapshot.get(key)
        if key in ("battery_soc", "ev_soc", "ev_limit"):
            return snapshot.get(key)
        if key == "available_energy":
            soc = snapshot.get("battery_soc")
            return data.get("capacity", 0) * max(soc - self.coordinator.config["backup_reserve"], 0) / 100 if soc is not None else None
        if key in ("capacity", "cost_coverage", "house_observations", "ev_sessions", "ev_energy_estimate", "ev_power_estimate"):
            return data.get(key)
        if key == "battery_calibration":
            return data.get(key, {}).get("status")
        if key in ("battery_efficiency_estimate", "battery_charge_estimate", "battery_discharge_estimate"):
            if not self.coordinator.config["has_battery"]:
                return None
            parameter = {"battery_efficiency_estimate": "round_trip_efficiency",
                         "battery_charge_estimate": "battery_charge_kw", "battery_discharge_estimate": "battery_discharge_kw"}[key]
            return data.get("battery_calibration", {}).get("estimates", {}).get(parameter, {}).get("effective")
        if key == "solar_error":
            return data.get("solar_quality", {}).get("mae_kwh")
        if key == "estimated_pricing_hours":
            return data.get("ledger", {}).get("estimated_coverage_hours", 0)
        if key == "net_cost_today":
            ledger = data.get("ledger", {})
            return round(ledger.get("import_cost", 0) - ledger.get("export_credit", 0), 4) if ledger.get("coverage_hours", 0) > 0 else None
        if key in ("import_cost_today", "export_credit_today"):
            return data.get("ledger", {}).get(key.removesuffix("_today"), 0)
        if key in ("solar_today", "home_today", "ev_today"):
            return data.get("ledger", {}).get(key.replace("_today", "_kwh"), 0)
        if key in ("ev_needed", "ev_shortfall"):
            return planned.get(key + "_kwh")
        if key in ("next_charge", "completion", "deadline"):
            value = planned.get(key)
            return datetime.fromtimestamp(value, timezone.utc) if value is not None else None
        if key == "advice":
            return planned.get("household", {}).get("summary", "Waiting for a fresh forecast")
        if key == "battery_action":
            if not self.coordinator.config["has_battery"]:
                return "Not installed"
            if not self.coordinator.config["battery_control"]:
                return "Monitoring only"
            if planned.get("battery_forecast_available") is False:
                return "Waiting for battery inputs"
            return {"charge": "Buy energy for later", "hold": "Save stored energy", "serve": "Power home from battery"}.get(planned.get(key), "Waiting for plan")
        if key == "ev_actual_status":
            if not self.coordinator.config["has_ev"]:
                return "Not installed"
            power = snapshot.get("ev_kw")
            if power is None:
                return "Waiting for charger data"
            if power > .2:
                return "Charging now"
            if snapshot.get("local_connected") is False:
                return "Not plugged in"
            if snapshot.get("local_connected") is True:
                soc, limit = snapshot.get("ev_soc"), snapshot.get("ev_limit")
                return "At selected limit" if soc is not None and limit is not None and soc >= limit else "Plugged in · paused"
            return "Connection unknown"
        if key == "ev_status":
            return {"not_installed": "Not installed", "monitor_only": "Monitoring only", "unplugged": "Plug in at home", "telemetry_missing": "Waiting for vehicle data", "ready": "Ready",
                    "blocked": "Waiting for vehicle controls or native event", "fallback_paused": "Price-data fallback · charging paused",
                    "charge_now": "Immediate charging requested", "deadline": "Charging for departure", "charging": "Scheduled charging", "waiting": "Waiting for planned hours"}.get(planned.get(key), "Waiting for plan")
        if key == "control_status":
            return self.coordinator.controller.status
        if key == "plan":
            return planned.get("selected_candidate", "stale")
        if key == "pricing_health":
            return data.get("fallback", {}).get("state", "Degraded")
        if key == "source_health":
            if not self.coordinator.config["has_solar"]:
                return "Solar not installed"
            sources = data.get("solar", {}).get("sources", [])
            return f"{sum(s['ready'] for s in sources)}/{len(sources)} solar sources ready"
        if key == "observations":
            return len(data.get("observations", []))
        if key == "components":
            enabled = [name for name in ("solar", "battery", "ev") if self.coordinator.config["has_" + name]]
            return ", ".join(enabled) if enabled else "Grid / pricing only"
        if key == "tariff_status":
            from .config import cents_rate
            from .tariffs import schedule_complete
            config = self.coordinator.config
            missing = [kind for kind, flat in (("supply", "flat_supply_cents"), ("delivery", "delivery_cents"))
                       if (config[kind + "_plan"] == "Time-of-use " + kind and not schedule_complete(config[kind + "_periods"]))
                       or (config[kind + "_plan"] == "Flat " + kind and cents_rate(config, flat) is None)]
            if config["export_rate"] == "Flat credit" and cents_rate(config, "flat_export_cents") is None:
                missing.append("export credit")
            if config["export_rate"] == "Supply plus adder" and cents_rate(config, "export_adder_cents") is None:
                missing.append("export adder")
            return "Missing periods/rates: " + ", ".join(missing) if missing else "Selected rate settings entered; check live/forecast availability"
        return None

    @property
    def extra_state_attributes(self):
        data, plan = self.coordinator.data or {}, self.fresh_plan
        if self.key in ("supply_price", "import_price", "import_price_usd"):
            components = data.get("price_components", {})
            return {"source": components.get("supply_source" if self.key == "supply_price" else "price_source"),
                    "comed_publication_bridge": components.get("comed_publication_bridge", False),
                    "comed_estimated_price": components.get("comed_estimated_price", False)}
        if self.key == "plan":
            return {"plan": plan, "basis": "Modeled feasible plans, not guaranteed savings or an export watt setpoint.", "operating_mode": self.coordinator.config["mode"]}
        if self.key == "advice":
            return plan.get("household", {}) | {"operating_mode": self.coordinator.config["mode"]}
        if self.key == "battery_action":
            return {"reason": plan.get("battery_reason"), "target_soc": plan.get("battery_target_soc"), "export_capability": plan.get("export_capability")}
        if self.key == "pricing_health":
            return data.get("fallback", {}) | {"device_results": self.coordinator.controller.fallback_results,
                "control_status": self.coordinator.controller.status,
                "operating_mode": self.coordinator.config["mode"],
                "departure_at_risk": bool(plan.get("ev_shortfall_kwh"))}
        if self.key == "source_health":
            return {"sources": data.get("solar", {}).get("sources", []), "status": data.get("forecast_status", {}),
                    "solar_calibration": data.get("solar_quality", {}), "mappings": self.coordinator.mappings}
        if self.key == "observations":
            return {"hours": data.get("observations", []), "basis": "Completed covered hours; forecasts frozen before each hour. Supply values are recorded running estimates, not settlement prices."}
        if self.key == "components":
            return {k: self.coordinator.config["has_" + k] for k in ("ev", "battery", "solar")} | {
                "ev_control": self.coordinator.config["has_ev"] and self.coordinator.config["ev_control"],
                "battery_control": self.coordinator.config["has_battery"] and self.coordinator.config["battery_control"],
                "home_basis": data.get("snapshot", {}).get("home_basis"), "grid_basis": data.get("snapshot", {}).get("grid_basis"),
                "ev_data_basis": data.get("snapshot", {}).get("ev_data_basis")}
        if self.key == "tariff_status":
            config = self.coordinator.config
            return {"supply_plan": config["supply_plan"], "delivery_plan": config["delivery_plan"],
                    "supply_periods": config["supply_periods"], "delivery_periods": config["delivery_periods"],
                    "status": data.get("forecast_status", {})}
        if "cost" in self.key or "credit" in self.key or self.key == "estimated_pricing_hours":
            ledger = data.get("ledger", {})
            return {"basis": "Measured grid power × contemporaneous supply + delivery; may include separately tracked published-forecast estimates. Not a settled bill; excludes fixed charges and unconfigured taxes.",
                    "coverage_hours": ledger.get("coverage_hours", 0),
                    "estimated_coverage_hours": ledger.get("estimated_coverage_hours", 0),
                    "estimated_import_cost": ledger.get("estimated_import_cost", 0),
                    "estimated_export_credit": ledger.get("estimated_export_credit", 0)}
        if self.key == "battery_calibration":
            return data.get("battery_calibration", {})
        if self.key in ("battery_efficiency_estimate", "battery_charge_estimate", "battery_discharge_estimate"):
            parameter = {"battery_efficiency_estimate": "round_trip_efficiency",
                         "battery_charge_estimate": "battery_charge_kw", "battery_discharge_estimate": "battery_discharge_kw"}[self.key]
            return data.get("battery_calibration", {}).get("estimates", {}).get(parameter, {})
        if self.key == "capacity":
            return {"basis": "Age model, not measured battery state of health", "install_date": self.coordinator.config["battery_install_date"]}
        return None
