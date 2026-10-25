# Feature guide and development history

This is the feature index for the **current source**, from the original planner
through the subsequent setup, learning, safety, advice and pricing work. Each row
links to the guide that explains how to use the feature and its limits. The
[settings reference](settings.md) lists every catalogue default, mapping role,
control-state name and script-adapter role.

## Which features are in my installation?

The latest numbered release is **0.3.0**, including the released features indexed below.
The explicitly inactive development foundation described later is not in that release.
Work merged after a release is **unreleased development** until the next release
is published, even if its source manifest still has the previous version.
Documentation on GitHub's main branch can therefore describe features not present
in an older HACS installation following stable releases. The handbook shipped
inside an installation belongs to the component files installed there; it is
generic help, not a detection of that home's configuration.

Use the release notes and installation source to identify the installed feature
set; a version number alone cannot distinguish a manually installed development
snapshot with the same manifest version. A merge does not publish a release or
update another installation automatically. See [updates](installation.md#updates-and-removal).

## Installation, setup and dashboards

| Feature | What it provides and where to learn more |
|---|---|
| Manual and HACS custom-repository installation | Install the integration without a separate NRG account. Dashboard packages are optional and registered separately. [Installation](installation.md). |
| Independent optional components | Grid-only advice, or any combination of one EV, one home-battery system and solar. Monitoring, device-control permissions and Observation/Control are separate. Hidden device choices are retained. [Overview](README.md#the-three-ideas-that-make-setup-easier). |
| Native setup forms and entities | Configure components, operation, prices, periods, meters, forecast sources, controls, notifications and assumptions without the dashboards. Defaults/ranges and structured configuration are in [Every setting](settings.md). |
| Read-only homeowner dashboard | Home Energy and Why? explain current prices, advice, measured equipment status, coverage and the modeled timeline. Equipment cards follow the selected components. [Read the dashboard](homeowner-guide.md). |
| Administrator settings dashboard | A distinct settings sidebar icon, separate Operation and Price-data fallback pages, readiness/guard diagnostics, sources, learning and cost details. [Navigation](README.md#where-to-go-in-home-assistant). |
| Live power-flow Sankey | Uses the actual power meters configured for HA Energy, never a fabricated planner flow. [Power flow](homeowner-guide.md#current-power-flow-the-sankey-diagram). |
| Direct local handbook | Accessible from both dashboards, with responsive tables, browser Find/Print, no scripts/external assets and content-versioned links. [Handbook access](installation.md#optional-dashboards). |

## Electricity pricing and resilience

| Feature | What it provides and where to learn more |
|---|---|
| Independent supply and delivery | Flat, timed or external pricing for each component; explicit unset versus zero and signed negative rates. Inputs use cents/kWh; USD/kWh sensors support HA Energy. [Pricing](pricing.md#the-prominent-buying-price). |
| Time-of-use period editor | Add/edit/remove periods, an optional blank-rate four-period template, starting weekdays, overnight periods, exact boundaries and DST behavior. Overlaps are rejected and gaps remain unknown. [Period editor](pricing.md#editing-timed-periods-in-ha). |
| External price entities and forecasts | Separate current/forecast mappings, supported interval aliases and currency units, configurable attribute names and validation. No ComEd substitution for another provider's missing prices. [External pricing](pricing.md#external-utility-price-integrations). |
| Separate export compensation and permission | No credit, flat credit or supply plus an adder; export permission does not schedule a forced battery sale or reconstruct credit banks. [Export compensation](pricing.md#export-compensation). |
| ComEd live, published and tentative prices | Current-hour running average, dated published forecasts and locally recorded tentative estimates are distinct sources. Old HTTP-success responses do not become fresh observations. [Sources and freshness](pricing.md#comed-price-sources-and-freshness). |
| New-hour publication bridge | Under Strict live pricing, a valid exact-hour forecast can bridge the first ten minutes. Prior-hour live values are never relabeled, and forecasts cannot release an existing outage. [Publication window](pricing.md#comeds-new-hour-publication-window). |
| Opt-in brief published estimates | Up to 60 minutes from the last verified live observation, with Degraded status, a fixed persistent deadline, continued EV planning and blocked battery grid charging. Refreshes/restarts cannot renew it. [Brief delays](pricing.md#brief-comed-live-data-delays). |
| Guarded price-data fallback | Standard protection or guided custom EV/battery actions; manual start/end requests; higher native reserve retention, export limits, per-device results and separate alerts. [Fallback actions](operations.md#price-data-fallback). |
| Stable automatic recovery | Distinct fresh observations over at least two minutes plus a fresh plan. Manual requests and automatic outage latches survive restarts; forecasts alone cannot release them. [Detection and recovery](operations.md#detection-and-recovery). |

## EV and home-battery planning

| Feature | What it provides and where to learn more |
|---|---|
| EV departure planning | Cheapest, solar-aware, earliest/latest and previous feasible schedules; normal window, completion buffer, stable-current bounds and fractional final intervals. The selected vehicle limit is read-only. [EV candidates](design.md#ev-candidates). |
| EV overrides and sleeping-vehicle support | Charge now, persistent one-off departure, overdue-session handling, separate observed/planned status, and opt-in saved readings while connected. [Everyday controls](operations.md#everyday-controls) and [measurement freshness](integrations.md#provider-neutral-measurements). |
| Supported battery modes | Hold, serve home and supported grid charging; capacity/age, reserve, conversion losses, optional cycling cost, native charge capability and whether hold accepts solar. No unsupported grid refill or forced exports. [Battery search](design.md#battery-search). |
| EV/battery coordination | No simultaneous planned grid charging of both; Preserve battery during EV charging also applies to fallback. Commands/readbacks do not guarantee instantaneous power response. [Battery search](design.md#battery-search) and [handover](operations.md#transfer-equipment-control). |
| Observation battery trajectory | A proposed battery line can be shown without live control, while missing SOC, controls or selected guards produce a specific blocker rather than an invented flat line. [Battery chart](homeowner-guide.md#modeled-energy-plan-the-battery-line). |
| Provider-neutral controls | Compatible HA numbers, selects and switches; optional scripts with mapped feedback; charge/hold capability checks; reserve/export options and protection/ownership guards. [Adapters](integrations.md#direct-controls-and-option-names) and [script variables](integrations.md#script-adapters). |
| Guarded execution and stale-plan revocation | Dated plan intervals, ownership/revision/permission checks, current target/reserve/readiness checks, readbacks, independent EV/battery error handling and revoked charging grants when plans expire. [Execution](design.md#household-advice-and-execution). |

## Learning, forecasts and measurement quality

| Feature | What it provides and where to learn more |
|---|---|
| Meter normalization and quality | W/kW conversion, grid/battery sign switches, house-only versus whole-home meters, derived site flows, balance checks (including house-only learning) and unknown-versus-absent equipment. [Measurements](integrations.md#provider-neutral-measurements). |
| Forecast.Solar sources and alternatives | Add/edit/remove sources, physical coverage groups, alternative weights, overlap rejection, age correction, cache freshness/retries, known nighttime zero and dawn/dusk completion only when every daylight portion is covered. [Solar sources](integrations.md#solar-forecasts-and-alternatives). |
| Household-demand learning | Covered hours retained around observation gaps without filling missing time, elapsed-time expiry, EV subtraction, recency weighting, weekday/weekend matching and explicit fallback demand. [Demand learning](learning.md#learn-household-demand). |
| Solar forecast calibration | Forecasts frozen before each hour; bounded actual/forecast correction after enough daylight samples, forecast error and source-change reset. [Solar learning](learning.md#solar-forecast-calibration). |
| EV calibration | Covered AC energy/SOC sessions, counter-reset/SOC-reversal rejection and conservative energy-per-point/power-per-amp estimates, with independent configured fallbacks. [EV learning](learning.md#calibrate-ev-charging-estimates). |
| Modeling robustness audit | Per-hour solar coverage/alternatives, explicit zero versus unknown, local-midnight normalization, exact repeated/skipped DST boundaries, device current bounds and independent physical/cost oracles. [Audit evidence and limits](review.md#modeling-and-forecasting-robustness-audit-unreleased). |
| Offline synthetic stress lab | Source-only CLI using the real planner/learners and an independent synthetic plant; seeded stress scenarios, frozen forecast scoring, EV/cost/physical outcomes, fixed-plan advice evaluation and optional decision traces. No HA instance, network, household data or live commands. [Simulation guide](simulation.md). |
| Passive battery calibration | Opt-in AC-side closed-cycle efficiency and sustained charge/discharge opportunities; paired counters, independent per-parameter fallbacks, retention and status. No forced calibration or battery-health claim. [Battery learning](learning.md#calibrate-battery-estimates). |
| Reset and retention | Disabling learning preserves completed summaries; Reset learning retains settings and cost ledgers. Mapping changes reset only the affected calibration/comparisons. [Reset behavior](learning.md#resetting-or-disabling-learning). |

## Advice, accounting and notifications

| Feature | What it provides and where to learn more |
|---|---|
| Reference-appliance advice | Compares a complete task now versus later, with grid/direct-solar/battery/mixed supply and the grid rate shown separately. The green window never operates an appliance. [Recommendations](homeowner-guide.md#the-recommendation). |
| Dependable economic horizon | Cost comparisons stop at the first applicable import/export/solar gap while the longer outlook retains physical energy and EV feasibility. Missing later data cannot make an earlier action free. [Planning method](design.md#battery-search). |
| Feasible refill valuation | Shared solar/grid charging power, supported modes, house/EV demand and losses constrain refill potential. A common conservative value covers insufficient refill; limited confidence suppresses savings notifications. [Valuation](accounting.md#different-money-figures). |
| Observed costs and coverage | Metered purchases minus export credits, signed costs, tariff-boundary splitting, partial-day/restart gaps and 62-day retention. Not a utility bill or proven savings. [Ledger](accounting.md#observed-ledger). |
| End-of-day net-cost forecast | Read-only covered cost so far plus remaining selected purchases minus export credits to local midnight. Published prices take priority; unpublished future ComEd hours use labeled matching-hour or recent published medians, with estimated-hour details and lower confidence. No defensible baseline, other missing coverage or unmodeled equipment still leaves it unknown; partial past coverage remains labeled. No new settings/permissions or changes to control pricing. Available in 0.3.0. [Dashboard forecast](homeowner-guide.md#forecast-net-cost-by-midnight), [tentative pricing](pricing.md#tentative-prices-for-the-end-of-day-cost-forecast) and [accounting](accounting.md#end-of-day-net-cost-forecast). |
| Forecast-priced accounting | Separate coverage, purchase-cost and export-credit subsets for newly tracked published-estimate intervals; exact deadline/hour cutoffs and no learning forecasts as live. [Estimated coverage](accounting.md#observed-ledger). |
| HA Energy price sensors | Independent USD/kWh buying and export entities; buying already includes delivery. NRG does not rewrite Energy configuration/history. [HA Energy](accounting.md#built-in-ha-energy). |
| Two notification types | Stable worthwhile household wait advice and separate fallback-entry/recovery alerts; independent opt-ins, shared notify services/quiet hours, deduplication/cooldown and Observation wording. [Notifications](operations.md#notifications). |

## Privacy, lifecycle and retired behavior

Settings, learning and bounded caches/ledgers stay in HA; reloads and updates retain
them. Integration removal deletes NRG's local store, not HA's separately retained
backups or recorder history. The diagnostics download is an allowlisted summary,
not a dump of rates, entity IDs, plans or household readings. The local handbook
contains generic documentation only. See [privacy](../PRIVACY.md),
[removal](installation.md#updates-and-removal) and [security reporting](../SECURITY.md).

The former **summer peak-import heuristic is retired**. Its saved option/entity
is cleaned up automatically and it no longer constrains charging. Use actual
supply/delivery schedules and configured permissions, not a seasonal switch.
There is no separately calculated capacity-charge saving. See
[the current planning rules](design.md#time-and-prices).

## Unreleased inactive foundation

A pure ComEd five-minute parser and hourly reconstruction model has invented-data
regressions for equal-weight hourly prices, corrections, completeness and DST.
**It is not connected to runtime, persisted history, daily totals, EOD, learning
or controls**, and adds no setting or permission. Provider retention terms and
an authoritative settled-price source remain open review gates. Existing settings,
learning, legacy costs and all safeguards are unchanged. See
[accounting development status](accounting.md#hourly-accounting-development-status).
A separate planner-horizon reproduction documents an unresolved discontinuity;
no optimizer fix or control-policy change is included.

## Development milestones since creation

| Stage | Features and improvements |
|---|---|
| Original implementation through **0.1.0** | Optional components; independent tariffs/export and period editor; external/ComEd/solar adapters; EV/battery planning; local learning; cost ledger; guarded provider-neutral controls; homeowner/admin dashboards and a complete local wiki. Setup/readiness explanations, private-store removal cleanup and retirement of the summer heuristic were included before 0.1.0. Publication/privacy checks and release-based updates were established. |
| **0.2.0** | Passive battery efficiency/charge/discharge calibration with independent fallbacks and AC-meter safeguards. Direct handbook buttons and a distinctive settings icon were also included by this release. |
| **0.3.0** | Guided price-data fallback and alerts; pricing-health cards hidden when no warning/request exists; dependable-horizon advice and feasible/common battery-refill valuation; bounded new-hour publication bridge; opt-in brief published estimates with persistent limits and separately tracked forecast-priced costs; modeling/forecasting robustness fixes and permanent independent-oracle regressions; offline seeded simulation of forecasts, learning and decision outcomes against independent synthetic physics; read-only end-of-day net-cost forecast with local-midnight and coverage safeguards, astronomical completion of covered dawn/dusk edges, input-specific gap explanations and clearly tentative estimates for unpublished ComEd hours, separate from control prices. |

The detailed verification evidence and open upstream dependency-audit findings are
in [the project review](review.md). Passing tests are not proof of globally optimal
plans, future savings or instantaneous physical device response. See
[scope and limitations](design.md#scope-and-objective) and [alternatives](alternatives.md).
