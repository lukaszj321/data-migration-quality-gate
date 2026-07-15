# Data Migration Quality Gate

Data Migration Quality Gate is a small CLI tool for validating a PostgreSQL data migration before a release or cutover. It compares a source database with a target database and returns a deployment decision that can be used by data engineers, migration teams, QA analysts, or release managers.

Milestone 2A is a working vertical slice. It validates YAML configuration, connects to two PostgreSQL databases, runs SQL-based checks, prints a CLI summary, writes a JSON report, and exits with a meaningful status code.

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

Counting rows is useful, but it is not enough to prove that a migration is correct. A target table can have the same number of rows while still missing real source records, containing unexpected records, duplicating logical migration keys, breaking logical references, or storing values outside accepted business domains.

## Source And Target

Docker Compose starts two separate PostgreSQL services:

- `source-db` on host port `5433`, database `source_db`
- `target-db` on host port `5434`, database `target_db`

Both databases contain:

- `customers`
- `accounts`
- `transactions`

Each table has a physical `row_id` primary key. Migration checks use logical keys configured in `migration.yaml`: `customer_id`, `account_id`, and `transaction_id`.

The target database intentionally does not define unique constraints or foreign keys on logical migration fields. That lets the demo represent bad migration outcomes: duplicate logical keys and orphan records can exist long enough for the quality gate to detect them.

## Implemented Checks

Milestone 2A implements eight checks:

- `row_count`: compares source and target row counts.
- `missing_keys`: finds logical keys present in source but absent from target.
- `unexpected_keys`: finds logical keys present only in target.
- `duplicate_keys`: finds duplicated logical keys in source and target separately.
- `schema_match`: compares source and target table structure, including columns, data types, character lengths, numeric precision/scale, and nullability.
- `null_check`: checks configured `not_null` columns in source and target.
- `allowed_values`: checks configured finite value sets, case-sensitively, while leaving NULL handling to `null_check`.
- `referential_integrity`: checks logical parent-child references inside each database, without requiring physical FK constraints.

Not implemented yet: `column_comparison`, `numeric_tolerance`, `checksum`, HTML reporting, GitHub Actions, cloud deployment, tags, or releases.

## Demonstration Defects

The target seed data contains controlled, deterministic defects:

| Problem | Table | Record/column | Detecting check |
| ------- | ----- | ------------- | ---------------- |
| Missing migrated transaction | `transactions` | `T006` | `missing_keys` |
| Missing migrated transaction | `transactions` | `T014` | `missing_keys` |
| Unexpected target transaction | `transactions` | `T999` | `unexpected_keys` |
| Duplicate logical transaction key | `transactions` | `T003` | `duplicate_keys` |
| Duplicate logical customer key | `customers` | `C003` | `duplicate_keys` |
| Forbidden NULL | `transactions` | `T999.amount` | `null_check` |
| Unsupported currency | `transactions` | `T999.currency = XYZ` | `allowed_values` |
| Orphan account reference | `transactions` | `T999.account_id = A999` | `referential_integrity` |
| Orphan customer reference | `transactions` | `T999.customer_id = C999` | `referential_integrity` |
| Controlled schema difference | `transactions` | `description VARCHAR(255)` source vs `VARCHAR(80)` target | `schema_match` |
| Changed amount for a future column comparison | `transactions` | `T004.amount` | Not implemented yet |
| Truncated text for a future column comparison | `transactions` | `T010.description` | Not implemented yet |

The source database is intentionally clean for the configured Milestone 2A rules.

## Logical Relations

`referential_integrity` is a logical check, not a physical database constraint. PostgreSQL does not reject the demo target rows, because the target schema intentionally avoids FK constraints. The quality gate checks the configured relationships with SQL and reports orphan records as migration defects.

This distinction is useful during migrations: a target landing area may need to accept imperfect data temporarily, while the gate decides whether the release should be allowed, reviewed, or blocked.

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

Checks: 23
Passed: 14
Warnings: 1
Failed: 8

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

`migration.yaml` uses database aliases instead of connection strings. Connection strings are read from `DQG_SOURCE_DB_URL` and `DQG_TARGET_DB_URL`. CLI errors do not print passwords or full connection strings.

Example table configuration:

```yaml
tables:
  transactions:
    primary_key: transaction_id
    checks:
      - row_count
      - missing_keys
      - unexpected_keys
      - duplicate_keys
      - schema_match
      - null_check
      - allowed_values
      - referential_integrity

    columns:
      transaction_id:
        not_null: true
      account_id:
        not_null: true
        references:
          table: accounts
          column: account_id
      customer_id:
        not_null: true
        references:
          table: customers
          column: customer_id
      amount:
        not_null: true
      currency:
        not_null: true
        allowed_values:
          - PLN
          - EUR
          - USD
          - CZK
      occurred_at:
        not_null: true
```

Configuration validation rejects unsupported check names, duplicate checks, invalid sample limits, empty allow lists, duplicate allowed values, broken references, and checks that do not have the required column metadata.

## Example New Check Results

Representative JSON result snippets:

```json
{
  "check_name": "schema_match",
  "table": "transactions",
  "status": "FAIL",
  "discrepancy_count": 1,
  "sample_records": [
    {
      "column": "description",
      "issue": "length_mismatch",
      "source": "varchar(255) NULL",
      "target": "varchar(80) NULL"
    }
  ]
}
```

```json
{
  "check_name": "referential_integrity",
  "table": "transactions",
  "status": "FAIL",
  "sample_records": [
    {
      "database": "target",
      "primary_key": "T999",
      "column": "account_id",
      "value": "A999",
      "referenced_table": "accounts",
      "referenced_column": "account_id"
    }
  ]
}
```

## Quality Commands

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy data_quality_gate
.\.venv\Scripts\python.exe -m pytest -m "not integration" -W error `
  --cov=data_quality_gate `
  --cov-branch `
  --cov-report=term-missing `
  --cov-fail-under=85
```

Integration tests require running PostgreSQL containers and the two connection variables:

```powershell
.\.venv\Scripts\python.exe -m pytest -m integration
```

## Public Report Models

The JSON report schema version remains `0.1`. Milestone 2A adds new `check_name` values but does not change the existing public shape of `CheckResult`, `MigrationSummary`, or `MigrationReport`.

Public models:

- `CheckStatus`: `PASS`, `WARN`, `FAIL`
- `CheckResult`: check name, table, status, discrepancy count, message, sample records, duration
- `MigrationSummary`: migration status, deployment decision, counts, timestamps, duration
- `MigrationReport`: schema version, summary, failed checks, all results

## Milestone 2A Limitations

This is not a production release. It does not compare all column values, does not apply numeric tolerances, does not calculate checksums, does not generate HTML reports, does not run in GitHub Actions, and does not publish anything to GitHub. It is intentionally small so the quality gate behavior is easy to inspect and extend.
