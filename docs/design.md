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

The horizon covers up to 48 real hours, split into 15-minute intervals and exact tariff,
departure, buffer and charging-window boundaries. Intervals carry UTC instants;
contract times and weekdays use HA's timezone. Repeated DST clock hours receive
the same time-of-use rate, while energy uses their real elapsed duration. Both
occurrences of a repeated tariff/window boundary and the clock-offset jump itself
split intervals, including non-quarter-hour and half-hour DST changes. Skipped
tariff/window clock times are evaluated using the rate/window actually in effect
after the jump, not a fictitious extra interval.

Supply and delivery are evaluated independently at every boundary, then added once.
Both support flat, timed and external prices; supply additionally supports ComEd.
External current observations are not extrapolated as future rates. Missing foreign
utility data never receives a ComEd historical fallback. See [pricing](pricing.md).
Flat rates also start unset. ComEd's live running average, published exact-hour
forecast and tentative estimate from locally recorded observations are distinct.
Only the documented publication bridge or opt-in bounded estimate allowance can
substitute a published forecast for missing current live pricing; learned-history
estimates cannot authorize it. No historical household profile is embedded.
See [sources and freshness](pricing.md#comed-price-sources-and-freshness).

For daily departure on a DST change, the first occurrence of an ambiguous local
time is used. A nonexistent spring time shifts forward by the DST jump.

## Measurements and statistics

Known absent equipment contributes zero; missing enabled equipment is unknown.
Complete applicable site meters can derive a missing home/grid reading from
`solar + grid + battery = home`, with the calculated basis identified.

At least once per minute, the previous valid sample is integrated only across gaps
of at most 180 seconds. An hour needs at least 80% coverage to be learned; its
covered energy is scaled to an hour. Missing/restart gaps are never zero observations.
An observation gap discards unfinished EV/battery sessions, but already covered
portions of a household/solar hour can still qualify if their combined coverage
reaches 80%. Restart still discards the unfinished in-memory hour.

House demand excludes separately measured EV charging. If that meter is unavailable,
learning can continue while the car is known not to be charging. If EV power exceeds
home power by more than 0.2 kW, or available site flows disagree by more than the
larger of 0.3 kW / 5% of home power, relevant learning pauses. Details exposes quality
and the balance residual rather than learning an impossible zero house load.

The recency-weighted hour-of-day profile uses up to 28 days; each older observation
has 0.9× the next newer weight. Weekday/weekend matching is used after three matching
observations. The 28-day age limit is enforced by elapsed time, not just a maximum
row count, so a long offline period cannot retain an obsolete profile indefinitely.
Missing profiles use the configured fallback.

Solar uses correctly grouped forecasts, optional compounded panel age and a bounded
actual/forecast ratio after six covered daylight hours. Forecasts are frozen before
the evaluated hour; later forecast improvements are not used as hindsight. Each
array needs an explicitly covered hour; a daily total alone never proves missing
daylight is zero. Alternatives are selected per hour. Daily normalization splits
at local midnight even when UTC hours straddle dates. Explicit covered zero-output
hours remain valid. A partial dawn/dusk hour is usable only when its provider
coverage plus HA's known astronomical darkness covers the whole interval. Night
overlap is merged, not double-counted; partial energy is never scaled to an hour.
Missing daylight or sun events leaves the edge unknown. Broken daytime shapes,
duplicate timestamps, invalid containers and implausible daily totals are rejected.

EV calibration uses covered sessions with at least five SOC points and five minutes.
The upper 80th-percentile AC kWh/point sample from the last twelve valid sessions is
conservative about required energy. Lower-percentile observed power/amp estimates
help avoid overpromising charging speed. An energy-counter decrease or SOC reversal
breaks the session even if the final totals later look plausible. It does not
estimate EV degradation.
Optional battery calibration uses closed SOC cycles to measure AC energy out/in
without inferring capacity. Charging and discharging capability each need repeated,
stable ten-minute opportunities with spare supply or unmet demand, independently
measured site flows and mid-range SOC. Each parameter requires three observations;
up to twelve within thirty days are used. One opt-in switch controls all three,
with independent manual fallbacks. No forced calibration cycle or health estimate
is made. All battery transitions and refill valuation use the same effective values.
The [learning guide](learning.md) explains the controls and measurement limits.

## EV candidates

```text
AC energy needed = (selected limit − SOC) × estimated AC kWh per percentage point
```

When EV control is enabled, compare cheapest-grid, solar-aware, earliest and latest
feasible schedules. Solar-aware charging values direct surplus at foregone export
credit and can lower current within its configured stable range. It increases
available current if otherwise a feasible deadline would be missed. The effective
current range intersects the configured and device-reported minimum/maximum using
whole amps, matching the writer; manual settings are not overwritten.

Use the completion buffer first, then the actual departure and additional available
time if necessary. Charge-now ignores price/window preferences. An incomplete
continuously connected session remains overdue rather than silently moving to tomorrow.

A previous feasible EV schedule competes to reduce churn. Preserve it when the
modeled improvement is below the selected threshold. Known-price charging periods
are preferred over unpriced gaps before comparing cost. An estimate used internally
for deadline calculations is not displayed as a known tariff or a free hour.

## Battery search

For each EV candidate, search supported **hold, serve the home, grid charge** modes
only through the contiguous dependable economic horizon: known import and applicable
export prices, plus solar coverage when solar is configured. Stop at the first gap;
a later island of known prices cannot justify an earlier economic action. The longer
outlook retains EV feasibility and physical energy with battery hold after that
boundary. An active price-data fallback instead retains its explicitly selected
baseline. Replanning can extend the economic horizon as coverage improves.

**Known limitation under separate review:** an allowance ending partway through
the current ComEd hour can introduce a gap even when the numerical forecast price
is unchanged. The contiguous-prefix rule can then discard later known refill
information and assume hold for the whole remaining outlook. This can change the
modeled current mode and EOD cost, not just the chart. An invented reproduction
is now tested separately; no horizon correction or extended control allowance is
implemented. A later correction must preserve unknown-tail/refill and command-time
safeguards rather than simply skipping gaps or treating estimates as known.

No battery, monitoring-only battery, missing controls or invalid SOC yields no
discretionary battery trajectory. No charge-capable mode/switch means grid charging
is excluded rather than invented. Unknown current prices/solar permit hold only.

Grid charging is not scheduled alongside EV charging. The preserve-battery option
also excludes serving the car from storage. There is no active seasonal charging
heuristic: the former summer restriction was removed. Actual configured tariffs,
coverage, equipment permissions and protections determine the permitted modes.

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

Energy remaining at the dependable boundary receives a common replacement value
from permitted grid and solar refill potential within that same horizon. Valuation
and dispatch share one mode-permission function. Grid refill requires a supported
charge mode and either a reversible grid-permission switch or distinct force-charge
mode; it is excluded during EV charging, price-data fallback and current intervals
using the opt-in published estimate. Estimate-backed operation retains a higher
reported native reserve and caps export permission to solar only or no exports. Solar surplus is
calculated after house and EV demand. If hold prevents solar charging, solar is
counted only where another permitted mode accepts it. Unavailable/monitor-only
batteries claim no scheduled refill potential.

Conversion losses and one shared charging-power budget limit grid plus solar in
each interval. Potential refill is weighted up to age-adjusted usable capacity:
a tiny solar surplus does not make the whole battery free to refill. This is a
hypothetical refill of depleted usable capacity, not today's headroom and not a
promise of a chronological refill after a particular appliance start.

If permitted potential cannot cover usable capacity, the uncovered portion receives
a conservative reference: the highest nonnegative known buying or applicable solar
export-opportunity rate, adjusted for charging losses. This reference is explicitly
not a charging opportunity or an invented future tariff. Advice confidence becomes
limited and savings notifications are withheld. Diagnostics distinguish covered
stored kWh, uncovered stored kWh, source contributions and the reference value.

EV schedules with equally ranked deadline feasibility and unpriced energy are
valued separately to respect their demand and mode restrictions. Their maximum
valuation is then used as a common conservative value for **all** candidate scores
and the appliance baseline/replay; a candidate cannot win merely by repricing the
same stored energy. Any insufficient refill coverage among those contenders limits
comparison confidence. These bounded estimates are not a global optimization or
refill guarantee. Calendar degradation does not imply a cycling cost; optional
wear cost defaults to zero.

Stored-battery sales are not scheduled or credited merely because export permission
is allowed. The modeled serve mode supplies home demand; it must not be mapped to
a forced export operation. Solar surplus exports when permitted/nonnegative,
otherwise it is modeled as curtailed. Native response is checked separately.

## Household advice and execution

Replay the selected modes with the reference appliance starting now or at each
15-minute boundary in the next day. Both the baseline and appliance scenario end at
the same dependable boundary and include foregone exports, losses, wear and the
value of their remaining battery energy there. The complete appliance duration must
fit inside that horizon. Missing future export compensation must not turn a later
solar refill into free energy or erase the cost of an earlier battery discharge.
Explicit zero credit and prohibited exports remain distinct from unknown credit.

Advice identifies the modeled appliance supply as grid, direct solar, battery or
mixed. Its grid-price attribute is a time-weighted supply-plus-delivery rate for
the selected window, not the appliance's modeled cost. Battery-backed use can be
worthwhile during an expensive grid hour; it is not necessarily a cheap-grid window.
These are incremental costs under the selected modes, not a separate globally
reoptimized appliance schedule. Incomplete equipment information limits confidence;
only dependable advice can send savings notifications. Tentative/gap outlook values
remain distinguishable. Advice never operates an appliance.

Current pricing health is reevaluated at command boundaries as well as coordinator
updates. Moving into or out of estimated pricing, entering/releasing fallback,
or changing assumptions invalidates the old plan. A ComEd estimate deadline is
an exact slot boundary; commands cannot extend it using an old charging grant.
The last verified live timestamp and automatic-outage latch persist across
restarts, without persisting an unfinished live-recovery confirmation.
See [price resilience](pricing.md#brief-comed-live-data-delays).

Plans expire after seven minutes and replan every five minutes/on important changes.
The serialized writer runs every thirty seconds and selects the applicable dated
plan interval, so tariff/charging boundaries do not wait for a fresh five-minute
plan. It rechecks ownership, revision, protection inputs, supported operations,
limits and readback at command boundaries. A failed battery command does not by
itself suppress independent EV checks.

Commands may take time to reach equipment. A battery may briefly supply a car before
the hold takes effect. Requests and readbacks do not guarantee instantaneous power;
the equipment retains its own electrical protections.

Settings are HA integration options. Compact hourly and battery-cycle/opportunity
learning, dated caches and 62
daily ledgers use HA Store, saved periodically and on shutdown. Bootstrap YAML never
overwrites existing UI options. The optional dashboard package excludes large
plan/source/observation entities from recorder. The power-flow Sankey card is
Home Assistant's built-in live data view of the Energy dashboard configuration;
ApexCharts is a separately installed optional chart dependency used for timelines.
