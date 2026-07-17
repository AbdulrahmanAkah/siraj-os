"""Evaluation utilities for human-reviewed Shamela gold annotations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


PENDING_HUMAN_ANNOTATION = "PENDING_HUMAN_ANNOTATION"


@dataclass(frozen=True)
class MatchCounts:
    expected: int
    actual: int
    exact_true_positive: int
    overlap_true_positive: int


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _span(item: dict[str, Any]) -> tuple[int, int] | None:
    value = (
        item.get("span")
        or item.get("original_text_span")
        or item.get("evidence_span")
    )
    if not isinstance(value, dict):
        return None
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError):
        return None
    return (start, end) if 0 <= start < end else None


def _overlaps(
    left: tuple[int, int] | None,
    right: tuple[int, int] | None,
) -> bool:
    if left is None or right is None:
        return False
    return max(left[0], right[0]) < min(left[1], right[1])


def _entity_label(item: dict[str, Any]) -> str:
    return str(
        item.get("normalized_surface_form")
        or item.get("surface")
        or item.get("text")
        or ""
    ).strip()


def _types(item: dict[str, Any]) -> set[str]:
    value = (
        item.get("entity_types")
        or item.get("expected_entity_types")
        or item.get("entity_type_candidate")
        or item.get("entity_type")
        or []
    )
    if isinstance(value, str):
        return {value}
    return {str(entry) for entry in value}


def _typed_label(field: str) -> Callable[[dict[str, Any]], str]:
    def resolve(item: dict[str, Any]) -> str:
        return str(item.get(field, "")).strip()

    return resolve


def _greedy_match(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    label: Callable[[dict[str, Any]], str],
    *,
    exact: bool,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    used: set[int] = set()
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for expected_item in expected:
        expected_span = _span(expected_item)
        expected_label = label(expected_item)
        for index, actual_item in enumerate(actual):
            if (
                index in used
                or label(actual_item) != expected_label
                or actual_item.get("_evaluation_key")
                != expected_item.get("_evaluation_key")
            ):
                continue
            actual_span = _span(actual_item)
            span_matches = (
                expected_span == actual_span
                if exact
                else _overlaps(expected_span, actual_span)
            )
            if span_matches:
                used.add(index)
                matches.append((expected_item, actual_item))
                break
    return matches


def _score_collection(
    expected: list[dict[str, Any]],
    actual: list[dict[str, Any]],
    label: Callable[[dict[str, Any]], str],
) -> tuple[dict[str, Any], list[tuple[dict[str, Any], dict[str, Any]]]]:
    exact_matches = _greedy_match(
        expected,
        actual,
        label,
        exact=True,
    )
    overlap_matches = _greedy_match(
        expected,
        actual,
        label,
        exact=False,
    )
    counts = MatchCounts(
        expected=len(expected),
        actual=len(actual),
        exact_true_positive=len(exact_matches),
        overlap_true_positive=len(overlap_matches),
    )
    exact_false_positive = counts.actual - counts.exact_true_positive
    exact_false_negative = counts.expected - counts.exact_true_positive
    overlap_false_positive = (
        counts.actual - counts.overlap_true_positive
    )
    overlap_false_negative = (
        counts.expected - counts.overlap_true_positive
    )
    return (
        {
            "expected_count": counts.expected,
            "actual_count": counts.actual,
            "exact": {
                "true_positive": counts.exact_true_positive,
                "false_positive": exact_false_positive,
                "false_negative": exact_false_negative,
                "precision": _ratio(
                    counts.exact_true_positive,
                    counts.actual,
                ),
                "recall": _ratio(
                    counts.exact_true_positive,
                    counts.expected,
                ),
                "false_positive_rate": _ratio(
                    exact_false_positive,
                    counts.actual,
                ),
                "false_negative_rate": _ratio(
                    exact_false_negative,
                    counts.expected,
                ),
            },
            "partial_overlap": {
                "true_positive": counts.overlap_true_positive,
                "false_positive": overlap_false_positive,
                "false_negative": overlap_false_negative,
                "precision": _ratio(
                    counts.overlap_true_positive,
                    counts.actual,
                ),
                "recall": _ratio(
                    counts.overlap_true_positive,
                    counts.expected,
                ),
                "false_positive_rate": _ratio(
                    overlap_false_positive,
                    counts.actual,
                ),
                "false_negative_rate": _ratio(
                    overlap_false_negative,
                    counts.expected,
                ),
            },
        },
        exact_matches,
    )


def _pending_result(
    gold_annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": PENDING_HUMAN_ANNOTATION,
        "total_gold_segments": len(gold_annotations),
        "evaluated_segments": 0,
        "pending_segments": len(gold_annotations),
        "metrics": {
            name: None
            for name in (
                "entity",
                "entity_type_accuracy",
                "event",
                "relation",
                "temporal",
                "isnad",
                "span_exact_match",
                "span_overlap_match",
                "false_positive_rate",
                "false_negative_rate",
            )
        },
        "note": (
            "Pending annotations are excluded from all quality scores."
        ),
    }


def evaluate_gold_annotations(
    gold_payload: dict[str, Any],
    current_payload: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate reviewed annotations without treating pending rows as truth."""

    gold_annotations = list(gold_payload.get("annotations", []))
    current_by_key = {
        (str(item["source_id"]), int(item["segment_id"])): item
        for item in current_payload.get("segments", [])
    }
    reviewed = [
        item
        for item in gold_annotations
        if item.get("reviewer_status")
        not in {"", None, PENDING_HUMAN_ANNOTATION}
    ]
    if not reviewed:
        return _pending_result(gold_annotations)

    expected: dict[str, list[dict[str, Any]]] = {
        "entity": [],
        "event": [],
        "relation": [],
        "temporal": [],
        "isnad": [],
    }
    actual: dict[str, list[dict[str, Any]]] = {
        key: [] for key in expected
    }
    for annotation in reviewed:
        key = (
            str(annotation["source_id"]),
            int(annotation["segment_id"]),
        )
        current = current_by_key.get(key, {})
        for name, expected_field, actual_field in (
            ("entity", "expected_entities", "entities"),
            ("event", "expected_events", "events"),
            ("relation", "expected_relations", "relations"),
            (
                "temporal",
                "expected_temporal_mentions",
                "temporal_mentions",
            ),
            ("isnad", "expected_isnad", "isnad_chains"),
        ):
            expected[name].extend(
                {
                    **item,
                    "_evaluation_key": key,
                }
                for item in annotation.get(expected_field, [])
            )
            actual[name].extend(
                {
                    **item,
                    "_evaluation_key": key,
                }
                for item in current.get(actual_field, [])
            )

    labels = {
        "entity": _entity_label,
        "event": _typed_label("event_type"),
        "relation": _typed_label("relation_type"),
        "temporal": _typed_label("temporal_type"),
        "isnad": lambda _: "ISNAD",
    }
    metrics: dict[str, Any] = {}
    entity_matches: list[
        tuple[dict[str, Any], dict[str, Any]]
    ] = []
    for name in ("entity", "event", "relation", "temporal", "isnad"):
        score, matches = _score_collection(
            expected[name],
            actual[name],
            labels[name],
        )
        metrics[name] = score
        if name == "entity":
            entity_matches = matches

    type_matches = sum(
        _types(expected_item) == _types(actual_item)
        for expected_item, actual_item in entity_matches
    )
    metrics["entity_type_accuracy"] = _ratio(
        type_matches,
        len(entity_matches),
    )
    exact_true_positive = sum(
        metrics[name]["exact"]["true_positive"]
        for name in ("entity", "event", "relation", "temporal", "isnad")
    )
    overlap_true_positive = sum(
        metrics[name]["partial_overlap"]["true_positive"]
        for name in ("entity", "event", "relation", "temporal", "isnad")
    )
    expected_total = sum(
        metrics[name]["expected_count"]
        for name in ("entity", "event", "relation", "temporal", "isnad")
    )
    actual_total = sum(
        metrics[name]["actual_count"]
        for name in ("entity", "event", "relation", "temporal", "isnad")
    )
    metrics["span_exact_match"] = _ratio(
        exact_true_positive,
        expected_total,
    )
    metrics["span_overlap_match"] = _ratio(
        overlap_true_positive,
        expected_total,
    )
    metrics["false_positive_rate"] = _ratio(
        actual_total - exact_true_positive,
        actual_total,
    )
    metrics["false_negative_rate"] = _ratio(
        expected_total - exact_true_positive,
        expected_total,
    )
    return {
        "status": "EVALUATED",
        "total_gold_segments": len(gold_annotations),
        "evaluated_segments": len(reviewed),
        "pending_segments": len(gold_annotations) - len(reviewed),
        "metrics": metrics,
        "note": (
            "Exact and partial-overlap scores are reported independently."
        ),
    }


__all__ = [
    "PENDING_HUMAN_ANNOTATION",
    "evaluate_gold_annotations",
]
