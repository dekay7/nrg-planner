"""One settings catalogue, shared by forms, entities, validation and documentation.

Prices entered by people are cents/kWh. Calculations use dollars/kWh.
No equipment identifiers or credentials belong in this catalogue.
"""
from dataclasses import dataclass
from typing import Any

DOMAIN = "nrg"
VERSION = "0.2.0"
STATIC_URL = "/nrg-planner"
PLATFORMS = ["sensor", "binary_sensor", "number", "select", "switch", "date", "time", "datetime", "button", "text"]


@dataclass(frozen=True)
class Setting:
    name: str
    section: str
    kind: str
    default: Any
    description: str
    unit: str | None = None
    low: float = 0
    high: float = 100
    step: float = 1
    choices: tuple[str, ...] = ()


SETTINGS = {
    "has_ev": Setting("This home has an EV", "components", "switch", False, "Enable vehicle monitoring and its dashboard cards. Leave off if you have no EV; EV readings, controls and calibration will not be required."),
    "has_battery": Setting("This home has a stationary battery", "components", "switch", False, "Enable battery monitoring and capacity estimates. Leave off if you have no home battery; battery sensors, reserve and operating controls will not be required."),
    "has_solar": Setting("This home has solar", "components", "switch", False, "Enable solar production, forecasts and their dashboard cards. Leave off for a home without panels; the planner then knows solar production is zero."),
    "ev_control": Setting("Let NRG control EV charging", "components", "switch", False, "Optional. Enable after mapping your charging switch/current controls or HA command scripts. With this off, NRG monitors the car and leaves its charging to your existing system."),
    "battery_control": Setting("Let NRG control the home battery", "components", "switch", False, "Optional. Enable after mapping the battery's operating controls or command scripts. With this off, the battery remains monitored and NRG does not assume it can schedule its energy."),
    "mode": Setting("Operating mode", "operation", "select", "Observation", "Observation calculates without equipment commands. Control authorizes only the components you enabled for NRG control. Switching to Observation does not restore settings already saved in your equipment.", choices=("Observation", "Control")),
    "price_fallback": Setting("When current prices are unavailable", "fallback", "select", "Existing behavior", "Standard protection keeps the normal planner rules: no discretionary battery use without dependable prices, but EV charging may continue to meet departure. Use my fallback actions instead applies the device actions you review before saving. If prices are already unusable and Control is authorized, saving can apply them immediately. A failed fetch alone does not trigger those actions while the current price is still usable. Neither choice enables device control or overrides Observation or protection guards.", choices=("Existing behavior", "Custom fallback")),
    "fallback_ev": Setting("EV action when prices are unavailable", "fallback_actions", "select", "Pause scheduled charging", "Used only with Use my fallback actions and EV control enabled. Pause scheduled charging can leave the car below its target at departure. Charge for departure uses the available charging window and may buy at an unknown price; it is not a completion guarantee. Charge now explicitly overrides the pause, but not equipment checks.", choices=("Pause scheduled charging", "Maintain departure readiness")),
    "fallback_battery": Setting("Battery action when prices are unavailable", "fallback_actions", "select", "Preserve battery", "Used only with Use my fallback actions and battery control enabled. Save battery energy holds stored energy for later. Power home above reserve requests self-consumption, not forced export. Both turn off grid charging where supported, retain a higher native reserve, and respect protection guards. Preserve battery during EV charging still takes priority.", choices=("Preserve battery", "Self-consumption")),
    "supply_plan": Setting("Supply plan", "tariff", "select", "Flat supply", "Choose your provider's supply pricing: a flat rate, your own timed periods, an external HA price sensor/forecast, or the optional ComEd hourly feed. Delivery is configured separately and added once.", choices=("Flat supply", "Time-of-use supply", "External supply entity", "Hourly ComEd")),
    "comed_price_resilience": Setting("During ComEd live-price delays", "tariff", "select", "Strict live pricing", "Strict live pricing keeps the existing ten-minute new-hour forecast bridge. Allow brief published estimates uses a valid forecast for the exact current hour for at most 60 minutes from the last verified live observation. Pricing stays Degraded, EV planning can continue, and battery grid charging is blocked. Refreshes and restarts do not renew the allowance. Cold starts without a verified observation get only the ten-minute publication bridge. Your fallback actions still apply when the allowance or coverage ends; this choice does not enable equipment control.", choices=("Strict live pricing", "Allow brief published estimates")),
    "flat_supply_cents": Setting("Flat supply rate", "tariff", "number", None, "Your contracted supply price, excluding delivery. Unset means unknown, not free. Enter an explicit zero only if your contract really has a zero supply rate.", "¢/kWh", -100, 100, .001),
    "external_supply_attribute": Setting("Supply forecast attribute", "tariff", "text", "forecast", "For an external provider, name the attribute containing forecast intervals. Each interval needs start, end and price (or the documented aliases). Units are read from the row or price entity. An external current price alone does not invent future prices."),
    "delivery_plan": Setting("Delivery plan", "tariff", "select", "Flat delivery", "Delivery can have its own flat rate, timed periods or external sensor. Its schedule need not match the supply schedule. Edit periods under Configure → Pricing periods.", choices=("Flat delivery", "Time-of-use delivery", "External delivery entity")),
    "delivery_cents": Setting("Flat delivery rate", "tariff", "number", None, "Your variable delivery/rider cost in cents per imported kWh. Include applicable variable riders, not fixed monthly fees. Unset means unknown; explicitly enter zero if no separate delivery charge applies.", "¢/kWh", -100, 100, .001),
    "external_delivery_attribute": Setting("Delivery forecast attribute", "tariff", "text", "forecast", "Attribute containing external delivery-price intervals. Supply and delivery forecasts are independent. See the handbook's supported interval fields and units."),
    "export_rate": Setting("Export credit basis", "tariff", "select", "No credit", "Configure how exported energy is credited; do not assume exports receive the import delivery rate. Credits may have billing restrictions not modeled here.", choices=("Supply plus adder", "Flat credit", "No credit")),
    "export_adder_cents": Setting("Export credit adder", "tariff", "number", None, "Added to the selected supply price only for Supply plus adder exports. Enter your own export agreement's value, including an explicit zero if appropriate. Unset means unknown.", "¢/kWh", -100, 100, .001),
    "flat_export_cents": Setting("Flat export credit", "tariff", "number", None, "Credit per exported kWh when Flat credit is selected. Independent of your buying rate. Enter your own value; unset means unknown.", "¢/kWh", -100, 100, .001),
    "export_policy": Setting("Export policy", "tariff", "select", "Solar only", "Solar only allows solar exports; Battery also allows stored energy exports; No exports requests neither. NRG sends this preference only when a matching control is configured. Otherwise set the same policy in your equipment. Permission alone does not force a sale.", choices=("Solar only", "Battery", "No exports")),
    "solar_install_date": Setting("Solar installation date", "solar", "date", None, "Used for panel age when a source has Apply age correction enabled. Leave unset until known; no age correction is invented. Measured solar is never reduced."),
    "solar_degradation": Setting("Solar annual degradation", "solar", "number", .7, "Compounded yearly reduction in an unadjusted forecast: (1 − rate/100)^age. Sources already calibrated to present output should have age correction off.", "%/year", 0, 10, .1),
    "solar_learning": Setting("Solar forecast calibration", "solar", "switch", True, "Compare the forecast saved before each daylight hour with what your solar meter later measured. After six well-measured daylight hours, NRG adjusts future forecasts by actual ÷ forecast, using up to 168 recent daylight hours. For example, consistently producing 8 kWh when 10 kWh was forecast gives about a 0.8 multiplier. The correction is limited to 0.5–1.5. It changes predictions, never measured production or panel settings."),
    "battery_capacity": Setting("Battery capacity at installation", "battery", "number", 10, "Generic starting assumption: replace with your equipment's full-charge capacity before backup reserve. The age estimate reduces this number; reserve and conversion losses are applied separately.", "kWh", 1, 250, .1),
    "battery_install_date": Setting("Battery installation date", "battery", "date", None, "Baseline date for the capacity entered above. If capacity is a current measured value, use its measurement date. An unset date applies no age adjustment."),
    "battery_degradation": Setting("Battery annual degradation", "battery", "number", 2, "Compounded yearly reduction of estimated full-charge capacity. Does not change measured SOC, power limits or efficiency, and is not a measured battery health result.", "%/year", 0, 15, .1),
    "backup_reserve": Setting("Backup reserve", "battery", "number", 20, "Minimum battery percentage kept out of discretionary use. NRG also sets the device's reserve if that control is mapped. Configured outage/protection sensors take priority.", "%", 0, 100, 1),
    "round_trip_efficiency": Setting("Battery round-trip efficiency", "battery", "number", 90, "Fallback AC-to-storage-to-AC efficiency when calibration is off or lacks enough cycles. Equal square-root losses are applied when charging and discharging. Learning never overwrites this value.", "%", 50, 100, 1),
    "battery_charge_kw": Setting("Modeled battery charging power", "battery", "number", 5, "Fallback charging power when calibration is off or lacks enough sustained charging opportunities. This is a model assumption, not a device watt setting or a ceiling on learned estimates. Use a conservative value supported by your equipment.", "kW", .5, 30, .5),
    "battery_discharge_kw": Setting("Modeled battery discharge power", "battery", "number", 5, "Fallback discharging power when calibration is off or lacks enough sustained discharge opportunities. This is a model assumption, not a device watt setting or a ceiling on learned estimates. Compare the effective estimate in Details with your equipment.", "kW", .5, 30, .5),
    "battery_learning": Setting("Calibrate battery estimates", "battery", "switch", False, "Opt in only with AC-side battery power and SOC measurements; DC battery-terminal meters are not supported. Passively calibrate round-trip efficiency after three covered cycles with at least a 30-point SOC excursion and return to the starting SOC. Charging and discharging power each need three sustained opportunities with spare supply or unmet demand, not ordinary low-load averages. Estimates use up to 12 recent observations per parameter within 30 days. Optional paired lifetime AC energy counters improve efficiency measurement; otherwise power is integrated. Manual values remain independent fallbacks. Learning sends no calibration commands and does not estimate capacity, degradation or battery health. Off stops battery learning and uses your manual values without deleting completed observations."),
    "battery_solar_while_held": Setting("Solar can recharge the battery while held", "battery", "switch", True, "Enable if the selected hold mode still accepts solar charging, as Tesla Backup normally does. Turn off if your inverter's standby mode prevents solar charging too. This changes the battery forecast to match the device's behavior."),
    "hold_battery_for_ev": Setting("Preserve battery during EV charging", "ev", "switch", True, "When NRG controls both devices, ask the home battery to hold its energy while the car charges. Commands can take time to reach the equipment, so the battery may briefly supply the car before the hold takes effect. With a monitored-only battery, set that behavior in its own controller."),
    "departure_time": Setting("Daily EV departure", "ev", "time", "08:00:00", "Generic starting time: enter your own local departure. A one-off departure takes precedence. Incomplete connected sessions remain overdue."),
    "ev_start_time": Setting("Normal charging window starts", "ev", "time", "20:00:00", "Start of normal daily charging availability. Review this generic window. It ends at departure; charge-now and deadline urgency can use time outside it."),
    "completion_buffer": Setting("EV completion buffer", "ev", "number", 45, "Aim to finish this many minutes before departure. Use the buffer if needed rather than miss the actual departure.", "min", 0, 180, 5),
    "ev_max_amps": Setting("Maximum EV charging current", "ev", "number", 16, "Generic starting limit: enter a current supported by your charger and circuit. Also bounded by the control entity's maximum, rounded down to whole amps for planning and commands. Script adapters need the real supported limit here. NRG never raises the vehicle's selected charge limit.", "A", 5, 80, 1),
    "ev_min_amps": Setting("Minimum stable EV current", "ev", "number", 6, "Smallest current used for solar-aware charging. NRG also honors the control entity's minimum, rounded up to whole amps. Below the effective minimum the car is paused. Must be no greater than your maximum current.", "A", 5, 32, 1),
    "ev_kw_at_max": Setting("Conservative EV power at maximum current", "ev", "number", 3.2, "Generic starting estimate: enter your measured AC charging power at the configured maximum current. Covered wall-charger observations can calibrate it.", "kW", .5, 25, .1),
    "ev_kwh_per_percent": Setting("EV AC energy per percentage point", "ev", "number", .6, "Generic starting estimate: replace with AC energy per vehicle SOC percentage point, including losses. Covered charging sessions can calibrate it; this is not an EV degradation model.", "kWh/%", .1, 3, .01),
    "ev_learning": Setting("Calibrate EV charging estimates", "ev", "switch", True, "Use observed AC energy and the car's percentage gain to estimate how much electricity charging needs. Sessions need at least 5 percentage points, 5 minutes and good meter coverage. NRG uses a conservative estimate from the last 12 sessions, and measured power per amp to improve charging-time estimates. Example: 9 kWh for a 10-point gain suggests 0.9 kWh per point. This estimates charging needs, not EV battery degradation. Off uses your fallback values."),
    "ev_allow_saved_readings": Setting("Allow saved vehicle readings while plugged in", "ev", "switch", False, "Some MQTT/vehicle feeds publish SOC, target and settings only when they change, so their saved values become old while the car sleeps. Enable to accept those available saved values while the home charger reports connected. Connection/protection checks and command readbacks still apply. Otherwise vehicle data needs recent reports; an asleep feed may need its own wake/refresh automation. Estimates can be less current when saved readings are allowed."),
    "house_learning": Setting("Learn household demand", "planning", "switch", True, "Learn typical home use at each clock hour from up to 28 days of meter readings. If an EV is installed, subtract its separately measured charging so it is not counted twice. An hour needs at least 80% valid coverage. Recent observations count more; weekday/weekend patterns separate after enough samples. This predicts ordinary demand so the battery and price advice can plan around daily life. Missing hours use your fallback, not zero."),
    "house_kw": Setting("Fallback house demand without EV", "planning", "number", 1, "Used for clock hours without enough observations, or with learning disabled. Excludes the car to avoid counting it twice.", "kW", .1, 30, .1),
    "flexible_load_kwh": Setting("Flexible appliance energy", "planning", "number", 1, "Energy used for household run-now versus later advice. Advice never starts an appliance.", "kWh", .1, 30, .1),
    "flexible_load_minutes": Setting("Flexible appliance duration", "planning", "number", 60, "Contiguous running time for the reference appliance. Every suggested window must fit this whole duration.", "min", 15, 360, 15),
    "minimum_saving_cents": Setting("Minimum worthwhile plan improvement", "planning", "number", 2, "Prefer a stable existing feasible plan unless a replacement improves modeled horizon cost by at least this amount. Also used for generic household advice.", "¢", 0, 500, 1),
    "battery_wear_cents": Setting("Optional battery cycling cost", "planning", "number", 0, "Optional estimated wear cost per AC kWh discharged. Calendar degradation above does not establish a cycling cost; zero makes no invented wear charge.", "¢/kWh", 0, 50, .1),
    "notifications": Setting("Send household advice notifications", "notifications", "switch", False, "Opt in to stable, worthwhile wait-until recommendations. Choose notify services in Configure → Notifications. Notifications do not command equipment."),
    "notification_saving_cents": Setting("Minimum benefit for household advice", "notifications", "number", 25, "Applies only to household advice notifications, not price-data fallback messages. Notify when delaying the reference appliance is expected to save at least this amount and the advice stays stable for two minutes.", "¢", 0, 1000, 1),
    "fallback_notifications": Setting("Send price-data fallback alerts", "notifications", "switch", False, "Optional entry and recovery alerts for Use my fallback actions, independent of household advice notifications and their savings threshold. Both message types share the selected notification services and quiet hours. This switch does not enable fallback or equipment control. Observation alerts describe a proposal, not equipment execution."),
    "quiet_start": Setting("Notification quiet hours start", "notifications", "time", "21:00:00", "Local start of quiet hours. Advice remains available on the dashboard."),
    "quiet_end": Setting("Notification quiet hours end", "notifications", "time", "08:00:00", "Local end of quiet hours. Equal start/end disables the quiet-hours restriction."),
    "grid_power_inverted": Setting("Grid meter reports export as positive", "measurements", "switch", False, "Enable when your provider reports positive export and negative import. NRG reverses that reading so its normalized grid power always means positive buying and negative selling."),
    "battery_power_inverted": Setting("Battery meter reports charging as positive", "measurements", "switch", False, "Enable when your provider reports positive charging and negative discharge. NRG reverses it so positive always means supplying the home in its own displays and model."),
    "home_includes_ev": Setting("Home meter includes EV charging", "measurements", "switch", True, "Enable for a whole-home load meter that includes the car. Disable for a house-only circuit meter; NRG then adds separately measured EV power for the Home total while learning the house-only reading directly."),
}

# Form order: home, grid/pricing, solar, battery/protection, then vehicle.
# Entity mappings are selected in the integration's Sources settings. No credentials.
MAPPINGS = {
    "home_power": ("Whole-home power", "sensor", "Total AC household demand including the EV, from any provider, W or kW."),
    "grid_power": ("Signed grid power", "sensor", "Grid meter: positive import, negative export, W or kW."),
    "grid_connected": ("Grid connected (optional)", "binary_sensor", "Optional protection input: on while connected. If selected, missing/off prevents equipment commands."),
    "live_supply": ("Current supply price (optional)", "sensor", "External supply-price sensor in cents/kWh or USD/kWh. Also usable instead of the live ComEd API in ComEd mode."),
    "supply_forecast": ("External supply forecast (optional)", "sensor", "Sensor with a list of price intervals in its configured forecast attribute. May be the same as the current-price sensor."),
    "live_delivery": ("Current delivery price (optional)", "sensor", "External delivery-price sensor for External delivery entity mode."),
    "delivery_forecast": ("External delivery forecast (optional)", "sensor", "Independent delivery-price interval list. Missing intervals remain unknown."),
    "solar_power": ("Actual solar power", "sensor", "Solar production from any integration, W or kW. Prefer a local meter when available."),
    "battery_power": ("Signed battery power", "sensor", "AC-side battery meter: positive discharge, negative charging, W or kW. DC battery-terminal power is not suitable for AC flows or battery calibration."),
    "battery_soc": ("Battery charge", "sensor", "Home battery percentage, independent of manufacturer or integration."),
    "battery_charge_energy": ("Battery lifetime AC charging energy (optional)", "sensor", "Increasing AC kWh received by the battery system, not stored DC energy or a resetting daily/session counter. Select both battery energy counters or neither; both must use the same AC boundary as battery power."),
    "battery_discharge_energy": ("Battery lifetime AC discharged energy (optional)", "sensor", "Increasing AC kWh delivered by the battery system. Pair with lifetime AC charging energy; missing/resetting selected counters pause efficiency learning rather than switching measurement methods."),
    "battery_mode": ("Battery mode control / feedback", ("select", "sensor", "input_select"), "Select/input_select controls work directly. Read-only feedback needs a script adapter. Configure the device's actual hold/serve/charge option names."),
    "battery_reserve": ("Battery reserve control / feedback (optional)", ("number", "sensor", "input_number"), "Optional device backup-reserve setting. Read-only feedback can be paired with a script adapter."),
    "battery_grid_charge": ("Grid-charge permission (optional)", ("switch", "binary_sensor", "sensor", "input_boolean"), "Optional permission switch. A separate force-charge operating mode can be used instead; no grid-charge commands are invented for unsupported devices."),
    "battery_export": ("Export policy control / feedback (optional)", ("select", "sensor", "input_select"), "Optional export-permission control. Configure option names under Control adapters. If omitted, set the policy in the device's own app."),
    "storm_watch": ("Protection event active (optional)", "binary_sensor", "Optional active protection event, e.g. Storm Watch or a manufacturer override. On or missing blocks commands when selected."),
    "grid_services": ("Grid services active (optional)", "binary_sensor", "Optional utility/grid-services event. On or missing blocks commands when selected."),
    "grid_services_enabled": ("External controller priority (optional)", "binary_sensor", "Optional ownership/protection flag: while on, an external controller has priority."),
    "ev_connected": ("EV plugged in", "binary_sensor", "Plug/connection sensor from any provider. If it identifies this home's charger, location need not also be mapped."),
    "ev_location": ("EV at home (optional)", ("device_tracker", "binary_sensor", "sensor"), "Optional additional home check: home for a tracker/sensor or on for a binary sensor. Omit when the connection sensor already identifies the home charger."),
    "ev_soc": ("Vehicle charge", "sensor", "Vehicle battery percentage, e.g. TeslaMate, Teslemetry, Tessie or another EV integration."),
    "ev_limit": ("Selected vehicle charge limit", ("number", "sensor", "input_number"), "Selected target percentage. Read only: NRG never raises it."),
    "ev_power": ("EV charging power", "sensor", "AC charging power from a charger or vehicle integration. Local meters are preferred, not required."),
    "ev_energy": ("EV lifetime AC energy", "sensor", "Increasing AC kWh counter for charging, not a resetting session counter. Optional; EV calibration needs it."),
    "ev_measured_current": ("EV measured current", "sensor", "Optional actual charging current in amperes. Otherwise the configured current-setting entity is used for power calibration."),
    "ev_current": ("EV current setting / feedback", ("number", "sensor", "input_number"), "Current setting in A. Number/input_number controls work directly. A read-only sensor needs an EV current script under Control adapters."),
    "ev_charge": ("EV charging control / feedback", ("switch", "binary_sensor", "sensor", "input_boolean"), "Switches work directly. Read-only state feedback needs start/stop scripts. Set its charging/paused state values under Control adapters if they are not on/off."),
}

# Friendly UI labels do not change saved values or control-policy comparisons.
OPTION_LABELS = {
    "price_fallback": {"Existing behavior": "Standard protection (default)", "Custom fallback": "Use my fallback actions"},
    "fallback_ev": {"Pause scheduled charging": "Pause scheduled charging", "Maintain departure readiness": "Charge for departure (price unknown)"},
    "fallback_battery": {"Preserve battery": "Save battery energy", "Self-consumption": "Power home above reserve (self-consumption)"},
}


def option_label(key, value):
    return OPTION_LABELS.get(key, {}).get(value, value)


DEFAULTS = {key: field.default for key, field in SETTINGS.items()}
OPTIONAL_RATES = frozenset({"flat_supply_cents", "delivery_cents", "export_adder_cents", "flat_export_cents"})
EXPORT_OPTIONS = {"Solar only": "pv_only", "Battery": "battery_ok", "No exports": "never"}
CONTROL_VALUES = {"battery_hold": "backup", "battery_serve": "self_consumption", "battery_charge": "backup",
                  "export_solar": "pv_only", "export_battery": "battery_ok", "export_none": "never",
                  "ev_on": "on", "ev_off": "off", "grid_charge_on": "on", "grid_charge_off": "off"}
COMMAND_SCRIPTS = ("ev_current", "ev_start", "ev_stop", "battery_mode", "battery_export", "battery_reserve", "grid_charge_on", "grid_charge_off")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
