# Prices, costs and savings estimates

## Supply and delivery

Internal prices use USD/kWh. Rate inputs and buying-price graphs use cents/kWh,
converted once. At each instant NRG independently evaluates supply and delivery,
then adds them. Different schedules, overnight periods, weekdays, flat rates and
external intervals are supported. ComEd is an optional supply adapter only.

Published/outlook rates are not necessarily settlement values. Missing prices do
not appear as zero. A known flat or configured timed rate does not need ComEd or
an internet price feed.

Export credit is independent: selected supply plus an adder, flat credit or no
credit. Export policy controls what is permitted where a supported device control
exists; it does not itself establish compensation or a timed sale. Credit-bank,
cash-out and billing-period restrictions are not automatically reconstructed.

Fixed customer fees do not change which hour is cheaper. Capacity charges and
unconfigured taxes are excluded; there is no modeled capacity-charge saving or
active seasonal charging heuristic.

## Hourly accounting development status

**Unreleased, inactive foundation only.** ComEd describes its hourly market rate
as the average of twelve five-minute prices. The source now includes a pure,
tested normalizer and hourly reconstruction model, but it is not connected to
the observed ledger, forecasts, learning or controls. New provider polling and
persistent price retention are gated on clarifying the API's retention terms;
no authoritative billing-final hourly series has been verified. There is no new
setting to enable this foundation. Existing costs, settings and learning remain
unchanged, including legacy totals and forecast-priced subsets.

**The current ledger still integrates contemporaneous running estimates.** It
does not yet reconcile a completed ComEd hour to one hourly rate. Do not interpret
this development work as corrected past costs, settled utility charges or repaired
Home Assistant Energy statistics. Export compensation stays as configured; the
applicable net-metering class/netting rules are not automatically inferred.

## Observed ledger

```text
purchase cost = positive grid kW × hours × buying price at that time
export credit = negative grid kW magnitude × hours × configured export credit
net cost      = purchase cost − export credit
```

The previous observed power is integrated only over gaps of at most three minutes.
Configured time-of-use boundaries split observed intervals exactly, including a
boundary partway through a sampling minute. Both occurrences of repeated DST
boundaries and the offset change itself are split; skipped clock times do not
create energy or a fictitious priced interval. Current variable-feed rates remain
contemporaneous estimates, including the explicitly labeled published forecast
during ComEd's bounded [new-hour publication window](pricing.md#comeds-new-hour-publication-window).
The optional [brief-delay estimate mode](pricing.md#brief-comed-live-data-delays)
can also use an exact-hour published forecast within its fixed allowance. Neither
forecast path becomes a recorded live supply observation for learning.

**Today's forecast-priced coverage** reports the hours newly accounted using
published estimates. Cost and coverage entities expose `estimated_coverage_hours`,
`estimated_import_cost` and `estimated_export_credit`; these amounts are subsets
of the displayed totals, not additional charges. Live/contract-rate coverage is
total coverage minus estimated coverage. Tracking begins with this update; older
saved ledger intervals are preserved but cannot be retroactively classified.
Estimated-price accounting stops at the earlier of the exact allowance deadline
or the real hour boundary, even between samples. A previous hour's forecast is
not carried into the following hour. Published estimates are not utility settlement
prices.

User rate changes do not retroactively reprice earlier observed intervals.

Missing price/grid data contributes neither cost nor cost coverage. Negative
purchase costs and negative export credits remain signed, including adverse native
exports that occur despite a request to stop them.

A complete set of applicable power meters can calculate a missing grid reading;
the basis is identified in diagnostics. A home with no sufficient site metering
does not get a claimed zero daily bill. Price advice still works.

Restart downtime is omitted rather than filled using a new price or counter jump.
Coverage is cost-covered hours divided by real elapsed local-day hours, including
DST. First days and outage days are partial. The ledger retains 62 days; learning
reset preserves it. Daily energy figures cover observed intervals and can differ
from the built-in Energy dashboard's lifetime-counter-based totals.

## End-of-day net-cost forecast

**Forecast net cost by midnight** (`sensor.nrg_net_cost_eod`) is the covered
ledger's purchases minus export credits plus the selected plan's remaining
interval cash costs up to the next local midnight. Published prices take priority;
unpublished future ComEd hours can use explicitly tentative supply estimates as
[described in pricing](pricing.md#tentative-prices-for-the-end-of-day-cost-forecast).
These reprice the already selected import/export flows after all planning decisions,
without reoptimizing equipment against tentative prices. Supply-linked export
credits use the same tentative supply plus the configured adder; flat credits and
no-credit settings remain independent of delivery. It includes supply and delivery;
it does **not** use `modeled_cost` or candidate scores, which include optional
battery wear and stored-energy replacement value. It excludes tomorrow's costs.
Current and midnight-crossing intervals are prorated by their real-time overlap.
Local midnight is calculated as the next calendar date, not by adding 24 hours,
so DST days retain their real 23/25-hour lengths.

The sensor updates with each measurement refresh, clipping already elapsed plan
time to avoid adding it again to the observed ledger. Earlier uncovered time is
never backfilled: a partial-day forecast remains labeled partial, and
`uncovered_past_hours` and today's observed coverage describe the omission. With
no covered observations today, it stays unknown rather than presenting a
forecast-only total as metered cost.

Dawn/dusk intervals can combine provider-covered daylight with HA's astronomical
nighttime zero without scaling the partial energy to a full hour. Every daylight
portion still needs forecast coverage for each physical array; unavailable sun
events or real daylight gaps remain unknown. Waiting explanations identify the
missing input and first uncovered local time when available.

Remaining cash-projection coverage must be continuous through midnight; unlike
the control/comparison horizon, it can include labeled tentative ComEd hours. A
stale plan, a missing price without a defensible estimate, missing applicable
delivery/export/solar coverage, an unmodeled installed battery or insufficient EV
charging information/controls leaves the value unknown with a reason. Recovery
is automatic when the data is ready. A monitoring-only
battery's independent dispatch is not assumed to match a schedule. A monitoring
EV contributes only its observed charging toward a known target. No future
plug-in or independent controller schedule is invented.

The projection is read-only and requires no new settings or control permissions.
Observation still blocks commands; the forecast assumes the proposal is followed.
It is not a utility bill, guaranteed savings or a cash-payout prediction. Entity
attributes separate observed and remaining net cost, observed estimated-price
coverage, future coverage timestamps, operating mode and the current status/reason.
`estimated_forecast_hours` and `estimated_forecast_intervals` identify the remaining
estimated portions, their supply/import/export rates in USD/kWh, source and available
sample/reference details. Each real hour is listed separately, including repeated
DST hours. `confidence` is `tentative` when future or covered observed prices include
estimates, `limited` for other partial-day totals, `forecast` for covered totals
without those price estimates, and `unavailable` while waiting. `status` still
separately reports `ready`, `partial_day` or `waiting`; ready means calculable, not
certain. The dashboards show tentative hours and retain partial-day warnings too.
These forecast-only estimates are never written into the observed ledger, learned
as live prices, or used to extend the dependable economic horizon. A fresh published
exact-current-hour price can cover its remaining projection beyond the control
policy's cutoff; it remains tentative and cannot authorize commands or observed
costs. Without that publication, the current hour is not filled from a median.

## Different money figures

1. **Observed net variable cost:** grid meter readings and contemporaneous rates,
   with explicit coverage. Not a complete settled utility bill.
2. **Forecast net cost by midnight:** covered observed net cost plus remaining
   planned cash costs for this local day, with earlier gaps explicitly omitted.
   Not the optimization score or a reconstructed complete bill.
3. **Modeled cost through dependable coverage:** a schedule comparison ending at
   the first price or applicable solar-coverage gap, including the remaining stored
   energy's replacement value and optional cycling cost. The displayed comparison
   endpoint may be earlier than the physical/EV outlook. With no dependable coverage,
   no economic cost is claimed. Individual outlook intervals also leave cost
   unknown when applicable solar coverage is missing, even if their prices are known.
4. **Reference-appliance benefit:** modeled difference between complete start
   windows for the selected energy/duration. Baseline and appliance replay share
   that same dependable endpoint, with applicable export/storage costs. An unknown
   future export credit is not a zero credit and cannot justify a free solar refill.
   The selected window's grid rate is shown separately from its appliance cost;
   grid, direct-solar, battery-backed and mixed supply describe modeled physical
   supply, not a claim that any source is free.

Battery replacement valuation counts only permitted refill potential after house
and EV demand, with a shared solar/grid charging-power budget. Insufficient refill
coverage uses an explicitly conservative known-price reference for the uncovered
stored energy, not an assumed future purchase or a promised refill. The dashboard
marks this limited and savings notifications are withheld. Competing feasible EV
schedules and household replay use one common conservative stored-energy value;
changing a candidate does not assign a cheaper price to the same battery energy.

No annual saving is claimed from software scenarios. Validate predicted versus
observed operation and reconcile actual bills.

## Built-in HA Energy

Use **`sensor.nrg_import_price_usd`** as the buying-price entity if configuring HA
Energy costs. It includes the selected supply and delivery methods; do not add
delivery again. Its availability follows price coverage.

During a permitted ComEd forecast bridge/estimate allowance, these entities can
publish a forecast-backed price. Their price-source attributes and Pricing health
identify that provenance; HA Energy using those entities will also be using the
estimate, not a settled utility rate. NRG's separate estimated-coverage subsets
are in its own ledger, not a retroactive correction of HA Energy history.

Use `sensor.nrg_export_price_usd` for export compensation. Changing Energy's price
sources is a separate supported UI action; NRG does not rewrite historical records.
