# Hourly home energy plan dashboard — implementation plan

**Status: implemented on the feature branch; unreleased.**

The sections below preserve the implementation specification. See the final
implementation record for the delivered choices, checks and remaining review gates.

Feature branch: `feat/home-energy-plan`, created from `origin/main` at `296cd5f`.
Target PR base: `main`. Keep the separate `work/comed-hourly-foundation` work out
of this PR. This document uses invented examples only.

## 1. Goal and scope

Replace **Grid prices · suggested appliance window** on **Home Energy** with a
clear picture of the selected home energy plan, hour by hour. Move that existing
price/appliance-window chart to **Why?**, alongside its recommendation explanation.

The new view must answer:

- When will the home buy electricity from the grid?
- When will the battery supply the home, save its energy, or charge?
- Is battery charging supplied by solar, the grid, or both?
- When is the EV expected to charge, and what demand does that add?
- When will surplus solar be exported or curtailed?
- Which parts are a proposed schedule, a fallback baseline, or an incomplete outlook?

This is a read-only presentation of the selected plan, not a new optimizer, a
change to equipment permissions, or a prediction of another controller's dispatch.
Do not change settings, learning, accounting, price eligibility, reserve policy,
EV deadlines, fallback/recovery behavior, or the existing live power-flow Sankey.

## 2. Proposed user experience

### Home Energy

Keep current prices, pricing-health warnings, household advice and live equipment
information. Replace the existing price chart in its current location with
**Home energy plan · next 24 hours**. Keep the live Sankey clearly titled
**Current power flow**, so forecasts cannot be mistaken for measurements.

Use the next 24 elapsed hours by default. Group the underlying dated intervals
into local clock hours without discarding within-hour changes. Clearly label the
current-hour remainder, any partial final hour, plan update time and **Now**.
Use one explicit as-of time for clipping, aggregation and details; an old plan's
elapsed portion must not be represented as future energy.

### Initial graph design (superseded by the readability follow-up in section 9)

Use stacked hourly energy columns, with one consistent **kWh** axis:

| Above zero: energy supplied | Below zero: where energy goes |
| --- | --- |
| Grid import | House demand, excluding the EV |
| Solar generation | EV charging |
| Battery supplying the home | Battery charging |
| | Grid export |
| | Solar curtailment, only when applicable |

Label the two directions **Supply** and **Use / export**. Below-zero columns mean
energy destination, not negative prices or negative physical consumption. Show
positive magnitudes in explanations/tooltips. Matching stack heights provide an
energy-balance check when the applicable forecast is complete.

Keep battery charge and discharge, and grid import and export, separate even if
both occur during one hour. Netting would hide the behavior the graph should
explain. Split battery charging into solar/grid amounts in the details, rather
than adding two more default legend entries. Do not add a price or SOC axis to
this main graph; show modeled end-of-hour SOC in details and retain the existing
48-hour battery trajectory on Why?.

Use stable, distinct colors and explicit series names; do not rely on color alone.
Hide equipment series for absent components and suppress irrelevant all-zero
export/curtailment series. Keep the legend compact on phones. Zoom/reset and
inspection must be read-only and usable by touch, not just mouse hover.

### Exact hourly details

Selecting/inspecting an hour must explain the actual selected intervals, not just
show a generic label such as "battery use". Include:

- Full local date, start/end time, timezone/offset and covered duration.
- Grid import/export, solar, house and EV energy in kWh.
- Battery discharge, charging from solar, charging from grid and modeled ending SOC.
- Battery action periods: **Save battery**, **Supply home**, **Charge from grid**.
  Show each change at its actual time if an hour contains multiple actions.
- EV charging windows, planned current and exact stop time where available.
- Whether the interval is inside dependable economic coverage, a conservative
  later outlook, or an active fallback baseline; name unavailable inputs.

Distinguish a requested battery mode from the modeled resulting flow. For example,
**Save battery** can still accept solar if configured, and **Supply home** need
not deliver energy if solar already covers demand or the reserve is reached.
Show that distinction rather than inferring actions from net battery energy.

Invented example:

> 18:00–19:00: grid import 1.4 kWh; solar 0.5 kWh; battery supply 0.6 kWh.
> House demand 1.0 kWh; EV 1.5 kWh.
> Battery supplies home 18:00–18:30, then saves energy during EV charging
> 18:30–19:00. Modeled ending SOC: 58%.

Provide a readable textual route to the same hourly details for keyboard and
assistive-technology users. A short **Next planned actions** summary beside/below
the graph should make upcoming grid charging, battery use and EV charging clear
without inspecting every bar.

### Why?

Move **Grid prices · suggested appliance window** here, immediately with the
reference-appliance explanation. Preserve its live/published/tentative price
series, green suggested window, inspection and zoom behavior. Retain the existing
48-hour modeled energy/SOC timeline and its battery-unavailable explanation.
The admin price outlook can remain unchanged.

Update wording so references to the green window clearly refer to the price chart
on Why?, not to the new home energy plan. Appliance advice remains advice only.

## 3. Data contract and aggregation

### What already exists

`custom_components/nrg/planner.py` already selects dated slots (usually 15 minutes,
plus exact tariff, deadline, availability and price-allowance boundaries). Public
slots include `house_kwh`, `solar_kwh`, `ev_kwh`, `import_kwh`, `export_kwh`,
`battery_action`, end-of-slot `battery_soc`, `ev_amps` and `ev_stop_at`.

`transition()` also calculates `solar_charge_kwh`, `grid_charge_kwh`,
`battery_discharge_kwh` and `curtailed_kwh`, but `plan()` currently discards these
when publishing the selected slots. Expose these selected transition results as
additive slot fields. Do not recalculate dispatch or infer charging from SOC
changes; conversion losses make that inference incorrect.

Use AC-side energy consistently:

```text
grid import + solar + battery discharge
  = house + EV + solar battery charge + grid battery charge + export + curtailment
```

Losses are already reflected in the stored-energy trajectory. Do not add a second
loss term to this AC-side balance or mix stored kWh with delivered kWh.

### Read-only projection

Implement a small pure presentation layer for hourly aggregation, with a single
normalized representation consumed by the graph and textual details. Prefer a
bounded server-side projection if needed to share timezone/boundary handling with
native HA templates; do not independently implement subtly different hourly
arithmetic in chart JavaScript and Jinja. Finalize its location/payload in the
frontend feasibility step below, measuring added state size.

Requirements:

- Aggregate selected slots only; no optimizer rerun or appliance-advice replay.
- Split at Home Assistant local-hour boundaries and clip to the displayed range.
  Prorate interval energy by overlap, consistent with the existing interval model.
- Preserve exact action boundaries and fractional EV completion; an hourly average
  is not a promise of constant instantaneous power throughout that hour.
- Retain gross charging/discharging and importing/exporting within an hour.
- Use UTC instants as identity and HA's timezone for labels/boundaries, not the
  browser's timezone. Add timezone metadata if the current plan lacks it.
- Keep both repeated fall-back hours distinct, omit nonexistent spring hours, and
  handle non-whole-hour timezone offsets and half-hour DST transitions.
- Do not average SOC percentages. Use the trajectory at the hour's ending instant;
  if clipping requires interpolation, use the modeled stored-energy endpoints and
  identify it as a model estimate. Never extend SOC through missing inputs.
- Treat older payloads without the new fields as unavailable for affected series,
  not zero. Keep existing consumers compatible; no storage migration is needed.
- Keep output bounded to the displayed horizon, with no new recorder history,
  network requests, household examples, or broad diagnostic exposure.

## 4. Honesty, permissions and unavailable data

- **Observation:** explicitly label the schedule as proposed; no commands are sent.
- **Control:** say it is the selected plan, subject to device checks. Commands and
  readback are not measured energy delivery. Keep actual status separate.
- **Monitoring-only battery:** do not invent its independent dispatch. Hide battery
  forecasts and dependent whole-site import/export totals, with the existing reason.
  Keep any independently valid demand/solar information available as partial data.
- **EV monitoring:** extrapolate only the already observed session supported by the
  current model, labeled as an extrapolation rather than scheduled NRG control.
  Do not predict future plug-ins or unknown charging duration.
- **Missing enabled component data:** show gaps/unavailable values and a reason.
  Zero is appropriate for known absent equipment, not missing telemetry or solar.
  Do not display a balanced complete-house stack using placeholder flows when an
  applicable battery/EV/solar forecast is unavailable.
- **Missing prices:** distinguish physical coverage from price/economic coverage.
  A known physical baseline can still be shown without calling its cost known or
  implying it is an economically optimized period.
- **Beyond `economic_until`:** name the existing conservative hold outlook, or the
  selected fallback baseline. Do not portray the full 24 hours as price-optimized.
- **Fallback:** visibly identify the selected baseline and recovery uncertainty.
  The graph must not authorize new charging or change fallback duration.
- **Stale/missing plan:** clear forecast series and show a waiting/expired message.
  Respect `expires_at`, including client-side expiry between sensor updates.
- Never extend an estimate allowance, skip a pricing gap, smooth a real mode
  change, or alter valuation to make the graph look better. Planner-horizon and
  ComEd accounting changes belong in separate work.

## 5. Implementation sequence

1. **Frontend/data feasibility checkpoint.** Prove stacked positive/negative hourly
   columns, shared hour inspection, touch interaction, exact action details and
   a keyboard-readable alternative with invented data and the documented
   ApexCharts Card 2.2.3 dependency. Verify partial-hour widths/labels and HA timezone
   handling. Prefer the existing dependency and builder; do not assume unsupported
   custom tooltip metadata or add another card dependency. If full action details
   cannot live reliably in tooltips, use a compact adjacent native hourly-details
   card backed by the same projection. Finalize that choice before the full build.
2. **Expose selected flows.** Add the four existing transition outputs to published
   slots, plus only the metadata needed for timezone/trajectory/explanation. Prove
   selected actions, candidate scores, costs, advice and writer behavior unchanged.
3. **Build hourly presentation.** Add the pure projection and tests for aggregation,
   action sequences, physical/economic availability and expiry. Keep payload size
   bounded and do not mutate the source plan.
4. **Build and place the graph.** Edit `tools/build_ui.py`, replace the Home Energy
   price chart, add the next-actions/status explanation, and move the price chart
   to Why?. Preserve admin views and read-only homeowner actions.
5. **Documentation and generation.** Update `docs/homeowner-guide.md`,
   `docs/features.md`, applicable design/troubleshooting help, and installation
   help only if the dependency/resource arrangement changes. Mark the feature as
   **unreleased development**, with defaults, permissions, missing-data and recovery
   behavior. Run `python -B tools/build_ui.py`; never hand-edit generated dashboards,
   translations, settings references or the handbook.
6. **Validate and prepare the PR.** Run the checks below, inspect desktop/mobile
   rendering using invented data, review scope against `main`, and prepare a PR
   describing the graph, chart move, safety invariants and validation evidence.
   Open/push the PR when implementation and review are complete, not for this
   planning-only change. Do not publish a release or change version values here.

## 6. Test and review checklist

Automated coverage should include:

- Grid-only; solar self-consumption/export/curtailment; solar battery charging;
  grid battery charging; battery discharge/hold/reserve; mixed-source hours.
- Both charge and discharge in one hour without netting; energy-balance checks
  against independent arithmetic; zero battery flow despite a selected serve mode.
- Multiple mode changes, exact tariff/availability boundaries, EV fractional stops,
  partial first/last hours, local midnight, repeated/skipped hours and half-hour DST.
- Observation versus Control; absent versus monitoring-only/unready equipment;
  missing solar/EV/battery data; fallback and conservative post-economic-horizon
  outlook; stale/missing/old payloads; finite-value validation.
- Unchanged selected dispatch, EV feasibility, advice, candidate scores, monetary
  totals, command eligibility and settings/learning retention.
- Executable Node chart tests for units/signs, clipping, null gaps and expiry.
- Generated-dashboard tests: the new graph is on Home Energy; the old price chart
  is on Why? and not Home Energy; component visibility and homeowner read-only
  behavior remain correct. Retain the existing price-chart regressions.
- Documentation links, feature availability, handbook inclusion, generated-asset
  reproducibility and bounded serialized state size.

Run the README development checks: UI/brand generation, full pytest, dependency
audit, Ruff F checks, privacy/history checks and `git diff --check`. Confirm CI
also passes reproducibility, Hassfest and HACS validation on the PR commit.
Record dependency/network limitations honestly rather than treating an unrun check
as passed.

Manual review must verify legend density, labels, shared-hour inspection, text
contrast, phone touch/scroll/zoom, keyboard-readable details, HA versus browser
timezone differences, missing-data messages, and separation of live versus planned
flows. Do not access a live household or operate equipment for these checks without
separate approval.

## 7. Definition of done

A homeowner can select any displayed hour and explain where electricity comes
from, where it goes, and the actual battery/EV action periods. Unknown behavior
is labeled rather than fabricated. The appliance-window price chart remains easy
to find on Why?. Existing defaults, settings, learning and controls are unchanged;
generated assets and user documentation match; checks pass or have explicitly
recorded external limitations. The completed feature is then ready for a focused
PR into `main`, not an automatic release.

## 8. Implementation record

- `planner.py` publishes the four already-selected transition flow values plus
  initial SOC and fallback-baseline metadata; no search, cost, advice or writer
  decision is changed.
- `hourly.py` computes a read-only, 24-hour projection at sensor publication time.
  The `sensor.nrg_plan` **hourly** attribute is separate from its command-plan
  attribute, so presentation clipping cannot mutate dispatch or persistence.
- `tools/build_ui.py` generates grouped positive/negative columns and adjacent
  native expandable hourly details, including charging sources, SOC, coverage,
  exact mode changes and EV current periods with their true end times. The price
  chart now appears only on Why? in the homeowner dashboard; admin charts remain.
- Hidden series retain aligned timestamp/value arrays for correct shared
  inspection. Known absent/zero series are suppressed in the legend. A width-only
  ResizeObserver uses the public chart update API: this avoids the bundled
  ApexCharts parent-height redraw clearing tooltips, while retaining responsive
  HA section/sidebar widths. Touch inspection and zoom/reset remain read-only.
- A fractional EV completion interval clipped at the current display time cannot
  locate all non-EV flows precisely. Its remaining EV energy is shown independently
  and the whole-site allocation stays unknown until replanning; completed charging
  is not shown as future use. No physical dispatch is recomputed for the display.
- Invented-data tests cover AC balance, gross flows, multiple modes, interval/SOC
  clipping, true EV stops, component readiness, old/stale payloads, coverage,
  fallback, missing solar propagation, DST/fractional zones, chart JavaScript,
  native templates, placement and read-only behavior.
- A local standalone Chromium harness loaded the actual ApexCharts Card 2.2.3
  bundle with invented HA state. Desktop and 390-pixel touch layouts, stable shared
  tooltips, magnitudes/labels, zoom/reset, light/dark rendering, section resizing,
  and a Kathmandu browser with Chicago HA time in both timezone-profile modes
  passed without console errors or horizontal page overflow. This is not a live
  HA deployment or a test of physical equipment. Native templates were rendered
  with HA in tests; a full installed-dashboard walkthrough remains a PR review step.
- Local projection measurement: about 2 ms and 15 KB for an invented 25-row mixed
  equipment example. No new runtime/browser dependency, stored history, setting,
  notification, permission or version change is introduced.

Final local checks: **645 tests passed**; Ruff F checks, `pip check`, privacy/history
(0 findings), generated UI/brand reproducibility and whitespace checks passed.

The dependency audit remains blocked on upstream HA-managed Pillow/uv packages;
see `docs/review.md`. Hosted Hassfest/HACS validation and PR CI have not been run
from the initial local implementation session. No release is published. Private
deployment/recovery records stay outside this repository.

## 9. Readability follow-up — independent household and charging scales

The original shared, signed stack let EV and grid-battery charging peaks flatten
smaller flows. Replace that presentation with two compact, unstacked panels:

- **Household flows · next 24 hours:** house demand, solar generation, battery
  supply, grid export and curtailment as positive-kWh lines.
- **Charging & grid import · next 24 hours:** EV and battery charging as separate
  positive-kWh bars, with total grid imports as a line. Total imports overlap with
  charging and must never be added to those bars.

Each panel has an independent linear, zero-based kWh axis with 10% headroom.
There is no clipping, log transform, negative-energy display or inferred allocation
of EV/solar/grid energy. The full hourly projection, precise tooltip dates, gross
flow totals, charging sources and action details remain unchanged. The charts are
flow comparisons, not complete stacked balance diagrams. Battery supply and
curtailment use dashed lines to distinguish overlapping flows.

All settings, learning, planner decisions and writer permissions remain unchanged.
No new setting, resource or dependency is introduced. The generated guides explain
the two scales and why heights between panels must not be compared directly.
Local verification: **652 tests pass**, including executable peak/headroom/source-
preservation regressions. Actual-card Chromium checks cover desktop/mobile/narrow
layouts, independent scales under an invented 50 kWh peak, exact wrapped tooltips,
both panels' hover/touch and zoom/reset, resizing, and HA/browser timezone choices.
