# NRG Planner

NRG Planner combines household electricity prices, optional solar forecasts,
optional home batteries and optional EVs into understandable energy advice.
Everything is configured through Home Assistant. It works with **any combination
of those components**, including a grid-only home with no EV, battery or panels.

**Start:** [Quick start](quick-start.md) · [Homeowner dashboard](homeowner-guide.md)

**Configure:** [Electricity pricing](pricing.md) · [Every setting](settings.md) ·
[Integrations and control adapters](integrations.md)

**Understand:** [Learning and calibration](learning.md) · [Exact planning method](design.md) ·
[Money and energy accounting](accounting.md)

**Install:** [Installation and optional dashboards](installation.md)

**Operate:** [Handover and recovery](operations.md)

The complete phone-friendly handbook is also installed at
**`/nrg-planner/guide.html`**, linked from Why? and Operation. No developer tools or
GitHub account are needed to read it.

## Fit the home, rather than requiring particular equipment

Under **Configure → Components**, choose whether the home has an EV, stationary
battery and/or solar. Each can be monitored without giving NRG control. Components
you turn off need no sensors, forecasts, calibration or controls, and their
homeowner cards are hidden.

- A grid-only home gets price graphs, flexible-use advice and optional meter-based costs.
- An EV-only home can use its own charger/vehicle integration without a Powerwall.
- A solar home can compare consumption with export credits without owning a battery.
- A battery home can schedule supported operating modes without solar or an EV.

Supply and delivery are independent: either can have a flat rate, your own timed
rate periods or an external HA price feed. ComEd hourly is an optional supply adapter.
All numeric tariff fields start unset; no household rates or historical profile
are bundled. Enter zero explicitly when it applies.

## Integrations and commands

NRG reads ordinary HA entities from your chosen integrations. Compatible number,
select and switch entities work directly, regardless of manufacturer. Optional HA
scripts adapt other APIs, MQTT and custom automations.

**Tessie is not required.** Teslemetry entities can be selected directly where their
capabilities match. TeslaMate can supply telemetry; charging control additionally
needs an actual command path, such as another integration or user-provided scripts.
NRG does not invent commands that a monitoring integration does not expose.

## Main screens

| Screen | Purpose |
|---|---|
| **NRG Planner → Home Energy** | Supply-plus-delivery price, best-use graph, the built-in live power-flow Sankey, applicable equipment levels, observed charging and optional costs. Read-only. |
| **Why?** | An accessible explanation and modeled energy timeline. |
| **NRG Planner settings** | Components, Operation, Tariff, Pricing periods, optional equipment settings, learning, notifications, sources, adapters and diagnostics. |
| **Settings → Devices & services → NRG Planner → Configure** | Persistent setup forms, period editor, source pickers and adapter configuration. |

Homeowner views are read-only; the administrator dashboard uses HA's admin-only
navigation. This presentation does not replace Home Assistant account/service
permissions: HA can allow authenticated users to read entity/dashboard configuration.

## Basic vocabulary

**kW** is power now. **kWh** is energy over time: a 2 kW appliance running for half
an hour uses 1 kWh. **SOC** is battery charge percentage. Rate inputs and graphs use
**cents/kWh**; total costs use dollars. External feeds currently recognize USD/kWh
or cents/kWh units.

**Observation** proposes schedules without device commands. **Control** authorizes
only the components separately enabled for NRG control. Releasing control does not
restore settings previously saved in equipment; follow the handover guide.

The planner selects a low-cost feasible plan from a bounded set of alternatives.
Forecasts and savings estimates remain distinguishable from measured power and
recorded costs. It makes no global-optimum or guaranteed-savings claim.
