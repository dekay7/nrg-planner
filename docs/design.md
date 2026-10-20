# How NRG Planner makes decisions

## Scope and objective

NRG compares feasible plans to reduce purchases minus export credits, including
storage losses, optional cycling cost and remaining stored-energy value. Ordinary
household demand is forecast; applicable EV deadlines and backup reserve take priority.
The calculation is pure Python. A separate guarded writer uses public HA services.

Every hardware component is optional. Only an enabled, controllable battery is
scheduled. An uncontrolled EV's already observed charging can be extrapolated to
its known target as a background load; it does not produce EV command permission.
A grid-only home needs neither battery nor EV data for price advice.

## Time and prices

The horizon covers 48 real hours, split into 15-minute intervals and exact tariff,
departure, buffer and charging-window boundaries. Intervals carry UTC instants;
contract times and weekdays use HA's timezone. Repeated DST clock hours receive
the same time-of-use rate, while energy uses their real elapsed duration.

Supply and delivery are evaluated independently at every boundary, then added once.
Both support flat, timed and external prices; supply additionally supports ComEd.
External current observations are not extrapolated as future rates. Missing foreign
utility data never receives a ComEd historical fallback. See [pricing](pricing.md).
Flat rates also start unset. The optional ComEd estimate uses only observations
learned by the current installation; no historical profile is embedded.

For daily departure on a DST change, the first occurrence of an ambiguous local
time is used. A nonexistent spring time shifts forward by the DST jump.

## Measurements and statistics

Known absent equipment contributes zero; missing enabled equipment is unknown.
Complete applicable site meters can derive a missing home/grid reading from
`solar + grid + battery = home`, with the calculated basis identified.

At least once per minute, the previous valid sample is integrated only across gaps
of at most 180 seconds. An hour needs at least 80% coverage to be learned; its
covered energy is scaled to an hour. Missing/restart gaps are never zero observations.

House demand excludes separately measured EV charging. If that meter is unavailable,
learning can continue while the car is known not to be charging. If EV power exceeds
home power by more than 0.2 kW, or available site flows disagree by more than the
larger of 0.3 kW / 5% of home power, relevant learning pauses. Details exposes quality
and the balance residual rather than learning an impossible zero house load.

The recency-weighted hour-of-day profile uses up to 28 days; each older observation
has 0.9× the next newer weight. Weekday/weekend matching is used after three matching
observations. Missing profiles use the configured fallback.

Solar uses correctly grouped forecasts, optional compounded panel age and a bounded
actual/forecast ratio after six covered daylight hours. Forecasts are frozen before
the evaluated hour; later forecast improvements are not used as hindsight.

EV calibration uses covered sessions with at least five SOC points and five minutes.
The upper 80th-percentile AC kWh/point sample from the last twelve valid sessions is
conservative about required energy. Lower-percentile observed power/amp estimates
help avoid overpromising charging speed. It does not estimate EV degradation.
The [learning guide](learning.md) explains all four controls with examples.

## EV candidates

```text
AC energy needed = (selected limit − SOC) × estimated AC kWh per percentage point
```

When EV control is enabled, compare cheapest-grid, solar-aware, earliest and latest
feasible schedules. Solar-aware charging values direct surplus at foregone export
credit and can lower current within its configured stable range. It increases
available current if otherwise a feasible deadline would be missed.

Use the completion buffer first, then the actual departure and additional available
time if necessary. Charge-now ignores price/window preferences. An incomplete
continuously connected session remains overdue rather than silently moving to tomorrow.

A previous feasible EV schedule competes to reduce churn. Preserve it when the
modeled improvement is below the selected threshold. Known-price charging periods
are preferred over unpriced gaps before comparing cost. An estimate used internally
for deadline calculations is not displayed as a known tariff or a free hour.

## Battery search

For each EV candidate, search supported **hold, serve the home, grid charge** modes.
No battery, monitoring-only battery, missing controls or invalid SOC yields no
discretionary battery trajectory. No charge-capable mode/switch means grid charging
is excluded rather than invented. Unknown current prices/solar permit hold only.

Grid charging is not scheduled alongside EV charging. The preserve-battery option
also excludes serving the car from storage. The optional seasonal peak precaution
is separate from tariff prices and starts off for non-ComEd configurations.

For round-trip efficiency `r`:

```text
next stored energy = stored energy
                   + AC charging energy × sqrt(r)
                   − AC delivered energy / sqrt(r)
```

Capacity, room, reserve and modeled power constrain every transition. Age-adjusted
capacity is baseline capacity × `(1 − annual degradation/100)^age`, with fractional
years from elapsed days / 365.2425. An unset date does not invent age.

Search width is bounded to roughly 80 capacity bins, at least 0.5 kWh apart. Exact
energy is carried inside bins and never rounded up. The least modeled-cost path per
bin survives. This approximate search is not a global-optimum claim. Numerical ties
favor less battery throughput, avoiding artificial flat-rate cycling.

Remaining energy receives a common replacement value from the cheapest known grid
and solar refill opportunities, with losses and finite charging power. Refill is
weighted up to usable capacity: a tiny solar surplus does not make the whole battery
free to refill. Insufficient known refill energy uses the mean known buying rate
for the remainder. Calendar degradation does not imply a cycling cost; optional
wear cost defaults to zero.

Stored-battery sales are not scheduled or credited merely because export permission
is allowed. The modeled serve mode supplies home demand; it must not be mapped to
a forced export operation. Solar surplus exports when permitted/nonnegative,
otherwise it is modeled as curtailed. Native response is checked separately.

## Household advice and execution

Replay the selected modes with the reference appliance starting now or at each
15-minute boundary in the next day. Include its complete duration, foregone exports
and end-of-horizon energy value. Only the contiguous trusted-price horizon competes.
Tentative/gap prices remain distinguishable. Advice never operates an appliance.

Plans expire after seven minutes and replan every five minutes/on important changes.
The serialized writer runs every thirty seconds and selects the applicable dated
plan interval, so tariff/charging boundaries do not wait for a fresh five-minute
plan. It rechecks ownership, revision, protection inputs, supported operations,
limits and readback at command boundaries. A failed battery command does not by
itself suppress independent EV checks.

Commands may take time to reach equipment. A battery may briefly supply a car before
the hold takes effect. Requests and readbacks do not guarantee instantaneous power;
the equipment retains its own electrical protections.

Settings are HA integration options. Compact hourly learning, dated caches and 62
daily ledgers use HA Store, saved periodically and on shutdown. Bootstrap YAML never
overwrites existing UI options. The optional dashboard package excludes large
plan/source/observation entities from recorder. The power-flow Sankey card is
Home Assistant's built-in live data view of the Energy dashboard configuration;
ApexCharts is a separately installed optional chart dependency used for timelines.
