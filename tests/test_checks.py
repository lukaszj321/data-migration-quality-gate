from __future__ import annotations

from sqlalchemy import Engine, text

from data_quality_gate.checks import (
    allowed_values,
    checksum,
    column_comparison,
    duplicate_keys,
    missing_keys,
    null_check,
    numeric_tolerance,
    referential_integrity,
    row_count,
    schema_match,
    unexpected_keys,
)
from data_quality_gate.checks.base import CheckContext
from data_quality_gate.checks.schema_match import ColumnSchema
from data_quality_gate.config import CheckName, ColumnConfig, ReferenceConfig, TableConfig
from data_quality_gate.models import CheckStatus


def test_row_count_detects_mismatch(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["B", "A"])
    _insert(target, ["A"])

    result = row_count.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.sample_records == [{"source_count": 2, "target_count": 1, "difference": -1}]


def test_missing_keys_limits_and_sorts_samples(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["C", "A", "B", "D"])
    _insert(target, ["D"])

    result = missing_keys.run(_context(source, target, sample_limit=2))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert result.sample_records == [{"item_id": "A"}, {"item_id": "B"}]


def test_unexpected_keys_warns_and_sorts_samples(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["B"])
    _insert(target, ["C", "A", "B"])

    result = unexpected_keys.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.WARN
    assert result.discrepancy_count == 2
    assert result.sample_records == [{"item_id": "A"}, {"item_id": "C"}]


def test_duplicate_keys_distinguishes_source_and_target(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "A", "B"])
    _insert(target, ["C", "C", "C"])

    result = duplicate_keys.run(_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 2
    assert result.sample_records == [
        {"database": "source", "item_id": "A", "duplicate_count": 2},
        {"database": "target", "item_id": "C", "duplicate_count": 3},
    ]


def test_empty_tables_pass(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    context = _context(source, target, sample_limit=5)

    assert row_count.run(context).status == CheckStatus.PASS
    assert missing_keys.run(context).status == CheckStatus.PASS
    assert unexpected_keys.run(context).status == CheckStatus.PASS
    assert duplicate_keys.run(context).status == CheckStatus.PASS


def test_null_check_detects_nulls_with_limit(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B"])
    _insert(target, ["C"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id IN ('A', 'B')"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id = 'C'"))

    result = null_check.run(_configured_context(source, target, sample_limit=2))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 3
    assert len(result.sample_records) == 2
    assert result.sample_records[0]["database"] == "source"


def test_allowed_values_detects_bad_values_and_ignores_null(
    sqlite_pair: tuple[Engine, Engine],
) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B"])
    _insert(target, ["C", "D"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'BAD' WHERE item_id = 'A'"))
        connection.execute(text("UPDATE items SET payload = NULL WHERE item_id = 'B'"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'ZZZ' WHERE item_id = 'C'"))
        connection.execute(text("UPDATE items SET payload = 'OK' WHERE item_id = 'D'"))

    result = allowed_values.run(_configured_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 2
    assert [sample["value"] for sample in result.sample_records] == ["BAD", "ZZZ"]


def test_referential_integrity_detects_orphans(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE parents (
                        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        parent_id VARCHAR(32)
                    )
                    """
                )
            )
    with source.begin() as connection:
        connection.execute(text("INSERT INTO parents (parent_id) VALUES ('P1')"))
        connection.execute(text("INSERT INTO items (item_id, payload) VALUES ('A', 'NOPE')"))
    with target.begin() as connection:
        connection.execute(text("INSERT INTO parents (parent_id) VALUES ('P1'), ('P1')"))
        connection.execute(text("INSERT INTO items (item_id, payload) VALUES ('B', 'P1')"))

    result = referential_integrity.run(_reference_context(source, target))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 1
    assert result.sample_records[0]["database"] == "source"


def test_schema_match_compares_loaded_schemas(
    monkeypatch, sqlite_pair: tuple[Engine, Engine]
) -> None:  # type: ignore[no-untyped-def]
    source, target = sqlite_pair
    source_schema = {
        "id": ColumnSchema("id", "character varying", 20, None, None, False),
        "amount": ColumnSchema("amount", "numeric", None, 10, 2, True),
        "payload": ColumnSchema("payload", "character varying", 255, None, None, True),
    }
    target_schema = {
        "id": ColumnSchema("id", "character varying", 20, None, None, True),
        "payload": ColumnSchema("payload", "character varying", 80, None, None, True),
        "extra": ColumnSchema("extra", "text", None, None, None, True),
    }
    monkeypatch.setattr(
        schema_match,
        "_load_schema",
        lambda engine, table: source_schema if engine is source else target_schema,
    )

    result = schema_match.run(_schema_configured_context(source, target))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 4
    assert [sample["issue"] for sample in result.sample_records] == [
        "missing_column_in_target",
        "nullability_mismatch",
        "length_mismatch",
        "unexpected_column_in_target",
    ]


def test_column_comparison_detects_exact_differences_and_skips_uncomparable_keys(
    sqlite_pair: tuple[Engine, Engine],
) -> None:
    source, target = sqlite_pair
    _insert(source, ["A", "B", "D", "D"])
    _insert(target, ["A", "C", "D", "D"])
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'changed' WHERE item_id = 'A'"))

    result = column_comparison.run(_exact_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 1
    assert result.sample_records == [
        {
            "primary_key": "A",
            "column": "payload",
            "source_value": "payload-A",
            "target_value": "changed",
        }
    ]
    assert "duplicate_source=1" in result.message
    assert "duplicate_target=1" in result.message


def test_column_comparison_treats_both_nulls_as_equal(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["A"])
    _insert(target, ["A"])
    for engine in (source, target):
        with engine.begin() as connection:
            connection.execute(text("UPDATE items SET payload = NULL WHERE item_id = 'A'"))

    result = column_comparison.run(_exact_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.PASS


def test_numeric_tolerance_uses_decimal_boundaries(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _add_amount_column(source)
    _add_amount_column(target)
    _insert(source, ["A", "B", "C"])
    _insert(target, ["A", "B", "C"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET amount = '10.00'"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET amount = '10.005' WHERE item_id = 'A'"))
        connection.execute(text("UPDATE items SET amount = '10.01' WHERE item_id = 'B'"))
        connection.execute(text("UPDATE items SET amount = '10.02' WHERE item_id = 'C'"))

    result = numeric_tolerance.run(_numeric_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.discrepancy_count == 1
    assert result.sample_records[0]["primary_key"] == "C"
    assert result.sample_records[0]["difference"] == "0.02"


def test_numeric_tolerance_handles_null_mismatch(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _add_amount_column(source)
    _add_amount_column(target)
    _insert(source, ["A"])
    _insert(target, ["A"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET amount = NULL WHERE item_id = 'A'"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET amount = '1.00' WHERE item_id = 'A'"))

    result = numeric_tolerance.run(_numeric_context(source, target, sample_limit=5))

    assert result.status == CheckStatus.FAIL
    assert result.sample_records[0]["difference"] is None


def test_checksum_detects_changes_and_is_deterministic(sqlite_pair: tuple[Engine, Engine]) -> None:
    source, target = sqlite_pair
    _insert(source, ["B", "A"])
    _insert(target, ["A", "B"])

    first = checksum.run(_checksum_context(source, target))
    second = checksum.run(_checksum_context(source, target))

    assert first.status == CheckStatus.PASS
    assert first.sample_records[0]["source_checksum"] == first.sample_records[0]["target_checksum"]
    assert first.sample_records == second.sample_records

    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'different' WHERE item_id = 'A'"))

    changed = checksum.run(_checksum_context(source, target))

    assert changed.status == CheckStatus.FAIL
    assert changed.discrepancy_count == 1


def test_checksum_distinguishes_naive_string_collision(
    sqlite_pair: tuple[Engine, Engine],
) -> None:
    source, target = sqlite_pair
    _insert(source, ["A"])
    _insert(target, ["A"])
    with source.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'ab|c' WHERE item_id = 'A'"))
    with target.begin() as connection:
        connection.execute(text("UPDATE items SET payload = 'a|bc' WHERE item_id = 'A'"))

    result = checksum.run(_checksum_context(source, target))

    assert result.status == CheckStatus.FAIL


def _context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
    )


def _configured_context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.NULL_CHECK, CheckName.ALLOWED_VALUES],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(not_null=True, allowed_values=["OK"]),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _reference_context(source: Engine, target: Engine) -> CheckContext:
    parent_config = TableConfig(
        primary_key="parent_id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={"parent_id": ColumnConfig(not_null=True)},
    )
    child_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.REFERENTIAL_INTEGRITY],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(
                references=ReferenceConfig(table="parents", column="parent_id")
            ),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=5,
        table_config=child_config,
        all_tables={"parents": parent_config, "items": child_config},
    )


def _schema_configured_context(source: Engine, target: Engine) -> CheckContext:
    table_config = TableConfig(
        primary_key="id",
        checks=[CheckName.SCHEMA_MATCH],
        columns={
            "id": ColumnConfig(not_null=True),
            "amount": ColumnConfig(),
            "payload": ColumnConfig(),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="id",
        sample_limit=10,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _exact_context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.COLUMN_COMPARISON],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "payload": ColumnConfig(compare=True),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _numeric_context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    table_config = TableConfig(
        primary_key="item_id",
        checks=[CheckName.NUMERIC_TOLERANCE],
        columns={
            "item_id": ColumnConfig(not_null=True),
            "amount": ColumnConfig(compare=True, tolerance="0.01"),
        },
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _checksum_context(source: Engine, target: Engine) -> CheckContext:
    table_config = TableConfig.model_validate(
        {
            "primary_key": "item_id",
            "checks": [CheckName.CHECKSUM],
            "columns": {"item_id": {}, "payload": {}},
            "checksum": {"columns": ["item_id", "payload"]},
        }
    )
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=5,
        table_config=table_config,
        all_tables={"items": table_config},
    )


def _insert(engine: Engine, keys: list[str]) -> None:
    with engine.begin() as connection:
        for key in keys:
            connection.execute(
                text("INSERT INTO items (item_id, payload) VALUES (:key, :payload)"),
                {"key": key, "payload": f"payload-{key}"},
            )


def _add_amount_column(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE items ADD COLUMN amount NUMERIC"))
