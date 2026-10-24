# Synthetic simulation and stress testing

**Available in the 0.3.0 source repository.** This is an offline developer tool,
not a dashboard, HA service or tool bundled in a HACS component download.
It asks: **if these forecasts were issued and this invented household behaved
this way, what decisions would NRG propose, and what would happen?**

## Safety, permissions and defaults

The simulator needs no Home Assistant instance, credentials, entity mappings or
household exports. It loads the production planning and learning modules without
loading the integration's HA entry point, runtime or command writer. It makes no
network requests and reads no HA storage or user options. Its only optional write
is the report path you explicitly choose. Reports contain invented data only.

Normal **Observation**, control permissions, notifications, settings and learning
are unchanged. The synthetic setup grants planning permission for its invented
EV and battery, and enables all learning, including battery calibration, **inside
the simulation only**. The real integration's battery-learning default remains
Off. `--no-learning` uses configured assumptions instead of learned estimates.
Do not use a simulation report as authorization to enable live controls.

## Run it

From a source checkout, using Python 3.14 (the project's tested version):

```sh
# List the stress scenarios. This tool uses only the Python standard library.
python -B tools/simulate.py --list

# One day, seven invented training days, reproducible seed; include all decisions.
python -B tools/simulate.py --scenario baseline --seed 42 --trace \
  --output local/simulation-baseline.json

# A broader sweep: every scenario, three consecutive seeds, two real days each.
python -B tools/simulate.py --scenario all --seed 42 --runs 3 --days 2 \
  --output local/simulation-suite.json

# Compare learned estimates with manual assumptions under the SAME synthetic truth.
python -B tools/simulate.py --scenario slow-ev --seed 42 --days 2 \
  --output local/slow-ev-learned.json
python -B tools/simulate.py --scenario slow-ev --seed 42 --days 2 --no-learning \
  --output local/slow-ev-manual.json

# Cold start: no prior synthetic observations.
python -B tools/simulate.py --scenario solar-miss --warmup-days 0 --trace \
  --output local/solar-cold-start.json
```

`local/` is ignored by git. Reports can be large with `--trace`; they are not
written unless `--output` is provided. Normal source/version metadata is included
so reports from changed code can be distinguished. The source hash covers the
simulator and the pure planning/learning dependencies, not the entire repository.

Defaults: `baseline`, seed 1, one run, one real 24-hour day, seven training days,
learning enabled, no trace and no output file. `--runs` accepts 1–100, `--days`
1–30 and `--warmup-days` 0–28. Repeated runs use consecutive seeds. A full suite
can take several minutes; start with one day/scenario before a large sweep.

## Scenarios

| Name | Stress applied |
|---|---|
| `baseline` | Morning/evening demand, a daylight solar shape, night/evening prices and independent measurement/forecast variation. |
| `volatile-prices` | Negative midday prices and an unexpected expensive evening. |
| `solar-miss` | Optimistic solar forecasts, followed by an unforecast afternoon cloud collapse. |
| `demand-spike` | An unforecast 4 kW evening load. |
| `price-gap` | Current and future supply unavailable for four hours, then restored. |
| `solar-gap` | Six hours of missing solar forecast coverage, then restored. |
| `slow-ev` | Actual charging power is half the configured value; actual AC energy per SOC point is higher. |
| `battery-mismatch` | Actual capacity, efficiency and charge/discharge power are below the configured assumptions. |
| `no-grid-charge` | No supported battery grid charging. |
| `grid-only` | No EV, battery or solar; advice and electricity costs still work. |
| `dst-spring` | Chicago spring clock jump with real elapsed energy/time. |
| `dst-fall` | Chicago repeated autumn hour, including both UTC instants. |

All scenarios use invented rates and equipment—not a model of a particular home.
The initial simulated car is connected at 45%, targets 80%, leaves at 08:00 and
returns at 18:00 with an invented commute resetting SOC to 45%. A battery starts
at 60% and retains a 20% reserve. The baseline policy charges the EV immediately
when connected and lets the battery serve demand without grid charging; it is
not constrained to the planner's preferred charging window. Both policies see
the same actual household, weather, equipment and prices, but have independent
battery/EV states.

Training also uses synthetic measurements and a simple routine. It is not counted
in evaluation costs. More training does not promise enough qualifying battery
cycles or power opportunities: per-parameter learning may correctly remain on its
configured fallback. The capacity-mismatch scenario cannot be fixed by battery
calibration, which intentionally does not infer capacity.

## How it works

1. A deterministic generator creates the actual demand, solar and price streams.
   Separate forecast streams use a generic daily shape plus forecast noise/bias;
   they do **not** read future actual measurements or unexpected load/cloud shocks.
   Seeds/streams do not depend on policy calls or how often replanning occurs.
2. Optional warm-up observations pass through the real coverage-gated household,
   solar, EV and passive battery learners. Future solar forecasts are frozen via
   the production statistics API before the measured hour, not revised afterward.
3. Every fifteen real minutes the actual `plan()` function receives current
   synthetic telemetry, the issued forecasts and the previous plan. Supply uses
   the production external-price lookup, separate flat delivery and flat solar
   export credit. Missing coverage remains unknown.
4. Only the current dated decision is applied to an independent AC energy model.
   This plant does **not** call the planner's physical transition function. It has
   its own true capacity, losses and power limits and honors EV current/fractional
   stops. Actual outcomes become later observations; a perfect forecast is never
   sent back to the policy.
5. Forecasts for 1-, 6- and 24-hour leads are frozen at issue and scored only once
   their target interval is observed. Post-hoc advice counterfactuals never affect
   the rolling policy, statistics or future truth.

Days are **24 real hours**, not local calendar days. A DST run can therefore end
at a different local clock hour. A one-day evaluation has no observed 24-hour-lead
outcomes; use at least two days for that metric. Forecasts beyond the evaluation
end are not scored, and an unfinished future departure is not counted as missed.

## Read the results

The console shows each run's cash costs, missed EV departures, invariant failures,
one-hour forecast MAE and final stored energy. JSON provides the full results:

| Report section | Meaning |
|---|---|
| `source`, `scenario`, `seed`, `truth_parameters`, `model_assumptions` | Reproduction metadata, true equipment and configured starting assumptions. Preserve source hash and Python version when comparing runs. |
| `policies` | Actual synthetic purchases minus solar export credits, imported/exported/EV energy, battery discharge, final battery energy and EV SOC; departure shortfalls in AC kWh. A missed departure means more than 0.1 kWh short. |
| `forecast_errors` | MAE, RMSE and signed bias at each lead. Positive bias means overprediction. Demand/solar are kW; supply is USD/kWh. Console supply MAE is converted to cents/kWh. |
| `one_step_errors` | Issued current household/solar predictions and next battery SOC versus the realized interval; manual house fallback and uncalibrated solar are separate references. SOC error is in percentage points. |
| `samples`, `missing` | Covered prediction counts versus unknown forecasts. Missing is not a zero prediction, and missing forecasts cannot make MAE look perfect without visible coverage loss. |
| `learning_before`, `learning_after` | Observation counts, EV/solar estimates and per-parameter battery sample/source status. These are simulated statistics, never saved to HA. |
| `decisions` | Replan count, battery-mode changes, EV on/off changes, limited advice and missing current price/solar coverage. Changes count interval-to-interval proposals, not HA service calls. |
| `invariant_violations` | Physical AC/stored-energy balance, reserve/capacity/power/export bounds and grid-charge constraints; plus audits of requested modes/current/SOC/coverage so plant clamping cannot conceal an invalid request. |
| `advice` | Hourly sampled wait recommendations whose complete task fits the observed evaluation and dependable horizon; predicted savings versus post-hoc fixed-plan outcomes, and waits that cost over $0.001 more than starting now. |
| `trace` | Optional dated decisions, known/unknown coverage, forecasts, candidate, EV current/stop/deadline, predicted shortfall, actual state, advice and interval physical/cash outcomes. |

For advice, replay the **issued modes and EV schedule** separately with the task
now and later, using the synthetic actuals and a shared initial state. Compare
the replay cash costs with remaining energy valued at that plan's terminal rate
at the same truncated dependable/evaluation boundary. This is a fixed-schedule
counterfactual, **not** the outcome of later replanning with an actual appliance.
Only waits are evaluated; it is not an exhaustive recommendation-regret measure.
Limited-confidence advice remains labeled limited in the report.

**Do not rank policies by cash cost alone.** A car that misses departure or a battery
left emptier can look cheaper. Inspect shortfalls, final battery/EV state, forecast
coverage and physical failures together. Policy cash costs do not include terminal
battery value or a utility bill's fixed charges/taxes; the reference baseline is
not optimal. No difference in these invented costs demonstrates household savings.

## Failures, recovery and limits

- Exit **0**: simulation completed with no invariant violations. It does not mean
  forecasts were accurate, all departures succeeded or the plan was optimal.
- Exit **1**: one or more physical/request invariants failed. JSON and trace identify
  the time/policy/check. Keep the scenario, seed and source hash for regression work.
- Invalid CLI values exit **2**. File permission errors or unexpected code errors
  are surfaced; the tool does not silently treat a partial report as success.
- Price/solar gaps restore coverage at their synthetic end; the next plan can
  resume economic decisions. This tests the pure planner's conservative response,
  **not** HA's fallback activation/recovery state machine.
- The plant assumes ideal immediate native-mode response and minute-resolution
  learning observations reconstructed within each simulated quarter-hour. It
  does not reproduce telemetry latency, command failures, device ownership,
  protection-event behavior, provider parsers, ComEd publication rules, battery
  aging, outages, script adapters or the HA scheduler/writer. Existing integration
  and independent-oracle tests remain necessary for those areas.
- No global-optimum or perfect-foresight policy is claimed. Synthetic distributions
  cannot prove general accuracy, real-world safety, hardware capability or savings.

For implementation details see [the planning method](design.md),
[learning](learning.md) and [cost accounting](accounting.md). Add scenarios and
regressions in `tools/simulate.py` and `tests/test_simulation.py`, using invented
fixtures only. No release is published by running this tool.
