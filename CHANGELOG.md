# Changelog

## [0.1.1] - 2026-07-16

### Fixed

- Preserved consistent logical-key ordering when comparing PostgreSQL source and target streams.
- Fixed false missing or unexpected key results for numeric logical keys such as `1`, `2`, `10`, and `11`.
- Fixed row pairing for `column_comparison` and `numeric_tolerance` when logical keys are numeric.

### Tests

- Added PostgreSQL integration coverage for integer logical keys.

## [0.1.0] - 2026-07-16

### Added

- PostgreSQL source and target demo environment.
- YAML configuration validated with Pydantic.
- `data-quality-gate` CLI.
- 11 quality check types:
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
- `PASS`, `WARN`, and `FAIL` check statuses.
- `ALLOW`, `REVIEW`, and `BLOCK` deployment decisions.
- JSON migration report.
- Standalone offline HTML migration report.
- Deterministic demo data with controlled target defects.
- Unit and PostgreSQL integration tests.
- Docker Compose demo environment.
- Installable Python package with wheel and sdist build support.

### Security

- Secret redaction for user-facing CLI diagnostics.
- Safe SQL identifier validation for configured tables, columns, and references.
- HTML escaping for report values, messages, and samples.
- Safe report filename generation with path traversal and Windows reserved-name protection.
