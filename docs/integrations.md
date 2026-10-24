# Integrations, sources and control adapters

## Provider-neutral measurements

Open **Settings → Devices & services → NRG Planner → Configure → Mappings**.
Only relevant optional component roles are shown. Select ordinary HA entities from
the integrations you already use. No credentials are copied into NRG.

**Meter conventions** in Configure (also on the Sources dashboard) can reverse a
provider's grid/battery power sign and identify a house-only meter that excludes
EV charging. These switches avoid requiring a custom template just to normalize
different manufacturers' conventions.

| Role | Meaning |
|---|---|
| Solar power | Actual AC solar production, W or kW. |
| Whole-home power | Total home load including an EV, if present. |
| Signed grid power | Positive import, negative export. |
| Signed battery power | AC-side power: positive discharge, negative charging. DC battery-terminal or combined hybrid-inverter power is not interchangeable. |
| Battery lifetime AC charging/discharged energy | Optional paired increasing kWh counters at the same AC boundary as battery power. Never daily/session-resetting counters or stored DC energy. |
| Battery / EV percentage | Charge percentage for the selected equipment. |
| EV connected | Connection at the home charger. An additional location check is optional. |
| EV target | Selected percentage, readable from a number, input_number or sensor. NRG never raises it. |
| EV current setting | Number/input_number control or a read-only A sensor paired with a script. |
| EV charging state/control | Switch/input_boolean, or read-only feedback paired with scripts. |
| EV power/current/lifetime energy | Optional AC observations for flows, household subtraction and calibration. |

Prefer local meters when available. For a complete set of applicable site meters,
NRG can calculate a missing home/grid flow from the power balance; its basis is
identified in component diagnostics. Absent solar/battery/EV is known zero. A missing
reading for enabled equipment stays unknown.

[Battery calibration](learning.md#calibrate-battery-estimates) is opt-in. Confirm
AC-side measurement semantics using your equipment documentation before enabling it.
Paired lifetime energy counters are preferred; with neither selected, covered
battery power is integrated. Independent home/grid/solar meters are needed for
power-opportunity detection, but efficiency learning does not require battery controls.

Local powers have three-minute report checks; current price entities have fifteen
minutes. Vehicle SOC/target/location checks allow one hour, and current feedback
five minutes. Static HA input helpers keep their saved setting until changed.
These checks concern integration reports, not proof that a remote vehicle sampled
fresh information. For a feed that publishes only on change, **Allow saved vehicle
readings while plugged in** accepts available retained SOC/target/settings while
the home connection is reported. It is off initially. Without it, a sleeping feed
may need a wake/refresh automation before control becomes ready. Connection and
configured protection inputs still need valid reports; command readbacks remain
required. Saved data can make estimates less current.

## Tessie, Teslemetry, TeslaMate and other providers

- **Tessie:** existing number/select/switch entities can be selected directly.
- **Teslemetry:** compatible entities work the same way; no Tessie dependency or
  integration-domain check exists.
- **TeslaMate:** HA/MQTT telemetry can monitor the car. TeslaMate telemetry alone
  is not a charging command interface; pair it with another command integration or
  your own HA scripts if NRG should control charging.
- **Other chargers/inverters/batteries:** ordinary HA entities or scripts can provide
  the same capabilities. Use monitoring only where the required operations are absent.

No EV requires a home battery. No battery requires solar or an EV. Only the devices
enabled for NRG control receive equipment requests.

## Direct controls and option names

Use **Configure → Control adapters** to match actual option/state names:

- Battery hold: preserve stored energy.
- Battery serve: supply household demand without forcing a grid sale.
- Battery charge: charge from the grid when permitted.
- Optional export permission, reserve and grid-charge switch.
- Nonstandard EV charging/paused feedback states, when they are not `on`/`off`.

Tesla-compatible default names are examples, not a provider requirement. Another
inverter might use `Standby`, `Self use` and `Grid charge`.

If the charge mode is the same as hold, NRG needs a separate grid-charge switch to
enable charging. A distinct force-charge mode can be used without that switch.
Without either, the planner does not schedule unsupported grid charging. Export and
reserve controls are optional. Set export behavior in the device's app if NRG has
no corresponding control; reserve is still respected in modeled use and hold requests.

Commands take time to reach equipment. For example, a battery may briefly supply
the car before a requested hold takes effect. NRG checks readbacks and measured
response; the device's own electrical protections remain responsible for its limits.

## Script adapters

Optionally select scripts for EV current/start/stop, battery mode/export/reserve,
or grid-charge permission. Keep the matching feedback entity mapped too. Scripts
are called with these variables:

| Variable | Value |
|---|---|
| `value` | Requested number, device mode name or configured feedback state. |
| `action` | Logical request, e.g. `hold`, `serve`, `charge`, `on`, `off`, or current. |
| `target_soc` | Proposed battery target, when applicable. |
| `reserve_soc` | Configured backup reserve during normal operation; during fallback or bounded estimated pricing, retains a higher reported native reserve, or is unknown if that feedback is invalid. |
| `export_policy` | Solar only, Battery or No exports during normal operation; capped to Solar only or No exports during fallback or bounded estimated pricing. |

An EV-current script can use `{{ value }}` as amps in its integration/MQTT action.
The selected current-setting feedback must then report that setting. Actual measured
current is a separate role: a stopped car drawing zero cannot confirm a 16 A setting.

Scripts should complete promptly and recheck NRG ownership before delayed device
operations. NRG validates before/after each script and waits up to fifteen seconds
for matching feedback, but it cannot rewrite a user script's internal sequence.
Scripts must honor the passed reserve/export limits and must not turn a logical
hold or serve-home request into forced export or speculative charging. Missing
feedback cannot be bypassed by a script. The complete role keys and default
control-state examples are in [the settings reference](settings.md#control-state-names-and-command-scripts).

## Optional protection inputs

A selected grid-connected sensor must report on. Selected protection/grid-services/
external-controller flags must report off. Missing selected guards pause applicable
commands. Battery-specific guards are not required for a home without a battery.
Remove a guard mapping if its device has been removed; an explicitly selected guard
is not silently ignored because it stops reporting.

## Solar forecasts and alternatives

For solar homes, open **Configure → Sources → Add forecast**. Select an enabled
Forecast.Solar entity, descriptive name, physical coverage group, alternative weight
and age-correction choice. NRG reads the entry's full time series once; today's,
tomorrow's and current-power sensors from one entry are not independent forecasts.

| Sources | Physical coverage groups | Combination |
|---|---|---|
| South + west roof | `south`, `west` | Add them. |
| Alternative predictions for south | `south`, `south` | Weighted average. |
| Alternative whole-system forecasts | `south,west`, `south,west` | Weighted average of totals. |
| Whole system + south alone | `south,west`, `south` | Rejected because coverage overlaps. |

See [learning](learning.md#solar-alternative-weight) for the worked weight example.
No calibration identifies individual-roof error from one combined meter.

Cached solar expires after three hours; failures retain the original age. A valid
alternative can cover a failed estimate for the same panels, but a missing entire
array is not a confident whole-system zero. Astronomically dark intervals are known
zero even when the provider drops the completed day after sunset. Missing daylight
stays unknown. Coverage and alternative selection are checked for each hour, not
just the presence of a daily total. A covered zero-output hour is valid. At dawn
and dusk, NRG can combine a partial provider hour with HA's astronomical darkness
**only when every daylight second is covered**. The partial hour keeps its actual
forecast energy; it is not scaled up to a full hour. Overlapping provider/night
coverage is counted once, including in fractional-hour timezones and DST days.
Missing daylight, unavailable sun events or a stale/missing array still stays
unknown. Long daytime power-shape gaps and malformed responses are rejected
instead of redistributing their energy into other hours. Genuine gaps can shorten
the dependable comparison horizon; EV deadline feasibility remains available. A failed
refresh keeps the previous valid cache only until its original three-hour expiry.
Startup/source updates trigger a cache read; failed sources retry after five
minutes, normal refresh after thirty.

Turn age correction off for a source already configured to current aged output.
Actual measured production is never reduced. Disable solar entirely for a home
without panels; no Forecast.Solar setup is then required.

## Check measurement conventions

Review your charger's documented electrical-service/phase configuration if reported
charging power disagrees with other meters. NRG does not change that configuration.
Use independently measured power and equipment documentation when resolving a
measurement mismatch; do not assume one manufacturer's defaults apply to your home.
