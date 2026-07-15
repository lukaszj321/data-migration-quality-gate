"""Compare source and target table schemas."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from data_quality_gate.checks.base import CheckContext, timed_result
from data_quality_gate.exceptions import CheckExecutionError
from data_quality_gate.models import CheckResult, CheckStatus

CHECK_NAME = "schema_match"
IGNORED_COLUMNS = {"row_id"}


@dataclass(frozen=True)
class ColumnSchema:
    name: str
    data_type: str
    character_maximum_length: int | None
    numeric_precision: int | None
    numeric_scale: int | None
    is_nullable: bool

    def display(self) -> str:
        if self.data_type in {"character varying", "varchar"}:
            length = (
                ""
                if self.character_maximum_length is None
                else f"({self.character_maximum_length})"
            )
            return f"varchar{length} {'NULL' if self.is_nullable else 'NOT NULL'}"
        if self.data_type == "numeric":
            precision = self.numeric_precision
            scale = self.numeric_scale
            suffix = "" if precision is None else f"({precision},{scale or 0})"
            return f"numeric{suffix} {'NULL' if self.is_nullable else 'NOT NULL'}"
        return f"{self.data_type} {'NULL' if self.is_nullable else 'NOT NULL'}"


def run(context: CheckContext) -> CheckResult:
    started = perf_counter()
    if context.table_config is None:
        raise CheckExecutionError("schema_match requires table configuration.")

    try:
        source_schema = _load_schema(context.source_engine, context.table)
        target_schema = _load_schema(context.target_engine, context.table)
    except SQLAlchemyError as exc:
        raise CheckExecutionError("Failed to inspect table schema.") from exc

    required_columns = set(context.table_config.columns)
    samples = _compare_schemas(source_schema, target_schema, required_columns)
    discrepancy_count = len(samples)
    status = CheckStatus.PASS if discrepancy_count == 0 else CheckStatus.FAIL
    message = (
        "Source and target schemas match for configured migration columns."
        if status == CheckStatus.PASS
        else f"Found {discrepancy_count} schema differences between source and target."
    )
    return timed_result(
        check_name=CHECK_NAME,
        table=context.table,
        status=status,
        discrepancy_count=discrepancy_count,
        message=message,
        sample_records=samples[: context.sample_limit],
        started=started,
    )


def _load_schema(engine: Engine, table: str) -> dict[str, ColumnSchema]:
    sql = text(
        """
        SELECT
            column_name,
            data_type,
            character_maximum_length,
            numeric_precision,
            numeric_scale,
            is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        ORDER BY column_name
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(sql, {"table_name": table}).mappings().all()
    return {
        str(row["column_name"]): ColumnSchema(
            name=str(row["column_name"]),
            data_type=str(row["data_type"]),
            character_maximum_length=_optional_int(row["character_maximum_length"]),
            numeric_precision=_optional_int(row["numeric_precision"]),
            numeric_scale=_optional_int(row["numeric_scale"]),
            is_nullable=str(row["is_nullable"]) == "YES",
        )
        for row in rows
        if str(row["column_name"]) not in IGNORED_COLUMNS
    }


def _compare_schemas(
    source_schema: dict[str, ColumnSchema],
    target_schema: dict[str, ColumnSchema],
    required_columns: set[str],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for column in sorted(required_columns | set(source_schema)):
        source = source_schema.get(column)
        target = target_schema.get(column)
        if source is None:
            continue
        if target is None:
            samples.append(
                {
                    "column": column,
                    "issue": "missing_column_in_target",
                    "source": source.display(),
                    "target": None,
                }
            )
            continue
        samples.extend(_column_differences(source, target))

    for column in sorted(set(target_schema) - set(source_schema)):
        target = target_schema[column]
        samples.append(
            {
                "column": column,
                "issue": "unexpected_column_in_target",
                "source": None,
                "target": target.display(),
            }
        )
    return samples


def _column_differences(source: ColumnSchema, target: ColumnSchema) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    if source.data_type != target.data_type:
        differences.append(_issue(source.name, "type_mismatch", source.display(), target.display()))
    if source.character_maximum_length != target.character_maximum_length:
        differences.append(
            _issue(source.name, "length_mismatch", source.display(), target.display())
        )
    if (
        source.numeric_precision != target.numeric_precision
        or source.numeric_scale != target.numeric_scale
    ):
        differences.append(
            _issue(source.name, "numeric_mismatch", source.display(), target.display())
        )
    if source.is_nullable != target.is_nullable:
        differences.append(
            _issue(source.name, "nullability_mismatch", source.display(), target.display())
        )
    return differences


def _issue(column: str, issue: str, source: str, target: str) -> dict[str, Any]:
    return {"column": column, "issue": issue, "source": source, "target": target}


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int | float | str):
        return int(value)
    raise TypeError(f"Expected numeric schema metadata value, got {type(value).__name__}.")
