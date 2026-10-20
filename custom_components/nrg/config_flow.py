"""Native setup and sectioned settings; all saved values live in entry.options."""
from datetime import datetime
from zoneinfo import ZoneInfo

import probatio as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .config import settings, validate, validate_sources
from .const import DOMAIN, MAPPINGS, SETTINGS, CONTROL_VALUES, COMMAND_SCRIPTS, WEEKDAYS, OPTIONAL_RATES
from .tariffs import schedule_complete


def fields(section, options):
    schema = {}
    values = settings(options)
    for key, field in SETTINGS.items():
        if field.section != section:
            continue
        marker = vol.Optional(key, description={"suggested_value": values[key]}) if values[key] is not None else vol.Optional(key)
        if field.kind == "number":
            control = selector.NumberSelector(selector.NumberSelectorConfig(min=field.low, max=field.high,
                step=field.step, mode=selector.NumberSelectorMode.BOX, unit_of_measurement=field.unit))
        elif field.kind == "select":
            control = selector.SelectSelector(selector.SelectSelectorConfig(options=list(field.choices), mode=selector.SelectSelectorMode.DROPDOWN))
        elif field.kind == "date":
            control = selector.DateSelector()
        elif field.kind == "time":
            control = selector.TimeSelector()
        elif field.kind == "text":
            control = selector.TextSelector()
        else:
            control = selector.BooleanSelector()
        schema[marker] = control
    if section == "ev":
        schema[vol.Optional("departure_override", description={"suggested_value": options.get("departure_override")})] = selector.DateTimeSelector()
    return vol.Schema(schema)


def mapping_fields(options):
    config = settings(options)
    def relevant(key):
        if key.startswith("ev_") and not config["has_ev"]:
            return False
        if key.startswith("battery_") and not config["has_battery"]:
            return False
        if key == "solar_power" and not config["has_solar"]:
            return False
        if key in ("storm_watch", "grid_services", "grid_services_enabled") and not config["has_battery"]:
            return False
        if key == "grid_connected" and not (config["has_ev"] or config["has_battery"]):
            return False
        if key == "live_supply" and config["supply_plan"] not in ("Hourly ComEd", "External supply entity"):
            return False
        if key == "supply_forecast" and config["supply_plan"] != "External supply entity":
            return False
        if key in ("live_delivery", "delivery_forecast") and config["delivery_plan"] != "External delivery entity":
            return False
        return True
    return vol.Schema({vol.Optional(key, description={"suggested_value": options.get("mappings", {}).get(key)}):
        selector.EntitySelector(selector.EntitySelectorConfig(domain=list(domain) if isinstance(domain, tuple) else domain))
        for key, (_, domain, _) in MAPPINGS.items() if relevant(key)})


def checked(hass, options):
    result = validate(options, datetime.now(ZoneInfo(hass.config.time_zone)).date())
    validate_sources(result.get("solar_sources", []))
    override = result.get("departure_override")
    if override:
        parsed = datetime.fromisoformat(override)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(hass.config.time_zone))
        # Keep a previously saved overdue override until explicitly cleared.
        result["departure_override"] = parsed.isoformat()
    for key, entity_id in result.get("mappings", {}).items():
        if key not in MAPPINGS or entity_id.split(".")[0] not in (MAPPINGS[key][1] if isinstance(MAPPINGS[key][1], tuple) else (MAPPINGS[key][1],)):
            raise ValueError(f"{key}: select an entity with the required domain")
        entry = er.async_get(hass).async_get(entity_id)
        if entry is not None and entry.disabled_by is not None:
            raise ValueError(f"{key}: choose an enabled entity")
    return result


class NRGConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NRGOptionsFlow()

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id("nrg_home")
        self._abort_if_unique_id_configured()
        if user_input is not None:
            self._initial = {key:field.default for key,field in SETTINGS.items() if field.section == "components"} | user_input
            return await self.async_step_tariff()
        return self.async_show_form(step_id="user", data_schema=fields("components", {}))

    async def async_step_tariff(self, user_input=None):
        if user_input is not None:
            self._initial |= user_input
            return await self.async_step_mappings()
        return self.async_show_form(step_id="tariff", data_schema=fields("tariff", self._initial))

    async def async_step_mappings(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                options = checked(self.hass, self._initial | {"mappings": user_input, "mode": "Observation", "solar_sources": []})
                return self.async_create_entry(title="NRG Planner", data={}, options=options)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        return self.async_show_form(step_id="mappings", data_schema=mapping_fields(self._initial), errors=errors,
                                    description_placeholders={"error": getattr(self, "_error", "")})

    async def async_step_import(self, user_input):
        await self.async_set_unique_id("nrg_home")
        self._abort_if_unique_id_configured()
        try:
            options = checked(self.hass, dict(user_input) | {"mode": "Observation"})
        except (ValueError, TypeError):
            return self.async_abort(reason="invalid_bootstrap")
        return self.async_create_entry(title="NRG Planner", data={}, options=options)


class NRGOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        config = settings(self.config_entry.options)
        menu = ["components", "operation", "tariff", "pricing_periods"]
        menu += [name for name in ("solar", "battery", "ev") if config["has_" + name]]
        menu += ["planning", "notifications", "mappings", "measurements"]
        if config["has_ev"] or config["has_battery"]:
            menu.append("controls")
        if config["has_solar"]:
            menu.append("sources")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def section(self, section, user_input):
        errors = {}
        if user_input is not None:
            changes = dict(user_input)
            for key, field in SETTINGS.items():
                if field.section == section and field.kind == "date" and key not in changes:
                    changes[key] = None
                if field.section == section and key in OPTIONAL_RATES and key not in changes:
                    changes[key] = None
            if section == "ev" and "departure_override" not in changes:
                changes["departure_override"] = None
            if section == "notifications" and "notification_targets" not in changes:
                changes["notification_targets"] = []
            try:
                result = checked(self.hass, dict(self.config_entry.options) | changes)
                return self.async_create_entry(title="", data=result)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        schema = fields(section, dict(self.config_entry.options))
        if section == "notifications":
            services = sorted("notify." + name for name in self.hass.services.async_services().get("notify", {}))
            schema = schema.extend({vol.Optional("notification_targets", description={"suggested_value": self.config_entry.options.get("notification_targets", [])}):
                selector.SelectSelector(selector.SelectSelectorConfig(options=services, multiple=True))})
        return self.async_show_form(step_id=section, data_schema=schema,
                                    errors=errors, description_placeholders={"error": getattr(self, "_error", "")})

    async def async_step_operation(self, user_input=None):
        return await self.section("operation", user_input)

    async def async_step_components(self, user_input=None):
        return await self.section("components", user_input)

    async def async_step_tariff(self, user_input=None):
        return await self.section("tariff", user_input)

    async def async_step_solar(self, user_input=None):
        return await self.section("solar", user_input)

    async def async_step_battery(self, user_input=None):
        return await self.section("battery", user_input)

    async def async_step_ev(self, user_input=None):
        return await self.section("ev", user_input)

    async def async_step_planning(self, user_input=None):
        return await self.section("planning", user_input)

    async def async_step_notifications(self, user_input=None):
        return await self.section("notifications", user_input)

    async def async_step_measurements(self, user_input=None):
        return await self.section("measurements", user_input)

    async def async_step_mappings(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                # Preserve mappings for disabled devices so re-enabling restores them.
                visible = {marker.schema for marker in mapping_fields(self.config_entry.options).schema}
                mappings = {k: v for k, v in self.config_entry.options.get("mappings", {}).items() if k not in visible}
                mappings.update(user_input)
                result = checked(self.hass, dict(self.config_entry.options) | {"mappings": mappings})
                return self.async_create_entry(title="", data=result)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        return self.async_show_form(step_id="mappings", data_schema=mapping_fields(self.config_entry.options), errors=errors,
                                    description_placeholders={"error": getattr(self, "_error", "")})

    async def async_step_sources(self, user_input=None):
        return self.async_show_menu(step_id="sources", menu_options=["add_source", "edit_source", "remove_source"])

    async def async_step_controls(self, user_input=None):
        config = settings(self.config_entry.options)
        def relevant(key):
            return config["has_ev"] if key.startswith("ev_") else config["has_battery"]
        errors = {}
        if user_input is not None:
            try:
                values = {k:v for k,v in config["control_values"].items() if not relevant(k)} | {k: v for k, v in user_input.items() if k in CONTROL_VALUES}
                scripts = {k:v for k,v in config["command_scripts"].items() if not relevant(k)} | {k.removeprefix("script_"): v for k, v in user_input.items() if k.startswith("script_")}
                result = checked(self.hass, dict(self.config_entry.options) | {"control_values": values, "command_scripts": scripts})
                return self.async_create_entry(title="", data=result)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        schema = {}
        for key, value in config["control_values"].items():
            if not relevant(key):
                continue
            role = "battery_mode" if key.startswith("battery_") else "battery_export" if key.startswith("export_") else None
            entity = self.hass.states.get(self.config_entry.options.get("mappings", {}).get(role, "")) if role else None
            choices = list(entity.attributes.get("options", [])) if entity else []
            schema[vol.Required(key, default=value)] = selector.SelectSelector(selector.SelectSelectorConfig(options=choices, custom_value=True)) if choices else str
        for key in COMMAND_SCRIPTS:
            if not relevant(key):
                continue
            schema[vol.Optional("script_" + key, description={"suggested_value": config["command_scripts"].get(key)})] = selector.EntitySelector(selector.EntitySelectorConfig(domain="script"))
        return self.async_show_form(step_id="controls", data_schema=vol.Schema(schema), errors=errors,
                                    description_placeholders={"error": getattr(self, "_error", "")})

    async def async_step_pricing_periods(self, user_input=None):
        if user_input:
            self._period_kind = user_input["component"]
            return await self.async_step_period_actions()
        return self.async_show_form(step_id="pricing_periods", data_schema=vol.Schema({
            vol.Required("component"): selector.SelectSelector(selector.SelectSelectorConfig(options=["supply", "delivery"]))}))

    async def async_step_period_actions(self, user_input=None):
        return self.async_show_menu(step_id="period_actions", menu_options=["add_period", "edit_period", "remove_period", "template_periods"])

    def period_choices(self):
        return [{"value": str(i), "label": f"{p['label']} · {p['start']}–{p['end']} · {p.get('rate_cents') if p.get('rate_cents') is not None else 'rate needed'} ¢/kWh"}
                for i, p in enumerate(self.config_entry.options.get(self._period_kind + "_periods", []))]

    async def async_step_add_period(self, user_input=None):
        self._period_index = None
        return await self.async_step_period(user_input)

    async def async_step_edit_period(self, user_input=None):
        if user_input:
            self._period_index = int(user_input["period"])
            self._period_original = dict(self.config_entry.options[self._period_kind + "_periods"][self._period_index])
            return await self.async_step_period()
        if not self.period_choices():
            return self.async_abort(reason="no_periods")
        return self.async_show_form(step_id="edit_period", data_schema=vol.Schema({vol.Required("period"):
            selector.SelectSelector(selector.SelectSelectorConfig(options=self.period_choices()))}))

    async def async_step_remove_period(self, user_input=None):
        if user_input:
            key = self._period_kind + "_periods"
            periods = list(self.config_entry.options.get(key, []))
            periods.pop(int(user_input["period"]))
            return self.async_create_entry(title="", data=dict(self.config_entry.options) | {key: periods})
        if not self.period_choices():
            return self.async_abort(reason="no_periods")
        return self.async_show_form(step_id="remove_period", data_schema=vol.Schema({vol.Required("period"):
            selector.SelectSelector(selector.SelectSelectorConfig(options=self.period_choices()))}))

    async def async_step_template_periods(self, user_input=None):
        key = self._period_kind + "_periods"
        if self.config_entry.options.get(key):
            return self.async_abort(reason="schedule_not_empty")
        rows = [{"label": label, "start": start, "end": end, "rate_cents": None, "days": list(WEEKDAYS)}
                for label, start, end in (("Morning", "06:00:00", "13:00:00"), ("Mid-Day Peak", "13:00:00", "19:00:00"),
                                          ("Evening", "19:00:00", "21:00:00"), ("Overnight", "21:00:00", "06:00:00"))]
        return self.async_create_entry(title="", data=dict(self.config_entry.options) | {key: rows})

    async def async_step_period(self, user_input=None):
        key = self._period_kind + "_periods"
        rows = list(self.config_entry.options.get(key, []))
        index = getattr(self, "_period_index", None)
        current = rows[index] if index is not None and index < len(rows) else {}
        errors = {}
        if user_input:
            try:
                if index is not None and current != self._period_original:
                    raise ValueError("The schedule changed; reopen the period editor")
                updated = rows + [dict(user_input)] if index is None else [dict(user_input) if i == index else row for i, row in enumerate(rows)]
                result = checked(self.hass, dict(self.config_entry.options) | {key: updated})
                return self.async_create_entry(title="", data=result)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        schema = vol.Schema({
            vol.Required("label", default=current.get("label", "")): str,
            vol.Required("start", default=current.get("start", "06:00:00")): selector.TimeSelector(),
            vol.Required("end", default=current.get("end", "13:00:00")): selector.TimeSelector(),
            vol.Required("rate_cents", description={"suggested_value": current.get("rate_cents")}): selector.NumberSelector(selector.NumberSelectorConfig(min=-1000, max=1000, step=.001, unit_of_measurement="¢/kWh", mode=selector.NumberSelectorMode.BOX)),
            vol.Required("days", default=current.get("days", list(WEEKDAYS))): selector.SelectSelector(selector.SelectSelectorConfig(options=list(WEEKDAYS), multiple=True))})
        return self.async_show_form(step_id="period", data_schema=schema, errors=errors,
            description_placeholders={"component": self._period_kind, "error": getattr(self, "_error", ""),
                                      "coverage": "Complete weekly schedule" if schedule_complete(rows) else "Some hours or rates are not configured; those prices stay unknown"})

    async def async_step_add_source(self, user_input=None):
        self._editing = None
        return await self.async_step_source(user_input)

    def source_choices(self):
        return [{"value": s["entity_id"], "label": f"{s.get('label', s['entity_id'])} · {s['group']}"}
                for s in self.config_entry.options.get("solar_sources", [])]

    async def async_step_edit_source(self, user_input=None):
        if user_input:
            self._editing = user_input["entity_id"]
            return await self.async_step_source()
        if not self.source_choices():
            return self.async_abort(reason="no_sources")
        return self.async_show_form(step_id="edit_source", data_schema=vol.Schema({
            vol.Required("entity_id"): selector.SelectSelector(selector.SelectSelectorConfig(options=self.source_choices()))}))

    async def async_step_remove_source(self, user_input=None):
        if user_input:
            result = dict(self.config_entry.options)
            result["solar_sources"] = [s for s in result.get("solar_sources", []) if s["entity_id"] != user_input["entity_id"]]
            return self.async_create_entry(title="", data=result)
        if not self.source_choices():
            return self.async_abort(reason="no_sources")
        return self.async_show_form(step_id="remove_source", data_schema=vol.Schema({
            vol.Required("entity_id"): selector.SelectSelector(selector.SelectSelectorConfig(options=self.source_choices()))}))

    async def async_step_source(self, user_input=None):
        errors = {}
        sources = list(self.config_entry.options.get("solar_sources", []))
        current = next((s for s in sources if s["entity_id"] == getattr(self, "_editing", None)), {})
        if user_input:
            try:
                selected = er.async_get(self.hass).async_get(user_input["entity_id"])
                if selected is None or selected.platform != "forecast_solar" or selected.disabled_by is not None:
                    raise ValueError("Choose an enabled Forecast.Solar entity")
                source = dict(user_input) | {"config_entry_id": selected.config_entry_id}
                updated = [s for s in sources if s["entity_id"] != getattr(self, "_editing", None)] + [source]
                result = checked(self.hass, dict(self.config_entry.options) | {"solar_sources": updated})
                return self.async_create_entry(title="", data=result)
            except ValueError as error:
                errors["base"] = "invalid_settings"
                self._error = str(error)
        return self.async_show_form(step_id="source", errors=errors,
            description_placeholders={"error": getattr(self, "_error", "")}, data_schema=vol.Schema({
                vol.Required("entity_id", description={"suggested_value": current.get("entity_id")}): selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor", integration="forecast_solar")),
                vol.Required("label", default=current.get("label", "Solar forecast")): str,
                vol.Required("group", default=current.get("group", "")): str,
                vol.Required("weight", default=current.get("weight", 1)): selector.NumberSelector(selector.NumberSelectorConfig(min=.1, max=100, step=.1, mode=selector.NumberSelectorMode.BOX)),
                vol.Required("apply_age", default=current.get("apply_age", True)): selector.BooleanSelector(),
            }))
