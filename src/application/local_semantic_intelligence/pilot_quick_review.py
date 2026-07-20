"""Independent, lightweight human review mode for Pilot-12."""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.application.operations_common import integrity_hash

from .orchestrator import atomic_write_json, atomic_write_text
from .pilot_evaluation import PilotEvaluationError, pilot_root
from .pilot_view_models import CATEGORY_LABELS


def _read_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8-sig"))


def _detailed_store(semantic_root: str | Path) -> Any:
    from .pilot_workbench import PilotAdjudicationStore

    return PilotAdjudicationStore(semantic_root)


QUICK_SCHEMA_VERSION = "siraj-local-semantic-pilot-quick-review-v1"
QUICK_PENDING = "QUICK_PENDING"
QUICK_COMPLETED = "QUICK_COMPLETED"
QUICK_JUDGMENTS = ("GOOD", "PARTIAL", "BAD", "NEEDS_CONTEXT")
QUICK_ERROR_CATEGORIES = (
    "MISSING_IMPORTANT_ELEMENTS",
    "ELEMENT_NOT_IN_TEXT",
    "WRONG_BOUNDARY",
    "WRONG_ENTITY_TYPE",
    "WRONG_OR_MISSING_EVENT",
    "WRONG_OR_MISSING_RELATION",
    "WRONG_PARTICIPANT_OR_PLACE_ROLE",
    "WRONG_OR_MISSING_TIME",
    "WRONG_ISNAD",
    "HALLUCINATION_OR_EXTERNAL_KNOWLEDGE",
    "TEXT_NOT_UNDERSTOOD",
    "OTHER",
)
QUICK_ERROR_LABELS = {
    "MISSING_IMPORTANT_ELEMENTS": "عناصر مهمة مفقودة",
    "ELEMENT_NOT_IN_TEXT": "عناصر غير موجودة في النص",
    "WRONG_BOUNDARY": "حدود اسم أو عبارة خاطئة",
    "WRONG_ENTITY_TYPE": "نوع الكيان خاطئ",
    "WRONG_OR_MISSING_EVENT": "حدث خاطئ أو مفقود",
    "WRONG_OR_MISSING_RELATION": "علاقة خاطئة أو مفقودة",
    "WRONG_PARTICIPANT_OR_PLACE_ROLE": "أدوار المشاركين أو الأماكن خاطئة",
    "WRONG_OR_MISSING_TIME": "زمن خاطئ أو مفقود",
    "WRONG_ISNAD": "سند خاطئ",
    "HALLUCINATION_OR_EXTERNAL_KNOWLEDGE": "هلوسة أو معرفة خارج النص",
    "TEXT_NOT_UNDERSTOOD": "النص لم يُفهم",
    "OTHER": "مشكلة أخرى",
}
QUICK_JUDGMENT_LABELS = {
    "GOOD": "النتيجة جيدة",
    "PARTIAL": "صحيحة جزئياً",
    "BAD": "النتيجة سيئة",
    "NEEDS_CONTEXT": "يحتاج سياقاً إضافياً",
}


class QuickReviewError(PilotEvaluationError):
    """Quick review data violates its independent lifecycle contract."""


def _quick_path(semantic_root: str | Path) -> Path:
    return pilot_root(semantic_root) / "pilot-12-quick-review.json"


def _backup_root(semantic_root: str | Path) -> Path:
    return pilot_root(semantic_root) / "quick-review-backups"


def _quick_record(annotation: dict[str, Any]) -> dict[str, Any]:
    return {
        "annotation_id": annotation["annotation_id"],
        "audit_segment_id": annotation["audit_segment_id"],
        "segment_id": annotation["segment_id"],
        "book_title": annotation["book_title"],
        "original_text": annotation["original_text"],
        "quick_status": QUICK_PENDING,
        "judgment": "",
        "error_categories": [],
        "notes": "",
    }


def prepare_quick_review(semantic_root: str | Path) -> dict[str, Any]:
    """Create the independent quick file without changing detailed adjudication."""

    detailed = _detailed_store(semantic_root).load()
    path = _quick_path(semantic_root)
    if path.exists():
        payload = _read_json(path)
        if payload.get("schema_version") != QUICK_SCHEMA_VERSION:
            raise QuickReviewError("UNSUPPORTED_QUICK_REVIEW_SCHEMA")
        return payload
    payload = {
        "schema_version": QUICK_SCHEMA_VERSION,
        "status": "QUICK_REVIEW_PENDING",
        "pilot_id": detailed.get("pilot_id"),
        "detailed_adjudication_untouched": True,
        "records": [_quick_record(item) for item in detailed["annotations"]],
    }
    atomic_write_json(path, payload)
    return payload


def _load_quick(semantic_root: str | Path) -> dict[str, Any]:
    payload = prepare_quick_review(semantic_root)
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 12:
        raise QuickReviewError("QUICK_REVIEW_REQUIRES_PILOT_12")
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise QuickReviewError("INVALID_QUICK_REVIEW_RECORD")
        identifier = record.get("annotation_id")
        if not identifier or identifier in seen:
            raise QuickReviewError("DUPLICATE_QUICK_REVIEW_RECORD")
        seen.add(identifier)
        if record.get("quick_status") not in {QUICK_PENDING, QUICK_COMPLETED}:
            raise QuickReviewError("INVALID_QUICK_REVIEW_STATUS")
        if record.get("quick_status") == QUICK_COMPLETED:
            if record.get("judgment") not in QUICK_JUDGMENTS:
                raise QuickReviewError("COMPLETED_QUICK_REVIEW_REQUIRES_JUDGMENT")
            if not isinstance(record.get("error_categories"), list):
                raise QuickReviewError("INVALID_QUICK_ERROR_CATEGORIES")
            if not set(record["error_categories"]).issubset(QUICK_ERROR_CATEGORIES):
                raise QuickReviewError("UNKNOWN_QUICK_ERROR_CATEGORY")
    return payload


def _save_quick(semantic_root: str | Path, payload: dict[str, Any]) -> dict[str, Any]:
    path = _quick_path(semantic_root)
    backup_root = _backup_root(semantic_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    versions = []
    for item in backup_root.glob("pilot-12-quick-review.backup-*.json"):
        try:
            versions.append(int(item.stem.rsplit("-", 1)[1]))
        except ValueError:
            continue
    backup = backup_root / f"pilot-12-quick-review.backup-{max(versions, default=0)+1:06d}.json"
    atomic_write_json(backup, _read_json(path))
    atomic_write_json(path, payload)
    return {"status": "SAVED", "backup_file": backup.name, "quick_hash": integrity_hash(payload)}


def quick_progress(semantic_root: str | Path) -> dict[str, Any]:
    payload = _load_quick(semantic_root)
    records = payload["records"]
    counts = Counter(item["quick_status"] for item in records)
    judgments = Counter(item.get("judgment") for item in records if item.get("judgment"))
    return {
        "total": len(records),
        "pending": counts[QUICK_PENDING],
        "completed": counts[QUICK_COMPLETED],
        "completion_percentage": round(counts[QUICK_COMPLETED] / len(records) * 100, 2),
        "judgments": dict(sorted(judgments.items())),
        "evaluation_eligible": counts[QUICK_COMPLETED] == len(records),
    }


def quick_update(
    semantic_root: str | Path,
    annotation_id: str,
    *,
    judgment: str,
    error_categories: list[str],
    notes: str,
) -> dict[str, Any]:
    if judgment not in QUICK_JUDGMENTS:
        raise QuickReviewError("INVALID_QUICK_JUDGMENT")
    if not set(error_categories).issubset(QUICK_ERROR_CATEGORIES):
        raise QuickReviewError("UNKNOWN_QUICK_ERROR_CATEGORY")
    payload = _load_quick(semantic_root)
    target = next((item for item in payload["records"] if item["annotation_id"] == annotation_id), None)
    if target is None:
        raise QuickReviewError("QUICK_REVIEW_RECORD_NOT_FOUND")
    target.update({
        "judgment": judgment,
        "error_categories": sorted(set(error_categories)),
        "notes": str(notes),
        "quick_status": QUICK_COMPLETED,
    })
    payload["status"] = "QUICK_REVIEW_COMPLETE" if all(item["quick_status"] == QUICK_COMPLETED for item in payload["records"]) else "QUICK_REVIEW_IN_PROGRESS"
    return _save_quick(semantic_root, payload)


def quick_undo(semantic_root: str | Path) -> dict[str, Any]:
    root = _backup_root(semantic_root)
    backups = sorted(root.glob("pilot-12-quick-review.backup-*.json"))
    if not backups:
        raise QuickReviewError("NO_QUICK_REVIEW_EDIT_TO_UNDO")
    previous = _read_json(backups[-1])
    atomic_write_json(_quick_path(semantic_root), previous)
    return {"status": "UNDONE", "restored_backup": backups[-1].name}


class PilotQuickReviewStore:
    """Workbench-compatible facade over the independent quick-review file."""

    def __init__(self, semantic_root: str | Path):
        self.semantic_root = Path(semantic_root).resolve()

    def load(self) -> dict[str, Any]:
        return _load_quick(self.semantic_root)

    def progress(self) -> dict[str, Any]:
        return quick_progress(self.semantic_root)

    def state(self) -> dict[str, Any]:
        return quick_state(self.semantic_root)

    def search(self, query: str) -> list[dict[str, Any]]:
        return quick_search(self.semantic_root, query)

    def update(self, annotation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        if set(patch) - {"judgment", "error_categories", "notes", "quick_status"}:
            raise QuickReviewError("QUICK_REVIEW_ONLY_ACCEPTS_QUICK_FIELDS")
        return quick_update(
            self.semantic_root,
            annotation_id,
            judgment=str(patch.get("judgment", "")),
            error_categories=list(patch.get("error_categories", [])),
            notes=str(patch.get("notes", "")),
        )

    def undo_last(self) -> dict[str, Any]:
        return quick_undo(self.semantic_root)

    def evaluate(self) -> dict[str, Any]:
        return quick_evaluate(self.semantic_root)


def _quick_presentation(semantic_root: str | Path) -> dict[str, Any]:
    detailed = _detailed_store(semantic_root).state()
    result = {}
    for identifier, presentation in detailed.get("presentation", {}).items():
        reconciled = presentation.get("tabs", {}).get("reconciled", {})
        categories = []
        for category in reconciled.get("categories", []):
            categories.append({
                "key": category["key"],
                "label": category["label"],
                "empty_message": category["empty_message"],
                "items": [_without_technical(item) for item in category.get("items", [])],
            })
        result[identifier] = {"tabs": {"reconciled": {"categories": categories}}}
    return result


def _without_technical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _without_technical(item) for key, item in value.items() if key != "technical"}
    if isinstance(value, list):
        return [_without_technical(item) for item in value]
    return value


def quick_state(semantic_root: str | Path) -> dict[str, Any]:
    payload = _load_quick(semantic_root)
    return {
        "schema_version": QUICK_SCHEMA_VERSION,
        "records": payload["records"],
        "progress": quick_progress(semantic_root),
        "presentation": _quick_presentation(semantic_root),
        "quick_mode": True,
        "detailed_adjudication_untouched": True,
        "ai_calls_allowed": False,
        "external_network_allowed": False,
    }


def quick_search(semantic_root: str | Path, query: str) -> list[dict[str, Any]]:
    needle = query.casefold().strip()
    return [
        {
            "annotation_id": item["annotation_id"],
            "book_title": item["book_title"],
            "segment_id": item["segment_id"],
            "quick_status": item["quick_status"],
        }
        for item in _load_quick(semantic_root)["records"]
        if not needle or needle in (item["book_title"] + " " + item["original_text"]).casefold()
    ]


def _report_records(semantic_root: str | Path) -> list[dict[str, Any]]:
    quick = _load_quick(semantic_root)["records"]
    manifest = _read_json(pilot_root(semantic_root) / "pilot-12-run-manifest.json")
    by_id = {item["audit_segment_id"]: item for item in manifest.get("segments", [])}
    return [{**item, **{key: by_id.get(item["audit_segment_id"], {}).get(key) for key in ("text_type", "execution_plan", "book_title")}} for item in quick]


def quick_evaluate(semantic_root: str | Path) -> dict[str, Any]:
    progress = quick_progress(semantic_root)
    if not progress["evaluation_eligible"]:
        raise QuickReviewError("QUICK_EVALUATION_REQUIRES_ALL_12_COMPLETED")
    records = _report_records(semantic_root)
    judgments = Counter(item["judgment"] for item in records)
    errors = Counter(error for item in records for error in item["error_categories"])
    by_text: dict[str, Counter[str]] = defaultdict(Counter)
    by_plan: dict[str, Counter[str]] = defaultdict(Counter)
    for item in records:
        by_text[item.get("text_type") or "غير محدد"][item["judgment"]] += 1
        by_plan[item.get("execution_plan") or "غير محدد"][item["judgment"]] += 1
    good = judgments["GOOD"]
    partial = judgments["PARTIAL"]
    bad = judgments["BAD"]
    if good >= 9 and bad == 0:
        decision = "MODEL_STRONG_ENOUGH_FOR_OPTIMIZATION"
    elif good + partial >= 9:
        decision = "MODEL_PROMISING"
    elif good + partial >= 4:
        decision = "MODEL_WEAK"
    else:
        decision = "MODEL_NOT_USEFUL"
    report = {
        "schema_version": QUICK_SCHEMA_VERSION,
        "pilot_id": _load_quick(semantic_root).get("pilot_id"),
        "status": "QUICK_REVIEW_EVALUATED",
        "is_full_gold_semantic_evaluation": False,
        "judgment_counts": dict(sorted(judgments.items())),
        "error_category_counts": {
            key: {"label": QUICK_ERROR_LABELS[key], "count": count}
            for key, count in sorted(errors.items())
        },
        "by_text_type": {key: dict(sorted(value.items())) for key, value in sorted(by_text.items())},
        "by_execution_plan": {key: dict(sorted(value.items())) for key, value in sorted(by_plan.items())},
        "baseline_comparison": {
            "available": True,
            "role": "CANDIDATE_GENERATOR_ONLY",
            "note": "Quick Review records human impressions; it does not calculate semantic precision or recall.",
        },
        "human_notes": [{"segment_id": item["segment_id"], "notes": item["notes"]} for item in records if item["notes"]],
        "preliminary_decision": decision,
        "detailed_adjudication_status": "UNCHANGED_AND_INDEPENDENT",
    }
    root = pilot_root(semantic_root)
    atomic_write_json(root / "pilot-12-quick-review-summary.json", report)
    lines = [
        "# Pilot-12 Quick Review Summary",
        "",
        "This is a rapid human impression, not a complete Gold semantic evaluation.",
        "",
        f"- Preliminary decision: `{decision}`",
        f"- Completed: `{progress['completed']}/{progress['total']}`",
        "",
        "## Judgments",
        "",
    ]
    lines.extend(f"- {QUICK_JUDGMENT_LABELS[key]}: {value}" for key, value in sorted(judgments.items()))
    lines.extend(["", "## Frequent error categories", ""])
    lines.extend(f"- {QUICK_ERROR_LABELS[key]}: {value}" for key, value in sorted(errors.items(), key=lambda pair: (-pair[1], pair[0])))
    atomic_write_text(root / "pilot-12-quick-review-summary.md", "\n".join(lines) + "\n")
    return report


__all__ = [
    "QUICK_COMPLETED",
    "QUICK_ERROR_CATEGORIES",
    "QUICK_ERROR_LABELS",
    "QUICK_JUDGMENTS",
    "QUICK_JUDGMENT_LABELS",
    "QUICK_PENDING",
    "QuickReviewError",
    "prepare_quick_review",
    "quick_evaluate",
    "quick_progress",
    "quick_search",
    "quick_state",
    "quick_undo",
    "quick_update",
]
