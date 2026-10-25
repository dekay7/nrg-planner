# Separate ComEd planner-horizon review gate

**Open design gate, no correction implemented.** Companion to the
[accounting handoff](comed-hourly-accounting.md) and
[source verification](comed-source-verification.md). This is intentionally separate
from the pure provider foundation and from any later accounting migration.

## Existing regressions reviewed

Read `docs/review.md`, `tests/test_advice.py`, `tests/test_valuation.py`, the
unknown-tail/refill cases in `tests/test_planner.py`, and the tentative projection
tests. These protections are requirements, not tests to weaken for a smoother chart:

- `trusted_prefix()` prevents unknown prices/exports/solar from implying free
  future refills, changing earlier candidate scores or corrupting appliance replay.
- Replacement value uses finite permitted charging power, EV demand, losses,
  available modes, reserve/capacity and a conservative uncovered reference.
- EV candidates and advice share one valuation and comparable endpoints.
- Read-only tentative projection reprices selected cash flows; it does not select
  new equipment modes or extend control authorization.

## Deterministic invented reproduction

`tests/test_planner_horizon_handoff.py` is a separate test file. No fixtures are
copied from a provider or household. Both runs use the same decision time, solar,
prices, equipment availability and current feasible battery actions:

- Central 2026-10-19 at 18:15; no EV; house load 2 kW.
- Battery 6 kWh, 80% SOC, 20% reserve, 100% synthetic efficiency, charge 4 kW,
  discharge 3 kW. Battery control modeling is enabled; default Observation remains.
- No grid-charge capability, no export credit, no native-reserve change/fallback.
- Supply 10¢ and delivery 4¢ per kWh in every physical interval for both runs.
- Solar 8 kWh in each of the hours starting 20:00 and 21:00; covered zero elsewhere.
- Compare current live supply 10¢ against a published estimate of exactly 10¢.
  The last-live anchor is 17:30, so the estimated allowance expires at 18:30.
  At 18:15 both current price paths are usable, and hold/serve permissions agree.

Current implementation results (model outputs, **not physical equipment tests**):

| Metric | Current live | Same numerical published estimate |
|---|---:|---:|
| First requested modeled battery mode | serve | hold |
| Dependable horizon from decision time | 47.75 h | 0.25 h |
| Replacement value per stored kWh | $0.00 | $0.14 |
| Remaining imports through local midnight | 4 kWh | 7.5 kWh |
| EOD including the same invented $1 covered cost | $1.56 | $2.05 |

The :30–:00 gap is genuinely unknown for control. All following hours still have
the same known forecast prices. Nevertheless `battery_search()` defaults the
**entire** tail to hold after the first gap. The EOD cash-only reprice can fill
that monetary gap, but cannot restore the discarded later dispatch decisions.
This explains a 49-cent EOD change and an initial modeled mode change without an
underlying numerical price change. The remaining battery energy differs too;
this is not evidence of a realized saving or an equal-terminal-energy comparison.

One passing characterization test locks down the reproduction and its cash/energy
outputs. A second, **strict xfail**, states the desired current-action invariance
for this particular fixture. It is explicitly an unresolved defect. Remove/update
the characterization and xfail only as part of the separately reviewed correction;
do not treat expected failure as a passing optimizer acceptance test.

## Candidate design for separate review (not approved or implemented)

Keep the existing command authorization and conservative comparison path intact.
Investigate a distinct **read-only physical forecast policy across gaps**, rather
than changing `trusted_prefix()` to skip them:

1. Keep explicit known/unknown price masks and bounded command cutoffs unchanged.
   The current hour has one numerical valuation snapshot across physical slots.
2. Through an unknown interval, simulate only an explicit conservative baseline
   (hold, with the configured held-solar behavior; or the already selected fallback
   baseline). Do not charge from an unknown grid rate or credit hypothetical sales.
3. After the gap, evaluate known forecast islands with chronological energy carried
   through the baseline interval. Report the assumed baseline and split forecast
   coverage. No unknown-period cost becomes zero/known.
4. Keep advice/candidate scoring on mutually comparable conservative boundaries
   until a separately justified valuation can include these islands. Never count
   an unpriced refill or let optimistic tail mutations cheapen earlier actions.
5. Measure EOD cash, actual modeled modes, energy, terminal energy, feasible refills
   and confidence—not just display smoothness. Read-only forecast improvements
   alone may improve EOD without repairing the initial command-mode discontinuity.

**Unresolved design issue:** the reproduction's first action changes because the
replacement value itself loses the later solar refill information. A forecast-only
tail fix is therefore not enough to establish the requested invariance. Allowing
later islands to influence current commands would change the existing dependable-
horizon policy; it needs an explicit reviewed safety argument and, if a new control
policy is required, owner approval before changing defaults. This document does
not authorize that change.

Before implementing, decide whether the conservative valuation can safely account
for bounded future known islands while proving invariance to untrusted-tail changes,
or whether current command economics must remain conservative with an honest
remaining limitation. Do not disguise this choice by extending the allowance,
marking tentative prices known, skipping gaps, smoothing the number or adding
unconditional mode stickiness. Real fallback/reserve/EV/authorization changes must
continue to act immediately.

## Exit evidence required

- Reproduction before/after, including modes, import/export energy, cents error and
  terminal stored energy; never percentage errors near zero net cost.
- All existing unknown-tail, limited-refill, candidate/replay/advice invariance,
  battery physics, deadline and command-time permission/price-age tests unchanged.
- New gap masks, multiple islands, unavailable solar, signed/zero prices, native
  reserve, fallback, DST, partial slots and no-hindsight simulations.
- No API backfill as live recovery, no estimate-backed grid charging, no cutoff
  extension, and no safety action delayed by switching thresholds.
- Accounting-only behavior reviewed independently before any later deployment of
  changed dispatch; deployment and equipment checks still require explicit approval.
