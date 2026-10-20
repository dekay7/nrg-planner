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

## Recovery

Use an HA backup and a previously reviewed component version when recovering from
an update. Backups may contain private settings and measurements. Keep them out of
issues and repositories.

Release NRG control before enabling another controller. Restoring component files
does not restore physical equipment settings or rewind saved options, learning,
ledgers, or recorder history. Reestablish the desired device baseline explicitly.

The standard integration diagnostics download is an intentionally limited support
summary. See [privacy](../PRIVACY.md) before sharing logs, screenshots, or state exports.
