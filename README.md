# NRG Planner

Home Assistant energy planning with independent supply and delivery tariffs,
optional EV/battery/solar support, and controls mapped to existing HA entities.

**Early development · version 0.2.0.** See the
[project review](docs/review.md) for current validation results and open release
items. NRG Planner is not included in the default HACS catalog.

> **Documentation scope:** this branch includes unreleased work after 0.2.0.
> A stable HACS installation may not contain every feature described here. See
> [the feature guide and development milestones](docs/features.md) for coverage
> from the original planner onward, and [pricing resilience](docs/pricing.md#brief-comed-live-data-delays)
> for current ComEd delay-handling rules—not a live provider-status claim.

## What it does

- Combine flat, time-of-use, or external supply and delivery prices. ComEd hourly
  is an optional supply adapter, not a requirement.
- Configure export compensation separately from import delivery charges.
- Compare EV deadlines, solar forecasts, battery reserve, conversion losses, and
  household demand in an explainable rolling plan.
- Monitor any combination of EV, stationary battery, and solar, including none.
- Use compatible HA numbers, switches, selects, or user-supplied command scripts.
- Start in **Observation** with equipment control and notifications disabled.
- Provide optional homeowner/admin dashboards, a local handbook, and bounded
  household, EV, solar and opt-in battery calibration from local measurements.
- Offer guarded price-data fallback, an opt-in bounded published-estimate mode
  for ComEd delays, and separate household-advice/fallback notifications.
- Explain dependable comparison coverage, feasible battery refill value and
  forecast-priced cost subsets rather than claiming guaranteed savings.

Supply, delivery, and export-rate fields start **unset**. They are not copied from
an example household. Unset is unknown; enter zero explicitly when applicable.
The default export basis is **No credit**. Generic equipment/model assumptions
are starting points to review, not detected hardware specifications.

## Requirements and scope

- Home Assistant **2026.10.2 or newer**; this version targets that release and
  Python 3.14.
- Existing integrations for the measurements and optional controls you select.
- USD/kWh or cents/kWh pricing. Other currencies are not currently supported.
- Forecast.Solar for the optional solar forecast adapter.
- One planned EV and one modeled stationary-battery system.

The bounded search is not a global optimization guarantee. Modeled costs are not
a utility bill or demonstrated savings. Demand charges, tax rules, credit banks,
and scheduled forced battery exports are not implemented. See
[the method](docs/design.md) and [accounting](docs/accounting.md).

## Manual installation

1. Download **Source code (zip)** from the
   [latest release](https://github.com/dekay7/nrg-planner/releases/latest) and extract it.
2. Copy only `custom_components/nrg/` to your HA configuration directory's
   `custom_components/nrg/` folder.
3. Restart Home Assistant.
4. Add **NRG Planner** in **Settings → Devices & services → Add integration**.
5. Follow the [quick start](docs/quick-start.md), entering your own rates and
   choosing only your installed equipment. Keep Observation selected initially.

The integration works through native entities and its configuration forms without
the optional dashboards. For the complete UI, follow
[dashboard installation](docs/installation.md#optional-dashboards).

## HACS custom-repository installation

1. Open **HACS** in Home Assistant, then **⋮ → Custom repositories**.
2. Enter `https://github.com/dekay7/nrg-planner`, select type **Integration**, and
   choose **Add**.
3. Find **NRG Planner** in HACS, open it, and download the latest stable release.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → NRG Planner** and
   follow the [quick start](docs/quick-start.md). Keep Observation selected initially.

Default-catalog inclusion is a later submission; it is not required for users to
install a public custom repository. HACS downloads the integration and its bundled
assets, but does not edit your HA configuration or register dashboard packages.
HACS offers published stable releases; routine development commits do not offer
updates to users following releases. The default branch is hidden from normal
HACS download choices. Existing users tracking `main` should select a numbered
release through **HACS → NRG Planner → Redownload → version selector** once.
See [updates](docs/installation.md#updates-and-removal) and the
[project review](docs/review.md).

## Documentation

- **[User wiki and complete documentation](docs/README.md)** — plain-language
  overview, setup paths, everyday use, and a guide to every topic. Also bundled
  as a self-contained, script-free page at `/nrg-planner/guide.html` in HA.
- **[Feature guide and development history](docs/features.md)** — all feature areas,
  setup links, retired behavior, and released versus unreleased milestones.
- [Quick start](docs/quick-start.md) · [Installation and dashboards](docs/installation.md)
- [Pricing](docs/pricing.md) · [Every setting](docs/settings.md)
- [Integrations and adapters](docs/integrations.md) · [Learning](docs/learning.md)
- [Homeowner guide](docs/homeowner-guide.md) · [Operations](docs/operations.md)
- [Troubleshooting and support](docs/troubleshooting.md) · [Common questions](docs/faq.md)
- [Plain-language glossary](docs/glossary.md)
- [Privacy](PRIVACY.md) · [Security reporting](SECURITY.md) · [Project review and release readiness](docs/review.md)
- [Free alternatives and intended community value](docs/alternatives.md)

## Development

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -B tools/build_ui.py
.venv/bin/python -B tools/build_brand.py
.venv/bin/python -B -m pytest -q
.venv/bin/python -B -m pip_audit --progress-spinner off
.venv/bin/python -B -m ruff check . --select F
.venv/bin/python -B tools/check_privacy.py --history
git diff --check
```

Node.js is used for executable chart tests. Generated UI assets are committed so
users need no build tools. The builders use only repository source and generic
documentation, never a live HA instance or household data files.

For each feature or behavior change, update its user-facing guide and the
[feature index](docs/features.md), including permissions, defaults, failure/recovery
behavior and release availability. Keep mappings/control/script help in the generated
settings reference; edit its builder/catalogue, not generated files. Regenerate the
handbook and dashboards together. Documentation tests check chapter inclusion, local
links, catalogue coverage and feature entry points so future additions do not drift.

## Releases

Use feature branches and pull requests into `main`. Run CI before merging and
batch related improvements into deliberate releases. Pushes and merges do not
automatically publish releases. Users following stable releases receive update
offers only when a new stable GitHub Release is published; installation is their
choice unless they configured update automation.

Use patch versions for compatible fixes (`0.1.1`) and minor versions for features
(`0.2.0`). Document breaking changes in minor releases while below `1.0`; after
`1.0`, use a major version for breaking changes. Test larger changes with GitHub
pre-releases such as `v0.2.0-beta.1`, which testers explicitly opt into. Draft
releases are unpublished.

When the owner requests a release:

1. Update `custom_components/nrg/manifest.json` and `VERSION` in
   `custom_components/nrg/const.py` to the same version. Update the README version
   and documented minimum HA version/`hacs.json` when applicable.
2. Rebuild generated assets using the development commands above. Test fresh
   setup and upgrades from the previous release; preserve settings and learning.
   Recheck live equipment behavior when controls or planning change.
3. Verify tests/privacy, asset reproducibility, Hassfest, and HACS on the exact
   candidate commit. Review dependency-audit results and record unresolved
   upstream findings in [the review record](docs/review.md).
4. Publish a GitHub Release tagged `v<version>` at that tested commit, such as
   `v0.1.1` for integration version `0.1.1`. A tag alone is not a published release.
   Include changes, compatibility/migration notes, and restart instructions.
   GitHub's source archives are sufficient for the existing HACS layout.

Keep published tags fixed. Correct a faulty release with a new patch version.

## License

[MIT](LICENSE). Maintained by [@dekay7](https://github.com/dekay7).
