# Private review and publication gates

This repository is deliberately private. Keep it private until the owner has
reviewed the candidate contents and explicitly chooses to publish it. Adding HACS
metadata is preparation, not publication or default-catalog approval.

## What to review

- [Privacy policy](../PRIVACY.md) and the exact tracked file list (`git ls-files`).
- [Security reporting policy](../SECURITY.md), repository security settings, and dependency-update automation.
- Fresh Git history and author/committer metadata (`git log --format=fuller`).
- Unset tariff fields and the absence of a bundled historical price profile.
- Generic examples, tests, dashboard YAML, generated HTML, and translations.
- Bounded local learning and the allowlisted diagnostic download.
- Optional device controls and the documented installation/update behavior.
- [Alternatives](alternatives.md) and the current limitations stated in the README.

## Automated checks

```sh
python -B tools/check_privacy.py --history
python -B -m pytest -q
python -B -m ruff check . --select F
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

The GitHub workflow runs tests, asset reproducibility, privacy/history checks, and
Hassfest while private. HACS repository validation is explicitly deferred while
private because HACS requires public repositories. Its job runs after publication;
skipped validation is not a passing HACS compatibility claim.

## Verification record — 2026-10-20

Reviewed `main` at `7cef5ec` and the accompanying local removal-cleanup changes,
using a fresh development environment with Python 3.14.8, Home Assistant
2026.10.2, and Node.js 22.23.1.

| Check | Result |
| --- | --- |
| Automated suite | 125 tests pass, including native setup, option edits, reload, command adapters, control guards, tariffs, forecasts, accounting, diagnostics, and executable chart code. |
| Lifecycle checks added during review | Reload preserves learning and ledgers without resuming charge-now. Removing either a loaded or unloaded entry deletes NRG storage and entities. |
| Handbook HTTP check | The bundled HTML is served correctly; configuration, storage, and parent-directory requests are rejected. |
| Fresh dependencies | Installation and `pip check` pass; `pip-audit` reports no known vulnerabilities. |
| Static checks | Ruff's configured `F` rules, Bandit on integration code, Actionlint, and `git diff --check` pass. |
| Publication privacy | The project checker finds no issues across 180 working-tree, staged, and historical file revisions after fetching all remote branches and tags. Gitleaks finds no secrets in the working tree or the nine reachable commits. |
| Bundled assets | UI and brand builders reproduce their output deterministically. |
| Optional public pricing | Live ComEd requests return a valid 24-row forecast and a fresh, valid current-hour price response. |

The review fixed retained private storage after integration removal and added
regression coverage. Reloads and updates still retain installation data.

[GitHub validation for the reviewed base commit](https://github.com/dekay7/nrg-planner/actions/runs/39473337612)
passes tests/privacy, dependency auditing, reproducibility, and Hassfest. Local
changes need the same CI checks after they are committed. All four open Dependabot
updates also have passing tests/privacy and Hassfest checks. GitHub dependency
alerts and automated security fixes are enabled; there are no open dependency
vulnerability alerts at review time.

**Remaining release evidence:** physical EV/battery behavior, a real HA restart
and component-file update, and browser/mobile dashboard installation have not been
verified by this automated review. HACS validation is skipped while private.
Private vulnerability reporting could not be verified through the repository API,
and branch protection/rulesets are unavailable on the current private-repository
plan. Verify and configure those settings after publication as described below.
The README and bundled handbook still accurately identify the project as a
private-review snapshot. These results support the source review; they do not
establish completion of every publication gate.

## Before an eventual public release

1. Complete the owner's manual privacy/source review, including generated assets.
2. Test a fresh HA installation, restart, update, removal, optional dashboard setup,
   and appropriate equipment behavior on independently configured installations.
3. Recheck history and release contents for identifiers, secrets, and data files.
4. Update the private-review status text only after the owner decides to publish.
5. Verify the configured Dependabot alerts/updates and SHA-pinned Actions.
6. Make the reviewed repository public only on the owner's explicit instruction.
7. Immediately enable GitHub private vulnerability reporting, configure required CI
   checks on `main` (branch protection is unavailable on this private repository's
   current GitHub plan), and verify those settings.
8. Pass HACS validation and Hassfest without ignored checks, then create a full
   GitHub release. Submit to the default catalog separately if desired.

No workflow automatically changes repository visibility, creates a release, or
deploys to a household's Home Assistant instance.
