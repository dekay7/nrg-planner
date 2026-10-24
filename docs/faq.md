# Common questions

## Do I need solar, a battery, or an electric car?

No. All three are optional and start disabled. A grid-only home can use price
information and flexible-use advice. Add a suitable grid or home power meter for
covered cost estimates. Turn off equipment you do not own under
**Configure → Components**.

## Does NRG replace Home Assistant's Energy dashboard?

No. The Energy dashboard remains useful for historical energy totals. NRG adds
forward-looking advice, optional EV/battery planning, and covered cost estimates.
The live power-flow diagram uses the meters already configured for HA Energy.
Its setup is separate from NRG's measurement mappings.

For HA Energy pricing, use `sensor.nrg_import_price_usd` for buying and
`sensor.nrg_export_price_usd` for export credit. The buying sensor already
includes delivery. See [accounting](accounting.md#built-in-ha-energy).

## Do I have to install the dashboards or edit YAML?

The integration's setup forms and native entities work without the optional
dashboards. NRG's own settings do not require YAML editing. The bundled dashboards
do require the small package include described in [installation](installation.md#optional-dashboards),
plus the separately installed ApexCharts Card for charts. YAML is a text-based
configuration format; copy the example carefully and merge existing sections.

## Will installation start controlling my equipment?

Fresh installations use **Observation**, with EV control, battery control, and
notifications off. Monitoring, individual control permission, and operating mode
are separate settings. Read [operation and handover](operations.md) before enabling
commands.

## How do I stop NRG controlling a device?

Select **Observation** to stop new equipment commands, or turn off the relevant
component's control switch. Settings already stored in the car, charger, or battery
remain there. Set the desired device baseline in its own controls before enabling
another controller. [Handover and recovery](operations.md) explains the sequence.

## Can I use my existing car, charger, or battery integration?

NRG uses compatible Home Assistant measurements, switches, numbers, and selects
rather than requiring a particular brand. Compatibility depends on the operations
and feedback that your integration exposes. Tessie is not required; compatible
Teslemetry entities can be used directly. TeslaMate can supply readings, but
charging control needs a separate command integration or suitable HA scripts.
See [integrations and adapters](integrations.md).

## Does it raise my car's charge limit?

No. The selected vehicle target is read-only to NRG. It plans toward that limit
using the available time and configured charging assumptions. A shortfall means
the model cannot reach the selected target by departure under those conditions.
Use **Charge now** or adjust the departure override when appropriate; see
[everyday controls](operations.md#everyday-controls).

## Why does ComEd enter fallback when its API still responds?

A successful request can contain an old reading. Live ComEd data must be less
than 15 minutes old and belong to the current hour. Under the default **Strict
live pricing**, only a valid published forecast during the first ten minutes of
a new hour can bridge missing live pricing.

The separate opt-in **Allow brief published estimates** can use a valid exact-hour
forecast for up to 60 minutes from the last verified live observation. It shows
Degraded, lets EV planning continue, blocks battery grid charging and retains
reserve/protection checks. Refreshing or restarting cannot renew the allowance.
Neither a forecast nor selecting this option releases an already active automatic
fallback; distinct fresh live recovery is still required.
See [brief ComEd delays](pricing.md#brief-comed-live-data-delays).

## Will missing prices always stop my car charging?

No. **Standard protection** can continue guarded EV charging to meet departure at
an unknown price. **Use my fallback actions** applies the separately reviewed
EV choice: pause scheduled charging or charge for departure. The pause can leave
the car below its target. **Charge now** explicitly overrides that pause, but never
connection, selected-target, current or protection checks. Permitted temporary
published-estimate operation can also keep normal EV planning available without
activating custom fallback. See [outage actions](operations.md#price-data-fallback).

## Why suggest an appliance window when the grid price is high?

The reference appliance may be supplied by the home battery rather than the grid.
The advice identifies grid, direct-solar, battery-backed or mixed supply and shows
the grid rate separately from modeled appliance cost. Stored energy still has
losses and future value, and solar used at home can give up export credit.

A high-price window is recommended only when its modeled appliance cost offers a
sufficient improvement within dependable coverage. Baseline and appliance costs
stop at the same supported boundary; unknown later export prices cannot make a
future battery refill free. See [the homeowner guide](homeowner-guide.md#the-recommendation).

## Why wait when the buying price is negative or solar is producing?

The relevant price includes **supply plus delivery**. Negative supply can still
leave a positive total. Solar used at home may give up an export credit; battery
energy has conversion losses and possible future value. Advice also compares a
complete run of your reference appliance rather than one cheap moment.
See [the homeowner guide](homeowner-guide.md#the-recommendation).

## Why does NRG recommend using energy as usual on a flat rate?

If shifting the complete task offers too little modeled benefit, that is the
expected recommendation. Solar, export credits, or a controllable battery may
still create differences, but a flat grid rate alone does not make one hour
cheaper than another.

## Does the displayed cost equal my bill or show money saved?

No. Today's net energy cost estimates covered grid purchases minus export credits.
It can include separately tracked published-forecast intervals during permitted
ComEd bridges/delays. **Today's forecast-priced coverage** and cost entity attributes
identify those newly classified subsets; older ledger entries are not retroactively
reclassified. HA Energy using NRG's price entities also receives a permitted
forecast-backed current price. Neither source is a settlement-price guarantee.
Missing readings and restart downtime reduce coverage. Fixed fees, capacity/demand
charges, and unconfigured taxes are excluded. Credit banks and billing restrictions
are not reconstructed. Modeled plan costs and appliance benefits answer different
questions; [accounting](accounting.md#different-money-figures) explains them.

## Can it manage multiple EVs, other currencies, or timed battery exports?

The current scope is one planned EV, one modeled stationary-battery system, and
USD-denominated pricing. It does not schedule forced battery exports or arbitrary
household appliances. Export permission is not a sale schedule. See
[how it works](design.md) and [alternatives](alternatives.md) for context.

## Does it need the internet or an NRG account?

There is no NRG account, analytics, or telemetry-upload service. Planning, saved
settings, and learning run in Home Assistant. Flat or configured timed prices need
no online price feed. ComEd and solar forecasts depend on their providers, and
your selected equipment integrations or notification services may use the cloud.
The bundled handbook needs no external assets. See [privacy](../PRIVACY.md).

## How long does learning take, and can I turn it off?

NRG uses the fallback assumptions until enough well-covered observations exist.
Solar calibration starts after six valid daylight hours; EV calibration needs
qualifying charging sessions; household learning builds from covered hours over
time. Optional battery calibration needs three covered, substantial closed-SOC cycles
for efficiency and three sustained opportunities per power direction. It may take
longer—or retain fallbacks—if normal operation does not provide those opportunities.
It does not estimate battery health. Each switch can be turned off independently.
**Reset learning** clears profiles and calibration while keeping settings and the
measured-cost ledger.
See [learning](learning.md) for the exact requirements.

## Why did a price change not send a notification?

Household advice and price-data fallback alerts are independent opt-ins. Advice
needs a stable, worthwhile wait recommendation with dependable coverage; a limited
refill estimate suppresses savings messages. Fallback alerts describe entry or
recovery, not every delayed request or estimated-price interval. Both need selected
notify services and respect quiet hours. Enabling messages grants no equipment
control. See [notifications](operations.md#notifications).

## What stays saved when Home Assistant restarts?

Settings, source mappings, completed learning, forecast caches and cost ledgers use
Home Assistant storage. Manual fallback requests, the automatic-outage latch and
the verified ComEd live timestamp also persist; restarting cannot renew a delay
allowance or use a forecast to release an existing outage. Incomplete battery
calibration opportunities/cycles and live recovery confirmation start over.

**Charge now** is session-only and clears on restart; it also clears on completion
or disconnection. A one-off departure takes precedence over the daily time and
can stay overdue while the car remains connected and incomplete; clear it when
no longer needed. Restart gaps are not filled with invented use. Integration
removal deletes NRG's own local store, whereas reloads/updates preserve it.
The [operations guide](operations.md) covers updates and recovery.

## Why do the online docs show a feature missing from my HACS installation?

Main-branch documentation can include unreleased development after 0.3.0. HACS
stable users receive features through published releases, not every merged PR.
A manually installed development snapshot may retain the same manifest version
as the latest release, so that number alone does not identify its feature set.
See [the feature history](features.md#development-milestones-since-creation) and
[updates](installation.md#updates-and-removal).

## Is NRG free, and where do I ask for help?

NRG is [MIT-licensed](https://github.com/dekay7/nrg-planner/blob/main/LICENSE).
Home Assistant hardware, electricity, and third-party integrations or services
may have their own costs. The maintainer is
[@dekay7](https://github.com/dekay7). Follow [getting help](troubleshooting.md#getting-help)
to prepare a useful report for the
[GitHub issue tracker](https://github.com/dekay7/nrg-planner/issues). Use the
[security policy](../SECURITY.md) to report suspected vulnerabilities privately.
