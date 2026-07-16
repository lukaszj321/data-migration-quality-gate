from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from data_quality_gate.checks.comparison_utils import ComparableRows, comparable_row_pairs


def test_comparable_row_pairs_preserves_integer_ordering() -> None:
    result = list(comparable_row_pairs(_rows([1, 2, 10, 11]), _rows([1, 2, 10, 11])))

    assert [item.source["primary_key"] for item in result if isinstance(item, ComparableRows)] == [
        1,
        2,
        10,
        11,
    ]
    assert not [item for item in result if isinstance(item, tuple)]


def test_comparable_row_pairs_reports_single_missing_integer_key() -> None:
    result = list(comparable_row_pairs(_rows([1, 2, 10, 11]), _rows([1, 10, 11])))

    assert _paired_keys(result) == [1, 10, 11]
    assert _side_only_keys(result, "source_only") == [2]
    assert _side_only_keys(result, "target_only") == []


def test_comparable_row_pairs_reports_single_unexpected_integer_key() -> None:
    result = list(comparable_row_pairs(_rows([1, 2, 10, 11]), _rows([1, 2, 3, 10, 11])))

    assert _paired_keys(result) == [1, 2, 10, 11]
    assert _side_only_keys(result, "source_only") == []
    assert _side_only_keys(result, "target_only") == [3]


def test_comparable_row_pairs_preserves_text_key_regression() -> None:
    result = list(
        comparable_row_pairs(_rows(["A001", "A002", "A010", "A011"]), _rows(["A001", "A010"]))
    )

    assert _paired_keys(result) == ["A001", "A010"]
    assert _side_only_keys(result, "source_only") == ["A002", "A011"]
    assert _side_only_keys(result, "target_only") == []


def _rows(keys: list[Any]) -> Iterator[dict[str, Any]]:
    return iter({"primary_key": key, "value": f"value-{key}"} for key in keys)


def _paired_keys(items: list[ComparableRows | tuple[str, dict[str, Any]]]) -> list[Any]:
    return [item.source["primary_key"] for item in items if isinstance(item, ComparableRows)]


def _side_only_keys(
    items: list[ComparableRows | tuple[str, dict[str, Any]]], side: str
) -> list[Any]:
    return [item[1]["primary_key"] for item in items if isinstance(item, tuple) and item[0] == side]
