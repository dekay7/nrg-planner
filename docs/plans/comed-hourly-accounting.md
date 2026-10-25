# ComEd hourly accounting, reconciliation, and planning — implementation handoff

**Status: proposed development work, not an implemented or released feature.**

Prepared against repository commit `31303b8` (version `0.3.0`). Recheck the current
branch and implementation before starting. This plan contains invented examples
only; do not add household data, credentials, or live-instance identifiers.

## 1. Objective and agreed approach

Make NRG's ComEd variable-cost accounting follow the hourly tariff, then use the
same hourly price model consistently in EOD estimates and planning.

**Collect five-minute prices, but value energy at the hourly rate.** For a complete
hour with twelve equal-duration prices:

```text
hourly supply rate = sum(twelve distinct five-minute prices) / 12
hourly import supply cost = covered imported kWh × hourly supply rate
```

Do not price each five-minute consumption block at its individual market price.
Do not average successive running averages or weight market prices by household
consumption. Prefer an authoritative published hourly billing rate if its source
and semantics can be verified; deriving an average from public five-minute data
must not be mislabeled as a guaranteed final utility charge.

Invented regression: six prices at 2¢/kWh followed by six at 10¢/kWh produce a
6¢/kWh hourly rate. Importing 1 kWh entirely in the first half-hour costs 6¢ in
supply, not 2¢. Delivery and export accounting are separate.

### Priorities

1. Correct hourly accounting and restart-safe price reconciliation.
2. Consistent provisional current-hour valuation and EOD estimates.
3. A separately tested fix for pricing-gap-driven planner instability.
4. Only adopt more sophisticated prediction or extra switching hysteresis after
   measurement shows that it improves on the simpler baseline.

No implementation, HA deployment, restart, control-setting change, commit, or
release was requested in the planning conversation. A fresh session should follow
its user's implementation instructions; this document does not authorize live
HA access, equipment changes, or publication.

## 2. Established facts and questions to verify first

Public references:

- [ComEd pricing explanation](https://hourlypricing.comed.com/live-prices/): the
  real-time hourly market price averages twelve five-minute prices; the current
  average is unfinished; prices undergo a stated 24-hour settlement period.
- [ComEd API documentation](https://hourlypricing.comed.com/hp-api/):
  `type=5minutefeed` supports recent data and inclusive custom time ranges;
  `type=currenthouraverage` exposes a current running average.
- [ComEd solar/net-metering overview](https://hourlypricing.comed.com/solar/).
  Use the applicable tariff, not marketing summaries, to establish exact credit
  and netting rules.

Before fixing parsers or declaring costs billing-accurate, verify and record:

- Whether an accessible authoritative completed/reconciled hourly series exists.
  Do not invent an endpoint or assume the public feed certifies billing finality.
- Whether five-minute timestamps label interval starts or ends; the query time
  zone, inclusive boundary behavior, DST handling, units, precision, and revisions.
  Prove hour assignment against a published hourly example where possible.
- Import/export netting and export-credit rules. Retain the configured compensation
  model unless a verified tariff-specific implementation is explicitly agreed.
  Do not infer that imports and exports have identical compensation or that
  delivery is credited on exports.
- Appropriate retry/catch-up limits and settlement-window refresh behavior. A
  proposed default is a rolling 48-hour recheck window, subject to source validation.

The new hour beginning is a reconciliation trigger, **not evidence that the prior
hour is complete or final**. Retry based on actual data completeness.

## 3. Relevant current implementation

Read these files before modifying behavior:

| Area | Entry points / current behavior |
| --- | --- |
| Provider/runtime | `custom_components/nrg/runtime.py`: `refresh_forecasts()`, `_async_update_data()`, `load()`, `persisted()`, `evaluate_fallback()`. Polls `currenthouraverage`; persists forecasts, learning, and a daily ledger. |
| Prices | `custom_components/nrg/forecast.py`: `price_at()`, `cost_price_estimate()`, publication bridge, estimate deadlines. |
| Accounting | `custom_components/nrg/statistics.py`: `Statistics.observe()` integrates power at contemporaneous rates; daily costs are not reconciled to completed hourly supply prices. Import/export kWh currently require usable prices too. |
| Learning | `Statistics._finish()` stores the last observed supply value for an hour, not necessarily its completed rate; `price_prior()` uses matching-clock-hour history. |
| EOD | `forecast_net_cost()` adds covered observed cost to the selected plan's remaining cash flows. `planner.add_cost_forecast()` reprices flows after dispatch decisions. |
| Planner | `make_slots()`, `trusted_prefix()`, `replacement_value()`, `battery_search()`, `plan()` in `custom_components/nrg/planner.py`. The planner already shares a current-hour rate across its remaining physical slots. |
| Writer | `custom_components/nrg/control.py` and `adapters.py`: permissions, current-price checks, reserve retention, fallback, device mappings. |
| Presentation | `sensor.py`, `binary_sensor.py`, `diagnostics.py`, `tools/build_ui.py`, and the accounting/pricing/learning/design guides. |

Two separate issues must not be conflated:

1. The ledger permanently accumulates a mixture of successive running-average
   prices instead of valuing a completed hour at its completed rate.
2. A bounded current-hour estimate can expire before the hour ends. The first gap
   truncates the economic horizon; battery valuation changes, and the remaining
   outlook defaults to hold. This can cause large EOD changes and actual mode
   changes even when numerical prices are unchanged.

The second issue has a deterministic invented-data reproduction. Passing existing
forecast tests does not establish correctness for either issue.

## 4. Design invariants

- Maintain separate facts for **energy coverage**, **price completeness/source**,
  **cost valuation**, and **command authorization**.
- Never invent missing energy, carry a prior-hour live rate into a new hour, or
  represent missing prices as zero. Real zero and negative prices remain valid.
- Preserve Observation defaults, explicit component permissions, native guards,
  reserve protections, EV deadlines, fallback/recovery policies, and settings.
- Preserve the prohibition on battery grid charging during published-estimate
  operation, retained native reserve, and applicable export restrictions.
- Historical price backfill/reconciliation is not fresh live evidence, cannot
  renew a control allowance or release fallback, and never directly authorizes
  equipment commands.
- Keep flat, time-of-use, and external-price behavior unchanged unless a separate
  reviewed requirement calls for changes. Scope reconciliation to ComEd.
- Keep bounded local aggregates and public prices; no raw household histories in
  source, fixtures, logs, generated assets, or commits. Public price requests must
  not transmit household energy measurements.
- Keep existing entities and a coherent UI; avoid proliferating competing totals.

## 5. Implementation work packages

### A. Provider normalization and hourly price cache

Create a small pure parsing/aggregation layer with no HA objects or network calls.
It may live in a focused new module rather than expanding `runtime.py`.

- Normalize interval identity to UTC with verified provider timestamp semantics.
- Deduplicate by physical interval, retain corrections and provenance, and validate
  timestamps, finite values, units, interval alignment, and source bounds.
- An hour is complete only with all twelve expected distinct intervals; twelve
  arbitrary rows, repeated polls, or a partial average do not qualify.
- Prefer verified authoritative hourly prices over reconstructed public averages.
  Distinguish provisional, complete-public-data, reconciled, and unavailable states.
  Do not assert utility finality merely because 24 hours elapsed.
- Retain sufficient numeric precision; document rounding choices. Round display
  values separately from accounting calculations.
- Add bounded asynchronous polling/catch-up, request deduplication, backoff, and
  later revision checks. Do not fetch on every sensor refresh when unnecessary.
- Persist cache/retry state needed for restart recovery; prune it deliberately.

**Exit:** independent invented parser tests prove completeness, correct hour
assignment, revisions, and failure behavior before ledger integration.

### B. Hourly energy ledger and tariff snapshots

Store hourly accounting separately from the existing `Statistics.hours` learning
rows. Each record needs enough information to reproduce its valuation:

- UTC hour identity, covered imported/exported kWh, and coverage durations.
- Segments for tariff/configuration changes or delivery boundaries within an hour.
- Applicable supply-plan identity, delivery charges, export basis/adder/flat terms,
  and original provisional contributions where needed for compatibility.
- Applied price source/revision and derived purchase/credit totals.

Capture valid energy even while pricing is missing. Keep measurement gaps explicit.
Use the existing covered-power method initially and label that basis honestly;
it is not utility-meter-exact. Utility interval energy or validated grid counters
can improve accuracy later, but do not silently add mappings or allocate a counter
jump across unknown hours. Do not double-count competing measurement methods.

- Revalue a record from its energy and captured tariff terms when a price changes.
- Derive daily totals from the hourly records plus a legacy baseline, rather than
  maintaining an unbounded stream of correction deltas.
- Corrections are idempotent and crash/restart-safe, update the original day, and
  do not alter measured coverage. Missing prices may recover; missing energy does not.
- Preserve original delivery charges and export terms. Reprice supply-linked
  credits only where applicable; flat/no-credit settings remain independent.
- Handle a switch away from ComEd within an hour without repricing another plan.

**Migration:** define a persisted cutover instant and immutable legacy totals.
Only newly recorded energy is eligible for new reconciliation. Do not derive
historical hourly energy from old daily totals. Preserve settings, existing ledger,
EV/solar/house/battery learning, fallback latches, and control continuity. Test old
HA Store formats; provide a real migration if changing the Store version. Learning
reset must preserve accounting and reconciliation state. Bound accounting retention
consistently with the existing 62-day ledger.

**Exit:** daily totals reproduce independent hourly arithmetic and survive retries,
restarts, mid-hour rate changes, mixed legacy/new days, and midnight corrections.

### C. Current-hour valuation and EOD

Use one explicitly provisional whole-hour supply estimate consistently for the
current hour's covered measured energy and remaining planned energy.

- Start with a transparent current running-average baseline, with existing labeled
  forecast fallbacks only where applicable. Do not weaken live-price guards just
  to make a monetary projection available.
- Keep forecast valuation separate from eligibility to account a price as live or
  authorize commands. Explain any recovered price coverage and revised totals.
- Rate or price-source changes revalue all eligible measured current-hour energy
  rather than only subsequent samples.
- EOD combines past-hour costs, provisional measured current-hour costs, remaining
  current-hour flows, and future-hour flows without overlap. Use one valuation
  snapshot even between plan rebuilds; repricing selected flows is not permission
  to change dispatch. Preserve local-midnight clipping, earlier measurement gaps,
  stale-plan checks, and applicable solar/EV/battery availability checks.
- Model uncertainty remains visible; reconciliation improves past costs but cannot
  make future demand, solar, prices, or equipment dispatch certain.

A more complex estimator is optional follow-up. A candidate can estimate the final
hour as `(sum(published prices) + predicted sum(unpublished prices)) / 12`, but must
beat the running-average baseline using as-of-time tests without future leakage.
Do not assume a day-ahead/running-average blend is automatically more accurate.

### D. Price learning

- Prefer reconciled/complete hourly prices with explicit provenance over legacy
  last-observed running estimates. Keep legacy learning marked approximate.
- Maintain one effective price sample per physical hour; poll frequency, restarts,
  and revisions must not inflate sample counts.
- Price corrections update the corresponding price sample without rewriting home,
  EV, solar, or battery measurements. Preserve bounded retention and DST identity.
- Do not let a historical API fetch count as a live recovery observation.

### E. Presentation and documentation

Preserve primary cost entities; add understandable attributes/status explanations
rather than several conflicting headline totals. Distinguish:

- Missing measurements versus missing/pending prices.
- Provisional versus complete/reconciled price coverage.
- Latest reconciliation time and remaining gaps.
- Legitimate revisions to current and previous days' cost totals.

Review the meaning of existing `estimated_coverage_hours` / estimated-cost subsets:
a forecast-priced observation is not the same thing as every unfinished hourly
price. Preserve compatibility or document a deliberate migration; do not silently
repurpose fields. Keep diagnostics allowlisted and compact; avoid storing public
five-minute series in every HA state attribute.

Update `docs/accounting.md`, `pricing.md`, `learning.md`, `design.md`, relevant
homeowner/troubleshooting help, and `features.md` with unreleased availability.
Explain that NRG corrections do not automatically rewrite HA Energy statistics or
settle a utility bill. Fixed charges, unconfigured taxes, capacity charges, and
credit-bank rules remain excluded. Modify builder/catalogue sources and regenerate
with `python -B tools/build_ui.py`; never hand-edit generated dashboards,
translations, settings reference, or handbook.

### F. Separately reviewed planner-horizon correction

Do not bundle an untested optimizer rewrite into accounting changes. First add an
invented reproduction with usable battery energy, no EV load, unchanged economic
prices, and a current-hour allowance expiring before the hour ends.

Design and explain a correction that:

- Keeps valid later forecast information from being discarded merely because of
  a temporary current-hour gap, without pretending the gap is known.
- Keeps read-only forecast assumptions separate from control permission and makes
  the assumed behavior through unknown periods explicit.
- Uses one hourly supply rate across physical slots, while retaining finer slots
  for EV stops, solar, delivery boundaries, reserves, and battery constraints.
- Preserves conservative replacement valuation, feasible refill constraints,
  candidate/advice comparison consistency, and unknown-price protections.
- Does not invent a tariff benefit from changes in the running average within a
  single hour or claim savings from unpriced future refills.

**Do not simply skip gaps in `trusted_prefix()`, mark tentative prices known, extend
control cutoffs, or smooth the displayed number.** Read the earlier dependable-
horizon/refill regression tests and `docs/review.md` before redesigning this area.

A source transition must not cause artificial whole-outlook hold assumptions when
prices and permitted actions are equivalent. This is not a promise that equipment
mode can never change: genuine authorization, fallback, reserve, EV, or price
changes must still take effect. If a safe correction needs a new control policy,
propose that policy for explicit approval rather than silently changing defaults.

Assess extra hysteresis only after correcting the root cause. Safety actions must
never be delayed by stability thresholds. Report physical-mode and energy/cost
results, not only smoother charts.

## 6. Validation and acceptance

Use invented fixtures and independent expected calculations. Extend existing
statistics, tariffs, ComEd publication/resilience, forecast, control, upgrade,
documentation, and simulation tests; add focused new modules as appropriate.

Required cases:

- Six 2¢ and six 10¢ prices; identical hourly energy shifted within the hour gives
  identical supply cost. No consumption-weighted prices or averaged averages.
- Complete/incomplete intervals, duplicate/out-of-order responses, corrections,
  legitimate zero/negative prices, invalid units/times, and provider failures.
- Correct interval-ending/starting assignment, inclusive fetch boundaries, real
  23/25-hour DST days, repeated hours, and non-Central HA display/day boundaries.
- Price-only outages with measured energy, measurement outages, counter resets if
  supported, partial hours, and no invented zero-cost or zero-energy gaps.
- Hourly price revisions applied once, original-day midnight corrections,
  tariff/export changes mid-hour, and supply-plan switches.
- Legacy stores, mixed cutover days, learning reset, persisted pending data,
  interruption/restart, and bounded pruning without orphaned daily contributions.
- Current-hour repricing and EOD observed/remaining boundaries; delivery, export,
  wear, and terminal-energy value are not accidentally counted as supply twice.
- Permissions, Observation, reserve, price-age/deadline, fallback/recovery, and
  estimated-price restrictions remain enforced at command time.
- Planner gap reproduction plus existing unknown-tail, refill feasibility,
  replacement-value, candidate-score, and advice invariance regressions.
- New documentation/UI labels render correctly and generated assets reproduce.

If adding a five-minute synthetic market, aggregate the independent plant's supply
cost hourly too; do not validate against an oracle that incorrectly bills every
five-minute interval separately. Forecast backtests must use only information
available at decision time, not subsequently revised prices.

Success metrics: absolute cost error in cents and separate import/export errors,
energy coverage, pending-price coverage, forecast error by lead time, physical mode
changes, and feasible operation. Avoid percentage errors against near-zero net
costs and do not claim annual savings from an invented scenario.

Run the full development checks from `README.md`, including generated assets,
pytest, Ruff, dependency audit, privacy/history checks, and `git diff --check`.
Report unrelated/upstream failures honestly. No live data belongs in test fixtures.

## 7. Delivery sequence and non-goals

Suggested independently reviewable changes:

1. Source verification, pure price parser/cache, and regression fixtures.
2. Hourly energy bookkeeping, legacy cutover, reconciliation, and persistence.
3. Consistent provisional valuation, EOD, price learning, and generated UI/docs.
4. Isolated planner-horizon design and correction with safety/simulation evidence.

Do not ship half-wired totals; use internal shadow comparisons during development
where useful, without adding permanent user-facing toggles unless necessary.

Out of scope unless separately requested: utility-data ingestion, bulk HA recorder
backfill, repairing HA Energy history, a full bill/credit-bank engine, a new
statistical forecasting system, broad optimizer replacement, and unconditional
mode-stickiness rules. Keep generic tariff adapters working.

Before any later live deployment, verify installed code/version and take a recovery
backup through the explicitly approved workflow. Stage accounting-only behavior
before changed control decisions. Do not change modes/permissions, restart HA, or
publish a release without explicit authorization. Do not bump versions merely to
write or start implementing this plan; follow the release workflow when requested.

## Fresh-conversation starter

> Read `AGENTS.md`, the development checks in `README.md`, and
> `docs/plans/comed-hourly-accounting.md`. Use this as the implementation handoff.
> Recheck the current code and verify the open provider/tariff semantics first.
> Implement and test the hourly-accounting work in reviewable stages, preserving
> user settings, learning, legacy costs, Observation defaults, and control guards.
> Treat the planner-horizon change as a separate design/test gate. Use invented
> fixtures only. Do not access/deploy to HA, change equipment settings, or publish
> a release unless I explicitly request it. Report completed stages, checks,
> unresolved questions, and any deliberately deferred work.
