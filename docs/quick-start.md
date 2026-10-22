# Quick start

**Goal:** get useful advice before deciding whether to automate any equipment.
You will need your electricity plan and the existing Home Assistant entities for
any equipment you select. A Home Assistant **entity** is a single reading or
control, such as a power sensor or charging switch.

In these steps, **Configure → …** means **Settings → Devices & services → NRG
Planner → Configure**, then the named section. Work through setup with an
administrator account. You can return to these forms at any time.

## 1. Install and select equipment

Follow [installation](installation.md), then add **NRG Planner** in **Settings →
Devices & services**. Choose only the EV, stationary battery, and solar equipment
you have. All three can be off. Monitoring and equipment control are separate.

Fresh installations start in **Observation**. Merely mapping a control entity does
not grant command permission.

## 2. Enter your own electricity plan

Supply and delivery are independent. Either supports flat rates, time-of-use
periods, or external HA entities/forecasts. ComEd hourly is an optional supply
adapter. Rates use cents/kWh; external feeds also accept USD/kWh.

Rate fields start blank. **Unset is unknown, not zero.** If delivery is already
included in your supply feed, explicitly enter zero for the separate delivery
component rather than double-counting it.

For timed pricing, use **Configure → Pricing periods**. The optional four-period
template has blank rates. Missing times and missing rates remain unknown.

Configure export compensation separately: No credit, Flat credit, or Supply plus
adder. Both numeric export fields start unset. They are never inferred from
delivery. See [pricing](pricing.md).

If you use Hourly ComEd, leave **During ComEd live-price delays → Strict live
pricing** selected initially, or explicitly review **Allow brief published
estimates**. The latter temporarily uses a published exact-hour forecast with
Degraded status and blocks battery grid charging; it is not permission to use
old live readings indefinitely. See [brief-delay limits](pricing.md#brief-comed-live-data-delays).

## 3. Map available HA measurements

In **Configure → Mappings**, choose ordinary entities from existing integrations:

- Grid and/or whole-home power for measured flows and cost estimates.
- Solar power and Forecast.Solar sources if solar is enabled.
- Battery power and SOC if a stationary battery is enabled.
- EV connection, SOC, selected target, and optional power/energy/current readings.

Disabled components contribute known zero. Missing enabled equipment stays
unknown. Review meter signs and whether the home meter includes EV charging in
**Configure → Meter conventions**.

## 4. Review generic equipment assumptions

The capacity, power, efficiency, current, charging window, and departure fields are
generic starting assumptions, not discovered specifications. Replace them with
appropriate values for your equipment before relying on a schedule.

Installation dates start unset. Leave them unset until known. Learning uses only
this HA installation's covered measurements; no household profile is bundled.
Household, EV and solar learning have independent switches. **Calibrate battery
estimates** is a separate opt-in, initially off: confirm AC-side power/SOC semantics
before enabling it. The [learning guide](learning.md) explains qualification,
manual fallbacks, retention and reset behavior; it never measures battery health.

## 5. Configure optional controls

Compatible switches, numbers, and selects work directly. **Configure → Control
adapters** maps battery modes, export settings, and optional command scripts to
your device's actual behavior. Default option names are examples, not proof of
compatibility. See [adapters](integrations.md).

Map available protection and external-controller-priority flags. A selected guard
must report the expected clear state; missing selected guards pause commands.

## 6. Choose outage behavior and optional notifications

Under **Configure → Price-data fallback**, the default **Standard protection**
keeps guarded planner rules, including EV departure charging at potentially unknown
prices. **Use my fallback actions** instead opens a review of the controlled
devices' EV pause/departure and battery hold/self-consumption actions. Saving can
apply those actions immediately when prices are unusable and Control is authorized.
Keep Observation while reviewing. A manual fallback request is a separate action.
See [fallback operation](operations.md#price-data-fallback).

Under **Configure → Notifications**, household advice and price-data fallback
alerts are independent opt-ins sharing your selected notify services and quiet
hours. Only household advice uses the benefit threshold and advice-stability test.
Notifications do not enable controls. See [notification behavior](operations.md#notifications).

## 7. Review the plan

Use the native entities or install the [optional dashboards](installation.md#optional-dashboards).
Compare the inputs, forecast coverage, and proposed actions with actual readings.
Use the [operations guide](operations.md) when transferring device control.
A battery-backed suggested appliance window need not be the cheapest grid hour.
Check dependable comparison coverage and any **Limited battery estimate** notice;
future missing rates do not establish a saving. Cost coverage may include separately
tracked forecast-priced intervals. See [the dashboard guide](homeowner-guide.md).

## What a working setup looks like

- The combined buying price matches your supply plus delivery. Blank prices call
  for a coverage check, not an assumption that electricity is free.
- The plan has a current explanation; a grid-only home can use price advice with
  no EV, battery, solar, or site power meter.
- Installed equipment readings make sense next to your meters or device apps.
  Daily cost appears only when sufficient site readings and prices are covered.
- In Observation, a proposed charging/battery action is advice rather than a
  device command. You can stay in this mode for ongoing monitoring.

You are ready for everyday use. Read the [homeowner guide](homeowner-guide.md) for
the graphs, [common questions](faq.md) for typical decisions, or
[troubleshooting](troubleshooting.md) if an expected reading is missing.
