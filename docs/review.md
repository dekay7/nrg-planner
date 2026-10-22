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
Assistant 2026.10.2 with **395 passing tests**. Invented regressions cover delayed
HTTP-success responses, the fixed 60-minute cutoff, exact-hour/expired/future
forecast coverage, cold starts, clock rollback, source changes, restart persistence,
manual/missing-delivery precedence, and distinct fresh live recovery. Planner and
command-time tests block estimated-price battery grid charging, preserve higher
native reserves and protection/permission guards, cap export permission and script
context, and keep EV departure planning available. Ledger tests distinguish signed
forecast-priced costs/credits and stop accounting at the exact estimate deadline.
Native options/select and real HA dashboard-template checks cover the UI.

Review hardened two boundaries: an expired allowance cannot be renewed by the
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
