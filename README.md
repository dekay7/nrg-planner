# NRG Planner

Home Assistant energy planning with independent supply and delivery tariffs,
optional EV/battery/solar support, and controls mapped to existing HA entities.

**Early development · version 0.1.0.** See the
[project review](docs/review.md) for current validation results and open release
items. NRG Planner is not included in the default HACS catalog.

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
  learning based on each installation's own measurements.

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

1. Download and extract this repository (**Code → Download ZIP** on GitHub).
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

1. Add `https://github.com/dekay7/nrg-planner` to HACS **Custom repositories** as
   category **Integration**.
2. Download NRG Planner and restart HA.
3. Add the integration in Devices & services and follow the quick start.

Default-catalog inclusion is a later submission; it is not required for users to
install a public custom repository. HACS downloads the integration and its bundled
assets, but does not edit your HA configuration or register dashboard packages.
Check the [validation record](docs/review.md#verification-record--2026-10-20) for
HACS validation status. Without a GitHub release, HACS downloads the default branch.

## Documentation

- **[User wiki and complete documentation](docs/README.md)** — plain-language
  overview, setup paths, everyday use, and a guide to every topic. Also bundled
  as a self-contained, script-free page at `/nrg-planner/guide.html` in HA.
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

## License

[MIT](LICENSE). Maintained by [@dekay7](https://github.com/dekay7).
