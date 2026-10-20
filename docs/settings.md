# Settings reference

Generated from the same catalogue as the UI. All settings persist across HA restarts; the charge-now override is intentionally session-only.

Open **NRG Planner settings**, or **Settings → Devices & services → NRG Planner → Configure**.

## This home has an EV
`has_ev` · components · Default: **False**

Enable vehicle monitoring and its dashboard cards. Leave off if you have no EV; EV readings, controls and calibration will not be required.

## This home has a stationary battery
`has_battery` · components · Default: **False**

Enable battery monitoring and capacity estimates. Leave off if you have no home battery; battery sensors, reserve and operating controls will not be required.

## This home has solar
`has_solar` · components · Default: **False**

Enable solar production, forecasts and their dashboard cards. Leave off for a home without panels; the planner then knows solar production is zero.

## Let NRG control EV charging
`ev_control` · components · Default: **False**

Optional. Enable after mapping your charging switch/current controls or HA command scripts. With this off, NRG monitors the car and leaves its charging to your existing system.

## Let NRG control the home battery
`battery_control` · components · Default: **False**

Optional. Enable after mapping the battery's operating controls or command scripts. With this off, the battery remains monitored and NRG does not assume it can schedule its energy.

## Operating mode
`mode` · operation · Default: **Observation**

Observation calculates without equipment commands. Control authorizes only the components you enabled for NRG control. Switching to Observation does not restore settings already saved in your equipment.

## Supply plan
`supply_plan` · tariff · Default: **Flat supply**

Choose your provider's supply pricing: a flat rate, your own timed periods, an external HA price sensor/forecast, or the optional ComEd hourly feed. Delivery is configured separately and added once.

## Flat supply rate
`flat_supply_cents` · tariff · Default: **unset** ¢/kWh

Your contracted supply price, excluding delivery. Unset means unknown, not free. Enter an explicit zero only if your contract really has a zero supply rate.

## Supply forecast attribute
`external_supply_attribute` · tariff · Default: **forecast**

For an external provider, name the attribute containing forecast intervals. Each interval needs start, end and price (or the documented aliases). Units are read from the row or price entity. An external current price alone does not invent future prices.

## Delivery plan
`delivery_plan` · tariff · Default: **Flat delivery**

Delivery can have its own flat rate, timed periods or external sensor. Its schedule need not match the supply schedule. Edit periods under Configure → Pricing periods.

## Flat delivery rate
`delivery_cents` · tariff · Default: **unset** ¢/kWh

Your variable delivery/rider cost in cents per imported kWh. Include applicable variable riders, not fixed monthly fees. Unset means unknown; explicitly enter zero if no separate delivery charge applies.

## Delivery forecast attribute
`external_delivery_attribute` · tariff · Default: **forecast**

Attribute containing external delivery-price intervals. Supply and delivery forecasts are independent. See the handbook's supported interval fields and units.

## Export credit basis
`export_rate` · tariff · Default: **No credit**

Configure how exported energy is credited; do not assume exports receive the import delivery rate. Credits may have billing restrictions not modeled here.

## Export credit adder
`export_adder_cents` · tariff · Default: **unset** ¢/kWh

Added to the selected supply price only for Supply plus adder exports. Enter your own export agreement's value, including an explicit zero if appropriate. Unset means unknown.

## Flat export credit
`flat_export_cents` · tariff · Default: **unset** ¢/kWh

Credit per exported kWh when Flat credit is selected. Independent of your buying rate. Enter your own value; unset means unknown.

## Export policy
`export_policy` · tariff · Default: **Solar only**

Solar only allows solar exports; Battery also allows stored energy exports; No exports requests neither. NRG sends this preference only when a matching control is configured. Otherwise set the same policy in your equipment. Permission alone does not force a sale.

## Solar installation date
`solar_install_date` · solar · Default: **unset**

Used for panel age when a source has Apply age correction enabled. Leave unset until known; no age correction is invented. Measured solar is never reduced.

## Solar annual degradation
`solar_degradation` · solar · Default: **0.7** %/year

Compounded yearly reduction in an unadjusted forecast: (1 − rate/100)^age. Sources already calibrated to present output should have age correction off.

## Solar forecast calibration
`solar_learning` · solar · Default: **True**

Compare the forecast saved before each daylight hour with what your solar meter later measured. After six well-measured daylight hours, NRG adjusts future forecasts by actual ÷ forecast, using up to 168 recent daylight hours. For example, consistently producing 8 kWh when 10 kWh was forecast gives about a 0.8 multiplier. The correction is limited to 0.5–1.5. It changes predictions, never measured production or panel settings.

## Battery capacity at installation
`battery_capacity` · battery · Default: **10** kWh

Generic starting assumption: replace with your equipment's full-charge capacity before backup reserve. The age estimate reduces this number; reserve and conversion losses are applied separately.

## Battery installation date
`battery_install_date` · battery · Default: **unset**

Baseline date for the capacity entered above. If capacity is a current measured value, use its measurement date. An unset date applies no age adjustment.

## Battery annual degradation
`battery_degradation` · battery · Default: **2** %/year

Compounded yearly reduction of estimated full-charge capacity. Does not change measured SOC, power limits or efficiency, and is not a measured battery health result.

## Backup reserve
`backup_reserve` · battery · Default: **20** %

Minimum battery percentage kept out of discretionary use. NRG also sets the device's reserve if that control is mapped. Configured outage/protection sensors take priority.

## Battery round-trip efficiency
`round_trip_efficiency` · battery · Default: **90** %

Estimated AC-to-storage-to-AC efficiency. Equal square-root losses are applied when charging and discharging.

## Modeled battery charging power
`battery_charge_kw` · battery · Default: **5** kW

Charging power used to estimate future battery energy. This setting does not directly set device watts. Use a conservative value supported by your equipment.

## Modeled battery discharge power
`battery_discharge_kw` · battery · Default: **5** kW

Discharging power used in the energy forecast. Your equipment may deliver a different rate; compare the forecast with its meter readings.

## Solar can recharge the battery while held
`battery_solar_while_held` · battery · Default: **True**

Enable if the selected hold mode still accepts solar charging, as Tesla Backup normally does. Turn off if your inverter's standby mode prevents solar charging too. This changes the battery forecast to match the device's behavior.

## Preserve battery during EV charging
`hold_battery_for_ev` · ev · Default: **True**

When NRG controls both devices, ask the home battery to hold its energy while the car charges. Commands can take time to reach the equipment, so the battery may briefly supply the car before the hold takes effect. With a monitored-only battery, set that behavior in its own controller.

## Daily EV departure
`departure_time` · ev · Default: **08:00:00**

Generic starting time: enter your own local departure. A one-off departure takes precedence. Incomplete connected sessions remain overdue.

## Normal charging window starts
`ev_start_time` · ev · Default: **20:00:00**

Start of normal daily charging availability. Review this generic window. It ends at departure; charge-now and deadline urgency can use time outside it.

## EV completion buffer
`completion_buffer` · ev · Default: **45** min

Aim to finish this many minutes before departure. Use the buffer if needed rather than miss the actual departure.

## Maximum EV charging current
`ev_max_amps` · ev · Default: **16** A

Generic starting limit: enter a current supported by your charger and circuit. Also bounded by the control entity's maximum. Script adapters need the real supported limit here. NRG never raises the vehicle's selected charge limit.

## Minimum stable EV current
`ev_min_amps` · ev · Default: **6** A

Smallest current used for solar-aware charging. Below this the car is paused. Must be no greater than your maximum current.

## Conservative EV power at maximum current
`ev_kw_at_max` · ev · Default: **3.2** kW

Generic starting estimate: enter your measured AC charging power at the configured maximum current. Covered wall-charger observations can calibrate it.

## EV AC energy per percentage point
`ev_kwh_per_percent` · ev · Default: **0.6** kWh/%

Generic starting estimate: replace with AC energy per vehicle SOC percentage point, including losses. Covered charging sessions can calibrate it; this is not an EV degradation model.

## Calibrate EV charging estimates
`ev_learning` · ev · Default: **True**

Use observed AC energy and the car's percentage gain to estimate how much electricity charging needs. Sessions need at least 5 percentage points, 5 minutes and good meter coverage. NRG uses a conservative estimate from the last 12 sessions, and measured power per amp to improve charging-time estimates. Example: 9 kWh for a 10-point gain suggests 0.9 kWh per point. This estimates charging needs, not EV battery degradation. Off uses your fallback values.

## Allow saved vehicle readings while plugged in
`ev_allow_saved_readings` · ev · Default: **False**

Some MQTT/vehicle feeds publish SOC, target and settings only when they change, so their saved values become old while the car sleeps. Enable to accept those available saved values while the home charger reports connected. Connection/protection checks and command readbacks still apply. Otherwise vehicle data needs recent reports; an asleep feed may need its own wake/refresh automation. Estimates can be less current when saved readings are allowed.

## Learn household demand
`house_learning` · planning · Default: **True**

Learn typical home use at each clock hour from up to 28 days of meter readings. If an EV is installed, subtract its separately measured charging so it is not counted twice. An hour needs at least 80% valid coverage. Recent observations count more; weekday/weekend patterns separate after enough samples. This predicts ordinary demand so the battery and price advice can plan around daily life. Missing hours use your fallback, not zero.

## Fallback house demand without EV
`house_kw` · planning · Default: **1** kW

Used for clock hours without enough observations, or with learning disabled. Excludes the car to avoid counting it twice.

## Flexible appliance energy
`flexible_load_kwh` · planning · Default: **1** kWh

Energy used for household run-now versus later advice. Advice never starts an appliance.

## Flexible appliance duration
`flexible_load_minutes` · planning · Default: **60** min

Contiguous running time for the reference appliance. Every suggested window must fit this whole duration.

## Minimum worthwhile plan improvement
`minimum_saving_cents` · planning · Default: **2** ¢

Prefer a stable existing feasible plan unless a replacement improves modeled horizon cost by at least this amount. Also used for generic household advice.

## Optional battery cycling cost
`battery_wear_cents` · planning · Default: **0** ¢/kWh

Optional estimated wear cost per AC kWh discharged. Calendar degradation above does not establish a cycling cost; zero makes no invented wear charge.

## Summer peak-import precaution
`summer_guard` · planning · Default: **False**

Optional regional precaution: avoid discretionary grid battery charging and, if feasible, EV charging on June–September weekdays noon–7 p.m. Off until explicitly enabled. It is not a predicted dollar saving; departure and charge-now win.

## Send household advice notifications
`notifications` · notifications · Default: **False**

Opt in to stable, worthwhile wait-until recommendations. Choose notify services in Configure → Notifications. Notifications do not command equipment.

## Minimum notification benefit
`notification_saving_cents` · notifications · Default: **25** ¢

Notify only when delaying the reference appliance is expected to save at least this amount and the recommendation stays stable for two minutes.

## Notification quiet hours start
`quiet_start` · notifications · Default: **21:00:00**

Local start of quiet hours. Advice remains available on the dashboard.

## Notification quiet hours end
`quiet_end` · notifications · Default: **08:00:00**

Local end of quiet hours. Equal start/end disables the quiet-hours restriction.

## Grid meter reports export as positive
`grid_power_inverted` · measurements · Default: **False**

Enable when your provider reports positive export and negative import. NRG reverses that reading so its normalized grid power always means positive buying and negative selling.

## Battery meter reports charging as positive
`battery_power_inverted` · measurements · Default: **False**

Enable when your provider reports positive charging and negative discharge. NRG reverses it so positive always means supplying the home in its own displays and model.

## Home meter includes EV charging
`home_includes_ev` · measurements · Default: **True**

Enable for a whole-home load meter that includes the car. Disable for a house-only circuit meter; NRG then adds separately measured EV power for the Home total while learning the house-only reading directly.
