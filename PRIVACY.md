# Privacy

## Repository contents

This project contains reusable source, generic documentation, and invented test
scenarios. It does not need bills, CSVs, photographs, usage exports, an existing
HA configuration, or a household's historical data to build or test.

Tariff inputs start unset. There is no embedded historical household price
profile. Generic equipment assumptions are described as assumptions and must be
reviewed for each installation. Documentation examples are illustrative.

The public maintainer identity is the GitHub account `dekay7`. Project commit
metadata should use that account's GitHub no-reply address, not a personal email.

## Runtime data stays in Home Assistant

NRG stores integration options and bounded learning/cost summaries through HA's
storage APIs. That includes user-entered rates, source mappings, hourly summaries,
EV-session estimates, and daily ledgers. These are private installation data, not
repository assets. HA backups may contain them.

NRG has no analytics, account registration, or telemetry-upload endpoint. The
optional ComEd adapter requests public pricing. The optional Forecast.Solar adapter
reads the selected integration's forecast service; that integration manages its
own provider connection. Device-control scripts and selected notification services
may use cloud services according to the user's existing integrations.

## Diagnostics and support

The standard integration diagnostics download is an allowlisted summary containing
the integration version, operating mode, component/control flags, source and sample
counts, plan availability, and whether the current buying price is known.

It excludes tariff values, tariff labels, equipment capacities, dates, departures,
notification recipients, entity/entry IDs, source labels, free-text errors, plans,
observations, and location data. It does not dump HA configuration or other
integrations' credentials.

Normal HA entities intentionally show configured rates and local planning details
to authorized HA users. Screenshots, state exports, and HA logs can therefore
contain private information even when the diagnostics summary does not. Review
those yourself before attaching them to an issue.

The local HTML handbook serves only bundled generic documentation, never user
configuration or runtime state.

## Publication protection

`tools/check_privacy.py` checks source and, with `--history`, reachable Git history
for disallowed files and common identifiers/secrets. It rejects files outside the
reviewed project layout and non-brand binary assets. CI runs the same check.

An optional, local-only deny file can add private indicators for an owner's review.
Keep that file outside the repository. Reports identify paths and finding types,
not matching secret values. Automated scans complement the owner's manual review;
they cannot recognize every form of personal information.

See [review and publication gates](docs/review.md).
