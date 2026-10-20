# Free alternatives and intended community value

Home-energy planning already has capable free alternatives. NRG should be judged
by useful operation and setup experience, not an unsupported claim of uniqueness.

| Project | Relevant overlap |
|---|---|
| [Predbat](https://springfall2008.github.io/batpred/) | Battery/solar forecasting, import/export pricing, and EV coordination across many inverters. Its current license permits free personal use; installation is a separate HA app/container. |
| [EMHASS](https://github.com/davidusb-geek/emhass) | MIT-licensed whole-home energy optimization, with solar, storage, and flexible loads. Installed as an HA app/container or Python module. |
| [EV Smart Charging](https://github.com/jonasbkarlsson/ev_smart_charging) | MIT-licensed, HACS-installable price-aware EV scheduling with completion deadlines. |
| [Quiet Solar](https://github.com/tmenguy/quiet-solar) | GPL-licensed native HA solar/load coordination. Its documented priority emphasizes solar self-consumption. |
| [evcc](https://github.com/evcc-io/evcc) | Broad EV/solar/energy management; some device integrations require a sponsorship token. |

[Netzero](https://www.netzero.energy/pricing) is another relevant Powerwall/EV and
dynamic-pricing product, but its advanced automation features currently require
a paid subscription after the trial. Pricing and licenses can change; consult
the linked projects before choosing.

## NRG's intended niche

A native HA integration with UI-configured, independent supply and delivery
tariffs, separate export compensation, and coordinated optional EV/battery/solar
planning through existing HA entities. The cost model values foregone exports and
storage losses rather than assuming self-consumed solar is always free.

The present scope is USD-denominated tariffs, an optional ComEd adapter, a
Forecast.Solar adapter, one EV, and one modeled stationary-battery system. It does
not schedule arbitrary appliances or force timed battery sales to the grid.

## Evidence still needed

Software scenario tests do not establish actual household savings, broad device
compatibility, or ease of installation. A useful beta should validate setup effort,
plan comprehension, restart/update behavior, and measured execution across
independently configured homes and tariff types. Financial claims need measured
operation and appropriate bill reconciliation.

The original private household data is neither required nor distributed for this
validation. Test scenarios in this repository are invented.
