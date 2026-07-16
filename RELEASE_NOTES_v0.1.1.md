# Data Migration Quality Gate 0.1.1

Data Migration Quality Gate 0.1.1 is a compatible patch release for 0.1.0. It fixes logical-key ordering for PostgreSQL streams when the configured migration key is numeric.

## Bug Fix

The previous implementation ordered rows in PostgreSQL by the native column type, then converted logical keys to Python strings while merging source and target streams. For integer keys, PostgreSQL returns values in numeric order, such as `1`, `2`, `10`, and `11`, while string comparison would order the same values as `"1"`, `"10"`, `"11"`, and `"2"`.

That mismatch could produce false missing or unexpected keys, skip valid comparable records, or attach value differences to the wrong logical key.

The bundled demo data used text keys such as `C003`, `A001`, and `T014`, so it did not expose this problem.

## Resolution

The patch preserves the native logical-key values returned from PostgreSQL and compares those native values while merging the already ordered source and target streams. This keeps the implementation streaming, avoids loading full tables for key matching, and keeps the report contract unchanged.

## Tests

- Added unit regression coverage for integer logical keys ordered as `1`, `2`, `10`, and `11`.
- Added unit regression coverage for missing and unexpected integer keys.
- Preserved text-key regression coverage for keys such as `A001`, `A002`, `A010`, and `A011`.
- Added PostgreSQL integration coverage for `INTEGER` logical keys across `missing_keys`, `unexpected_keys`, `column_comparison`, and `numeric_tolerance`.
- Added integration coverage proving value differences remain attached to the correct numeric keys.

## Compatibility

- JSON report schema remains `0.1`.
- No configuration changes are required.
- No new check types were added.
- `v0.1.1` is a compatible patch release for `v0.1.0`.

## Limitations

- PostgreSQL only.
- No package publication to PyPI.
- No published container image or container registry integration.
- No HTTP API.
- No hosted dashboard.
- No React frontend.
- No cloud deployment.
- Full-table checksum comparison is deterministic but not optimized for multimillion-row datasets.
- Not intended as a production data quality platform.
