# Reading NRG Planner

## Electricity price now

The large **¢/kWh** number includes the selected **supply plus delivery** prices.
They may each be flat, follow independent timed periods, or come from external
feeds. Supply and delivery are also shown separately so the total is explainable.

Hourly current values can change before settlement. Contracted time-of-use rates
change at the configured boundaries. Solid forecast lines represent published
outlooks; dashed lines are estimates. A gap means price information is missing,
not that energy is free.

## The recommendation

- **Good time to use energy:** now is among the better modeled opportunities.
- **Use energy as usual:** shifting the reference task is not worth the difference.
- **Wait until …:** a sufficiently cheaper complete window is available.
- **Waiting for dependable coverage:** the information cannot support a full comparison.

The green segment marks a recommended window for the administrator's reference
appliance, initially **1 kWh over one hour**. The benefit concerns that task, not
the entire house. Use energy whenever it is needed; this advice does not start or
stop household appliances. Tap/hover a graph point to inspect it and use zoom/reset
without changing equipment.

Solar can have an export-credit opportunity cost, and stored energy has losses and
future value. NRG considers applicable equipment rather than assuming all solar or
battery electricity is free. Homes without that equipment need no such assumptions.

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
charge-now or a one-off departure override.

Battery percentage is measured. Available kWh uses the configured age-adjusted
capacity and reserve, rather than claiming a measured battery-health test.

While Observation is selected, schedules are proposals. Devices may currently be
following another controller. Monitoring-only equipment continues to use its own
controls; NRG does not promise it will follow the modeled schedule.

## Net energy cost today

Purchases minus export credits are estimated from covered meter readings and the
contemporaneous supply-plus-delivery rates. A negative total means modeled credits
exceed purchases over the covered time; it does not establish a cash payout.

Coverage matters. First days, restarts and missing readings are partial, not free.
Fixed fees, capacity charges and unconfigured taxes are excluded. A home with no
site power meter gets price advice but no claimed metered daily cost.

Use **Why?** and the linked complete handbook for explanations. The homeowner
dashboard has no equipment or configuration controls.
