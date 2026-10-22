# Settings reference

Open **NRG Planner settings**, or **Settings → Devices & services → NRG Planner → Configure**.

These descriptions and defaults are generated from the same catalogue as the setup forms. **On** means enabled; **Off** means disabled. **Unset** means no value has been supplied, not zero. Numeric ranges describe what the form accepts, not what your equipment supports.

All settings below persist across HA restarts. The separate charge-now override is intentionally session-only; see [everyday controls](operations.md#everyday-controls).

## Components

Select the equipment you have. Monitoring and command permission are separate.

### This home has an EV

Default: **Off**.

Enable vehicle monitoring and its dashboard cards. Leave off if you have no EV; EV readings, controls and calibration will not be required.

Reference key: `has_ev`.

### This home has a stationary battery

Default: **Off**.

Enable battery monitoring and capacity estimates. Leave off if you have no home battery; battery sensors, reserve and operating controls will not be required.

Reference key: `has_battery`.

### This home has solar

Default: **Off**.

Enable solar production, forecasts and their dashboard cards. Leave off for a home without panels; the planner then knows solar production is zero.

Reference key: `has_solar`.

### Let NRG control EV charging

Default: **Off**.

Optional. Enable after mapping your charging switch/current controls or HA command scripts. With this off, NRG monitors the car and leaves its charging to your existing system.

Reference key: `ev_control`.

### Let NRG control the home battery

Default: **Off**.

Optional. Enable after mapping the battery's operating controls or command scripts. With this off, the battery remains monitored and NRG does not assume it can schedule its energy.

Reference key: `battery_control`.

## Operation

Choose whether schedules remain proposals or can operate enabled equipment.

### Operating mode

Default: **Observation**.

Observation calculates without equipment commands. Control authorizes only the components you enabled for NRG control. Switching to Observation does not restore settings already saved in your equipment.

Choices: **Observation**, **Control**.

Reference key: `mode`.

## Price-data fallback

Choose the protection policy under Configure → Price-data fallback. This is separate from equipment permissions and operating mode.

### When current prices are unavailable

Default: **Standard protection (default)**.

Standard protection keeps the normal planner rules: no discretionary battery use without dependable prices, but EV charging may continue to meet departure. Use my fallback actions instead applies the device actions you review before saving. If prices are already unusable and Control is authorized, saving can apply them immediately. A failed fetch alone does not trigger those actions while the current price is still usable. Neither choice enables device control or overrides Observation or protection guards.

Choices: **Standard protection (default)**, **Use my fallback actions**.

Reference key: `price_fallback`.

## Fallback device actions

The next screen after choosing Use my fallback actions shows only devices enabled for NRG control. Hidden choices are retained, not reset. The dashboard groups these settings on its Price-data fallback page.

### EV action when prices are unavailable

Default: **Pause scheduled charging**.

Used only with Use my fallback actions and EV control enabled. Pause scheduled charging can leave the car below its target at departure. Charge for departure uses the available charging window and may buy at an unknown price; it is not a completion guarantee. Charge now explicitly overrides the pause, but not equipment checks.

Choices: **Pause scheduled charging**, **Charge for departure (price unknown)**.

Reference key: `fallback_ev`.

### Battery action when prices are unavailable

Default: **Save battery energy**.

Used only with Use my fallback actions and battery control enabled. Save battery energy holds stored energy for later. Power home above reserve requests self-consumption, not forced export. Both turn off grid charging where supported, retain a higher native reserve, and respect protection guards. Preserve battery during EV charging still takes priority.

Choices: **Save battery energy**, **Power home above reserve (self-consumption)**.

Reference key: `fallback_battery`.

## Tariff

Set your supply, delivery, and export pricing. For timed rates, use [Pricing periods](pricing.md#editing-timed-periods-in-ha).

### Supply plan

Default: **Flat supply**.

Choose your provider's supply pricing: a flat rate, your own timed periods, an external HA price sensor/forecast, or the optional ComEd hourly feed. Delivery is configured separately and added once.

Choices: **Flat supply**, **Time-of-use supply**, **External supply entity**, **Hourly ComEd**.

Reference key: `supply_plan`.

### During ComEd live-price delays

Default: **Strict live pricing**.

Strict live pricing keeps the existing ten-minute new-hour forecast bridge. Allow brief published estimates uses a valid forecast for the exact current hour for at most 60 minutes from the last verified live observation. Pricing stays Degraded, EV planning can continue, and battery grid charging is blocked. Refreshes and restarts do not renew the allowance. Cold starts without a verified observation get only the ten-minute publication bridge. Your fallback actions still apply when the allowance or coverage ends; this choice does not enable equipment control.

Choices: **Strict live pricing**, **Allow brief published estimates**.

Reference key: `comed_price_resilience`.

### Flat supply rate

Default: **Unset**.

Your contracted supply price, excluding delivery. Unset means unknown, not free. Enter an explicit zero only if your contract really has a zero supply rate.

Accepted range: **-100 to 100 ¢/kWh**; adjustable in increments of **0.001 ¢/kWh**.

Reference key: `flat_supply_cents`.

### Supply forecast attribute

Default: **forecast**.

For an external provider, name the attribute containing forecast intervals. Each interval needs start, end and price (or the documented aliases). Units are read from the row or price entity. An external current price alone does not invent future prices.

Reference key: `external_supply_attribute`.

### Delivery plan

Default: **Flat delivery**.

Delivery can have its own flat rate, timed periods or external sensor. Its schedule need not match the supply schedule. Edit periods under Configure → Pricing periods.

Choices: **Flat delivery**, **Time-of-use delivery**, **External delivery entity**.

Reference key: `delivery_plan`.

### Flat delivery rate

Default: **Unset**.

Your variable delivery/rider cost in cents per imported kWh. Include applicable variable riders, not fixed monthly fees. Unset means unknown; explicitly enter zero if no separate delivery charge applies.

Accepted range: **-100 to 100 ¢/kWh**; adjustable in increments of **0.001 ¢/kWh**.

Reference key: `delivery_cents`.

### Delivery forecast attribute

Default: **forecast**.

Attribute containing external delivery-price intervals. Supply and delivery forecasts are independent. See the handbook's supported interval fields and units.

Reference key: `external_delivery_attribute`.

### Export credit basis

Default: **No credit**.

Configure how exported energy is credited; do not assume exports receive the import delivery rate. Credits may have billing restrictions not modeled here.

Choices: **Supply plus adder**, **Flat credit**, **No credit**.

Reference key: `export_rate`.

### Export credit adder

Default: **Unset**.

Added to the selected supply price only for Supply plus adder exports. Enter your own export agreement's value, including an explicit zero if appropriate. Unset means unknown.

Accepted range: **-100 to 100 ¢/kWh**; adjustable in increments of **0.001 ¢/kWh**.

Reference key: `export_adder_cents`.

### Flat export credit

Default: **Unset**.

Credit per exported kWh when Flat credit is selected. Independent of your buying rate. Enter your own value; unset means unknown.

Accepted range: **-100 to 100 ¢/kWh**; adjustable in increments of **0.001 ¢/kWh**.

Reference key: `flat_export_cents`.

### Export policy

Default: **Solar only**.

Solar only allows solar exports; Battery also allows stored energy exports; No exports requests neither. NRG sends this preference only when a matching control is configured. Otherwise set the same policy in your equipment. Permission alone does not force a sale.

Choices: **Solar only**, **Battery**, **No exports**.

Reference key: `export_policy`.

## Solar

Only relevant when solar is enabled. These settings adjust predictions, not measured production.

### Solar installation date

Default: **Unset**.

Used for panel age when a source has Apply age correction enabled. Leave unset until known; no age correction is invented. Measured solar is never reduced.

Reference key: `solar_install_date`.

### Solar annual degradation

Default: **0.7 %/year**.

Compounded yearly reduction in an unadjusted forecast: (1 − rate/100)^age. Sources already calibrated to present output should have age correction off.

Accepted range: **0 to 10 %/year**; adjustable in increments of **0.1 %/year**.

Reference key: `solar_degradation`.

### Solar forecast calibration

Default: **On**.

Compare the forecast saved before each daylight hour with what your solar meter later measured. After six well-measured daylight hours, NRG adjusts future forecasts by actual ÷ forecast, using up to 168 recent daylight hours. For example, consistently producing 8 kWh when 10 kWh was forecast gives about a 0.8 multiplier. The correction is limited to 0.5–1.5. It changes predictions, never measured production or panel settings.

Reference key: `solar_learning`.

## Battery

Only relevant when a home battery is enabled. Review the generic assumptions against your equipment.

### Battery capacity at installation

Default: **10 kWh**.

Generic starting assumption: replace with your equipment's full-charge capacity before backup reserve. The age estimate reduces this number; reserve and conversion losses are applied separately.

Accepted range: **1 to 250 kWh**; adjustable in increments of **0.1 kWh**.

Reference key: `battery_capacity`.

### Battery installation date

Default: **Unset**.

Baseline date for the capacity entered above. If capacity is a current measured value, use its measurement date. An unset date applies no age adjustment.

Reference key: `battery_install_date`.

### Battery annual degradation

Default: **2 %/year**.

Compounded yearly reduction of estimated full-charge capacity. Does not change measured SOC, power limits or efficiency, and is not a measured battery health result.

Accepted range: **0 to 15 %/year**; adjustable in increments of **0.1 %/year**.

Reference key: `battery_degradation`.

### Backup reserve

Default: **20 %**.

Minimum battery percentage kept out of discretionary use. NRG also sets the device's reserve if that control is mapped. Configured outage/protection sensors take priority.

Accepted range: **0 to 100 %**; adjustable in increments of **1 %**.

Reference key: `backup_reserve`.

### Battery round-trip efficiency

Default: **90 %**.

Fallback AC-to-storage-to-AC efficiency when calibration is off or lacks enough cycles. Equal square-root losses are applied when charging and discharging. Learning never overwrites this value.

Accepted range: **50 to 100 %**; adjustable in increments of **1 %**.

Reference key: `round_trip_efficiency`.

### Modeled battery charging power

Default: **5 kW**.

Fallback charging power when calibration is off or lacks enough sustained charging opportunities. This is a model assumption, not a device watt setting or a ceiling on learned estimates. Use a conservative value supported by your equipment.

Accepted range: **0.5 to 30 kW**; adjustable in increments of **0.5 kW**.

Reference key: `battery_charge_kw`.

### Modeled battery discharge power

Default: **5 kW**.

Fallback discharging power when calibration is off or lacks enough sustained discharge opportunities. This is a model assumption, not a device watt setting or a ceiling on learned estimates. Compare the effective estimate in Details with your equipment.

Accepted range: **0.5 to 30 kW**; adjustable in increments of **0.5 kW**.

Reference key: `battery_discharge_kw`.

### Calibrate battery estimates

Default: **Off**.

Opt in only with AC-side battery power and SOC measurements; DC battery-terminal meters are not supported. Passively calibrate round-trip efficiency after three covered cycles with at least a 30-point SOC excursion and return to the starting SOC. Charging and discharging power each need three sustained opportunities with spare supply or unmet demand, not ordinary low-load averages. Estimates use up to 12 recent observations per parameter within 30 days. Optional paired lifetime AC energy counters improve efficiency measurement; otherwise power is integrated. Manual values remain independent fallbacks. Learning sends no calibration commands and does not estimate capacity, degradation or battery health. Off stops battery learning and uses your manual values without deleting completed observations.

Reference key: `battery_learning`.

### Solar can recharge the battery while held

Default: **On**.

Enable if the selected hold mode still accepts solar charging, as Tesla Backup normally does. Turn off if your inverter's standby mode prevents solar charging too. This changes the battery forecast to match the device's behavior.

Reference key: `battery_solar_while_held`.

## EV

Only relevant when an EV is enabled. Review charging limits and times for your own vehicle and routine.

### Preserve battery during EV charging

Default: **On**.

When NRG controls both devices, ask the home battery to hold its energy while the car charges. Commands can take time to reach the equipment, so the battery may briefly supply the car before the hold takes effect. With a monitored-only battery, set that behavior in its own controller.

Reference key: `hold_battery_for_ev`.

### Daily EV departure

Default: **08:00:00**.

Generic starting time: enter your own local departure. A one-off departure takes precedence. Incomplete connected sessions remain overdue.

Reference key: `departure_time`.

### Normal charging window starts

Default: **20:00:00**.

Start of normal daily charging availability. Review this generic window. It ends at departure; charge-now and deadline urgency can use time outside it.

Reference key: `ev_start_time`.

### EV completion buffer

Default: **45 min**.

Aim to finish this many minutes before departure. Use the buffer if needed rather than miss the actual departure.

Accepted range: **0 to 180 min**; adjustable in increments of **5 min**.

Reference key: `completion_buffer`.

### Maximum EV charging current

Default: **16 A**.

Generic starting limit: enter a current supported by your charger and circuit. Also bounded by the control entity's maximum. Script adapters need the real supported limit here. NRG never raises the vehicle's selected charge limit.

Accepted range: **5 to 80 A**; adjustable in increments of **1 A**.

Reference key: `ev_max_amps`.

### Minimum stable EV current

Default: **6 A**.

Smallest current used for solar-aware charging. Below this the car is paused. Must be no greater than your maximum current.

Accepted range: **5 to 32 A**; adjustable in increments of **1 A**.

Reference key: `ev_min_amps`.

### Conservative EV power at maximum current

Default: **3.2 kW**.

Generic starting estimate: enter your measured AC charging power at the configured maximum current. Covered wall-charger observations can calibrate it.

Accepted range: **0.5 to 25 kW**; adjustable in increments of **0.1 kW**.

Reference key: `ev_kw_at_max`.

### EV AC energy per percentage point

Default: **0.6 kWh/%**.

Generic starting estimate: replace with AC energy per vehicle SOC percentage point, including losses. Covered charging sessions can calibrate it; this is not an EV degradation model.

Accepted range: **0.1 to 3 kWh/%**; adjustable in increments of **0.01 kWh/%**.

Reference key: `ev_kwh_per_percent`.

### Calibrate EV charging estimates

Default: **On**.

Use observed AC energy and the car's percentage gain to estimate how much electricity charging needs. Sessions need at least 5 percentage points, 5 minutes and good meter coverage. NRG uses a conservative estimate from the last 12 sessions, and measured power per amp to improve charging-time estimates. Example: 9 kWh for a 10-point gain suggests 0.9 kWh per point. This estimates charging needs, not EV battery degradation. Off uses your fallback values.

Reference key: `ev_learning`.

### Allow saved vehicle readings while plugged in

Default: **Off**.

Some MQTT/vehicle feeds publish SOC, target and settings only when they change, so their saved values become old while the car sleeps. Enable to accept those available saved values while the home charger reports connected. Connection/protection checks and command readbacks still apply. Otherwise vehicle data needs recent reports; an asleep feed may need its own wake/refresh automation. Estimates can be less current when saved readings are allowed.

Reference key: `ev_allow_saved_readings`.

## Planning

Set household-demand estimates, reference-appliance advice, and optional planning preferences.

### Learn household demand

Default: **On**.

Learn typical home use at each clock hour from up to 28 days of meter readings. If an EV is installed, subtract its separately measured charging so it is not counted twice. An hour needs at least 80% valid coverage. Recent observations count more; weekday/weekend patterns separate after enough samples. This predicts ordinary demand so the battery and price advice can plan around daily life. Missing hours use your fallback, not zero.

Reference key: `house_learning`.

### Fallback house demand without EV

Default: **1 kW**.

Used for clock hours without enough observations, or with learning disabled. Excludes the car to avoid counting it twice.

Accepted range: **0.1 to 30 kW**; adjustable in increments of **0.1 kW**.

Reference key: `house_kw`.

### Flexible appliance energy

Default: **1 kWh**.

Energy used for household run-now versus later advice. Advice never starts an appliance.

Accepted range: **0.1 to 30 kWh**; adjustable in increments of **0.1 kWh**.

Reference key: `flexible_load_kwh`.

### Flexible appliance duration

Default: **60 min**.

Contiguous running time for the reference appliance. Every suggested window must fit this whole duration.

Accepted range: **15 to 360 min**; adjustable in increments of **15 min**.

Reference key: `flexible_load_minutes`.

### Minimum worthwhile plan improvement

Default: **2 ¢**.

Prefer a stable existing feasible plan unless a replacement improves modeled horizon cost by at least this amount. Also used for generic household advice.

Accepted range: **0 to 500 ¢**; adjustable in increments of **1 ¢**.

Reference key: `minimum_saving_cents`.

### Optional battery cycling cost

Default: **0 ¢/kWh**.

Optional estimated wear cost per AC kWh discharged. Calendar degradation above does not establish a cycling cost; zero makes no invented wear charge.

Accepted range: **0 to 50 ¢/kWh**; adjustable in increments of **0.1 ¢/kWh**.

Reference key: `battery_wear_cents`.

## Notifications

Household advice and price-data fallback alerts are independently opt-in. Both use the notification services and quiet hours in Configure → Notifications; only advice uses the minimum-benefit threshold.

### Send household advice notifications

Default: **Off**.

Opt in to stable, worthwhile wait-until recommendations. Choose notify services in Configure → Notifications. Notifications do not command equipment.

Reference key: `notifications`.

### Minimum benefit for household advice

Default: **25 ¢**.

Applies only to household advice notifications, not price-data fallback messages. Notify when delaying the reference appliance is expected to save at least this amount and the advice stays stable for two minutes.

Accepted range: **0 to 1000 ¢**; adjustable in increments of **1 ¢**.

Reference key: `notification_saving_cents`.

### Send price-data fallback alerts

Default: **Off**.

Optional entry and recovery alerts for Use my fallback actions, independent of household advice notifications and their savings threshold. Both message types share the selected notification services and quiet hours. This switch does not enable fallback or equipment control. Observation alerts describe a proposal, not equipment execution.

Reference key: `fallback_notifications`.

### Notification quiet hours start

Default: **21:00:00**.

Local start of quiet hours. Advice remains available on the dashboard.

Reference key: `quiet_start`.

### Notification quiet hours end

Default: **08:00:00**.

Local end of quiet hours. Equal start/end disables the quiet-hours restriction.

Reference key: `quiet_end`.

## Meter conventions

Normalize the readings reported by your existing integrations.

### Grid meter reports export as positive

Default: **Off**.

Enable when your provider reports positive export and negative import. NRG reverses that reading so its normalized grid power always means positive buying and negative selling.

Reference key: `grid_power_inverted`.

### Battery meter reports charging as positive

Default: **Off**.

Enable when your provider reports positive charging and negative discharge. NRG reverses it so positive always means supplying the home in its own displays and model.

Reference key: `battery_power_inverted`.

### Home meter includes EV charging

Default: **On**.

Enable for a whole-home load meter that includes the car. Disable for a house-only circuit meter; NRG then adds separately measured EV power for the Home total while learning the house-only reading directly.

Reference key: `home_includes_ev`.

## Configuration beyond catalogue fields

The forms also store the structured choices below. Use Configure or the native entities; do not edit HA storage files. These choices persist across restarts, unlike Charge now.

| Configuration | Initial value and behavior | Guide |
|---|---|---|
| `supply_periods`, `delivery_periods` | Empty independent schedules; the optional template leaves rates blank. | [Period editor](pricing.md#editing-timed-periods-in-ha) |
| `mappings` | No entities selected on fresh setup; only relevant roles are shown, and hidden choices are retained. | [Measurements](integrations.md#provider-neutral-measurements) |
| `solar_sources` | No forecasts selected; use Add/Edit/Remove for entity, label, physical group, weight and age correction. | [Solar sources](integrations.md#solar-forecasts-and-alternatives) |
| `departure_override` | Unset; one-off local date/time takes precedence over daily departure. | [Everyday controls](operations.md#everyday-controls) |
| `notification_targets` | No notify services selected; shared by the two independent message types. | [Notifications](operations.md#notifications) |
| `control_values` | Device-state examples below, not detected compatibility. | [Control adapters](integrations.md#direct-controls-and-option-names) |
| `command_scripts` | No scripts selected; each selected command path still requires mapped feedback. | [Script adapters](integrations.md#script-adapters) |

## Measurement and control entity mappings

Configure → Mappings selects ordinary entities from your existing integrations. Mapping a control never enables equipment commands. Input helpers retain their saved settings; other readings follow the documented freshness checks.

| Reference key | HA role | Accepted entity domains | Description |
|---|---|---|---|
| `home_power` | Whole-home power | `sensor` | Total AC household demand including the EV, from any provider, W or kW. |
| `grid_power` | Signed grid power | `sensor` | Grid meter: positive import, negative export, W or kW. |
| `grid_connected` | Grid connected (optional) | `binary_sensor` | Optional protection input: on while connected. If selected, missing/off prevents equipment commands. |
| `live_supply` | Current supply price (optional) | `sensor` | External supply-price sensor in cents/kWh or USD/kWh. Also usable instead of the live ComEd API in ComEd mode. |
| `supply_forecast` | External supply forecast (optional) | `sensor` | Sensor with a list of price intervals in its configured forecast attribute. May be the same as the current-price sensor. |
| `live_delivery` | Current delivery price (optional) | `sensor` | External delivery-price sensor for External delivery entity mode. |
| `delivery_forecast` | External delivery forecast (optional) | `sensor` | Independent delivery-price interval list. Missing intervals remain unknown. |
| `solar_power` | Actual solar power | `sensor` | Solar production from any integration, W or kW. Prefer a local meter when available. |
| `battery_power` | Signed battery power | `sensor` | AC-side battery meter: positive discharge, negative charging, W or kW. DC battery-terminal power is not suitable for AC flows or battery calibration. |
| `battery_soc` | Battery charge | `sensor` | Home battery percentage, independent of manufacturer or integration. |
| `battery_charge_energy` | Battery lifetime AC charging energy (optional) | `sensor` | Increasing AC kWh received by the battery system, not stored DC energy or a resetting daily/session counter. Select both battery energy counters or neither; both must use the same AC boundary as battery power. |
| `battery_discharge_energy` | Battery lifetime AC discharged energy (optional) | `sensor` | Increasing AC kWh delivered by the battery system. Pair with lifetime AC charging energy; missing/resetting selected counters pause efficiency learning rather than switching measurement methods. |
| `battery_mode` | Battery mode control / feedback | `select`, `sensor`, `input_select` | Select/input_select controls work directly. Read-only feedback needs a script adapter. Configure the device's actual hold/serve/charge option names. |
| `battery_reserve` | Battery reserve control / feedback (optional) | `number`, `sensor`, `input_number` | Optional device backup-reserve setting. Read-only feedback can be paired with a script adapter. |
| `battery_grid_charge` | Grid-charge permission (optional) | `switch`, `binary_sensor`, `sensor`, `input_boolean` | Optional permission switch. A separate force-charge operating mode can be used instead; no grid-charge commands are invented for unsupported devices. |
| `battery_export` | Export policy control / feedback (optional) | `select`, `sensor`, `input_select` | Optional export-permission control. Configure option names under Control adapters. If omitted, set the policy in the device's own app. |
| `storm_watch` | Protection event active (optional) | `binary_sensor` | Optional active protection event, e.g. Storm Watch or a manufacturer override. On or missing blocks commands when selected. |
| `grid_services` | Grid services active (optional) | `binary_sensor` | Optional utility/grid-services event. On or missing blocks commands when selected. |
| `grid_services_enabled` | External controller priority (optional) | `binary_sensor` | Optional ownership/protection flag: while on, an external controller has priority. |
| `ev_connected` | EV plugged in | `binary_sensor` | Plug/connection sensor from any provider. If it identifies this home's charger, location need not also be mapped. |
| `ev_location` | EV at home (optional) | `device_tracker`, `binary_sensor`, `sensor` | Optional additional home check: home for a tracker/sensor or on for a binary sensor. Omit when the connection sensor already identifies the home charger. |
| `ev_soc` | Vehicle charge | `sensor` | Vehicle battery percentage, e.g. TeslaMate, Teslemetry, Tessie or another EV integration. |
| `ev_limit` | Selected vehicle charge limit | `number`, `sensor`, `input_number` | Selected target percentage. Read only: NRG never raises it. |
| `ev_power` | EV charging power | `sensor` | AC charging power from a charger or vehicle integration. Local meters are preferred, not required. |
| `ev_energy` | EV lifetime AC energy | `sensor` | Increasing AC kWh counter for charging, not a resetting session counter. Optional; EV calibration needs it. |
| `ev_measured_current` | EV measured current | `sensor` | Optional actual charging current in amperes. Otherwise the configured current-setting entity is used for power calibration. |
| `ev_current` | EV current setting / feedback | `number`, `sensor`, `input_number` | Current setting in A. Number/input_number controls work directly. A read-only sensor needs an EV current script under Control adapters. |
| `ev_charge` | EV charging control / feedback | `switch`, `binary_sensor`, `sensor`, `input_boolean` | Switches work directly. Read-only state feedback needs start/stop scripts. Set its charging/paused state values under Control adapters if they are not on/off. |

## Control-state names and command scripts

Configure → Control adapters matches these example values to the actual device. They are not manufacturer detection or permission to issue commands. Match hold/serve/charge behavior before transferring control; never map serve-home to forced export.

| Control value key | Default device-state example |
|---|---|
| `battery_hold` | `backup` |
| `battery_serve` | `self_consumption` |
| `battery_charge` | `backup` |
| `export_solar` | `pv_only` |
| `export_battery` | `battery_ok` |
| `export_none` | `never` |
| `ev_on` | `on` |
| `ev_off` | `off` |
| `grid_charge_on` | `on` |
| `grid_charge_off` | `off` |

Script selections start empty and use available `script.*` entities. The form field is `script_` plus the role; it is stored under `command_scripts`. See [script variables and feedback limits](integrations.md#script-adapters), including reserve/export restrictions during fallback and estimated pricing.

| Script role key | Selection field |
|---|---|
| `ev_current` | `script_ev_current` |
| `ev_start` | `script_ev_start` |
| `ev_stop` | `script_ev_stop` |
| `battery_mode` | `script_battery_mode` |
| `battery_export` | `script_battery_export` |
| `battery_reserve` | `script_battery_reserve` |
| `grid_charge_on` | `script_grid_charge_on` |
| `grid_charge_off` | `script_grid_charge_off` |
