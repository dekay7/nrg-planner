# Prices, costs and savings estimates

## Supply and delivery

Internal prices use USD/kWh. Rate inputs and buying-price graphs use cents/kWh,
converted once. At each instant NRG independently evaluates supply and delivery,
then adds them. Different schedules, overnight periods, weekdays, flat rates and
external intervals are supported. ComEd is an optional supply adapter only.

Published/outlook rates are not necessarily settlement values. Missing prices do
not appear as zero. A known flat or configured timed rate does not need ComEd or
an internet price feed.

Export credit is independent: selected supply plus an adder, flat credit or no
credit. Export policy controls what is permitted where a supported device control
exists; it does not itself establish compensation or a timed sale. Credit-bank,
cash-out and billing-period restrictions are not automatically reconstructed.

Fixed customer fees do not change which hour is cheaper. Capacity charges and
unconfigured taxes are excluded. The optional seasonal precaution is not an
invented per-kWh cost or a claimed capacity-dollar saving.

## Observed ledger

```text
purchase cost = positive grid kW × hours × buying price at that time
export credit = negative grid kW magnitude × hours × configured export credit
net cost      = purchase cost − export credit
```

The previous observed power is integrated only over gaps of at most three minutes.
Configured time-of-use boundaries split observed intervals exactly, including a
boundary partway through a sampling minute. Current variable-feed rates remain
contemporaneous running estimates. User rate changes do not retroactively reprice
earlier observed intervals.

Missing price/grid data contributes neither cost nor cost coverage. Negative
purchase costs and negative export credits remain signed, including adverse native
exports that occur despite a request to stop them.

A complete set of applicable power meters can calculate a missing grid reading;
the basis is identified in diagnostics. A home with no sufficient site metering
does not get a claimed zero daily bill. Price advice still works.

Restart downtime is omitted rather than filled using a new price or counter jump.
Coverage is cost-covered hours divided by real elapsed local-day hours, including
DST. First days and outage days are partial. The ledger retains 62 days; learning
reset preserves it. Daily energy figures cover observed intervals and can differ
from the built-in Energy dashboard's lifetime-counter-based totals.

## Different money figures

1. **Observed net variable cost:** grid meter readings and contemporaneous rates,
   with explicit coverage. Not a complete settled utility bill.
2. **Modeled cost through dependable coverage:** a schedule comparison ending at
   the first price or applicable solar-coverage gap, including the remaining stored
   energy's replacement value and optional cycling cost. The displayed comparison
   endpoint may be earlier than the physical/EV outlook. With no dependable coverage,
   no economic cost is claimed.
3. **Reference-appliance benefit:** modeled difference between complete start
   windows for the selected energy/duration. Baseline and appliance replay share
   that same dependable endpoint, with applicable export/storage costs. An unknown
   future export credit is not a zero credit and cannot justify a free solar refill.
   The selected window's grid rate is shown separately from its appliance cost;
   grid, direct-solar, battery-backed and mixed supply describe modeled physical
   supply, not a claim that any source is free.

No annual saving is claimed from software scenarios. Validate predicted versus
observed operation and reconcile actual bills.

## Built-in HA Energy

Use **`sensor.nrg_import_price_usd`** as the buying-price entity if configuring HA
Energy costs. It includes the selected supply and delivery methods; do not add
delivery again. Its availability follows price coverage.

Use `sensor.nrg_export_price_usd` for export compensation. Changing Energy's price
sources is a separate supported UI action; NRG does not rewrite historical records.
