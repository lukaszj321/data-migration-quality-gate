# Data Migration Quality Gate 0.1.0

Data Migration Quality Gate is a portfolio engineering project that demonstrates a local quality gate for PostgreSQL data migrations. It compares a source database with a target database, runs a configured set of data quality checks, and returns a deployment decision that can block an unsafe migration.

This is a demonstration tool, not a production-ready system.

## Highlights

- PostgreSQL source and target demo databases.
- YAML-based migration configuration.
- `data-quality-gate` command line interface.
- 31 configured demo checks across `customers`, `accounts`, and `transactions`.
- JSON report for machine-readable results.
- Standalone offline HTML report for human review.
- Docker Compose demo environment.
- Optional Docker Compose runner for the CLI container.
- Installable Python package with wheel and sdist artifacts.
- Unit and PostgreSQL integration test coverage.

## Checks

Version 0.1.0 includes 11 check types:

- `row_count`
- `missing_keys`
- `unexpected_keys`
- `duplicate_keys`
- `schema_match`
- `null_check`
- `allowed_values`
- `referential_integrity`
- `column_comparison`
- `numeric_tolerance`
- `checksum`

## Example Usage

Validate configuration:

```powershell
data-quality-gate validate migration.yaml
```

Run the quality gate:

```powershell
data-quality-gate run migration.yaml
```

Run through Docker Compose:

```powershell
docker compose --profile runner run --rm quality-gate run migration.yaml
```

Example demo result:

```text
Migration: legacy-payments-to-new-payments
Status: FAIL

Checks: 31
Passed: 18
Warnings: 1
Failed: 12

Deployment decision: BLOCK
JSON report: reports\legacy-payments-to-new-payments-<run-id>.json
HTML report: reports\legacy-payments-to-new-payments-<run-id>.html
```

The demo target database intentionally contains controlled defects, so the expected demo deployment decision is `BLOCK`.

## Reports

The JSON report is the machine-readable source of truth and keeps schema version `0.1`.

The HTML report is generated from the same report model. It is a single self-contained file with embedded CSS, no JavaScript, no CDN, and no external assets.

## Local Requirements

- Python 3.12
- Docker and Docker Compose
- PostgreSQL containers started by Docker Compose

## Limitations

- PostgreSQL only.
- No package publication to PyPI.
- No published container image or container registry integration.
- No HTTP API.
- No hosted dashboard.
- No React frontend.
- No cloud deployment.
- Not intended as a production data quality platform.
