# Installation and updates

## Private review

HACS requires a public GitHub repository. While this repository remains private,
download it using an authorized GitHub account and copy `custom_components/nrg/`
into the HA configuration directory's `custom_components/nrg/`. Restart HA and
add **NRG Planner** in Devices & services. No SSH deployer or site file is needed.

No Git history, tests, development tools, or repository data files belong in the
installed component directory beyond the files already under `custom_components/nrg/`.

## HACS after publication

Add `https://github.com/dekay7/nrg-planner` in HACS Custom repositories, category
**Integration**. Download, restart HA, and add the integration through Devices &
services. Default-catalog approval is not required for this custom-repository path.

All integration assets, dashboard definitions, and the generic handbook are inside
`custom_components/nrg/` and are delivered together. HACS does not edit your
configuration, enable device control, or register dashboard packages.

## Optional dashboards

The integration's native entities and setup forms work without dashboards.
For the bundled homeowner and admin views:

1. Install **ApexCharts Card** through HACS and verify its JavaScript module is
   registered in **Settings → Dashboards → Resources**. NRG does not redistribute
   a copy or download it automatically. The chart templates target ApexCharts
   Card 2.2.3; recheck charts after frontend updates.
2. Merge the following into `configuration.yaml`. If a `homeassistant` section
   or `packages` key already exists, merge rather than creating duplicate keys:

   ```yaml
   homeassistant:
     packages:
       nrg_planner: !include custom_components/nrg/dashboard-package.yaml
   ```

   For an existing `!include_dir_named packages` setup, instead add a file in
   that directory containing:

   ```yaml
   !include ../custom_components/nrg/dashboard-package.yaml
   ```

3. Check HA configuration and restart. **NRG Planner** and **NRG Planner settings**
   appear in the sidebar. The settings dashboard requires an admin account.
4. Configure power meters in HA's built-in Energy dashboard for the live Sankey.
   NRG does not overwrite Energy preferences or create substitute meter readings.

The package includes recorder exclusions for large NRG diagnostic entities; merge
them with any existing recorder configuration as needed. It does not contain
tariffs, entity mappings for your hardware, or an automatically imported site file.

Bundled dashboards reference the integration's initial `nrg_*` entity IDs. If you
rename those IDs, use your own dashboard copy and update the references. Keep
customizations outside the integration directory so component updates preserve them.

The local handbook is served at `/nrg-planner/guide.html` when HA's HTTP integration
is available. Its contents are generic and do not include saved configuration.

## Updates and removal

For manual updates, replace only the component directory with a reviewed newer
copy and restart. HACS updates follow the same component boundary. Integration
options, learning, and ledgers use HA storage, not files inside the component.

Before removing NRG, release its control and establish the desired device baseline
as described in [operations](operations.md). Remove the integration through Devices
& services, remove its dashboard-package include if present, then remove its
component through HACS or your manual file-management method. Check configuration
before restarting. Use supported HA interfaces for stored configuration/history;
do not manually edit HA's storage files.
