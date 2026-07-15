# Data Migration Quality Gate

Data Migration Quality Gate is a small CLI tool for validating a PostgreSQL data migration before a release or cutover. It compares a source database with a target database and returns a deployment decision that can be used by data engineers, migration teams, QA analysts, or release managers.

Milestone 1 is a working vertical slice. It validates YAML configuration, connects to two PostgreSQL databases, runs four SQL-based checks, prints a CLI summary, writes a JSON report, and exits with a meaningful status code.

```mermaid
flowchart LR
    A[(Source PostgreSQL)] --> C[Data Quality Checks]
    B[(Target PostgreSQL)] --> C
    D[YAML Configuration] --> C
    C --> E[Check Results]
    E --> F[PASS / WARN / FAIL]
    E --> G[JSON Report]
    F --> H[ALLOW / REVIEW / BLOCK]
```

## Why This Exists

Counting rows is useful, but it is not enough to prove that a migration is correct. A target table can have the same number of rows while still missing real source records, containing unexpected records, or duplicating logical migration keys. This project demonstrates those cases with deterministic PostgreSQL data.

## Source And Target

Docker Compose starts two separate PostgreSQL services:

- `source-db` on host port `5433`, database `source_db`
- `target-db` on host port `5434`, database `target_db`

Both databases contain:

- `customers`
- `accounts`
- `transactions`

Each table has a physical `row_id` primary key. Migration checks use logical keys configured in `migration.yaml`: `customer_id`, `account_id`, and `transaction_id`.

The target database intentionally does not define unique constraints or foreign keys on logical migration fields. That lets the demo represent bad migration outcomes.

## Implemented Checks

Milestone 1 implements exactly four checks:

- `row_count`: compares source and target row counts.
- `missing_keys`: finds logical keys present in source but absent from target.
- `unexpected_keys`: finds logical keys present only in target.
- `duplicate_keys`: finds duplicated logical keys in source and target separately.

Future milestones may add `schema_match`, `null_check`, `column_comparison`, `numeric_tolerance`, `allowed_values`, `referential_integrity`, `checksum`, and HTML reporting. They are not implemented yet.

## Intentional Target Defects

The target seed data contains controlled migration defects:

- `transactions`: missing source transaction keys `T006` and `T014`.
- `transactions`: unexpected target-only transaction key `T999`.
- `transactions`: duplicated logical key `T003`.
- `customers`: duplicated logical key `C003`.
- Future-check-only defects that Milestone 1 does not evaluate: changed amount for `T004`, shortened text for `T010`, `NULL` description for `T999`, account `A999` and customer `C999` references for `T999`, unsupported currency `XYZ`, and duplicate customer content.

## Install And Run

Create the databases:

```powershell
docker compose down --volumes --remove-orphans
docker compose up -d
docker compose ps
```

Set connection variables:

```powershell
$env:DQG_SOURCE_DB_URL="postgresql+psycopg://dqg_demo:dqg_demo_password@localhost:5433/source_db"
$env:DQG_TARGET_DB_URL="postgresql+psycopg://dqg_demo:dqg_demo_password@localhost:5434/target_db"
```

Install the package:

```powershell
python -m pip install -e ".[dev]"
data-quality-gate --version
```

Validate configuration only:

```powershell
data-quality-gate validate migration.yaml
```

Run the quality gate:

```powershell
data-quality-gate run migration.yaml
```

Example summary:

```text
Migration: legacy-payments-to-new-payments
Status: FAIL

Checks: 12
Passed: 7
Warnings: 1
Failed: 4

Deployment decision: BLOCK
JSON report: reports/legacy-payments-to-new-payments-<run-id>.json
```

## Exit Codes

- `0`: all checks passed, deployment decision `ALLOW`
- `1`: at least one warning and no failures, deployment decision `REVIEW`
- `2`: at least one failure, deployment decision `BLOCK`
- `3`: invalid configuration
- `4`: technical or database failure

## YAML Configuration

`migration.yaml` uses database aliases instead of connection strings:

```yaml
migration:
  name: legacy-payments-to-new-payments
  source: source_db
  target: target_db
  sample_limit: 5
```

Connection strings are read from `DQG_SOURCE_DB_URL` and `DQG_TARGET_DB_URL`. CLI errors do not print passwords or full connection strings.

## Quality Commands

```powershell
python -m ruff check .
python -m ruff format --check .
python -m mypy data_quality_gate
python -m pytest -m "not integration" -W error `
  --cov=data_quality_gate `
  --cov-branch `
  --cov-report=term-missing
```

Integration tests require running PostgreSQL containers and the two connection variables:

```powershell
python -m pytest -m integration
```

## Public Report Models

The JSON report schema version is `0.1`. It is separate from the application version.

Public models:

- `CheckStatus`: `PASS`, `WARN`, `FAIL`
- `CheckResult`: check name, table, status, discrepancy count, message, sample records, duration
- `MigrationSummary`: migration status, deployment decision, counts, timestamps, duration
- `MigrationReport`: schema version, summary, failed checks, all results

## Milestone 1 Limitations

This is not a production release. It does not generate HTML reports, does not compare individual column values, does not validate schemas, does not run in GitHub Actions, and does not publish anything to GitHub. It is intentionally small so the core gate behavior is easy to inspect and extend.
