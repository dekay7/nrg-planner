# Supply, delivery and time-of-use plans

## The prominent buying price

```text
Buying price at a time = supply price at that time + delivery price at that time
```

The schedules are independent. A flat supply contract can have variable delivery,
and a flat delivery rate can accompany variable supply. You can also use two
different time-of-use schedules or external feeds. ComEd is only one optional
supply source; it is never used as a fallback for another provider's missing rates.

Prices are entered in **cents/kWh**, converted once to USD/kWh internally.
Negative rates remain signed. A −2¢ supply price plus 6¢ delivery still costs 4¢ to import.
These are illustrative numbers, not defaults. All numeric rate inputs start unset;
unknown rates remain unknown until supplied. Enter zero explicitly if applicable.

## ComEd price sources and freshness

ComEd is an optional supply adapter, not a fallback provider for other tariffs.
It combines the public current-hour-average API with dated published forecasts.
ComEd forecast labels use Central hour-ending times; the parser converts them to
real hour starts rather than treating the website's `Date.UTC` label as UTC.
Ambiguous/nonexistent DST labels and incomplete forecasts are rejected rather
than guessed. A previously valid cache or current live observation may still be
usable independently.

| Source | Meaning and limits |
|---|---|
| `running_average` | A live observation less than **15 minutes** old that belongs to the current real hour; not a final settlement price. A recent prior-hour reading is still not a current-hour price. |
| `day_ahead` | A published exact-hour forecast with a **36-hour** cache limit. Dependable as a forecast for planning, but substitutes for missing current live pricing only under the bounded policies below. |
| `recorded_estimate` | A tentative estimate from this installation's previously recorded live observations for the matching Central clock hour. Dashed in charts; no embedded household profile, no current-live authorization and no permission for discretionary battery economics. |

Repeated successful HTTP responses containing the same old timestamp do not
refresh the underlying live observation. A mapped **Current supply price** sensor
can replace the live API; its HA report timestamp and declared units are validated.
That report is not proof that the upstream provider took a new measurement.

## ComEd's new-hour publication window

With the default **Strict live pricing** policy, the first live running average
is not necessarily available at the hour boundary. For the first ten minutes,
NRG can use the **published forecast for that exact
hour** while awaiting live pricing. It does not reuse the previous hour's live
price or invent a rate from learned history. The forecast must be within its
normal 36-hour freshness limit.

This short bridge is labeled `day_ahead` in price-source attributes and charts;
`comed_publication_bridge` identifies it in Pricing health and the buying/supply
price entities. A normal publication gap alone keeps Pricing health Healthy;
a transport failure still shows Degraded. Neither status activates fallback
while the price remains usable. Live pricing takes priority as soon as it is
available, and NRG makes a fresh plan at that handover.

Without a valid published forecast, or if the live gap continues beyond ten past,
normal price-data protection applies. A forecast bridge cannot release an already
active automatic fallback; that still requires fresh live recovery observations.
See [detection and recovery](operations.md#detection-and-recovery).

## Brief ComEd live-data delays

Under **Configure → Tariff → During ComEd live-price delays**, the default
**Strict live pricing** preserves the behavior above. Opting into **Allow brief
published estimates** lets NRG temporarily use the published forecast for the
**exact current hour** when live pricing is delayed. This is an estimate, not a
live or settled price. It also works with a mapped ComEd live-price sensor.
Other supply plans are unaffected.

The allowance ends **60 minutes after the last verified live observation's
timestamp**, not 60 minutes after discovering the delay. The API uses ComEd's
provider timestamp; a mapped sensor uses its HA report timestamp. Repeated old
responses, forecast refreshes, hour changes, settings edits and restarts do not
renew it. Without a verified observation, only the normal first-ten-minute
publication bridge is available. Once an existing allowance expires, a new-hour
bridge cannot extend the outage. A valid exact-hour forecast is always required
and must satisfy the normal 36-hour cache limit. Missing delivery pricing still
makes the combined price unusable.

During estimated operation:

- **Pricing health is Degraded**, with `comed_estimated_price: true`, source
  `day_ahead`, last live age, forecast age, fixed deadline and remaining allowance.
- EV planning can continue within its usual permissions, charging limits and
  departure rules, instead of immediately applying a fallback pause. It may buy
  at a price different from the forecast.
- Battery grid charging is blocked, including any previously planned grant.
  Self-consumption/hold decisions remain guarded; a higher native reserve is
  retained and export permission is capped to solar only or no exports.
- Cost totals include separately tracked forecast-priced intervals, never learned
  as live supply observations. See [accounting](accounting.md#observed-ledger).

Loss of forecast/delivery coverage or expiry of the allowance invokes the selected
price-data protection. Forecasts cannot release an already active automatic
fallback; recovery still requires distinct fresh live observations spanning at
least two minutes and a new plan. Manual requests remain active until ended.
The automatic outage latch and verified-observation timestamp survive restarts.
Switching between live and estimated pricing invalidates the old plan promptly.
No choice enables equipment control or bypasses Observation/protection guards.

## Tentative prices for the end-of-day cost forecast

**Unreleased after 0.2.0.** The read-only **Forecast net cost by midnight** can
estimate unpublished **future ComEd supply hours** for the remaining local day,
without waiting for the next-day feed. ComEd's hour-ending labels mean today's
feed ends at 23:00; the next-day feed supplies today's 23:00–midnight hour. There
is no hard-coded afternoon publication time.

The cash forecast uses this order:

1. Use the applicable published exact-hour price (and current live price where
   available). When current live pricing is missing, a fresh publication for the
   **exact current hour** can price its remaining cash projection, labeled
   `day_ahead` and tentative, even beyond the separate control-policy cutoff.
   It does not make the current price usable for commands or observed accounting.
2. For an unpublished future hour, use the median of this installation's recorded
   live supply observations for the matching **Central clock hour**, when present
   in the existing bounded learning history. Label it `recorded_estimate`, with
   its sample count. These observations are running estimates, not settlements.
3. Without matching history, use the **median of published supply prices in the
   preceding 24 real hours**, labeled `published_price_median`, with sample count
   and reference timestamps. Rows must also satisfy the normal 36-hour fetch-age
   limit; future fetch timestamps, old dated hours and later published hours do
   not qualify. A single spike does not dominate this median. The baseline stays
   constant within each real hour. A new installation can use this baseline
   without inventing a learned household profile.
4. Without either baseline, keep the forecast unknown and explain the gap. Never
   use an unconfigured rate, a flat-rate placeholder, the last live price carried
   forward, or zero as a missing supply estimate. A genuine signed or zero median
   remains signed or zero.

These estimates reprice the **already selected energy flows**, including applicable
supply-linked export credits, only after equipment planning. They do not set
`price_known`/`export_known`, change ordinary slot costs, extend the dependable
comparison horizon, authorize charging, alter advice/notifications, make a current
live-price outage usable for control, or update the observed ledger. A missing
current hour without a fresh exact-hour publication is never filled from history
or a published-price median. Missing delivery,
applicable export settings, daylight coverage or equipment inputs still block the
forecast. Other providers and unconfigured flat/time-of-use rates are not filled
from ComEd data.

The sensor exposes `estimated_forecast_hours`, `estimated_forecast_intervals` and
`confidence: tentative`; both dashboards show which remaining hours use estimates
and their supply rates/sources. Covered observed costs that include published-price
estimates also lower confidence. Partial-day omissions remain separately labeled.
A normal fresh plan replaces tentative prices when ComEd publishes exact-hour
coverage, automatically removing the tentative label if no other estimated prices
remain. See [forecast accounting](accounting.md#end-of-day-net-cost-forecast).

This default forecast behavior needs **no new setting or permission** and is
independent of the opt-in **Allow brief published estimates** control policy.
Observation defaults, live-price guards, equipment permissions, fallback/recovery,
user settings and learning are unchanged.

## Editing timed periods in HA

1. Open **Settings → Devices & services → NRG Planner → Configure → Pricing periods**.
2. Choose **Supply** or **Delivery**.
3. Add a period, edit/remove an existing one, or start an empty schedule with the
   four-period example.
4. Enter the name, start, end, rate and starting weekdays.
5. Select **Time-of-use supply** and/or **Time-of-use delivery** on the Tariff page
   for the components whose schedules should operate.

The template starts with these times. Its rates are blank until you enter them:

| Period | Starts | Ends | Supply rate | Delivery rate |
|---|---|---|---|---|
| Morning | 6 a.m. | 1 p.m. | Your rate | Your rate |
| Mid-Day Peak | 1 p.m. | 7 p.m. | Your rate | Your rate |
| Evening | 7 p.m. | 9 p.m. | Your rate | Your rate |
| Overnight | 9 p.m. | 6 a.m. | Your rate | Your rate |

Each component has its own copy: changing delivery's peak time does not change
supply's. The template never overwrites an existing schedule.

### Boundary and weekday rules

- Start is included; end is excluded. A 1 p.m. reading belongs to the period starting
  at 1 p.m., not the one ending then.
- End earlier than start crosses midnight. Equal start/end means a 24-hour period.
- Weekdays describe the day the period **starts**. Monday 9 p.m.–6 a.m. extends to
  Tuesday 6 a.m.
- Two periods cannot overlap. The editor rejects that ambiguity.
- Gaps and blank rates can be saved while you build a schedule. Their prices stay
  unknown, the coverage status identifies incomplete schedules, and those intervals
  do not authorize discretionary battery moves.
- Times use Home Assistant's timezone. Repeated DST clock times use the same tariff;
  nonexistent spring clock times are skipped in real elapsed-time accounting.

For weekend rates that change exactly at midnight, split weekday overnight into
**00:00–06:00** and **21:00–00:00**, both Monday–Friday, then add **00:00–00:00** for
Saturday/Sunday. This avoids a Friday overnight period overlapping Saturday's rate.

## External utility-price integrations

Choose External supply/delivery entity and map its current sensor. Optionally map
a forecast sensor too; it can be the same entity. Configure the forecast attribute
name, default `forecast`.

Supported interval fields are:

| Purpose | Accepted fields |
|---|---|
| Start | `start`, `valid_from`, `start_time` |
| End | `end`, `valid_to`, `end_time` |
| Price | `price`, `value_inc_vat`, `value`, `per_kwh` |
| Units | row `unit` / `unit_of_measurement`, otherwise the entity's unit |

Use explicit timezone-aware ISO timestamps and `USD/kWh`, `$/kWh`, `¢/kWh`,
`c/kWh` or `cents/kWh`. Overlapping intervals, missing end times, unrecognized units
and naive timestamps are rejected. A template sensor can normalize other formats.
An example forecast attribute:

```yaml
forecast:
  - start: '2026-10-20T06:00:00-05:00'
    end: '2026-10-20T07:00:00-05:00'
    price: 0.12
    unit: USD/kWh
```

A current entity alone provides a current observation. It does not invent a future
hourly schedule. Supply/delivery forecasts may have different interval lengths;
the planner includes their exact boundaries.

## Export compensation

Configure **Supply plus adder**, **Flat credit** or **No credit** independently of
delivery. A net-metering credit may have billing-period restrictions; NRG values it
at the configured marginal rate, rather than claiming a cash payout or maintaining
a utility credit bank. Fixed, capacity and unconfigured tax charges are excluded.
