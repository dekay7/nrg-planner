# Plain-language glossary

## Electricity and money

| Term | What it means |
|---|---|
| **Grid** | The public electricity network. Import means buying from it; export means sending electricity back. |
| **W / kW (power)** | How fast electricity is being used or produced right now. 1,000 watts (W) = 1 kilowatt (kW). |
| **kWh (energy)** | An amount of electricity over time. A 2 kW appliance running for half an hour uses 1 kWh. |
| **¢/kWh** | Cents for one kWh. At 12¢/kWh, using 2 kWh costs 24¢. This is an example, not a default. |
| **USD/kWh** | Dollars for one kWh. $0.12/kWh and 12¢/kWh mean the same rate. NRG's rate-entry fields use cents; total costs use dollars. |
| **Supply** | The electricity itself, priced by your supplier. |
| **Delivery** | The variable per-kWh cost of bringing electricity to your home, including applicable variable riders. Fixed monthly fees are separate. |
| **Tariff** | Your electricity pricing rules: what you pay or receive, and when. |
| **Flat rate** | A per-kWh price that stays the same across the configured hours. |
| **Time-of-use (TOU)** | Different prices for configured clock periods or weekdays, such as peak and overnight. |
| **Hourly / dynamic price** | A changing price supplied by an external feed or supported adapter. A current observation does not guarantee a future rate. |
| **Export credit** | The value credited for electricity sent to the grid. It need not match what you pay to buy electricity or be payable as cash. |
| **Export policy** | Whether equipment should permit solar exports, battery exports, or neither, where a matching control exists. It does not define a credit or schedule a sale. |
| **Net cost** | Purchase cost minus export credit for the covered time. A negative number means modeled credits exceeded purchase cost during that time. |
| **Opportunity cost** | The benefit you give up by using energy one way rather than another, such as losing an export credit when you use solar at home. |

## Cars, solar, and storage

| Term | What it means |
|---|---|
| **EV** | Electric vehicle. |
| **Stationary battery** | A home battery, distinct from the battery in an EV. |
| **SOC / state of charge** | Battery percentage: how full a home or vehicle battery reports itself to be. |
| **Capacity (kWh)** | The amount of energy a full battery can hold. A configured or age-adjusted estimate is not a measured battery-health test. |
| **Backup reserve** | The battery percentage kept out of discretionary use so it remains available for backup. |
| **A / amps (current)** | A measure used to set EV charging speed. Use a current supported by the charger and circuit. |
| **AC energy** | Electricity measured on the home's alternating-current side, including charging losses rather than only the increase stored in a vehicle battery. |
| **Round-trip efficiency** | How much energy comes back after storage. A modeled 90% round trip means about 9 kWh returned from 10 kWh put in. |
| **Degradation** | Gradual reduction in capacity or production with age. NRG's configured annual assumptions adjust predictions, not actual meter readings. |
| **Array / coverage group** | Physical solar panels represented by a forecast. Separate roofs add together; alternative forecasts for the same panels are averaged. |
| **Hold / serve / grid charge** | Battery actions: preserve stored energy, supply the home's demand, or charge using grid electricity. They must match your device's actual modes. |
| **Departure / completion buffer** | When the car is needed, and how early NRG should aim to finish. The buffer can be used if necessary to meet the actual departure. |
| **Shortfall** | Energy the model cannot deliver to the selected EV target by departure under current assumptions. |

## Home Assistant and planning

| Term | What it means |
|---|---|
| **HA / Home Assistant** | The platform hosting NRG and your equipment integrations. |
| **Integration** | Software that connects a device or service to Home Assistant. NRG is itself an integration. |
| **Entity** | One named measurement or control in HA, such as a power sensor, switch, or charge-limit number. Its identifier may look like `sensor.nrg_import_price`. |
| **Mapping** | Telling NRG which existing HA entity supplies a particular reading or control. |
| **Adapter / script** | A translation between NRG's request and the command your equipment supports. A script is an HA action sequence you supply when direct controls are insufficient. |
| **Feedback / readback** | A device's reported setting after a command. An accepted request is not proof that power changed immediately. |
| **Guard / protection input** | A selected reading that must be valid and in the expected state before commands are allowed, such as grid connection or external-controller priority. |
| **Observation** | Plans and advice without equipment commands. |
| **Control** | Operating mode permitting commands to separately enabled components when the required checks pass. |
| **Forecast / model** | A prediction of future prices, solar, demand, or equipment behavior. It can differ from what actually happens. |
| **Horizon** | The future period being compared. NRG's equipment plan looks 48 real hours ahead. |
| **Reference appliance / flexible load** | The energy and uninterrupted duration of the example task used for run-now-versus-later advice. It is not an automatically controlled appliance. |
| **Coverage** | How much time has usable readings and prices. Missing time is unknown, not zero usage or free electricity. |
| **Calibration / learning** | Improving predictions using valid local observations. It does not rewrite measurements. |
| **Pricing health** | Healthy, Degraded, Fallback or Recovering describes usable price data and selected protection, not the grid's electrical condition. |
| **Publication bridge** | A valid exact-hour ComEd forecast temporarily covering the first ten minutes of a new hour while live pricing is published. It is not a prior-hour live price. |
| **Brief published estimates** | An opt-in current-hour forecast allowance ending 60 minutes after the last verified live observation. Degraded, not live; blocks battery grid charging and cannot renew itself on refresh/restart. |
| **Price-data fallback** | Standard guarded protection or explicitly reviewed custom EV/battery actions when current pricing is unusable. Manual requests and automatic recovery have separate rules. |
| **Dependable economic horizon** | The contiguous period with the applicable price/solar coverage needed for a supported cost comparison. The physical/EV outlook can extend beyond it. |
| **Refill potential / common battery value** | Permitted solar/grid charging capacity after demand, modes and losses; insufficient potential uses a conservative reference shared by candidate schedules and advice, not a promised future refill. |
| **Forecast-priced coverage** | Newly tracked ledger time priced using a permitted published forecast. Its costs/credits are subsets of totals, not live or settled prices; old history is not retroactively classified. |
| **HACS** | Home Assistant Community Store, an optional way to install community integrations and dashboard cards. It is not required for manual installation of NRG itself. |
| **YAML / package** | A text configuration format and a grouped HA configuration file. The optional dashboard package registers NRG's bundled views. |
| **Sankey** | A flow diagram whose bands show the amount of power moving between sources and consumers. NRG's card uses HA Energy's configured live meters. |

For examples in context, see [pricing](pricing.md), the
[homeowner guide](homeowner-guide.md), and [learning](learning.md).
