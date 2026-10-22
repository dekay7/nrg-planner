# Installation and updates

## What to have ready

Use a Home Assistant administrator account and Home Assistant **2026.10.2 or
newer**; this version targets 2026.10.2. NRG runs inside HA, so end users do not
need Python, Node.js, or build tools. Generated dashboards and the handbook are
already included.

The **HA configuration directory** is the folder containing your
`configuration.yaml`, commonly `/config` on Home Assistant OS. Open it using your
existing file-management method, such as File editor, Studio Code Server, or a
network share. Other installation types may keep it at a different path.

## Manual installation

1. Open the [latest GitHub release](https://github.com/dekay7/nrg-planner/releases/latest),
   download **Source code (zip)** under **Assets**, and extract it.
2. Open your HA configuration directory. Create `custom_components` there if it
   does not exist.
3. Copy the repository's **`custom_components/nrg/` folder**, including all its
   contents, into that directory. The result should look like this:

   ```text
   <HA configuration directory>/
     configuration.yaml
     custom_components/
       nrg/
         __init__.py
         manifest.json
         assets/
         dashboards/
         ...
   ```

4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration**, search for
   **NRG Planner**, and follow the [quick start](quick-start.md).

No SSH deployer or site file is needed. If NRG does not appear, see
[troubleshooting](troubleshooting.md#nrg-does-not-appear-in-add-integration).

No Git history, tests, development tools, or repository data files belong in the
installed component directory beyond the files already under `custom_components/nrg/`.

## HACS custom repository

With HACS already installed in Home Assistant:

1. Open **HACS**, then the **⋮** menu and **Custom repositories**.
2. Paste `https://github.com/dekay7/nrg-planner` into the repository field.
3. Select type **Integration** and choose **Add**.
4. Search for **NRG Planner** in HACS, open its entry, and download the latest
   stable release.
5. Restart Home Assistant.
6. Open **Settings → Devices & services → Add integration**, select **NRG Planner**,
   and follow the [quick start](quick-start.md). Start in Observation and enter your
   own rates and equipment mappings.

Default-catalog approval is not required for this custom-repository path.
See the [project review](review.md) for validation results. HACS uses published
stable releases, with the development branch hidden from normal download choices.
If you previously installed `main`, use **HACS → NRG Planner → Redownload** and
select a numbered release in the version selector to follow releases.

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
is available. Open that path on your own HA address, or use the handbook link in
**Why?** or **Operation**. Its contents are generic and do not include saved
configuration. It includes troubleshooting, FAQs, a glossary, and privacy details.
There are no scripts, external fonts, or external assets. Use browser Find to
search and Print to save a PDF; reading a loaded copy needs no internet connection.

## Updates and removal

Check the [feature guide and milestones](features.md#development-milestones-since-creation)
when comparing the online docs with your installation. The latest stable release
is 0.2.0; later main-branch work is unreleased until a new release is explicitly
published. A manually installed development snapshot may still report 0.2.0, so
keep its source commit with your private deployment record. The bundled handbook
travels with the installed component rather than silently following GitHub main.
Do not move a published tag to make its contents match development docs.

Routine development commits do not offer updates to users following stable
releases. A published stable GitHub Release makes a new version available in HACS;
install it when convenient unless you have configured automatic updates. Review
the release notes for compatibility changes or migration steps, then restart HA
after installing. Beta pre-releases are for testers who explicitly opt into them.
To select an older release, use HACS **Redownload** and its version selector;
check its compatibility with your current HA version and stored data first.

For manual updates, replace only the component directory with a reviewed newer
copy and restart. HACS updates follow the same component boundary. Integration
options, learning, and ledgers use HA storage, not files inside the component.
Completed battery calibration, saved fallback requests/outage latches and ComEd
continuity timestamps are retained too. New opt-in features do not automatically
enable controls, battery calibration, custom fallback, or brief published estimates.
The retired summer-heuristic option/entity is cleaned up automatically and no longer
blocks charging. No manual storage-file migration is required.

Before removing NRG, release its control and establish the desired device baseline
as described in [operations](operations.md). Remove the integration through Devices
& services, remove its dashboard-package include if present, then remove its
component through HACS or your manual file-management method. Check configuration
before restarting. Use supported HA interfaces for stored configuration/history;
do not manually edit HA's storage files.

Removing the integration through Devices & services deletes its local learning,
forecast caches, notification bookkeeping, and measured-cost ledger. Reloads and
updates preserve these data. HA recorder history and existing backups follow HA's
own retention settings.
