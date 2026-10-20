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
