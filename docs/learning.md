# What the learning and calibration controls do

These controls improve estimates from observed data. They never alter recorded
meter values, a vehicle's selected limit, or equipment power limits. They send no
calibration commands. Improved predictions can affect the normal plan only within
existing component/control permissions; Observation still sends no equipment commands.
They work only for installed components with enough valid measurements.

## Solar forecast calibration

**Purpose:** correct a forecast that is consistently too optimistic or pessimistic
for the actual installation.

Before an hour starts, NRG saves the combined age-adjusted forecast for that hour.
Afterward, it compares it with the solar meter's covered production. It does not
compare against a forecast updated after the result was already known.

After six valid daylight hours, it calculates:

```text
Correction = total measured solar ÷ total previously forecast solar
Corrected future forecast = age-adjusted forecast × correction
```

For example, repeatedly measuring 8 kWh when 10 kWh was forecast suggests a **0.8×**
correction. If actual output is consistently higher, the factor can exceed 1.

The calculation uses up to 168 recent covered daylight hours within the retained
history, excludes tiny/nighttime forecasts, and bounds the factor to **0.5–1.5**.
Mean absolute error in Details indicates how far the saved hourly forecasts missed.
Cloud changes can still cause surprises: this corrects a persistent bias, not weather.
Only explicitly covered forecast hours qualify. A daily total does not fill missing
daylight with zero; a covered zero-output time series remains valid. Incomplete
edge hours are excluded rather than scaled into complete predictions.

It does not infer individual-roof accuracy from one whole-system meter. Changing
sources or age settings clears the old solar comparisons. Turning calibration off
uses the source forecast and configured age correction without the learned multiplier.

## Calibrate EV charging estimates

**Purpose:** estimate how much AC electricity and time the car needs to reach its
already selected charge limit.

A valid session has at least **five percentage points gained**, **five minutes**,
and good uninterrupted measurement coverage. The increasing AC energy counter and
SOC change give:

```text
AC kWh per percentage point = energy used by charging ÷ SOC percentage-point gain
```

Example: 9 kWh for a change from 60% to 70% suggests **0.9 kWh per point**. Another
10-point gain is provisionally budgeted at about 9 kWh. This includes charging losses.

NRG keeps the last **12 valid sessions** and chooses a conservative upper-percentile
energy estimate. Covered charging power divided by measured/set current also gives
power per amp; a conservative lower-percentile value helps avoid promising a finish
time based on an unusually fast session. Details shows the effective estimates.

Missing meters, gaps, counter resets and SOC reversals do not create learned sessions.
A decrease anywhere within a session discards that candidate, even if the final
counter/SOC reading later recovers to a plausible total. Without a
valid estimate—or with the switch off—NRG uses the fallback kWh/point and charging
power you entered. **No EV battery degradation percentage or health estimate is made.**

## Learn household demand

**Purpose:** predict ordinary household usage so storage and flexible-use advice
can work around daily life.

NRG integrates the home power meter. If an EV is installed and separately measured,
it subtracts car charging; otherwise it can learn while the car is known not to be
charging. A home without an EV uses the whole-home reading directly.

An hour needs at least **80% valid coverage**. Missing time is not learned as zero.
Already covered portions on either side of an observation gap can still qualify;
the gap itself adds neither energy nor coverage. Restart discards the unfinished
hour rather than resuming it with a new sample.
Impossible/inconsistent meter combinations pause the relevant learning rather than
creating a false zero-house baseline.

It keeps up to **28 days** of hourly summaries, compares matching clock hours, and
gives each older matching observation **0.9×** the weight of the next newer one.
After three matching observations, weekdays/weekends can have their own profile.
The 28-day limit uses elapsed time, so extended downtime expires old hourly demand,
price-history and solar-calibration observations rather than keeping them forever.

Example: if evenings repeatedly use more power than afternoons, the forecast
reserves more energy for those evenings. An unfamiliar hour still uses your fallback.
It predicts patterns rather than identifying individual appliances or controlling
comfort settings. Turning learning off uses your explicit house-demand estimate.

## Calibrate battery estimates

**Purpose:** improve effective round-trip efficiency and sustained charging/discharging
power without estimating capacity, degradation or battery health.

The single **Calibrate battery estimates** switch is **off initially**, preserving
existing manual assumptions until you opt in. Enable it only with a battery's
**AC-side power** and SOC readings. DC battery-terminal power, stored DC energy,
and a hybrid inverter's combined solar/battery output are not interchangeable with
an AC battery meter. Use equipment documentation to confirm the measurement boundary.
NRG cannot identify AC versus DC from the sensor's unit alone. As with the manual
power settings, calibration supports up to 30 kW in either direction.

Learning is passive and works in Observation and with a monitoring-only battery.
It never requests extra cycling, changes reserve or authorizes controls. Monitoring
still does not forecast another controller's future battery schedule.

### Round-trip efficiency

NRG follows a covered charge/discharge or discharge/charge cycle until reported SOC
returns to its starting point, with at least a **30-percentage-point excursion**:

```text
Round-trip efficiency = measured AC energy out ÷ measured AC energy in
```

For example, consuming 5 kWh and later delivering 4.4 kWh while returning to the
starting SOC suggests **88%**. No configured capacity is used in that calculation.
A cycle must last at least ten minutes, consume at least 0.5 kWh, finish within
24 hours, and contain no more than two hours of idle time. Missing/invalid readings,
gaps over 180 seconds, protection events and unexplained SOC changes discard the
incomplete cycle. Values outside **50–100%** are rejected, not silently clamped.
A crossing of the starting SOC is interpolated within the final observation interval.

Optionally map **both** lifetime AC charging and discharged-energy counters, in kWh,
at the same AC boundary as battery power. They must increase rather than reset
at midnight or each session. With either selected, both are required throughout
the cycle; missing readings, resets and implausible jumps discard the candidate.
Without selected counters, NRG integrates the previous signed power sample.
Minute-level sampling can miss rapid changes; counters are preferable when available.

After at least **three consistent cycles**, the effective efficiency is total
accepted energy out divided by total accepted energy in. Cycles more than five
percentage points from the recent median are excluded. The planner retains its
explicit assumption of equal square-root losses in each direction; round-trip
observations cannot identify separate charge/discharge efficiencies.

This is a field estimate under observed operating conditions, not a laboratory
rating. Rounded/recalibrated SOC and unmetered auxiliaries limit accuracy. Metered
standby consumption within a qualifying cycle is included; the bounded idle time
avoids treating arbitrary multi-day storage losses as conversion losses.

### Charging and discharging power

Ordinary low-load readings do **not** establish the battery's power capability.
Power learning requires independent, consistent home, grid and applicable solar
meters; calculated home/grid readings cannot establish a qualifying opportunity.
SOC must be between the larger of **10% / reserve + 5 points** and **85%**.

- Charging needs at least 0.5 kW of battery charging and either at least 0.5 kW of
  solar export remaining, or grid import with fresh feedback confirming a distinct
  force-charge mode. Grid-charge permission alone is not proof of forced charging.
- Discharging needs at least 0.5 kW of battery output while the site still imports
  at least 0.5 kW: evidence of unmet household demand.
- Each opportunity needs a **ten-minute block** whose highest power is no more
  than 10% above its lowest. Brief spikes, short events and low-demand averages
  cannot create a higher capability estimate.

Each continuous opportunity contributes only one completed summary: its highest
stable ten-minute power floor. After **three opportunities per direction**, their
median becomes that direction's effective modeled power. This estimates demonstrated
sustained operating capability, not a guaranteed hardware maximum. Temporary device
limits and environmental conditions can still change future output.

### Fallbacks, visibility and retention

Each of the three estimates becomes usable independently. NRG retains up to the
last **12 completed observations per parameter**, using only those within **30 days**.
A missing or expired estimate uses its own configured fallback. Manual power values
are fallbacks, not ceilings on learned values; calibration never writes device watts.

**Details** shows effective efficiency, charge/discharge power and **Battery
calibration** status. Open an estimate for its source (`configured` or `learned`),
sample count and last observation. The calibration entity explains collection status.

Switching calibration off stops collection and uses manual values without deleting
completed summaries. Restarts preserve completed learning but discard unfinished
cycles and opportunities. Changing measurement mappings, sign conventions or charge-mode
interpretation clears battery calibration only. Manual capacity/age changes do not
alter measured efficiency. After replacing hardware behind unchanged entity IDs,
use **Reset learning** before collecting a new baseline.

**Capacity, installation age, annual degradation and optional cycling cost remain
manual assumptions. No battery state-of-health result is inferred.**

## Solar alternative weight

**Purpose:** combine multiple estimates for the **same physical panels** without
counting their electricity twice.

For forecasts in the same physical coverage group:

```text
Combined forecast = sum(forecast × weight) ÷ sum(weights)
```

For example:

| Forecast for the same roof | Energy | Weight |
|---|---:|---:|
| A | 10 kWh | 1 |
| B | 14 kWh | 3 |

The result is `(10 × 1 + 14 × 3) ÷ 4 = 13 kWh`. Equal weights give a simple average.
With only one forecast, changing its weight changes nothing. A weight is not a panel
count or capacity multiplier.

After averaging alternatives, forecasts for different physical arrays are added.
A separate west roof forecast of 5 kWh would make the total 18 kWh. Weights are
explicit user choices; the whole-system solar calibration is a separate operation.

## Recorded ComEd prices

The current matching-hour price prior uses saved live running estimates, not
completed settlement rates. The unreleased hourly-normalization foundation is
not connected to learning and does not replace or clear these samples. A later
price-learning migration must update one sample per physical hour without
rewriting household, EV, solar or battery measurements. Historical backfill must
never count as live recovery evidence. See
[accounting development status](accounting.md#hourly-accounting-development-status).

## Resetting or disabling learning

Each learning switch can be turned off independently. Reset learning clears the
learned profiles, battery observations, EV sessions and forecast comparisons, while
retaining the measured cost ledger. Installation dates, manual assumptions, tariff periods and entity
selections remain saved. Disabled/nonexistent components need no calibration setup.
