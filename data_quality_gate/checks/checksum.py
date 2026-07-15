"""Compute deterministic table checksums for configured columns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, quote_identifier, timed_result
from data_quality_gate.checks.comparison_utils import canonical_value
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "checksum"


@dataclass(frozen=True)
class TableChecksum:
    checksum: str
    row_count: int


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None or context.table_config.checksum is None:
        raise CheckExecutionError("checksum requires checksum configuration.")

    columns = context.table_config.checksum.columns
    try:
        source = _table_checksum(context.source_engine, context.table, context.primary_key, columns)
        target = _table_checksum(context.target_engine, context.table, context.primary_key, columns)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to execute checksum.") from exc

    status = CheckStatus.PASS if source.checksum == target.checksum else CheckStatus.FAIL
    discrepancy_count = 0 if status == CheckStatus.PASS else 1
    message = (
        "Source and target checksums match."
        if status == CheckStatus.PASS
        else "Source and target checksums differ."
    )
    sample_records = [
        {
            "source_checksum": source.checksum,
            "target_checksum": target.checksum,
            "source_row_count": source.row_count,
            "target_row_count": target.row_count,
            "columns": columns,
        }
    ]
    return timed_result(
        check_name=CHECK_NAME,
        table=context.table,
        status=status,
        discrepancy_count=discrepancy_count,
        message=message,
        sample_records=sample_records[: context.sample_limit],
        started=started,
    )


def _table_checksum(
    engine: Engine, table: str, primary_key: str, columns: list[str]
) -> TableChecksum:
    row_hashes: list[tuple[str, str]] = []
    for row in _rows(engine, table, primary_key, columns):
        canonical_row = [
            {"column": column, "value": canonical_value(row[column])} for column in columns
        ]
        row_payload = json.dumps(
            canonical_row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        row_hash = hashlib.sha256(row_payload.encode("utf-8")).hexdigest()
        key_payload = json.dumps(
            canonical_value(row["primary_key"]),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        row_hashes.append((key_payload, row_hash))

    ordered_hashes = [row_hash for _, row_hash in sorted(row_hashes)]
    payload = json.dumps(ordered_hashes, separators=(",", ":"))
    checksum_value = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return TableChecksum(checksum=checksum_value, row_count=len(row_hashes))


def _rows(engine: Engine, table: str, primary_key: str, columns: list[str]) -> list[dict[str, Any]]:
    quoted_table = quote_identifier(table)
    quoted_key = quote_identifier(primary_key)
    selected_columns = ",\n            ".join(
        f"{quote_identifier(column)} AS {quote_identifier(column)}" for column in columns
    )
    sql = text(
        f"""
        SELECT
            {quoted_key} AS primary_key,
            {selected_columns}
        FROM {quoted_table}
        ORDER BY {quoted_key} IS NULL, {quoted_key}, row_id
        """
    )
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(sql).mappings().all()]
