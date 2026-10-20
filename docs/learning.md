# What the learning and calibration controls do

These controls improve estimates from observed data. They never alter recorded
meter values, appliance behavior, battery settings or a vehicle's selected limit.
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

Missing meters, gaps and counter resets do not create learned sessions. Without a
valid estimate—or with the switch off—NRG uses the fallback kWh/point and charging
power you entered. **No EV battery degradation percentage or health estimate is made.**

## Learn household demand

**Purpose:** predict ordinary household usage so storage and flexible-use advice
can work around daily life.

NRG integrates the home power meter. If an EV is installed and separately measured,
it subtracts car charging; otherwise it can learn while the car is known not to be
charging. A home without an EV uses the whole-home reading directly.

An hour needs at least **80% valid coverage**. Missing time is not learned as zero.
Impossible/inconsistent meter combinations pause the relevant learning rather than
creating a false zero-house baseline.

It keeps up to **28 days** of hourly summaries, compares matching clock hours, and
gives each older matching observation **0.9×** the weight of the next newer one.
After three matching observations, weekdays/weekends can have their own profile.

Example: if evenings repeatedly use more power than afternoons, the forecast
reserves more energy for those evenings. An unfamiliar hour still uses your fallback.
It predicts patterns rather than identifying individual appliances or controlling
comfort settings. Turning learning off uses your explicit house-demand estimate.

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

## Resetting or disabling learning

Each learning switch can be turned off independently. Reset learning clears the
learned profiles, EV sessions and forecast comparisons, while retaining the measured
cost ledger. Installation dates, manual assumptions, tariff periods and entity
selections remain saved. Disabled/nonexistent components need no calibration setup.
