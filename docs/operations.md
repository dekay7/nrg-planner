# Operation, handover, and recovery

## Observation and Control

**Observation** calculates plans without equipment commands. **Control** authorizes
only components separately enabled for NRG control. Mapping entities does not
implicitly enable commands. Notifications are opt-in and never operate appliances.

Switching back to Observation stops new commands but does not restore settings
already saved in equipment. Choose a desired physical baseline when transferring
ownership, disabling control, or removing NRG.

## Transfer equipment control

1. Check component selections, rates, measurements, meter conventions, and modeled
   assumptions in Observation. Missing rates are unknown, not free electricity.
2. Match actual mode/state names and command/readback capabilities. Do not map a
   forced-export mode to the logical "serve home" action.
3. Record device settings needed for recovery: charging state/current/target and
   applicable battery mode, reserve, export policy, and grid-charge permission.
4. Disable competing controllers and scheduled command automations. Use the optional
   external-controller-priority/protection mappings where suitable; NRG cannot
   automatically discover every other controller.
5. Enable the desired EV/battery control switches and select Control.
6. Compare acknowledged commands with readback and measured device response.

The equipment retains its own electrical protections. A service acknowledgment
does not establish instantaneous power delivery or completion of a charge cycle.

## Everyday controls

- **Charge now** bypasses prices and the normal charging window, but respects
  connection, selected vehicle target, current limits, and mapped guards. It clears
  on completion, disconnection, or restart.
- **One-off departure** overrides the daily time. An incomplete connected session
  stays overdue rather than silently moving to the following day.
- **Refresh** reloads configured pricing/forecast inputs.
- **Reset learning** removes learned profiles and calibration, preserving settings
  and the measured-cost ledger.
- **Notifications** require opt-in, selected notify services, stable advice, a
  minimum modeled benefit, and non-quiet hours.

## Missing data

Selected guard inputs must remain available and clear. Unsupported operations
are not scheduled. Missing current/forecast prices or solar coverage prevent
discretionary battery moves. Locally learned price estimates remain tentative;
there is no bundled historical household fallback.

A missing or stale plan revokes charging grants where supported. Explicit
charge-now can operate without price data when EV checks pass. Battery failures
are reported independently of EV execution, including when revoking a stale plan.
Battery readiness, charge target, reserve, and EV activity are rechecked before
each charging/discharging request. Shutdown blocks new equipment requests.

## Price-data fallback

Open **Configure → Price-data fallback**, or the **Price-data fallback** dashboard
page. Choose **Use my fallback actions**, then review the device actions on the
next screen. Only devices installed and enabled for NRG control have action
choices; other saved choices are retained, not reset. Enable permissions on
**Components** and keep **Operation → Observation** selected while reviewing.

The default is **Standard protection (default)**. This is not an all-charging-off
setting: it keeps normal guarded planner rules, including EV departure charging
at potentially unknown prices. **Use my fallback actions** instead applies your
chosen baseline automatically when current prices become unusable. Saving that
choice does not start a manual request or enable equipment control. **Saving can
apply your actions immediately** if prices are already unusable and Control is
authorized. The dashboard routes policy changes through the guided configuration
so you can review device actions before saving; edits to device actions on the
dashboard take effect immediately if fallback is active. Neither policy sends
commands in Observation or overrides configured grid, protection,
or external-owner guards.

Choose the baseline for each device:

- **EV: Pause scheduled charging** stops scheduled charging, even if that risks
  departure readiness. **Charge for departure (price unknown)** uses the remaining
  charging opportunities and may buy energy at an unknown price. It is not a
  completion guarantee. **Charge now**
  explicitly overrides the fallback pause; connection, target and current checks
  still apply.
- **Battery: Save battery energy** holds stored energy. **Power home above reserve
  (self-consumption)** lets the battery supply the home above backup reserve. Both revoke grid charging where
  supported. Fallback never lowers the device's reserve, requests forced exports,
  or intentionally supplies the EV when Preserve battery during EV charging is on.
  Native protections remain responsible for instantaneous electrical behavior.

For a conservative unknown-price response, choose **Pause scheduled charging**
and **Power home above reserve (self-consumption)**. Choose **Save battery energy**
instead when retaining backup energy matters more. These use the existing battery
reserve and Preserve battery during EV charging settings; there are no separate
fallback copies to keep in sync. A pricing outage is not evidence of high prices or a grid
outage, and neither policy guarantees the lowest eventual bill.

### Detection and recovery

**Pricing health** distinguishes Healthy, Degraded, Fallback, and Recovering.
A failed live fetch is Degraded while the current observation is still usable.
With **Use my fallback actions** selected, automatic fallback starts when current
supply or delivery pricing is missing, stale or invalid and no permitted bridge
or estimate is usable. Standard protection instead keeps its normal guarded
planner rules. ComEd live observations must be less than 15 minutes old **and
belong to the current hour**. The previous hour's live price is never relabeled as
current.

ComEd normally needs time to publish the first running average of a new hour.
Under **Strict live pricing**, during the **first ten minutes only**, a valid
published forecast for that exact hour can bridge the gap without activating
fallback. Pricing health explains the
bridge; its attributes and the buying/supply price entities report
`comed_publication_bridge: true`, with source `day_ahead`, not a live observation.
The forecast must satisfy the normal 36-hour cache limit. Missing, expired or
learned-only forecasts cannot bridge the gap. If live pricing is still absent at
ten past under Strict live pricing, current pricing becomes unusable and the
selected protection applies.

The optional **Allow brief published estimates** setting under **Tariff** adds a
bounded estimated-price mode instead of immediately applying fallback actions.
It requires a valid forecast for the exact current hour and ends 60 minutes after
the last verified live observation. Cold starts without one get only the usual
ten-minute bridge. Refreshes, hour changes and restarts never renew an existing
allowance. During this mode Pricing health stays Degraded, EV planning can
continue, battery grid charging is blocked, and higher native reserves are
retained. The setting defaults to Strict live pricing for existing and new users;
other supply plans are unaffected. See [brief live-data delays](pricing.md#brief-comed-live-data-delays).

A genuine fetch/DNS error remains visible as Degraded while the forecast bridge
or cached live observation is usable. An expected previous-hour response during
the publication window is not itself a fetch failure.

Missing tomorrow forecasts alone do not activate fallback; configured
flat/time-of-use rates do not depend on ComEd.

Automatic recovery requires valid observations spanning at least two minutes;
live sources must supply a distinct observation, not just repeated reads of the
same cache. Neither the publication bridge nor optional estimated pricing releases
an already active automatic fallback or counts as fresh live recovery evidence.
The automatic outage latch is saved so restarting cannot bypass that requirement.
A manual request also stays active. A fresh plan is required before normal dispatch
resumes. Old charging settings are not blindly restored. The fallback outlook assumes the selected
baseline continues until recovery; it is not a prediction of outage duration.

**Start manual fallback now** uses the selected baseline immediately, without
waiting for cached prices to expire. It is shown only with **Use my fallback
actions** and requires confirmation. The request stays saved across restarts and
price recovery until **End manual fallback request** is pressed. Ending the
manual request does not force normal operation while automatic fallback or its
recovery checks still apply. A saved manual request can also be ended after
switching to Standard protection; otherwise it can resume when fallback is
selected again.
Automatic fallback is reevaluated from current data after restart; saved settings,
learning and the cost ledger are preserved. Charge now remains session-only.

### Verify the result

Pricing health attributes show observation timestamps/ages, missing components,
selected policies, manual/charge-now overrides and per-device command results.
An acknowledged mode is not proof of measured power delivery. If a device fails,
the other device is still attempted; unavailable controls cannot be bypassed by a
fallback policy. An unmapped reserve/export control must be configured appropriately
in the equipment itself. Do not map a forced-export mode to self-consumption.
Command scripts must apply only the requested action and honor readback. During
fallback or optional estimated-price operation, their `reserve_soc` context retains
a higher reported native reserve (or is unknown if that feedback is invalid), and `export_policy` is capped to
Solar only or No exports; neither is permission to invent a missing control.

The Price-data fallback page separates policy selection, device actions, status
and manual requests, and links to optional alerts. Observation banners explicitly
describe a proposal, not executed equipment actions. Operation keeps everyday
mode/EV overrides and links to this page.

Missing prices remain unknown in cost accounting and are never filled with a
made-up emergency rate or claimed savings. Valid published-price estimates used
by the publication bridge or optional bounded estimate mode are tracked separately
in forecast-priced coverage, purchase-cost and export-credit attributes. Older
ledger intervals are not retroactively reclassified.

## Notifications

Under **Configure → Notifications**, **Household advice messages** and
**Price-data fallback alerts** are separate opt-ins, both initially off.

- Household advice sends a worthwhile **wait-until** recommendation only when
  dependable comparison confidence and complete task coverage exist, the benefit
  reaches its notification threshold, and the same recommendation remains stable
  for at least two minutes. A limited battery-refill estimate suppresses it.
  NRG deduplicates a delivered window per selected notify service. The planner's
  separate minimum-improvement setting controls schedule stability, not this
  notification threshold.
- Price-data alerts describe custom-fallback activation or recovery, not every
  failed fetch or Degraded estimate. They are independent of the appliance benefit
  threshold and use a five-minute transition-alert cooldown. Observation messages
  describe proposals, not executed equipment commands.

Select at least one existing notify service; none is selected automatically.
Both message types share these destinations and the configured local quiet hours.
Equal quiet-hour start/end disables quiet hours; periods crossing midnight are
supported. No message is expected solely because a price changed. A pending alert
can wait for quiet hours/cooldown to end; it is not an immediate-delivery guarantee.
Alert permission does not enable fallback or equipment control, and dashboard
visibility needs no notification permission.

## Recovery

Use an HA backup and a previously reviewed component version when recovering from
an update. Backups may contain private settings and measurements. Keep them out of
issues and repositories.

Release NRG control before enabling another controller. Restoring component files
does not restore physical equipment settings or rewind saved options, learning,
ledgers, or recorder history. Reestablish the desired device baseline explicitly.

The standard integration diagnostics download is an intentionally limited support
summary. See [privacy](../PRIVACY.md) before sharing logs, screenshots, or state exports.
