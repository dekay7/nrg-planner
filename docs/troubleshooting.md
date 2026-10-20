# Troubleshooting and support

Start with the symptom below. **Configure → …** means **Settings → Devices &
services → NRG Planner → Configure**. The optional administrator dashboard is
called **NRG Planner settings**.

## NRG does not appear in Add integration

1. Confirm that Home Assistant is 2026.10.2 or newer; this snapshot targets 2026.10.2.
2. For a manual installation, check that `manifest.json` is directly inside your HA
   configuration directory's `custom_components/nrg/` folder. A nested
   `custom_components/nrg/nrg/` or a copy of the repository outside the HA
   configuration directory is not the expected layout.
3. Restart Home Assistant after copying the component, then look in **Settings →
   Devices & services → Add integration** for **NRG Planner**.
4. If it is still absent, review the Home Assistant logs for a component-loading
   error and include the relevant, reviewed error in a support report.

HACS cannot install this private-review repository. Use the manual path while
access is private; see [installation](installation.md).

## The integration is installed, but no NRG dashboards appear

Dashboards are optional and are not registered automatically. Complete the
[dashboard package setup](installation.md#optional-dashboards), check the HA
configuration, and restart. The **NRG Planner settings** view appears only for
administrators. You can configure and use native entities without these views.

## Charts say Custom element does not exist or are blank

- For `apexcharts-card` errors, install **ApexCharts Card** separately through HACS
  and verify its module in **Settings → Dashboards → Resources**. The bundled
  templates target version **2.2.3**. Reload the browser after resource changes.
- If the card loads but has no data, inspect NRG's buying price, pricing coverage,
  and source status. Chart lines omit missing or expired plan data.
- An **External supply/delivery** current sensor alone cannot fill future hours.
  Add a supported forecast or use your contracted flat/timed rates.
- If entity IDs were renamed, the bundled dashboard still refers to the initial
  `nrg_*` IDs. Update the references in your own dashboard copy.

## Electricity price is unknown, too high, or 100 times wrong

Open **Configure → Tariff** and check supply and delivery separately.

- Both components need a valid rate for the combined buying price. Blank means
  unknown. Enter zero explicitly if there is no separate delivery cost.
- If supply already includes delivery, do not add delivery again.
- Type rates in **cents/kWh**: a $0.12/kWh rate is **12**, not **0.12**, in a
  cents field. External sensors must declare supported USD/kWh or cents/kWh units.
- For timed pricing, select the time-of-use plan as well as saving its periods.
  Check uncovered hours, blank rates, starting weekdays, and the HA timezone.
- For external feeds, inspect the selected current/forecast entities, forecast
  attribute, timestamps, interval ends, units, and freshness.

Negative supply is not necessarily a negative total after delivery is added.
See [pricing](pricing.md) for accepted interval fields and overnight rules.

## Advice says Waiting for dependable coverage

NRG needs enough trustworthy information to compare a **complete** run of the
reference task. Check price coverage first, then the forecasts and enabled
equipment readings that apply to your home. A one-hour task cannot be compared
using only one known 15-minute slot.

Turn off components you do not have under **Components**. A disabled component
contributes a known zero; an enabled component with missing readings is unknown.
Use **Refresh** after correcting inputs. Tentative price estimates are not the
same as dependable published or contracted coverage.

## Power flows are missing, reversed, or inconsistent

NRG's normalized readings mean **positive grid = buying** and **positive battery =
supplying the home**. In **Configure → Meter conventions**, reverse the applicable
reading only if your provider uses the opposite convention. Check whether the
home meter includes EV charging so it is not added or subtracted twice.

Review **Details → Local measurement quality** and the power-balance residual.
Mismatched meters can pause learning. Map power entities in W or kW rather than
energy counters in kWh for live power roles.

The **Sankey diagram has its own setup**: configure actual power meters in Home
Assistant's Energy dashboard. NRG's Mappings screen does not populate it. Missing
meters are not replaced with forecast flows. See [the homeowner guide](homeowner-guide.md#current-power-flow-the-sankey-diagram).

## The plan exists, but my car or battery is not following it

Read **Operation → Control status** before checking the device.

1. **Mode:** Observation proposes only; select Control when you intend to hand over
   operation.
2. **Component permission:** enable the relevant EV/battery control switch separately.
3. **Inputs:** confirm connection, charge percentage, selected EV target, required
   controls, and their available feedback. A plan is not observed operation.
4. **Protection:** selected guard entities must report the expected clear states.
   A missing selected guard blocks commands; it is not silently ignored.
5. **Command compatibility:** match your actual option/state names under **Control
   adapters**. Read-only feedback needs a working command script if no direct
   switch, number, or select can perform the action.
6. **Ownership:** check for a manufacturer's schedule or another automation
   overwriting settings. Follow [control handover](operations.md#transfer-equipment-control).

**Writer authorized** indicates mode and component permission, not that every
device is ready. **Protection guards**, **EV ready**, and **Battery ready** identify
additional checks. Commands and device response may take time; feedback should
confirm settings. Do not map forced battery export to NRG's serve-home action.

## The modeled battery line is missing

Observation mode supports the proposed battery trajectory. It does not need Control
mode or permission to issue live commands.

1. Enable the battery component and its planning/control permission under Components,
   while keeping Observation selected for a command-free review.
2. Check the explanation beneath **Modeled energy plan · next 48 hours** and the
   **Battery plan** reason. Monitoring-only batteries have no NRG dispatch trajectory.
3. Confirm that battery percentage and compatible mode-control feedback are available.
4. Open **Operation → Protection guards → More info**. The `guard_issues` attribute
   identifies each mapped input that is missing, unavailable, stale, or not in its
   expected clear state. The planner's explanation includes the same blocker.
5. If a chosen provider exposes an unavailable grid-services sensor, choose an
   available equivalent for the same equipment in Mappings. Preserve the protection
   check; do not substitute an unrelated always-off entity.

Missing price/solar coverage restricts discretionary moves; a missing battery
trajectory is separately explained by its planning inputs/readiness. A forecast is
a proposal, not a prediction that the equipment's own controller will follow it.

## My sleeping car's readings are considered old

Some integrations publish vehicle values only when they change. First confirm the
home-charger connection and that the readings are still appropriate. You can
provide a wake/refresh automation through the existing integration. Alternatively,
**EV → Allow saved vehicle readings while plugged in** accepts available retained
SOC/target/settings while the home connection is reported. It starts off and
allows less-current estimates; it does not bypass connection, protection, or
command-feedback checks. See [reading freshness](integrations.md#provider-neutral-measurements).

## EV ready time is late or there is a departure shortfall

Check the daily departure, any one-off override, vehicle target, current charge,
maximum/stable current, modeled charging power, energy per percentage point, and
actual connection. Generic defaults are not detected hardware specifications.

**Charge now** bypasses prices and the normal charging window when EV checks pass.
It does not raise the vehicle target or ignore current/protection limits. Clear an
outdated one-off departure using **Clear one-off departure**. An incomplete
continuously connected session stays overdue instead of quietly moving to tomorrow.

## The battery will not grid-charge or export on schedule

Grid charging requires a supported charge action. If charge and hold share the
same device mode, a separate grid-charge permission switch is needed; otherwise a
distinct charge-capable mode can work. Missing trustworthy price/solar inputs,
reserve, and device readiness can also limit moves.

NRG does not schedule forced battery exports. **Battery** export policy permits
exports where a control exists; it does not request a timed sale. Without a mapped
export control, configure that policy in the equipment's own app. See
[control adapters](integrations.md#direct-controls-and-option-names).

## Solar totals look doubled or a source is unavailable

Add distinct physical arrays, but average alternatives covering the **same**
panels. Do not add several sensors from one Forecast.Solar entry as separate
independent forecasts. A whole-system forecast and a partial overlapping roof
cannot be combined as separate coverage. Review each source's group and status.

For a consistently low prediction, check whether both provider calibration and
NRG age correction are reducing the same output. Turn age correction off for a
provider already adjusted to current panel output. A missing daylight forecast
stays unknown; nighttime can be known zero. See [solar sources](integrations.md#solar-forecasts-and-alternatives).

## Today's cost is absent, surprisingly low, or different from HA Energy

Check **Today's cost coverage** together with the net cost. Cost tracking needs
sufficient grid/site power readings and contemporaneous prices. First days,
missing readings, and downtime are partial. Price advice can still work without
site metering.

NRG integrates covered power samples; HA Energy can use lifetime energy counters.
Their totals need not match. Fixed fees and unconfigured taxes are outside NRG's
variable-cost ledger. Changing a rate does not retroactively reprice recorded
intervals. See [accounting](accounting.md).

## Learning or notifications do not seem to work

**Learning:** check the relevant switch and measurement coverage. Household hours
need 80% valid coverage. Solar needs six valid daylight comparisons. EV sessions
need at least five percentage points, five minutes, and covered AC energy readings
from an increasing lifetime counter. Until then, configured fallbacks are expected.
[Learning](learning.md) explains each requirement. Reset only when you intend to
discard learned profiles and comparisons.

**Notifications:** enable notifications and select existing notify services in
**Configure → Notifications**. The feature sends stable wait-until advice only
when its modeled benefit reaches your threshold and quiet hours permit it. A
two-minute stability requirement prevents immediate messages; the default
threshold is 25¢ for the reference task. No message is expected just because a
price changed.

## The handbook looks old after an update

Open it using a dashboard's handbook link; the generated link includes a content
version to avoid an old cached copy. Reload the browser if needed. With a manual
update, confirm the complete `custom_components/nrg/` directory was replaced,
including `assets/guide.html` and the bundled dashboards.

## Getting help

Use the [GitHub issue tracker](https://github.com/dekay7/nrg-planner/issues) if you
have repository access. During private review, contact the repository owner through
the existing review channel if the tracker is unavailable. Maintainer:
[@dekay7](https://github.com/dekay7).

Include:

- Home Assistant and NRG versions, plus manual/HACS installation method. The NRG
  version is in the integration's `manifest.json` and its diagnostics summary.
- What you expected, what happened, and the steps that reproduce it.
- Enabled components, Observation/Control mode, affected provider integration,
  and relevant readiness/coverage status.
- For chart issues, browser and ApexCharts Card version.
- If useful, the standard **Download diagnostics** from NRG's integration entry.
  It is a limited summary rather than a complete configuration dump.

Review any logs, screenshots, entity exports, or attachments before sharing;
they may show private local settings. Do not attach an HA backup or entire
configuration directory. The [privacy guide](../PRIVACY.md#diagnostics-and-support)
describes exactly what the standard diagnostic download includes and excludes.

For update rollback, removal, or returning control to another system, follow
[installation](installation.md#updates-and-removal) and [recovery](operations.md#recovery).
