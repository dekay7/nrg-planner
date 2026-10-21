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

## Tariff

Set your supply, delivery, and export pricing. For timed rates, use [Pricing periods](pricing.md#editing-timed-periods-in-ha).

### Supply plan

Default: **Flat supply**.

Choose your provider's supply pricing: a flat rate, your own timed periods, an external HA price sensor/forecast, or the optional ComEd hourly feed. Delivery is configured separately and added once.

Choices: **Flat supply**, **Time-of-use supply**, **External supply entity**, **Hourly ComEd**.

Reference key: `supply_plan`.

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

Advice messages are opt-in. Select existing notify services in Configure → Notifications.

### Send household advice notifications

Default: **Off**.

Opt in to stable, worthwhile wait-until recommendations. Choose notify services in Configure → Notifications. Notifications do not command equipment.

Reference key: `notifications`.

### Minimum notification benefit

Default: **25 ¢**.

Notify only when delaying the reference appliance is expected to save at least this amount and the recommendation stays stable for two minutes.

Accepted range: **0 to 1000 ¢**; adjustable in increments of **1 ¢**.

Reference key: `notification_saving_cents`.

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
