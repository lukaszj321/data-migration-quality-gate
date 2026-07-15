from __future__ import annotations

from sqlalchemy import Engine, text

from data_quality_gate.checks import duplicate_keys, missing_keys, row_count, unexpected_keys
from data_quality_gate.checks.base import CheckContext
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


def _context(source: Engine, target: Engine, sample_limit: int) -> CheckContext:
    return CheckContext(
        source_engine=source,
        target_engine=target,
        table="items",
        primary_key="item_id",
        sample_limit=sample_limit,
    )


def _insert(engine: Engine, keys: list[str]) -> None:
    with engine.begin() as connection:
        for key in keys:
            connection.execute(
                text("INSERT INTO items (item_id, payload) VALUES (:key, :payload)"),
                {"key": key, "payload": f"payload-{key}"},
            )
