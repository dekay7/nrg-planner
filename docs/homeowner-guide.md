# Reading NRG Planner

## Electricity price now

The large **¢/kWh** number includes the selected **supply plus delivery** prices.
They may each be flat, follow independent timed periods, or come from external
feeds. Supply and delivery are also shown separately so the total is explainable.

Hourly current values can change before settlement. Contracted time-of-use rates
change at the configured boundaries. Solid forecast lines represent published
outlooks; dashed lines are estimates. A gap means price information is missing,
not that energy is free.

## Pricing health and missing-price protection

- **Healthy:** current import pricing is usable.
- **Degraded:** a fetch failed, current pricing is limited, or the administrator
  enabled temporary published-estimate operation during a ComEd delay. A usable
  cached price or permitted estimate may still be used; this status alone does
  not mean custom fallback began.
- **Fallback:** the administrator's selected missing-price actions apply. In
  **Observation**, the banner explicitly describes a proposal and no equipment
  commands are sent.
- **Recovering:** fresh prices returned, but fallback stays active while recovery
  is confirmed and a new plan is prepared.

These are pricing-data states, not reports of a power outage or unusually high
prices. The administrator configures actions and checks device results on
**NRG Planner settings → Price-data fallback**. An active policy does not prove every
command succeeded. A manual request persists until ended; fresh prices alone do
not end that request. See [fallback operation](operations.md#price-data-fallback).

For ComEd, Strict live pricing permits a short published-forecast bridge during
the first ten minutes of a new hour. The separate opt-in **Allow brief published
estimates** mode can continue for at most 60 minutes from the last verified live
observation, not from the time an error is noticed. Its Degraded explanation shows
last live age, forecast age and remaining allowance. EV planning can continue;
battery grid charging is blocked and reserve/protection checks remain. Repeated
old readings or restarting do not renew it. An already active automatic fallback
still needs confirmed fresh live recovery. See [pricing resilience](pricing.md#brief-comed-live-data-delays).

A published estimate remains on the solid **Published outlook** graph line. It is
not the dashed **Tentative estimate** learned from historical local observations.
Check Pricing health and the source attributes rather than assuming every visible
current price is live.

## The recommendation

- **Good time to use energy:** now is among the better modeled opportunities.
- **Use energy as usual:** shifting the reference task is not worth the difference.
- **Wait until …:** a sufficiently cheaper complete window is available.
- **Waiting for dependable coverage:** the information cannot support a full comparison.
- **Price-data fallback active:** economic advice is paused; review the selected
  device baseline rather than assuming a price-based schedule.

The green segment marks a recommended window for the administrator's reference
appliance, initially **1 kWh over one hour**. The benefit concerns that task, not
the entire house. Use energy whenever it is needed; this advice does not start or
stop household appliances. Tap/hover a graph point to inspect it and use zoom/reset
without changing equipment.

Solar can have an export-credit opportunity cost, and stored energy has losses and
future value. NRG considers applicable equipment rather than assuming all solar or
battery electricity is free. Homes without that equipment need no such assumptions.

**Battery-backed use** can be suggested even when grid electricity is expensive:
the model expects stored energy to supply the task. The green graph segment is
therefore not necessarily the cheapest grid-price window. **Why this advice?** shows
the reference task, modeled appliance cost, the window's average grid price and the
end of dependable comparison coverage. Costs include battery losses and remaining
energy value; missing later prices do not make replacement energy free. If coverage
cannot support the full task, NRG waits for dependable information instead of
claiming a saving.

**Limited battery estimate** means permitted refill potential cannot cover the
modeled usable battery capacity. NRG checks charging capability, car demand and
whether the native hold mode accepts solar before counting a refill opportunity.
Uncovered stored energy uses a conservative known-price reference rather than an
assumed cheap purchase. The displayed comparison remains an estimate, and savings
notifications are withheld. No new equipment permission or control is enabled.

## Current power flow: the Sankey diagram

The Home Energy tab shows Home Assistant's built-in **power Sankey card**, the
same live power-flow diagram as the **Now** tab of the Energy dashboard. It is
unaffected by the dashboard's date selection and shows instantaneous power: the
width of each band follows current flow from sources (grid, solar panels and
battery) to consumers in the home.

The card reads the power entities configured in **Settings → Dashboards →
Energy**, not planner estimates. Devices are grouped into floors and areas only
when those are configured there. A meter that is not configured in the Energy
dashboard is simply absent from the diagram; NRG never substitutes an invented
or estimated flow for missing equipment.

## Only the equipment this home has

EV cards, battery gauges and solar information appear only when enabled under
Components. Monitoring does not mean NRG is controlling a device. Observed charging
status uses local/provider power and connection readings; a proposed plan is shown
separately.

With NRG EV control enabled, planned start/readiness aim for the selected limit by
departure. The vehicle target is never raised by NRG. A shortfall means the model
cannot meet that target under current assumptions. The administrator can use
charge-now or a one-off departure override. An explicitly selected missing-price
EV pause can leave the car below its target at departure; Charge now can override
that pause, but not equipment protection checks.

Battery percentage is measured. Available kWh uses the configured age-adjusted
capacity and reserve, rather than claiming a measured battery-health test.

While Observation is selected, schedules are proposals. Devices may currently be
following another controller. Monitoring-only equipment continues to use its own
controls; NRG does not promise it will follow the modeled schedule.

## Modeled energy plan: the battery line

The **Battery %** line is the proposed NRG battery trajectory, not the measured
percentage gauge. It works in **Observation** when battery planning/control is
enabled and the battery inputs, compatible controls and selected protection guards
are ready. Observation blocks commands, not this forecast.

With monitoring-only equipment, unavailable battery data, or a missing/active
selected guard, NRG omits the trajectory instead of inventing a flat percentage.
The explanation below the chart names the blocker. **Operation → Protection
guards** also exposes the affected entity and its expected state in More info.
See [battery-line troubleshooting](troubleshooting.md#the-modeled-battery-line-is-missing).

## Net energy cost today

Purchases minus export credits are estimated from covered meter readings and the
contemporaneous supply-plus-delivery rates. A negative total means modeled credits
exceed purchases over the covered time; it does not establish a cash payout.

Coverage matters. First days, restarts and missing readings are partial, not free.
Fixed fees, capacity charges and unconfigured taxes are excluded. A home with no
site power meter gets price advice but no claimed metered daily cost.

Totals can include published-price estimates during an allowed ComEd bridge or
brief delay. **NRG Planner settings → Details → Today's forecast-priced coverage**
shows the newly tracked estimated hours; cost/coverage entity attributes separate
`estimated_import_cost`, `estimated_export_credit` and `estimated_coverage_hours`.
These are subsets of the totals, not additional charges. Old ledger history is
not retroactively classified. See [accounting](accounting.md#observed-ledger).

### Forecast net cost by midnight

Directly below **Net energy cost today**, **Forecast net cost by midnight**
(`sensor.nrg_net_cost_eod`) adds the covered net cost so far to the remaining
modeled purchases minus export credits, stopping at midnight in your Home
Assistant timezone. It includes supply and delivery, but not fixed fees,
unconfigured taxes, battery wear or a value assigned to leftover stored energy.
Negative forecasts are possible; they do not establish a cash payout.

This is a read-only estimate requiring no new permissions or settings. In
**Observation**, it assumes the proposed schedule is followed; NRG still sends no
commands. Household demand, solar, EV activity and device behavior can change the
outcome. Monitoring-only EVs include only an already observed charge toward a
known target, not a prediction of future plug-ins or another controller's schedule.

**Partial day** means earlier missing readings are not included in either total.
The forecast does not reconstruct setup/restart gaps or claim a complete daily
bill; check **Today's cost coverage**. More info separates `observed_net_cost`,
`remaining_net_cost`, `uncovered_past_hours` and future coverage timestamps.
Remaining interval costs are prorated when the current time or midnight cuts a
plan interval. The day boundary follows local time, including 23/25-hour DST days.

Before ComEd publishes every remaining hour, the forecast can still be useful.
It uses published prices first, then a **tentative** estimate for an unpublished
future supply hour: the median of recorded prices for that Central clock hour,
or a recent published-price median if there is no matching history. No built-in
household rate or assumed zero price is substituted. More info and the note below the
totals identify the estimated hours, rates and sources; **Tentative forecast ·
lower confidence** remains visible even with partial-day coverage. Published
prices replace estimates automatically on a normal planning refresh. See
[tentative pricing](pricing.md#tentative-prices-for-the-end-of-day-cost-forecast)
for freshness limits and fallback details.

This estimates the cost of the already selected energy flows; it does not change
EV/battery schedules, buying-price sensors, household advice or equipment-control
pricing rules. It requires no opt-in to the separate ComEd live-delay policy.
Estimated current-hour prices from that bounded policy and estimated observed
costs also lower forecast confidence. This is still an uncertain energy forecast,
not a promise that the selected schedule or price will occur.

Normal sunrise/sunset boundaries do not need a full-hour provider point: NRG
combines the covered daylight portion with HA's known nighttime zero. It never
fills genuinely missing daylight this way. If coverage is still missing, the
explanation names the input and first uncovered local time.

The forecast still waits for a missing price without a defensible estimate, a
current live-price outage beyond its existing bounded policy, missing delivery or
export settings, or missing solar coverage; none is treated as zero.
It also needs some covered cost today, a fresh plan, an applicable battery outlook
and sufficient EV charging information/compatible controls. A monitoring-only
battery's independent dispatch is not predicted, so its forecast stays unknown.
The explanation below the totals names the blocker. It returns automatically when
these inputs are ready; no control permission is enabled to obtain a forecast.

Use **Why?** and the linked complete handbook for explanations. The homeowner
dashboard has no equipment or configuration controls.
