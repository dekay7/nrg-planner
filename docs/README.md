# NRG Planner documentation

**Understand your electricity costs. Find a better time to use energy. Coordinate
the equipment you already have.**

NRG Planner is an integration for **Home Assistant**, the home-automation platform.
It combines your electricity rates with available household readings to suggest
when using energy may cost less. If you choose, it can also manage electric-vehicle
(EV) charging and a home battery through your existing Home Assistant integrations.

You can use it with any combination of an EV, home battery, and solar panels,
including **none of them**. Start with advice and add equipment as needed.

## Find what you need

| I want to… | Read this |
|---|---|
| Set it up for the first time | [Installation](installation.md), then [Quick start](quick-start.md) |
| Understand the dashboard and its advice | [Homeowner guide](homeowner-guide.md) |
| Enter my electricity rates | [Pricing](pricing.md) |
| Connect a car, home battery, or solar forecast | [Integrations and adapters](integrations.md) |
| Change a setting or check its default | [Settings reference](settings.md) |
| Charge now, change departure, or transfer control | [Everyday operation](operations.md) |
| Fix missing readings, charts, or commands | [Troubleshooting](troubleshooting.md) |
| Get a quick answer or translate an unfamiliar word | [Common questions](faq.md) · [Glossary](glossary.md) |
| Understand learning, calculations, or cost figures | [Learning](learning.md) · [Planning method](design.md) · [Accounting](accounting.md) |
| Check data use, report a security issue, or get help | [Privacy](../PRIVACY.md) · [Security reporting](../SECURITY.md) · [Support](troubleshooting.md#getting-help) |
| Compare projects or review publication readiness | [Alternatives](alternatives.md) · [Project review](review.md) |

**Read inside Home Assistant:** open **Why? → Open the complete household handbook**
or the handbook link in **NRG Planner settings → Operation**. You can also open
`/nrg-planner/guide.html` on the same Home Assistant address. For example, replace
the part after your Home Assistant address with that path.

The bundled handbook is one self-contained page. It works on phones, uses no
JavaScript or external fonts, and needs no GitHub account to read. Use your
browser's **Find in page** to search, or **Print → Save as PDF** for a reference copy.
Once loaded, reading it needs no internet connection; your Home Assistant server
must still be reachable to open it. Its text is generic, not your live settings.

## Before you begin

- **Home Assistant 2026.10.2 or newer.** This project targets 2026.10.2; newer
  releases may need compatibility checks. A standalone app is not provided.
- **An administrator account** for installing and configuring the integration.
- **Your electricity plan**, showing the variable supply and delivery prices and,
  if relevant, the credit for electricity you send to the grid.
- **Existing Home Assistant integrations** for equipment you want to monitor or
  control. NRG uses their readings and controls rather than connecting to each
  manufacturer's account itself.
- **USD pricing.** Rate inputs use cents per kilowatt-hour; other currencies are
  not currently supported.

**Current availability:** this is a private-review snapshot. Authorized reviewers
can install it manually. HACS installation becomes available after the owner
publishes and validates the repository; it is not currently in the default HACS
catalog. See [installation](installation.md) for the exact steps.

## What can it do for my home?

| Your home | What NRG can provide |
|---|---|
| Grid electricity only | Buying-price graphs and advice about moving a flexible task to a better time. A suitable power meter adds covered daily-cost estimates. |
| An EV | Monitor charging and charge level; optionally plan charging toward the selected vehicle limit before departure. No home battery is required. |
| Solar panels | Combine supported solar forecasts with demand and export credits to assess when using solar is worthwhile. No battery is required. |
| A home battery | Monitor charge level and usable-energy estimates; optionally plan supported hold, home-supply, and grid-charge modes. Solar and an EV are optional. |
| A combination | Compare their effects together, including charging losses, export credits, EV deadlines, and battery reserve. |

The current model supports **one planned EV and one stationary-battery system**.
Forecast.Solar is the supported optional solar-forecast adapter. ComEd hourly is
one optional supply-price adapter; you do not need to be a ComEd customer.

NRG gives advice for a reference appliance, such as a task that uses 1 kWh over an
hour. It does not automatically start dishwashers, laundry, heating, or other
arbitrary appliances. It does not schedule forced battery sales to the grid.

## The three ideas that make setup easier

### 1. Monitoring and control are separate choices

Enable the equipment your home has under **Configure → Components**. This shows
its readings and relevant cards. Separately choose whether NRG may control the
EV or battery. Choosing a measurement or control entity alone grants no permission.

New installations use **Observation**: NRG proposes a plan without issuing
equipment commands. **Control** permits commands only for components whose
individual control switches are enabled and whose checks pass.

For example, you can monitor a battery, let NRG manage the car, and leave the
battery under its manufacturer's controller. See [handover](operations.md#transfer-equipment-control)
when you are ready to change who controls a device.

### 2. Buying and selling electricity have different prices

Your **buying price = supply + delivery**. Supply pays for electricity; delivery
covers the variable cost of bringing it to your home. Each can be flat,
time-of-use, or an external price feed, independently of the other.

**Example only:** 8¢ supply plus 4¢ delivery means 12¢/kWh to buy. A task using
2 kWh would cost 24¢ for that energy. If an all-in feed already includes delivery,
enter **0** for separate delivery so it is not added twice.

**Export credit** is what your plan credits for electricity sent back to the grid.
Set it separately; it may be lower than the buying price. Free-looking solar can
still have a cost: using it now may mean giving up an export credit.

All numeric tariff fields begin **unset**. Blank means **unknown**, not free.
Enter zero explicitly when it really applies. The initial export basis is
**No credit**. See [pricing](pricing.md) for schedules and external feeds.

### 3. Measurements and predictions tell different stories

- **Measured:** what a meter or device reports now, such as battery percentage or
  charging power.
- **Forecast or modeled:** what may happen later, such as tomorrow's solar or a
  proposed charging start.
- **Observed cost estimate:** metered power combined with configured prices during
  the time NRG actually covered.

A plan is not proof that a device is doing it. A low partial-day cost is not proof
of a low bill. NRG reports missing coverage rather than treating it as zero.
The planner compares a bounded set of feasible schedules; it does not promise a
mathematically perfect plan or guaranteed savings.

## Where to go in Home Assistant

In this guide, **Configure → …** means start at **Settings → Devices & services →
NRG Planner → Configure**, then choose the named section.

| Screen | What you do there |
|---|---|
| **NRG Planner → Home Energy** | Read prices, household advice, live power flow, enabled equipment, and available cost estimates. This optional homeowner view is read-only. |
| **NRG Planner → Why?** | Read the reason behind the advice, inspect the modeled energy timeline, and open this handbook. |
| **NRG Planner settings** | Use the optional administrator dashboard for components, operation, rates, equipment assumptions, sources, and details. |
| **Settings → Devices & services → NRG Planner → Configure** | Use the setup forms to save rates, period schedules, measurements, forecast sources, control adapters, and notification services. Dashboards are not required. |
| **Home Assistant's Energy dashboard configuration** | Select the actual power meters used by the live power-flow diagram. NRG's own mappings do not configure that diagram. |

The optional dashboards need a one-time package setup and ApexCharts Card. Their
absence after installing the integration is expected until you complete
[dashboard installation](installation.md#optional-dashboards).

The administrator dashboard's navigation is admin-only. Homeowner views provide
read-only presentation; Home Assistant's own account and service permissions still
govern access to entities and configuration.

## Your first useful result

1. [Install](installation.md) NRG and select only the equipment you actually have.
2. Enter your supply and delivery pricing, plus export compensation if applicable.
3. Map the measurements available from your existing integrations. Price advice
   does not require a site meter; measured daily costs do.
4. Replace generic capacity, charging-power, current, and departure assumptions
   with values appropriate to your equipment and routine.
5. Read the advice and explanation in **Observation**, then compare the readings
   with your device apps or meters. Complete [control handover](operations.md)
   if you want NRG to operate the enabled devices.

Continue with the [step-by-step quick start](quick-start.md). If something is
missing, use [troubleshooting](troubleshooting.md); unfamiliar terms are in the
[plain-language glossary](glossary.md).
