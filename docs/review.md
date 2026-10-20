# Private review and publication gates

This repository is deliberately private. Keep it private until the owner has
reviewed the candidate contents and explicitly chooses to publish it. Adding HACS
metadata is preparation, not publication or default-catalog approval.

## What to review

- [Privacy policy](../PRIVACY.md) and the exact tracked file list (`git ls-files`).
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

## Before an eventual public release

1. Complete the owner's manual privacy/source review, including generated assets.
2. Test a fresh HA installation, restart, update, removal, optional dashboard setup,
   and appropriate equipment behavior on independently configured installations.
3. Recheck history and release contents for identifiers, secrets, and data files.
4. Update the private-review status text only after the owner decides to publish.
5. Make the reviewed repository public only on the owner's explicit instruction.
6. Pass HACS validation and Hassfest without ignored checks, then create a full
   GitHub release. Submit to the default catalog separately if desired.

No workflow automatically changes repository visibility, creates a release, or
deploys to a household's Home Assistant instance.
