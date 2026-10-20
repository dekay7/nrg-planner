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
| Hosted content | Repository description, issue/pull-request bodies, comments, and all 56 existing Actions run logs pass the identifier/secret checks. Generic GitHub runner/Dependabot paths and timestamp fragments were excluded from log privacy findings. No GitHub releases or Actions artifacts are present. |
| Dependencies | `pip check` passes. **`pip-audit` fails: nine known advisories in two dependencies pinned by Home Assistant 2026.10.2.** See the open finding below. |
| Static checks | Ruff's configured `F` rules, Bandit on integration code, Actionlint, and `git diff --check` pass. |
| Bundled assets | The handbook and dashboards are regenerated from their sources; UI and brand builders reproduce their output deterministically. |
| GitHub CI for the reviewed base | Hassfest passes. The combined tests/privacy job fails at dependency auditing before its tests run. The preparation changes separate those jobs so both results remain visible. |
| Repository metadata | MIT license, repository description/topics, enabled issue tracker, integration manifest, HACS manifest, and bundled brand icon are present. |
| Repository security | Dependabot alerts, automated security fixes, SHA-pinned Actions, and read-only default workflow permissions are enabled. No open Dependabot alerts were returned; this does not override the failing local/CI audit. |
| HACS and public security settings | HACS validation is pending a public repository. Private vulnerability reporting could not be verified through the API; branch protection/rulesets require public visibility on the current GitHub plan. |

[GitHub validation for the reviewed base commit](https://github.com/dekay7/nrg-planner/actions/runs/39510895873)
records the dependency failure. Publication-preparation changes also require CI
on their committed revision. This record does not claim that all checks pass.

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

Before declaring validation complete, move the tested HA version to a compatible
upstream release that resolves the findings, then rerun dependency resolution,
the full suite, and the audit. Recheck the documented minimum HA version and
`hacs.json` if the supported baseline changes.

## Publication and release checklist

1. Complete the owner's source/privacy review, including generated assets and
   GitHub-hosted content. Real-name commit attribution was approved for this
   publication review; do not add personal email addresses or household data.
2. Commit and push the reviewed preparation changes. Resolve the dependency finding
   above and require passing `tests-and-privacy`, `dependency-audit`, and `hassfest`
   jobs on the exact candidate revision before declaring it ready.
3. Record fresh HA installation, restart, component-file update, removal, optional
   dashboard/browser/mobile setup, and appropriate physical EV/battery behavior.
   These manual checks are not established by the automated suite; the earlier
   review did not verify them on independently configured installations.
4. Recheck all remote branches, tags, pull-request heads, and release contents for
   identifiers, secrets, and data files. Make the reviewed repository public only
   on the owner's instruction, after the unresolved findings are addressed.
5. Enable GitHub private vulnerability reporting and configure `main` protection
   as soon as public visibility makes those settings available. Require the
   validation jobs, including `hacs` once it has run, and verify the settings.
6. Check the visibility-triggered workflow and pass HACS validation without ignored
   checks. Verify an actual HACS custom-repository installation before claiming
   that installation path has been tested end to end.
7. Create a versioned GitHub release with notes matching the integration's version
   and verification evidence. HACS can use the default branch without a release;
   default-catalog submission is a separate, optional step.

No workflow automatically changes repository visibility, creates a release, or
deploys to a household's Home Assistant instance.
