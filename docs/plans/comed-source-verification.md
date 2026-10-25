# ComEd source verification and first implementation gate

**Reviewed 2026-10-25 against `31303b8` (0.3.0). Unreleased, inactive foundation.**
This supplements the [implementation handoff](comed-hourly-accounting.md); it does
not replace its invariants or authorize deployment. Only public provider pages
were accessed. No Home Assistant instance, account, household measurements or
equipment was accessed. No recorded public price series is included in fixtures.

## Sources actually checked

1. [ComEd API documentation](https://hourlypricing.comed.com/hp-api/).
2. [ComEd live-price explanation](https://hourlypricing.comed.com/live-prices/),
   including its publicly served chart JavaScript.
3. [API terms of service](https://hourlypricing.comed.com/comed-hourly-pricing-apis-terms-of-service/),
   linked by the API documentation. These introduce the retention gate below.
4. [ComEd solar overview](https://hourlypricing.comed.com/solar/) and
   [FAQs](https://hourlypricing.comed.com/faqs/). The FAQs link the
   [2025 ratebook](https://www.comed.com/cdn/assets/v3/assets/blt3ebb3fed6084be2a/blt86ebee5fe6ed02f8/678aca912c996f726133ec1e/2025_Ratebook.pdf?branch=prod_alias).
   Relevant tariff sheet numbers, **not PDF page numbers**, are BESH 34 and 46.1,
   and POGNM 298–302.1. The accessible book is dated 2025; it is not proof that
   these are the latest sheets for every customer in October 2026. The current
   rates landing page and older net-metering FAQ URL returned a protection page,
   not usable tariff text. No attempt was made to circumvent it.
5. Bounded public GET probes of the documented `5minutefeed` API, plus the `day`
   series used by the site's own live-price chart. These are empirical checks,
   not a new contractual schema or a utility billing certification.

## Findings, confidence and implementation decisions

| Question | Evidence / remaining limit | Decision |
|---|---|---|
| What is billed hourly? | The live-price explanation says the hourly market price averages twelve five-minute prices; a running average is unfinished. BESH sheet 34 applies an hourly energy charge to each kWh in that hour. | Equal-duration mean, never consumption weights or mean-of-running-means. |
| Units | The public chart uses cents/kWh. The documented API's price values match that scale in bounded comparisons; its JSON has `millisUTC` and `price`, not a declared per-row currency. | The dedicated parser has a fixed cents/kWh source contract. Contradictory optional units reject a response. Do not use this parser for arbitrary external feeds. |
| Five-minute identity | `millisUTC` is documented UTC epoch milliseconds. Comparing start-based and end-based grouping to adjacent completed chart hours on 2026-10-19 supports **interval-start** assignment. The evening price transition distinguishes the two groupings; this is not just an equal-price example. | A label at 18:00 belongs to 18:00–18:05, not 17:55–18:00. Normalize in UTC. No changes to the existing Central hour-ending day-ahead parser. |
| Query timezone | A `202610191100`–`202610191300` probe returned UTC endpoints corresponding to 11:00–13:00 Central daylight time. The API docs specify `YYYYMMDDhhmm` but do not explicitly promise a timezone. | Central prevailing time is empirically supported, not fully specified by the API docs. No new query formatter is activated. |
| Inclusive boundaries | Documentation explicitly says inclusive. An equal-start/end probe returned that one physical interval, and adjacent range endpoints were included. | Deduplicate by UTC identity. The next hour's `:00` endpoint never becomes the previous hour's thirteenth price. |
| DST | Spring 2026 probes have UTC identities across the skipped clock hour. A fall 2025 probe was incomplete, including missing early hours. Wall-clock range parameters have no offset/fold selector. | The pure layer handles 23/25-hour days and separate repeated hours using UTC. Do not infer completeness from requested wall bounds or infer an absent fold. Catch-up request behavior across ambiguous bounds still needs validation. |
| Completed hourly source | The live-price page itself requests `/rrtp/ServletFeed?type=day&date=YYYYMMDD`. This is a real completed/indicative series, not an invented endpoint. It uses Central hour-ending chart labels and one decimal cent display precision in the inspected response. | It is **not** documented by the public JSON API as a billing-final, revisioned hourly series. Do not activate it as an authoritative settled source or silently prefer its rounded values. |
| Revisions / finality | The site explicitly says informational prices undergo a 24-hour settlement period and may be absent. Some historical hourly/five-minute comparisons differ beyond display rounding. There is no public per-row settlement flag or documented revision sequence. | Re-fetch corrections must replace price content. Twelve intervals establish complete **public data**, not finality; age alone never upgrades that claim. A certified reconciled hourly source remains unverified. |
| Precision / rounding | Inspected feed prices had decimal-cent text, but the API docs give no guaranteed precision or billing-rounding algorithm. BESH and POGNM apply additional tariff terms, with some rounding at monthly adjustment level. | Preserve decimal inputs; do not round each energy segment to cents. The foundation accepts up to twelve fractional cent digits and uses 36 significant digits for division. These are defensive implementation bounds, not provider promises. Display rounding is separate. |
| Retry / catch-up | No numeric request limit or guaranteed archive retention is stated in the checked API docs/terms. Missing historical intervals were observed. | A 48-hour recheck remains a proposed engineering bound, not a provider guarantee. Polling, retry persistence and catch-up are not activated in this stage. Respect failures/limits; a new hour is only a trigger to check completeness. |

### A newly discovered retention gate

The API terms, **Content → Prohibitions on content**, restrict building databases,
permanent copies, and cached copies beyond the cache header, unless permitted by
the owner or applicable law. The sampled successful JSON response had **no
`Cache-Control` or `Expires` lifetime**. This is not evidence of permission for a
persistent 48-hour raw cache, 28-day learned provider-price series, or 62-day
price provenance archive. The terms also restrict access to documented means;
the website's internal `day` feed is not automatically a supported new API.

**Do not activate new provider retention/polling until this is resolved.** Confirm
a permitted source/retention basis with the provider or another applicable
permission; absence of a header is not an unlimited-cache grant. This is a
technical implementation gate, not a legal opinion. The existing adapter's
caching/price-learning behavior also deserves review; this stage neither expands
nor deletes existing user data. Do not purge legacy costs/learning as a workaround.
No attempt is made to bypass provider access controls or rate limits.

A new fetch adapter should also expose response cache policy rather than discard
headers via the existing text-only helper. A persistence design must specify what
is allowed to retain (raw public intervals versus derived household accounting),
expiry, deletion and restart recovery. Owner approval of implementation scope is
not a substitute for source permission.

## Import, export and tariff scope

The tariff confirms why supply and delivery cannot be treated symmetrically:

- BESH sheet 34 defines the hourly energy charge from the ComEd-zone LMP with
  uncollectible/loss adjustments. Sheet 46.1 calls the website prices
  **indicative**, in Central prevailing time, including applicable loss and
  uncollectible adjustments. Do not blindly apply another adjustment to a public
  retail indicative price, or assume every five-minute JSON price is a certified
  bill component. Exact feed-to-tariff equivalence is not established here.
- POGNM sheet 300 defines monetary supply adjustments for NM2/NM5 using hourly
  net output/net supply and multiple supply components. Sheet 301.1 describes
  monetary energy adjustments for NM8/NM11 on a similar hourly basis.
- Sheet 301 has delivery adjustments for NM2/NM4; these are not a universal
  export entitlement. Classification depends on supply, eligibility, rebate and
  grandfathering provisions (sheets 298–298.2). Sheet 302.1 also distinguishes
  half-hour net and gross delivery measurements. A covered power integral is not
  automatically the utility's netting/metering method.
- Consequently a single generic import/export compensation assumption cannot
  implement every ComEd tariff. The user's applicable class/current sheets have
  not been established, and should not be inferred from having solar.

**Decision:** retain the configured no-credit / flat / supply-plus-adder model,
including original delivery and export terms for any later ledger reconciliation.
Do not net gross imports/exports, add delivery export credit, select a class, change
an adder or claim bill accuracy. A tariff-specific netting/credit engine requires
separate agreement and verified applicable sheets. Fixed charges, capacity,
unconfigured taxes and credit banks remain excluded. NRG corrections must not
claim to repair HA Energy history.

## Implemented review boundary: pure foundation only

`custom_components/nrg/comed.py` is intentionally **not imported by runtime**:

- Standard-library-only strict parsing of bounded, inclusive UTC-label ranges;
  finite values, alignment, source bounds and size limits. Errors contain no raw
  response content. Invalid/conflicting batches are rejected atomically.
- Immutable normalized points; deterministic deduplication; newer per-interval
  corrections override older observations. Conflicting same-time observations
  reject instead of letting response order choose a rate.
- Bounded **in-memory** hourly reconstruction with content-derived revision IDs,
  provenance and observation timestamps. It has **no serialization/Store API**.
- `unavailable`, `provisional`, and `complete_public_data` states. A complete hour
  needs the twelve correct physical intervals and an elapsed hour; never twelve
  arbitrary rows or repeated polls. There is no `final`/`reconciled` timer state.
- Equal-weight arithmetic retains signed/zero values and decimal precision.
  A partial hour's rate is only a read-only published-interval mean, not a
  replacement live/control source. Historical data cannot refresh live guards.
- At most 48 preceding physical hours plus the current hour in this prototype;
  expiry is also enforced on reads. This **engineering cap is not a grant to
  cache provider content**. No real provider data enters this cache in runtime.

`tests/test_comed_hourly.py` uses wholly invented values and independent expected
arithmetic. It covers shifted energy, unequal running means, inclusive boundaries,
missing/duplicate/out-of-order rows, corrections, stale/equal-time conflicts,
malformed/oversized/invalid-unit data, zero/negative rates, precision, bounds,
clock rollback, pruning and real 23/25-hour Central days. A standard-library-only
subprocess loads the module without HA. Existing 0.3.0 runtime behavior is unchanged.

## Remaining gates, in order

1. Review the source/retention findings; establish permission and a supported
   source/query contract, including ambiguous DST ranges and retry policy. No
   authoritative billing-final hourly series has been verified.
2. Complete package A's asynchronous single-flight polling, bounded backoff,
   catch-up and permitted persistence, with transport/restart tests. Do not
   connect historical prices to live fallback recovery.
3. Implement package B's energy-first hourly ledger and immutable legacy cutover
   in a separate reviewable change. No daily total is changed in this stage.
4. Implement C/D/E's snapshot-consistent provisional current-hour/EOD valuation,
   price-only learning revisions and coherent statuses/docs. Preserve existing
   estimated-cost subset meanings; do not migrate by guessing historical energy.
5. Keep the [planner-horizon design/reproduction](comed-planner-horizon.md) separate.
   No optimizer, control policy, cutoff or mode hysteresis is changed here.

No version bump, HA deployment/restart, equipment changes or release are part of
this stage. Commits and a draft PR package the foundation for review; they do not
activate it or authorize deployment. Full validation results belong in the
repository review record; a deliberately xfailed desired-invariance planner test
is an open gate, not a fix.
