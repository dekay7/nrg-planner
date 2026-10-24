# Project review and release readiness

This page records verification evidence, open findings, and the release process.
HACS metadata describes the installation layout; passing HACS validation and
default-catalog inclusion are separate results that must be verified.

## What to review

- [Privacy policy](../PRIVACY.md) and the exact tracked file list (`git ls-files`).
- [Security reporting policy](../SECURITY.md), repository security settings, and dependency-update automation.
- All reachable Git history, including author/committer names and no-reply email addresses.
- Unset tariff fields and the absence of a bundled historical price profile.
- Generic examples, tests, dashboard YAML, generated HTML, and translations.
- Bounded local learning and the allowlisted diagnostic download.
- Optional device controls and the documented installation/update behavior.
- [Alternatives](alternatives.md) and the current limitations stated in the README.
- GitHub issues, pull requests, comments, releases, and uploaded artifacts as well as source files.

## Automated checks

```sh
python -B tools/check_privacy.py --history
python -B -m pytest -q
python -B -m ruff check . --select F
python -B -m pip check
python -B -m pip_audit --progress-spinner off
python -B tools/build_ui.py
python -B tools/build_brand.py
git diff --check
git diff --exit-code
```

Builders should reproduce committed assets without changing them. Review untracked
files too; `git diff` alone does not show those. Optional local-only private
indicators can be passed to the privacy checker with `--deny-file PATH`; keep that
file outside this repository.

The GitHub workflow runs tests, asset reproducibility, privacy/history checks,
dependency auditing, and Hassfest. Dependency auditing is an independent job so
that an advisory does not prevent tests and privacy checks from running; an audit
finding still fails validation. HACS validation runs for public repositories,
including on GitHub's visibility-change event. A skipped job is not a passing
HACS result.

## Verification record — 2026-10-20

Reviewed `main` at `cfcc7a0` and the accompanying publication-preparation changes
with Python 3.14.8, Home Assistant 2026.10.2, and Node.js 22.23.1. The owner approved
retaining existing real-name commit attribution. Email addresses in reachable
commit metadata use GitHub no-reply addresses.

| Check | Result |
| --- | --- |
| Automated suite | 129 tests pass, including native setup, option edits, reload/removal, command adapters, control guards, tariffs, forecasts, accounting, diagnostics, handbook HTTP boundaries, and executable chart code. |
| Publication privacy | The project checker passes for the working tree, index, and all fetched branches, tags, and pull-request heads. Household-specific indicators appear only in the owner-approved commit names. Gitleaks finds no secrets in the working tree or reachable history. |
| Hosted content | During publication review, repository description, issue/pull-request bodies, comments, and all 56 existing Actions run logs passed the identifier/secret checks. Generic GitHub runner/Dependabot paths and timestamp fragments were excluded from log privacy findings. No GitHub releases or Actions artifacts were present at that point. |
| Dependencies | `pip check` passes. **`pip-audit` fails: nine known advisories in two dependencies pinned by Home Assistant 2026.10.2.** See the open finding below. |
| Static checks | Ruff's configured `F` rules, Bandit on integration code, Actionlint, and `git diff --check` pass. |
| Bundled assets | The handbook and dashboards are regenerated from their sources; UI and brand builders reproduce their output deterministically. |
| Publication-preparation CI | At `c3c5122`, tests/privacy, asset reproducibility, and Hassfest pass. The independent dependency-audit job reports the upstream findings below. |
| Live checks | The owner reports that the live installation/lifecycle, browser/mobile dashboard, and physical equipment checks worked successfully. This is owner-reported validation on the owner's installation. |
| Repository metadata | MIT license, repository description/topics, enabled issue tracker, integration manifest, HACS manifest, and bundled brand icon are present. |
| Repository security | Dependabot alerts, automated security fixes, SHA-pinned Actions, and read-only default workflow permissions are enabled. No open Dependabot alerts were returned; this does not override the failing local/CI audit. |
| HACS | Public-repository validation at `5212fbf` passes. Custom-repository installation instructions are provided. The owner deferred HACS setup and default-catalog submission; an end-to-end HACS installation is not claimed as tested. |

[GitHub validation for the publication-preparation commit](https://github.com/dekay7/nrg-planner/actions/runs/39514726446)
records the passing tests/privacy and Hassfest jobs and the dependency-audit
failure. This record does not claim that all checks pass.

### Open dependency finding

Home Assistant 2026.10.2 pins:

- **Pillow 12.3.0:** CVE-2026-112895, CVE-2026-112400, CVE-2026-112397,
  CVE-2026-112896, CVE-2026-112897, CVE-2026-112395, CVE-2026-112404, and
  CVE-2026-112899. The audit lists **13.0.0** as the fixed version.
- **uv 0.12.23:** PYSEC-2026-4321. The audit lists **0.13.4** as the fixed version.

Home Assistant 2026.10.2 is the latest published stable HA version at review time.
The integration declares no additional runtime dependencies, but its development
environment installs HA's pinned packages, and the host HA installation manages
its own runtime dependencies. These findings remain open: no advisories are
ignored, and no incompatible overrides are added to HA's exact requirements.

When a compatible upstream HA release resolves these findings, update the tested
version and rerun dependency resolution, the full suite, and the audit. Recheck
the documented minimum HA version and `hacs.json` if the supported baseline changes.

## Advice correctness verification — 2026-10-22

The dependable-horizon fix is verified locally with Python 3.14.8 and Home Assistant
2026.10.2: **307 tests pass**, including invented missing-export-price regressions,
baseline-mode/score invariance beyond coverage gaps, storage losses and wear,
explicit zero credit, prohibited exports, battery constraints, EV feasibility,
DST durations, notification confidence and real HA dashboard-template rendering.
The original planner reproduces a falsely free evening window on the invented
regression; the corrected planner does not. Ruff's configured `F` checks, dependency
consistency, privacy/history checks and deterministic UI/brand builds pass.
Hosted validation results remain recorded on the pull request; local verification
is not a claim of live equipment validation or deployment.

A fresh isolated audit now reports **25 advisories: 24 for Pillow 12.3.0 and one
for uv 0.12.23**. These are the same HA-pinned packages described in the open
finding above, with additional published Pillow advisories. The reported fixed
versions remain Pillow 13.0.0 and uv 0.13.4. This fix changes no dependency pins,
adds no advisory exclusions and does not resolve that upstream finding. An audit
failure remains visible rather than being reported as a fully green validation.

## Refill-capability hardening verification — 2026-10-22

The follow-up hardening has **334 passing tests** on the same Python/HA baseline.
It reproduces the former unsupported-grid-refill valuation and verifies the fix,
EV demand subtraction and grid-charge exclusion, hold/solar behavior, fallback,
availability, reserve/capacity/losses, shared candidate/advice valuation, actual
notification suppression and native HA charge-mode capability detection. Permanent
invariant checks cross-check refill accounting against physical transitions over
64 permission/mode combinations and test 300 randomized permission restrictions.

An additional deterministic invented-only stress audit passes 2,000 scenarios,
28,324 physical intervals, 9,632 appliance windows, 2,000 untrusted-tail mutations,
1,251 independent grid-only cost comparisons and 16 fallback combinations. Ruff,
privacy/history, dependency consistency and reproducible generated assets pass.
The dependency audit still reports the same **25 HA-pinned Pillow/uv advisories**
above; requirements and advisory handling are unchanged. Hosted results are recorded
on the pull request. These checks do not claim globally optimal schedules, promised
chronological refills or verified physical equipment response.

## ComEd publication-gap verification — 2026-10-22

The bounded new-hour forecast bridge is verified locally on the current mainline
with Python 3.14.8 and Home Assistant 2026.10.2: **355 tests pass**. Invented
regressions cover uninterrupted hourly handover, the exact ten-minute cutoff,
missing/expired forecasts, missing delivery prices, manual and automatic fallback,
distinct live recovery observations, transport failures, DST transitions, price
provenance, and cost coverage without learning forecasts as live observations.
Observation defaults, control permissions, settings and learning formats are unchanged.
The generated handbook/dashboards, Ruff checks, dependency consistency and
privacy/history checks pass; generated assets reproduce deterministically.

The dependency audit still reports the **25 existing HA-pinned Pillow/uv
advisories** documented above. This change adds no dependency overrides or audit
exclusions. Hosted CI and the code review are recorded on the pull request;
local verification does not claim live deployment or physical equipment validation.

## Bounded ComEd estimate verification — 2026-10-22

The opt-in brief-delay policy is verified locally on Python 3.14.8 and Home
Assistant 2026.10.2 with **396 passing tests**. Invented regressions cover delayed
HTTP-success responses, the fixed 60-minute cutoff, exact-hour/expired/future
forecast coverage, cold starts, clock rollback, source changes, restart persistence,
manual/missing-delivery precedence, and distinct fresh live recovery. Planner and
command-time tests block estimated-price battery grid charging, preserve higher
native reserves and protection/permission guards, cap export permission and script
context, and keep EV departure planning available. Ledger tests distinguish signed
forecast-priced costs/credits and stop accounting at the exact estimate deadline
or hour boundary, never carrying the prior hour's estimate into a new hour.
Native options/select and real HA dashboard-template checks cover the UI.

An additional invented-only timestamp/freshness stress audit passes 10,000 cases.
Review hardened the boundaries: an expired allowance cannot be renewed by the
next hour's publication bridge, and a saved automatic outage latch prevents a
restart from treating a forecast as live recovery evidence. Other supply plans
ignore the saved ComEd option. Existing settings, learning, ledgers, Observation
defaults and explicit control permissions are preserved. Strict live pricing
remains the default; the new policy requires an explicit opt-in.

Ruff, privacy/history, dependency consistency and deterministic generated assets
pass. The dependency audit now reports **36 advisories: 35 for Pillow 12.3.0 and
one for uv 0.12.23**, the same HA-managed packages in the open finding above.
No requirements or audit exclusions change. Hosted CI and the self-review are
recorded on the pull request; this local record is not a claim of independent
review, live deployment, or verified physical equipment response. No release is
published by this change.

## Full feature documentation audit — 2026-10-22

Audited the original implementation and each subsequent feature/behavior change
through the bounded-estimate work against the current source and user guides.
The [feature guide](features.md) now indexes the complete feature areas and
separates original/0.1.0, 0.2.0 and unreleased development. It explicitly marks the
summer charging heuristic as retired. Removed its stale active-feature claims,
replaced the dated provider-availability banner with durable pricing guidance,
and aligned homeowner/setup/FAQ/troubleshooting, pricing, notification, script,
privacy, accounting and update instructions with current behavior.

The generated settings reference covers all **56 catalogue settings, 28 mapping
roles, 10 control-state examples and eight command-script roles**, plus structured
period/source/departure/notification choices. All documentation chapters are
bundled into the local handbook. New regression checks verify chapter inclusion,
source-derived defaults/help, mapping/control/script coverage, Markdown link
fragments, original/new feature entry points, and release/retirement clarity.

**427 tests pass** on Python 3.14.8 / HA 2026.10.2, including 31 new documentation
checks. Ruff, privacy/history, dependency consistency, local links and generated
asset reproduction pass. The unchanged HA-pinned dependency audit still reports
**36 Pillow/uv advisories** as detailed above; none is suppressed. This audit adds
no pricing, planning, control, storage, dependency or version behavior change.
Hosted CI/self-review are recorded on its PR; no new release is published.

## Modeling and forecasting robustness audit — unreleased

Reviewed the modeling/forecasting pipeline, its measurement boundaries and its
existing tests. This is a local source-and-test audit of unreleased development,
not an independent review, a deployment or an empirical forecast-accuracy study.
Observation defaults, explicit control permissions, manual settings, completed
valid learning and ledger formats remain unchanged. No release is published.

### Algorithm inventory and coverage

| Area | Implementation and verification |
| --- | --- |
| Input normalization and measurement quality | `config.py`, `runtime.py`: finite/unit/sign/range checks, unknown versus absent hardware, independent site balance, house-only and EV subtraction, device current bounds. Native HA regressions cover these boundaries. |
| Tariff and price forecasts | `tariffs.py`, `forecast.py`, `fallback.py`: independent supply/delivery/export, overnight schedules, explicit dated external intervals, ComEd labels/freshness/publication allowances, recovery and provenance. Existing pricing/fallback suites plus new second-by-second DST oracles pass. |
| Solar forecast modeling | `forecast.py`: trapezoidal power integration, local-day normalization, cache expiry, alternative weighting versus distinct arrays, age adjustment, explicitly covered hours, known astronomical night. New missing/zero/malformed/gapped and non-whole-hour timezone regressions pass. |
| Household demand and solar bias | `statistics.py`: previous-sample integration, 80% hourly coverage, EV exclusion, elapsed-time retention, recency/day-type demand estimates, frozen-before-hour solar residuals and bounded correction. Gap/retention regressions and existing no-hindsight tests pass. |
| EV energy, power and schedules | `statistics.py`, `planner.py`: conservative session percentiles, invalid-session rejection, deadlines/buffers/windows, four candidate allocations, prior-plan stability, fractional stops and observed-only charging. New independent feasibility checks cover 200 randomized cases across all four allocation strategies. |
| Passive battery calibration | `battery_learning.py`: closed SOC cycles, paired counters or AC power integration, sustained independent opportunities, outlier rejection, per-parameter minimum samples, 30-day expiry and manual fallbacks. The full existing cycle/opportunity/native HA suite passes; no calibration formula is changed. |
| Battery capacity and dispatch | `config.py`, `planner.py`: compounded age, square-root losses, capacity/reserve/power constraints, mode permissions, bounded-bin search and no fictional battery sales. New checks cover 1,200 randomized physical transitions and 80 short searches against exhaustive feasible-mode oracles. |
| Refill valuation and household advice | `planner.py`: common candidate/advice value, permitted finite refill, conservative uncovered reference, trusted contiguous horizon and incremental replay. Existing permission/tail-invariance suites pass; 100 randomized grid-only appliance scenarios match an independent overlap-cost oracle. |
| Measured accounting and execution boundary | `statistics.py`, `runtime.py`, `control.py`: signed variable costs, exact tariff/estimate/hour boundaries, unobserved gaps, stale-plan revocation and guarded writer. New repeated-hour ledger regressions and the existing control/integration suites pass. |

### Confirmed findings and corrections

- **Unknown solar was being reported as zero.** A cache's daily date no longer
  establishes coverage for every hour. Alternatives are selected per covered hour;
  uncovered arrays remain unknown. Missing applicable solar also leaves an
  interval's displayed modeled cost unknown, even with known prices.
- **Broken solar shapes could concentrate a daily total into surviving hours.**
  Long daytime gaps are rejected. Malformed containers, duplicate instants and
  implausible daily totals produce handled validation errors; a failed refresh
  retains only the original, still-fresh cache. Partial edge hours are excluded
  rather than treated as complete coverage. Astronomical darkness remains the
  only basis for filling missing night with zero.
- **Explicit zero solar could disappear.** Covered all-zero series with zero
  energy now remain valid zero forecasts rather than returning an empty series.
- **Normalization crossed local midnight incorrectly in fractional-hour zones.**
  Integration now splits at local midnight before applying each day's energy
  normalization; complete UTC bins can contain contributions from both days.
- **Solar weight validation was inconsistent.** Scope/duplicate/finite-positive
  weight validation is shared by settings and aggregation. Relative-weight scaling
  avoids overflow without changing the weighted-average interpretation.
- **DST intervals missed repeated boundaries and clock jumps.** Tariff and EV
  windows now split at both real occurrences, as well as the offset change itself.
  This fixes exact ledger pricing and window availability for non-quarter-hour,
  skipped and half-hour transitions. Daily departure retains its documented first-
  occurrence / spring-forward resolution.
- **EV sessions could hide intermediate counter resets or SOC reversals.** Either
  decrease now breaks the candidate even when later totals recover. Valid completed
  observations and the conservative percentile formulas are retained.
- **Hourly learning retained stale history and lost valid covered portions.**
  Old summaries expire after 28 elapsed days, including after downtime. Covered
  portions around an observation gap can still qualify at 80%; missing time adds
  neither coverage nor energy. Unfinished EV/battery sessions still break at gaps,
  and restarts still discard unfinished in-memory observations.
- **House-only learning bypassed the site-balance gate.** Inconsistent independent
  site meters now pause that profile just as they pause whole-home/EV learning.
- **EV predictions ignored the device current floor.** Planning now intersects
  configured/device minimum and maximum in whole amps, scaling fallback power to
  the effective ceiling. Unsupported ranges fail readiness; user values are not
  rewritten and command-time bounds are still independently checked.

### Verification and remaining limits

The baseline suite passed **427 tests**. The new permanent audit module adds
**39 cases**: when run against an isolated copy of the original commit, **30 fail
and nine pass**; against the corrected implementation all pass. The full suite
passes **466 tests**, including native HA integration and executable chart tests.
The deterministic randomized checks use invented fixtures and fixed seeds, not
household traces. They check feasibility/accounting and independent oracles, not
just snapshots of the implementation's output.

Ruff's configured `F` rules, dependency consistency, privacy/history checks,
generated UI/brand reproducibility and whitespace checks pass. The dependency
audit still fails on the same **36 HA-pinned Pillow/uv advisories** documented
above. No dependency override or advisory exclusion is introduced.

Remaining limits are explicit: battery binning and the small EV candidate set
are approximate, not globally optimal. Solar power is interpolated between valid
provider points; hourly demand and bounded calibration do not predict weather or
unusual household behavior. Conservative partial solar-edge coverage can shorten
advice, including near sunrise/sunset, while EV deadline feasibility remains
available. Sample-based calibration depends on AC measurement boundaries, coverage
and SOC precision; it is not a health/capacity measurement. Refill potential is not
a promise of a chronological refill. No real-home forecast backtest, future saving,
physical command response or live deployment was validated by this audit.

## Offline synthetic simulation verification (unreleased)

The [source-only simulation tool](simulation.md) exercises the production planner
and coverage-gated learners without importing Home Assistant or invoking its
runtime/writer. A separate AC plant realizes decisions under invented actuals;
forecasts use independent seeded streams, with future predictions frozen before
scoring. It reports missing coverage, forecast error, EV departure shortfalls,
final stored energy, physical/request invariants and fixed-plan advice outcomes.
It is not a real-house backtest, global-optimum benchmark or live-control test.

Local verification on Python 3.14.8 and HA 2026.10.2 passes **485 tests**, including
18 simulator regressions and standard-library-only execution outside the checkout.
A sweep of all **12 scenarios**, seed 1, one evaluation day and one synthetic
training day completes with no physical/request invariant violations. A separate
uncalibrated slow-charger regression deliberately misses departure, demonstrating
that completion failures are reported rather than masked by modeled feasibility.
Tests also cover reproducibility, unknown forecast coverage/recovery, partial EV
stops, independent energy/cost calculations, DST instants, training restart/session
boundaries and post-hoc advice isolation.

Ruff's configured `F` rules, dependency consistency, privacy/history and whitespace
checks pass. Handbook/dashboard assets are regenerated with the standard builder.
The dependency audit still fails on the **36 existing HA-pinned Pillow/uv
advisories** above; the simulator adds no dependency, override or audit exclusion.
No installation settings, learning formats, control defaults or version values
change, and no release or live deployment is performed.

## End-of-day net-cost forecast verification — unreleased

Local verification on Python 3.14.8 / HA 2026.10.2 passes **514 tests**. New
invented regressions cover observed-plus-remaining cash accounting, exclusion of
comparison scores and tomorrow's costs, interval clipping, signed export credits,
23/25-hour DST days, partial history, missing future coverage, unmodeled equipment,
automatic data recovery, native sensor registration/stale-plan revocation and
read-only dashboard placement immediately below the observed net cost.

Ruff, privacy/history, dependency consistency, whitespace and deterministic UI/brand
build checks pass. The dependency audit reports **38 advisories: 37 for Pillow
12.3.0 and one for uv 0.12.23**, the same HA-managed packages in the open finding.
No dependency pins or advisory exclusions change. Existing settings, learning,
ledgers, Observation defaults and control permissions are preserved. No release,
live deployment or physical equipment validation is claimed.

## Solar dawn/dusk coverage correction — unreleased

Local verification on Python 3.14.8 / HA 2026.10.2 passes **535 tests**, including
21 new invented dawn/dusk regressions. The parser can merge provider-covered
portions with HA astronomical darkness before deciding whether an edge hour is
complete. It retains normalized partial-hour energy without scaling it to an hour
or counting overlapping night coverage twice. End-to-end cash accounting now
reaches midnight for a complete daylight forecast; a genuinely missing daylight
edge still waits and names its first missing input/local time.

Tests cover both edges, missing/invalid/polar sun events, internal daytime gaps,
physical arrays versus alternatives, stale caches, fractional-hour timezones, DST,
daily energy conservation and the existing single cached service read. No provider
polling, control permission, manual setting, learning or ledger format is added
or changed. Older caches gain edge coverage only after a successful normal refresh;
failed refreshes retain their original age and cannot manufacture coverage.

Ruff, dependency consistency, privacy/history, whitespace and reproducible bundled
assets pass. The same **38 HA-pinned Pillow/uv advisories** remain open; no package
overrides, workflow changes or audit exclusions are introduced. This record is
source-and-test verification, not a claim of independent review or a release.

## Tentative unpublished ComEd cost forecast — unreleased

Local verification on Python 3.14.8 / HA 2026.10.2 passes **574 tests**. The
read-only EOD cash projection now prices unpublished future ComEd hours with a
recorded matching-hour median or a recent published-price median, after selecting
all equipment actions. Separate cash-projection fields leave ordinary tariffs,
slot costs, economic coverage, advice and control guards unchanged. Sensor
attributes and both generated dashboards identify estimated hours/rates/sources
and tentative confidence; partial-day omissions remain visible.

Invented regressions cover the morning 23:00–midnight gap, publication handover,
recorded-history precedence, median spike resistance, signed/zero rates,
supply-linked and independent export credits, baseline freshness, unchanged other
tariffs, current live outages without a publication, exact-current-hour published
cash projections beyond control cutoffs, remaining coverage/equipment blockers,
elapsed clipping, DST hours, real HA sensor updates and dashboard-template rendering. A
comparison with forecast repricing disabled verifies identical selected flows,
controls, advice and comparison costs.

Ruff, dependency consistency, privacy/history, whitespace and reproducible UI/brand
build checks pass. The dependency audit still reports the existing **38 advisories
in HA-managed Pillow 12.3.0 / uv 0.12.23**; no dependencies or audit exclusions are
changed. Settings, learning, observed ledgers, Observation defaults and explicit
control permissions are preserved. No version bump or release is made; these
source checks do not claim physical-equipment validation.

## 0.3.0 release-candidate verification — 2026-10-24

The owner requested a new release. Version 0.3.0 batches the feature and correctness
work since 0.2.0; see the [release milestones](features.md#development-milestones-since-creation).
The manifest, runtime version and README agree, and the guides now identify the
0.3.0 feature set. Home Assistant 2026.10.2 remains the minimum/tested baseline;
no runtime dependency, storage version or manual migration is introduced.

Local verification with Python 3.14.8, HA 2026.10.2 and Node.js 22.23.4 passes
**577 tests**. This includes native fresh setup plus invented 0.2.0-format store
restoration in Observation and Control: existing settings, explicit permissions,
completed household/EV/battery learning and observed ledgers survive. New fallback
and ComEd estimate policies retain their conservative defaults. Tests exercise
native HA services and guarded commands, not physical equipment.

The 12-scenario synthetic sweep (seed 1, one evaluation day and one warmup day)
completes without physical/request invariant violations or missed EV departures.
It uses invented inputs and does not establish real-home accuracy or savings.
Ruff, dependency consistency, privacy/history and whitespace checks pass. Bundled
UI/handbook/dashboard and brand assets are rebuilt with the standard builders;
release-candidate CI checks reproducibility, Hassfest and HACS on the candidate.
Hosted results are tracked on [release-preparation PR #18](https://github.com/dekay7/nrg-planner/pull/18);
the final exact-commit validation run is linked from the GitHub release notes.

The dependency audit still fails with **38 advisories: 37 for Pillow 12.3.0 and
one for uv 0.12.23**, both pinned by HA 2026.10.2. Reported fixes remain Pillow
13.0.0 and uv 0.13.4; no override or advisory exclusion is introduced. These are
the existing upstream findings, not a fully green validation.

**Live revalidation and release authorization:** on 2026-10-24, the owner confirmed
successful checks of the current dashboards and live equipment behavior, clearing
the outstanding publication gate for the requested release. This is owner-reported
validation, not independent physical-equipment verification. Final publication
requires the exact-commit hosted checks above; the known upstream dependency
findings remain visible and published tags stay fixed.

## Publication decision — 2026-10-20

The owner confirmed that the live checks worked and explicitly authorized public
source publication. The Home Assistant-pinned dependency findings are accepted as
upstream follow-up, rather than a blocker for publishing this repository. They
remain visible in dependency auditing. Existing real-name commit attribution is
approved for publication; personal email addresses and household data remain
outside the publication contents.

HACS setup is deferred. Users can add the public repository to HACS as a custom
integration using the [installation instructions](installation.md#hacs-custom-repository).
Default-catalog inclusion and a versioned GitHub release are not prerequisites
for this installation path.

## Release baseline — 0.1.0

The owner requested the initial numbered release and a release-based development
workflow. Integration version `0.1.0` is published as GitHub Release `v0.1.0`.
Normal HACS download choices hide the development branch; users following stable
releases receive update offers for published stable releases, rather than routine
commits. Existing branch installations can select a numbered release once through
HACS Redownload. The upstream dependency findings above remain documented follow-up.

## Maintenance and release follow-up

1. Track upstream HA dependency fixes and rerun the audit when the tested version
   changes. Continue running tests/privacy, reproducibility, and Hassfest on changes.
2. Review source, generated assets, reachable history, and GitHub-hosted contents
   for identifiers, secrets, and household data before future releases.
3. Review GitHub private vulnerability reporting and `main` protection settings
   for the public repository.
4. Review HACS validation results and record an actual custom-repository
   installation when HACS setup is performed. Default-catalog submission is optional.
5. Follow the [release workflow](https://github.com/dekay7/nrg-planner#releases) for
   future versions. Publish only on explicit request, keep version values aligned,
   and retain the tested commit behind every published tag.

No workflow automatically changes repository visibility, creates a release, or
deploys to a household's Home Assistant instance.
