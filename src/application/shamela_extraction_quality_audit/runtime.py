"""Deterministic quality audit over the five-book Shamela extraction pilot."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_runtime import project_paths

from .evaluator import (
    PENDING_HUMAN_ANNOTATION,
    evaluate_gold_annotations,
)


AUDIT_SCHEMA_VERSION = "shamela-extraction-quality-audit-v1"

BOOK_SAMPLE_PLAN = {
    400: {
        "role": "GENERAL_HISTORY",
        "minimum_segments": 20,
        "title": "الحوادث الجامعة والتجارب النافعة",
    },
    619: {
        "role": "SIRA",
        "minimum_segments": 15,
        "title": "القوافي الندية في السيرة المحمدية",
    },
    5: {
        "role": "BIOGRAPHY_RIJAL",
        "minimum_segments": 10,
        "title": "أسماء المدلسين",
    },
    405: {
        "role": "REGIONAL_VIRTUES",
        "minimum_segments": 10,
        "title": "فضائل مصر المحروسة",
    },
    151020: {
        "role": "INTELLECTUAL_TEXT",
        "minimum_segments": 10,
        "title": "جهد القريحة في تجريد النصيحة",
    },
}

_KUNYA_OR_TITLE_RE = re.compile(
    r"\b(?:أبو|أبي|أبا|أم|الخليفة|السلطان|الملك|الأمير|"
    r"الإمام|الشيخ|الحافظ|القاضي)\b"
)
_HISTORICAL_TRIGGER_RE = re.compile(
    r"\b(?:غزا|هاجر|بعث|دخل|خرج|قدم|تزوج|قتل|فتح|سار|"
    r"عاد|دعا|عزل|بويع|ولي|توفي|مات|ولد|حارب|قاتل)\b"
)
_EXPLICIT_TEMPORAL_RE = re.compile(
    r"\b(?:سنة|عام|القرن|قبل|بعد)\b|[٠-٩0-9]{2,4}\s*(?:هـ|م)\b"
)
_GENERIC_NAME_TOKENS = {
    "أم لا",
    "أبيه",
    "أبي",
    "كله",
    "غيره",
    "هذا",
    "هذه",
    "ذلك",
    "الذي",
    "الصفات",
    "الصفات اللازمة",
    "مصر وأحوالها",
}
_NISBA_RE = re.compile(
    r"\b[\u0621-\u064A]{3,}(?:اني|اوي|ي)\b$"
)
_REVIEW_CATEGORIES = (
    "ALIAS_AMBIGUITY",
    "INCOMPLETE_ARABIC_NAME",
    "PARTIAL_NAME_OVERLAP",
    "KUNYA_AMBIGUITY",
    "NISBA_AMBIGUITY",
    "NARRATOR_CONTEXT_AMBIGUITY",
    "COMMON_NOUN_MISTAKEN_FOR_PERSON",
    "PLACE_PERSON_AMBIGUITY",
    "INSUFFICIENT_CONTEXT",
    "CONFLICTING_TYPE_EVIDENCE",
)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path.name}")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path.name}:{error.lineno}:{error.colno}"
        ) from error


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = handle.name
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _group(
    items: Iterable[dict[str, Any]],
    id_field: str,
) -> dict[tuple[str, int], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[
            (str(item["source_id"]), int(item["segment_id"]))
        ].append(item)
    for values in grouped.values():
        values.sort(key=lambda item: str(item[id_field]))
    return dict(grouped)


def _span(item: dict[str, Any]) -> dict[str, Any] | None:
    return (
        item.get("original_text_span")
        or item.get("evidence_span")
    )


def _safe_percentage(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


def _int_or_zero(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(value)


class ShamelaExtractionQualityAudit:
    """Create a reusable human-review set without changing extraction."""

    def __init__(
        self,
        project_root: str | Path,
        pilot_root: str | Path,
        extraction_root: str | Path,
        output_root: str | Path,
    ):
        self.project_root = Path(project_root).resolve()
        self.pilot_root = Path(pilot_root).resolve()
        self.extraction_root = Path(extraction_root).resolve()
        self.output_root = Path(output_root).resolve()
        paths = project_paths(self.project_root)
        working_root = Path(paths.working_root).resolve()
        try:
            self.pilot_root.relative_to(working_root)
            self.extraction_root.relative_to(working_root)
            self.output_root.relative_to(working_root)
        except ValueError as error:
            raise ValueError("AUDIT_PATH_OUTSIDE_PROJECT_WORKING_ROOT") from error
        if self.output_root in {
            self.pilot_root,
            self.extraction_root,
        }:
            raise ValueError("AUDIT_OUTPUT_MUST_BE_ISOLATED")

    def run(self) -> dict[str, Any]:
        extraction = self._load_extraction()
        books = self._load_books()
        indices = self._build_indices(extraction)
        sample = self._build_sample(books, indices)
        current = self._current_extraction(sample, indices)
        gold = self._gold_template(sample, current)
        baseline = evaluate_gold_annotations(gold, current)
        review_analysis = self._analyze_human_review(extraction)
        systematic = self._systematic_analysis(
            books,
            extraction,
            indices,
        )
        taxonomy = self._error_taxonomy(systematic, review_analysis)
        backlog = self._improvement_backlog(taxonomy)
        readiness = self._readiness_gate(baseline)

        extraction_hashes = {
            filename: _file_sha256(self.extraction_root / filename)
            for filename in sorted(
                (
                    "entity-mentions.json",
                    "canonical-entity-candidates.json",
                    "event-mentions.json",
                    "historical-claims.json",
                    "relation-mentions.json",
                    "isnad-chains.json",
                    "temporal-mentions.json",
                    "entity-resolution-review-queue.json",
                    "extraction-run-manifest.json",
                )
            )
        }
        sample_ids = [
            item["audit_segment_id"]
            for item in sample
        ]
        audit_id = deterministic_id(
            "shamela_extraction_quality_audit",
            [
                AUDIT_SCHEMA_VERSION,
                extraction["manifest"]["run_id"],
                sample_ids,
                extraction_hashes,
            ],
        )
        manifest = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "audit_id": audit_id,
            "created_at": CANONICAL_TIMESTAMP,
            "extraction_run_id": extraction["manifest"]["run_id"],
            "selection_policy": "DETERMINISTIC_STRATIFIED_BY_BOOK_AND_SIGNAL",
            "sample_count": len(sample),
            "book_quotas": [
                {
                    "book_id": book_id,
                    **BOOK_SAMPLE_PLAN[book_id],
                    "selected_segments": sum(
                        item["book_id"] == book_id
                        for item in sample
                    ),
                }
                for book_id in sorted(BOOK_SAMPLE_PLAN)
            ],
            "sample_segment_ids": sample_ids,
            "source_artifact_hashes": extraction_hashes,
            "annotation_status": PENDING_HUMAN_ANNOTATION,
            "scope": {
                "human_annotation_complete": False,
                "semantic_quality_scored": False,
                "extractor_modified": False,
                "network_used": False,
                "shamela_installation_accessed": False,
            },
        }
        sample_manifest = {
            **manifest,
            "segments": [
                {
                    key: item[key]
                    for key in (
                        "audit_segment_id",
                        "book_id",
                        "book_role",
                        "source_id",
                        "segment_id",
                        "locator",
                        "volume",
                        "page",
                        "selection_reasons",
                    )
                }
                for item in sample
            ],
        }
        quality_baseline = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "audit_id": audit_id,
            "status": PENDING_HUMAN_ANNOTATION,
            "evaluation": baseline,
            "structural_integrity": systematic["structural_integrity"],
            "current_extraction_volume": {
                "entity_mentions": len(extraction["entities"]),
                "event_mentions": len(extraction["events"]),
                "relation_mentions": len(extraction["relations"]),
                "claims": len(extraction["claims"]),
                "temporal_mentions": len(extraction["temporals"]),
                "isnad_chains": len(extraction["isnads"]),
            },
            "semantic_metrics": {
                "entity_precision": None,
                "entity_recall": None,
                "entity_type_accuracy": None,
                "event_precision": None,
                "event_recall": None,
                "relation_precision": None,
                "relation_recall": None,
                "temporal_precision": None,
                "temporal_recall": None,
                "isnad_precision": None,
                "isnad_recall": None,
                "false_positive_rate": None,
                "false_negative_rate": None,
            },
            "warning": (
                "No semantic score is final until the Gold Set is reviewed "
                "by a human."
            ),
        }
        payloads = {
            "audit-sample-manifest.json": sample_manifest,
            "gold-annotation-template.json": gold,
            "current-extraction-on-gold-sample.json": current,
            "human-review-reason-analysis.json": review_analysis,
            "extraction-error-taxonomy.json": taxonomy,
            "extraction-quality-baseline.json": quality_baseline,
            "extraction-improvement-backlog.json": backlog,
            "knowledge-graph-readiness-gate.json": readiness,
        }
        self.output_root.mkdir(parents=True, exist_ok=True)
        for filename, payload in sorted(payloads.items()):
            _atomic_write(
                self.output_root / filename,
                _canonical_json(payload),
            )
        _atomic_write(
            self.output_root / "gold-annotation-review.md",
            self._gold_markdown(gold),
        )
        _atomic_write(
            self.output_root / "extraction-quality-audit-report.md",
            self._audit_markdown(
                manifest,
                systematic,
                review_analysis,
                baseline,
                readiness,
            ),
        )
        return {
            "audit_id": audit_id,
            "status": "VALID_PENDING_HUMAN_ANNOTATION",
            "sample_count": len(sample),
            "human_review_required_count": review_analysis[
                "human_review_required_total"
            ],
            "semantic_metrics_status": PENDING_HUMAN_ANNOTATION,
            "readiness_status": readiness["status"],
            "output_root": str(self.output_root),
        }

    def _load_extraction(self) -> dict[str, Any]:
        files = {
            "manifest": ("extraction-run-manifest.json", None),
            "entities": ("entity-mentions.json", "entity_mentions"),
            "candidates": (
                "canonical-entity-candidates.json",
                "canonical_entity_candidates",
            ),
            "events": ("event-mentions.json", "event_mentions"),
            "claims": ("historical-claims.json", "historical_claims"),
            "relations": ("relation-mentions.json", "relation_mentions"),
            "isnads": ("isnad-chains.json", "isnad_chains"),
            "temporals": ("temporal-mentions.json", "temporal_mentions"),
            "review_queue": (
                "entity-resolution-review-queue.json",
                "review_items",
            ),
        }
        result: dict[str, Any] = {}
        for name, (filename, key) in files.items():
            payload = _read_json(self.extraction_root / filename)
            result[name] = payload if key is None else list(payload[key])
        if result["manifest"].get("status") != "VALID":
            raise ValueError("EXTRACTION_INPUT_NOT_VALID")
        return result

    def _load_books(self) -> dict[int, dict[str, Any]]:
        ledger_payload = _read_json(
            self.pilot_root / "shamela-pilot-source-ledger.json"
        )
        if not isinstance(ledger_payload, list):
            raise ValueError("PILOT_SOURCE_LEDGER_MUST_BE_A_LIST")
        source_ids = {
            int(item["book_id"]): str(item["source_id"])
            for item in ledger_payload
        }
        books: dict[int, dict[str, Any]] = {}
        for book_id in sorted(BOOK_SAMPLE_PLAN):
            path = self.pilot_root / "books" / str(book_id) / "book.v1.json"
            payload = _read_json(path)
            if int(payload["segment_count"]) != len(payload["segments"]):
                raise ValueError(f"BOOK_SEGMENT_COUNT_MISMATCH:{book_id}")
            if book_id not in source_ids:
                raise ValueError(f"BOOK_MISSING_FROM_SOURCE_LEDGER:{book_id}")
            payload["_audit_source_id"] = source_ids[book_id]
            books[book_id] = payload
        return books

    @staticmethod
    def _build_indices(
        extraction: dict[str, Any],
    ) -> dict[str, dict[tuple[str, int], list[dict[str, Any]]]]:
        return {
            "entities": _group(
                extraction["entities"],
                "mention_id",
            ),
            "events": _group(
                extraction["events"],
                "event_mention_id",
            ),
            "claims": _group(
                extraction["claims"],
                "claim_id",
            ),
            "relations": _group(
                extraction["relations"],
                "relation_id",
            ),
            "temporals": _group(
                extraction["temporals"],
                "temporal_id",
            ),
            "isnads": _group(
                extraction["isnads"],
                "chain_id",
            ),
        }

    def _segment_reasons(
        self,
        segment: dict[str, Any],
        source_id: str,
        indices: dict[
            str,
            dict[tuple[str, int], list[dict[str, Any]]],
        ],
        heading_ids: set[int],
    ) -> list[str]:
        segment_id = int(segment["segment_id"])
        key = (source_id, segment_id)
        text = str(segment["body_original"])
        entities = indices["entities"].get(key, [])
        events = indices["events"].get(key, [])
        relations = indices["relations"].get(key, [])
        temporals = indices["temporals"].get(key, [])
        isnads = indices["isnads"].get(key, [])
        reasons: list[str] = []
        if isnads:
            reasons.append("CURRENT_ISNAD_CHAIN")
        if temporals or _EXPLICIT_TEMPORAL_RE.search(text):
            reasons.append("TEMPORAL_EXPRESSION")
        if events:
            reasons.append("CURRENT_EVENT_MENTION")
        if relations:
            reasons.append("CURRENT_RELATION_MENTION")
        if len(entities) >= 2:
            reasons.append("MULTIPLE_ENTITY_MENTIONS")
        if _KUNYA_OR_TITLE_RE.search(text):
            reasons.append("KUNYA_OR_HISTORICAL_TITLE")
        if any(
            {"PLACE", "CITY", "REGION"}
            & set(item.get("entity_type_candidate", []))
            for item in entities
        ):
            reasons.append("PLACE_MENTION")
        if (
            not events
            and not relations
            and not temporals
            and not isnads
        ):
            reasons.append("NEGATIVE_CONTROL_NO_CURRENT_SIGNAL")
        if _HISTORICAL_TRIGGER_RE.search(text) and not events:
            reasons.append("UNCOVERED_HISTORICAL_TRIGGER")
        if segment_id in heading_ids:
            reasons.append("HEADING_BEARING_SEGMENT")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) >= 4 and sum(map(len, lines)) / len(lines) < 55:
            reasons.append("POETRY_OR_SHORT_LINE_STRUCTURE")
        if len(text) >= 3000:
            reasons.append("LONG_DENSE_SEGMENT")
        return sorted(set(reasons))

    def _build_sample(
        self,
        books: dict[int, dict[str, Any]],
        indices: dict[
            str,
            dict[tuple[str, int], list[dict[str, Any]]],
        ],
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        preferred = (
            "CURRENT_ISNAD_CHAIN",
            "TEMPORAL_EXPRESSION",
            "CURRENT_EVENT_MENTION",
            "CURRENT_RELATION_MENTION",
            "UNCOVERED_HISTORICAL_TRIGGER",
            "KUNYA_OR_HISTORICAL_TITLE",
            "MULTIPLE_ENTITY_MENTIONS",
            "PLACE_MENTION",
            "NEGATIVE_CONTROL_NO_CURRENT_SIGNAL",
            "HEADING_BEARING_SEGMENT",
            "POETRY_OR_SHORT_LINE_STRUCTURE",
            "LONG_DENSE_SEGMENT",
        )
        for book_id in sorted(BOOK_SAMPLE_PLAN):
            book = books[book_id]
            source_id = str(book["_audit_source_id"])
            heading_ids = {
                int(item["page_segment_id"])
                for item in book.get("headings", [])
            }
            candidates: list[dict[str, Any]] = []
            for segment in sorted(
                book["segments"],
                key=lambda item: int(item["segment_id"]),
            ):
                reasons = self._segment_reasons(
                    segment,
                    source_id,
                    indices,
                    heading_ids,
                )
                candidates.append(
                    {
                        "audit_segment_id": deterministic_id(
                            "shamela_quality_audit_segment",
                            [
                                book_id,
                                source_id,
                                int(segment["segment_id"]),
                                segment["locator"],
                            ],
                        ),
                        "book_id": book_id,
                        "book_title": BOOK_SAMPLE_PLAN[book_id]["title"],
                        "book_role": BOOK_SAMPLE_PLAN[book_id]["role"],
                        "source_id": source_id,
                        "segment_id": int(segment["segment_id"]),
                        "locator": str(segment["locator"]),
                        "volume": _int_or_zero(segment.get("volume")),
                        "page": _int_or_zero(segment.get("page")),
                        "original_text": str(segment["body_original"]),
                        "selection_reasons": reasons,
                    }
                )
            quota = int(BOOK_SAMPLE_PLAN[book_id]["minimum_segments"])
            chosen: list[dict[str, Any]] = []
            chosen_ids: set[int] = set()
            for reason in preferred:
                candidate = next(
                    (
                        item
                        for item in candidates
                        if reason in item["selection_reasons"]
                        and item["segment_id"] not in chosen_ids
                    ),
                    None,
                )
                if candidate is not None and len(chosen) < quota:
                    chosen.append(candidate)
                    chosen_ids.add(candidate["segment_id"])
            remaining = [
                item
                for item in candidates
                if item["segment_id"] not in chosen_ids
            ]
            needed = quota - len(chosen)
            if needed:
                positions = [
                    min(
                        len(remaining) - 1,
                        (index * len(remaining)) // needed,
                    )
                    for index in range(needed)
                ]
                for position in positions:
                    candidate = remaining[position]
                    if candidate["segment_id"] in chosen_ids:
                        continue
                    candidate = {
                        **candidate,
                        "selection_reasons": sorted(
                            set(candidate["selection_reasons"])
                            | {"DETERMINISTIC_QUOTA_FILL"}
                        ),
                    }
                    chosen.append(candidate)
                    chosen_ids.add(candidate["segment_id"])
            if len(chosen) < quota:
                for candidate in remaining:
                    if candidate["segment_id"] in chosen_ids:
                        continue
                    chosen.append(
                        {
                            **candidate,
                            "selection_reasons": sorted(
                                set(candidate["selection_reasons"])
                                | {"DETERMINISTIC_QUOTA_FILL"}
                            ),
                        }
                    )
                    chosen_ids.add(candidate["segment_id"])
                    if len(chosen) == quota:
                        break
            if len(chosen) != quota:
                raise ValueError(f"SAMPLE_QUOTA_UNSATISFIED:{book_id}")
            selected.extend(
                sorted(chosen, key=lambda item: item["segment_id"])
            )
        return selected

    @staticmethod
    def _current_extraction(
        sample: list[dict[str, Any]],
        indices: dict[
            str,
            dict[tuple[str, int], list[dict[str, Any]]],
        ],
    ) -> dict[str, Any]:
        segments: list[dict[str, Any]] = []
        for item in sample:
            key = (item["source_id"], item["segment_id"])
            segments.append(
                {
                    "audit_segment_id": item["audit_segment_id"],
                    "source_id": item["source_id"],
                    "segment_id": item["segment_id"],
                    "locator": item["locator"],
                    "entities": indices["entities"].get(key, []),
                    "events": indices["events"].get(key, []),
                    "relations": indices["relations"].get(key, []),
                    "claims": indices["claims"].get(key, []),
                    "temporal_mentions": indices["temporals"].get(key, []),
                    "isnad_chains": indices["isnads"].get(key, []),
                }
            )
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "status": "CURRENT_EXTRACTION_SNAPSHOT",
            "segments": segments,
        }

    @staticmethod
    def _gold_template(
        sample: list[dict[str, Any]],
        current: dict[str, Any],
    ) -> dict[str, Any]:
        current_by_id = {
            item["audit_segment_id"]: item
            for item in current["segments"]
        }
        annotations = []
        for item in sample:
            annotations.append(
                {
                    "annotation_id": deterministic_id(
                        "shamela_gold_annotation",
                        [item["audit_segment_id"]],
                    ),
                    "audit_segment_id": item["audit_segment_id"],
                    "book_id": item["book_id"],
                    "book_title": item["book_title"],
                    "source_id": item["source_id"],
                    "segment_id": item["segment_id"],
                    "locator": item["locator"],
                    "original_text": item["original_text"],
                    "expected_entities": [],
                    "expected_entity_types": [],
                    "expected_events": [],
                    "expected_relations": [],
                    "expected_temporal_mentions": [],
                    "expected_isnad": [],
                    "explicitly_absent_items": [],
                    "reviewer_status": PENDING_HUMAN_ANNOTATION,
                    "reviewer_notes": "",
                    "current_extraction": current_by_id[
                        item["audit_segment_id"]
                    ],
                }
            )
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "annotation_schema": {
                "span_contract": {
                    "start": "zero-based inclusive character offset",
                    "end": "zero-based exclusive character offset",
                    "text": "must equal original_text[start:end]",
                },
                "expected_entities": (
                    "List of {span, normalized_surface_form, entity_types}"
                ),
                "expected_events": (
                    "List of {span, event_type, notes}"
                ),
                "expected_relations": (
                    "List of {evidence_span, relation_type, "
                    "subject_span, object_span}"
                ),
                "expected_temporal_mentions": (
                    "List of {span, temporal_type, precision, calendar}"
                ),
                "expected_isnad": (
                    "List of {evidence_span, narrator_spans}"
                ),
            },
            "annotation_status": PENDING_HUMAN_ANNOTATION,
            "annotations": annotations,
        }

    @staticmethod
    def _review_category(
        candidate: dict[str, Any],
        mentions: list[dict[str, Any]],
        partial_collision_mentions: set[str],
    ) -> str:
        name = str(candidate["canonical_name"]).strip()
        tokens = name.split()
        types = set(candidate.get("entity_type", []))
        contexts = {
            item.get("mention_context", "BODY")
            for item in mentions
        }
        evidence_types = {
            tuple(sorted(item.get("entity_type_candidate", [])))
            for item in mentions
        }
        mention_ids = set(candidate.get("linked_mentions", []))
        if "ISNAD" in contexts:
            return "NARRATOR_CONTEXT_AMBIGUITY"
        if name in _GENERIC_NAME_TOKENS or (
            "PERSON" in types
            and len(tokens) == 1
            and not name.startswith("ال")
        ):
            return "COMMON_NOUN_MISTAKEN_FOR_PERSON"
        if types & {"PERSON", "PROPHET", "CALIPH", "RULER"} and types & {
            "PLACE",
            "CITY",
            "REGION",
        }:
            return "PLACE_PERSON_AMBIGUITY"
        if len(evidence_types) > 1:
            return "CONFLICTING_TYPE_EVIDENCE"
        if name.startswith(("أبو ", "أبي ", "أبا ", "أم ")):
            return "KUNYA_AMBIGUITY"
        if (
            not tokens
            or name.startswith(("بن ", "ابن ", "بنت ", "ل"))
            or name.endswith((" بن", " ابن", " بنت"))
        ):
            return "INCOMPLETE_ARABIC_NAME"
        if len(candidate.get("aliases", [])) > 1:
            return "ALIAS_AMBIGUITY"
        if mention_ids & partial_collision_mentions:
            return "PARTIAL_NAME_OVERLAP"
        if _NISBA_RE.search(name) and len(tokens) <= 2:
            return "NISBA_AMBIGUITY"
        return "INSUFFICIENT_CONTEXT"

    def _analyze_human_review(
        self,
        extraction: dict[str, Any],
    ) -> dict[str, Any]:
        mention_by_id = {
            item["mention_id"]: item
            for item in extraction["entities"]
        }
        partial_collision_mentions = {
            mention_id
            for item in extraction["review_queue"]
            if item["reason"] == "PARTIAL_NAME_COLLISION_ONLY"
            for mention_id in item["mention_ids"]
        }
        reviewed = [
            item
            for item in extraction["candidates"]
            if item["review_status"] == "HUMAN_REVIEW_REQUIRED"
        ]
        categories: Counter[str] = Counter()
        examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for candidate in sorted(
            reviewed,
            key=lambda item: item["candidate_id"],
        ):
            mentions = [
                mention_by_id[mention_id]
                for mention_id in candidate["linked_mentions"]
            ]
            category = self._review_category(
                candidate,
                mentions,
                partial_collision_mentions,
            )
            categories[category] += 1
            if len(examples[category]) < 5:
                examples[category].append(
                    {
                        "candidate_id": candidate["candidate_id"],
                        "canonical_name": candidate["canonical_name"],
                        "entity_type": candidate["entity_type"],
                        "mention_count": len(mentions),
                        "rule_ids": candidate["rule_ids"],
                    }
                )
        total = len(reviewed)
        raw_reasons = Counter(
            item["reason"]
            for item in extraction["review_queue"]
            if item["review_status"] == "HUMAN_REVIEW_REQUIRED"
        )
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "human_review_required_total": total,
            "classification_method": (
                "Deterministic diagnostic taxonomy; not human ground truth."
            ),
            "category_distribution": [
                {
                    "category": category,
                    "count": categories[category],
                    "percentage": _safe_percentage(
                        categories[category],
                        total,
                    ),
                    "examples": examples[category],
                }
                for category in _REVIEW_CATEGORIES
            ],
            "raw_extractor_reason_distribution": [
                {
                    "reason": reason,
                    "count": count,
                    "percentage": _safe_percentage(count, total),
                }
                for reason, count in sorted(raw_reasons.items())
            ],
            "do_not_merge_partial_collision_count": sum(
                item["reason"] == "PARTIAL_NAME_COLLISION_ONLY"
                for item in extraction["review_queue"]
            ),
            "classification_count_consistent": sum(
                categories.values()
            )
            == total,
        }

    @staticmethod
    def _systematic_analysis(
        books: dict[int, dict[str, Any]],
        extraction: dict[str, Any],
        indices: dict[
            str,
            dict[tuple[str, int], list[dict[str, Any]]],
        ],
    ) -> dict[str, Any]:
        segment_texts: dict[tuple[str, int], str] = {}
        per_book: list[dict[str, Any]] = []
        heading_in_body = 0
        heading_extraction_overlap = 0
        poetry_like_segments = 0
        index_like_segments = 0
        uncovered_trigger_segments: list[dict[str, Any]] = []
        for book_id, book in sorted(books.items()):
            source_id = str(book["_audit_source_id"])
            segments = list(book["segments"])
            character_count = sum(
                len(str(item["body_original"]))
                for item in segments
            )
            entity_count = sum(
                len(indices["entities"].get(
                    (source_id, int(segment["segment_id"])),
                    [],
                ))
                for segment in segments
            )
            event_count = sum(
                len(indices["events"].get(
                    (source_id, int(segment["segment_id"])),
                    [],
                ))
                for segment in segments
            )
            overlap_pairs = 0
            exact_duplicate_spans = 0
            for segment in segments:
                segment_id = int(segment["segment_id"])
                key = (source_id, segment_id)
                text = str(segment["body_original"])
                segment_texts[key] = text
                current_entities = indices["entities"].get(key, [])
                entity_spans = sorted(
                    (
                        int(item["original_text_span"]["start"]),
                        int(item["original_text_span"]["end"]),
                    )
                    for item in current_entities
                )
                exact_duplicate_spans += (
                    len(entity_spans) - len(set(entity_spans))
                )
                for index, left in enumerate(entity_spans):
                    overlap_pairs += sum(
                        max(left[0], right[0])
                        < min(left[1], right[1])
                        for right in entity_spans[index + 1:]
                    )
                lines = [
                    line.strip()
                    for line in text.splitlines()
                    if line.strip()
                ]
                if (
                    len(lines) >= 4
                    and sum(map(len, lines)) / len(lines) < 55
                ):
                    poetry_like_segments += 1
                if re.search(r"\b(?:فهرس|المحتويات)\b", text):
                    index_like_segments += 1
                if (
                    _HISTORICAL_TRIGGER_RE.search(text)
                    and not indices["events"].get(key)
                ):
                    uncovered_trigger_segments.append(
                        {
                            "book_id": book_id,
                            "source_id": source_id,
                            "segment_id": segment_id,
                            "locator": segment["locator"],
                        }
                    )
            heading_ids = {
                int(item["page_segment_id"]): item
                for item in book.get("headings", [])
            }
            for segment_id, heading in heading_ids.items():
                text = segment_texts.get((source_id, segment_id), "")
                heading_text = str(heading.get("text_original", "")).strip()
                if heading_text and heading_text in text:
                    heading_in_body += 1
                    if any(
                        item["original_text_span"]["text"] in heading_text
                        or heading_text
                        in item["original_text_span"]["text"]
                        for item in indices["entities"].get(
                            (source_id, segment_id),
                            [],
                        )
                    ):
                        heading_extraction_overlap += 1
            per_book.append(
                {
                    "book_id": book_id,
                    "title": BOOK_SAMPLE_PLAN[book_id]["title"],
                    "segments": len(segments),
                    "characters": character_count,
                    "entity_mentions": entity_count,
                    "entity_mentions_per_segment": round(
                        entity_count / len(segments),
                        3,
                    ),
                    "entity_mentions_per_1000_characters": round(
                        entity_count / character_count * 1000,
                        3,
                    )
                    if character_count
                    else 0.0,
                    "event_mentions": event_count,
                    "event_mentions_per_segment": round(
                        event_count / len(segments),
                        3,
                    ),
                    "overlapping_entity_span_pairs": overlap_pairs,
                    "duplicate_entity_spans": exact_duplicate_spans,
                }
            )

        invalid_spans: list[dict[str, Any]] = []
        checked_spans = 0
        for collection_name, items in (
            ("ENTITY", extraction["entities"]),
            ("EVENT", extraction["events"]),
            ("CLAIM", extraction["claims"]),
            ("RELATION", extraction["relations"]),
            ("TEMPORAL", extraction["temporals"]),
            ("ISNAD", extraction["isnads"]),
        ):
            for item in items:
                span = _span(item)
                if span is None:
                    invalid_spans.append(
                        {
                            "collection": collection_name,
                            "id": next(
                                (
                                    value
                                    for key, value in item.items()
                                    if key.endswith("_id")
                                ),
                                "",
                            ),
                            "reason": "MISSING_SPAN",
                        }
                    )
                    continue
                checked_spans += 1
                text = segment_texts.get(
                    (str(item["source_id"]), int(item["segment_id"])),
                    "",
                )
                start = int(span["start"])
                end = int(span["end"])
                if (
                    start < 0
                    or end <= start
                    or end > len(text)
                    or text[start:end] != span["text"]
                ):
                    invalid_spans.append(
                        {
                            "collection": collection_name,
                            "id": next(
                                (
                                    value
                                    for key, value in item.items()
                                    if key.endswith("_id")
                                ),
                                "",
                            ),
                            "reason": "SPAN_TEXT_MISMATCH",
                        }
                    )

        context_by_surface: dict[str, set[str]] = defaultdict(set)
        for item in extraction["entities"]:
            context_by_surface[item["normalized_surface_form"]].add(
                item.get("mention_context", "BODY")
            )
        cross_context_surfaces = sorted(
            surface
            for surface, contexts in context_by_surface.items()
            if {"BODY", "ISNAD"}.issubset(contexts)
        )
        event_type_distribution = Counter(
            item["event_type"]
            for item in extraction["events"]
        )
        sira = next(
            item for item in per_book if item["book_id"] == 619
        )
        history = next(
            item for item in per_book if item["book_id"] == 400
        )
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "per_book_density": per_book,
            "structural_integrity": {
                "checked_spans": checked_spans,
                "invalid_spans": len(invalid_spans),
                "span_integrity_rate": round(
                    (checked_spans - len(invalid_spans))
                    / checked_spans,
                    6,
                )
                if checked_spans
                else None,
                "locator_missing_count": sum(
                    not item.get("locator")
                    for collection in (
                        extraction["entities"],
                        extraction["events"],
                        extraction["claims"],
                        extraction["relations"],
                        extraction["temporals"],
                        extraction["isnads"],
                    )
                    for item in collection
                ),
            },
            "invalid_span_examples": invalid_spans[:20],
            "history_density_finding": {
                "book_id": 400,
                "entity_mentions": history["entity_mentions"],
                "segments": history["segments"],
                "characters": history["characters"],
                "entity_mentions_per_segment": history[
                    "entity_mentions_per_segment"
                ],
                "entity_mentions_per_1000_characters": history[
                    "entity_mentions_per_1000_characters"
                ],
                "overlapping_entity_span_pairs": history[
                    "overlapping_entity_span_pairs"
                ],
                "duplicate_entity_spans": history[
                    "duplicate_entity_spans"
                ],
                "interpretation": (
                    "High density is associated with long chronicle entries, "
                    "nested name patterns, and overlapping title/lineage rules."
                ),
            },
            "sira_low_event_finding": {
                "book_id": 619,
                "event_mentions": sira["event_mentions"],
                "segments": sira["segments"],
                "uncovered_trigger_segments": sum(
                    item["book_id"] == 619
                    for item in uncovered_trigger_segments
                ),
                "interpretation": (
                    "The phase-one event trigger vocabulary does not cover "
                    "many sira narrative verbs and the book contains "
                    "substantial verse/paratext structure."
                ),
            },
            "heading_analysis": {
                "headings_present_inside_body": heading_in_body,
                "headings_with_entity_extraction_overlap": (
                    heading_extraction_overlap
                ),
                "risk": (
                    "Heading text can be counted as body evidence when the "
                    "source segment embeds the heading."
                ),
            },
            "structure_risks": {
                "poetry_or_short_line_segments": poetry_like_segments,
                "index_like_segments": index_like_segments,
                "uncovered_historical_trigger_segments": len(
                    uncovered_trigger_segments
                ),
                "uncovered_trigger_examples": (
                    uncovered_trigger_segments[:20]
                ),
            },
            "isnad_context_analysis": {
                "detected_chains": len(extraction["isnads"]),
                "surfaces_seen_in_body_and_isnad_count": len(
                    cross_context_surfaces
                ),
                "surfaces_seen_in_body_and_isnad_examples": (
                    cross_context_surfaces[:20]
                ),
                "automatic_authenticity_judgment": False,
            },
            "event_type_distribution": [
                {"event_type": key, "count": value}
                for key, value in sorted(event_type_distribution.items())
            ],
        }

    @staticmethod
    def _error_taxonomy(
        systematic: dict[str, Any],
        review: dict[str, Any],
    ) -> dict[str, Any]:
        category_counts = {
            item["category"]: item["count"]
            for item in review["category_distribution"]
        }
        history = systematic["history_density_finding"]
        sira = systematic["sira_low_event_finding"]
        heading = systematic["heading_analysis"]
        structures = systematic["structure_risks"]
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "status": "DIAGNOSTIC_NOT_GOLD_CONFIRMED",
            "findings": [
                {
                    "finding_id": "ENTITY_BOUNDARY_OVERGENERATION",
                    "severity": "HIGH",
                    "evidence_count": history["entity_mentions"],
                    "evidence": history,
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "COMMON_NOUN_PERSON_CANDIDATES",
                    "severity": "HIGH",
                    "evidence_count": category_counts.get(
                        "COMMON_NOUN_MISTAKEN_FOR_PERSON",
                        0,
                    ),
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "SIRA_EVENT_TRIGGER_UNDERCOVERAGE",
                    "severity": "HIGH",
                    "evidence_count": sira[
                        "uncovered_trigger_segments"
                    ],
                    "evidence": sira,
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "UNCOVERED_HISTORICAL_TRIGGERS",
                    "severity": "HIGH",
                    "evidence_count": structures[
                        "uncovered_historical_trigger_segments"
                    ],
                    "evidence": {
                        "segment_count": structures[
                            "uncovered_historical_trigger_segments"
                        ],
                        "examples": structures[
                            "uncovered_trigger_examples"
                        ],
                    },
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "HEADING_BODY_CONTAMINATION_RISK",
                    "severity": "MEDIUM",
                    "evidence_count": heading[
                        "headings_with_entity_extraction_overlap"
                    ],
                    "evidence": heading,
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "POETRY_OR_PARATEXT_RULE_MISMATCH",
                    "severity": "MEDIUM",
                    "evidence_count": structures[
                        "poetry_or_short_line_segments"
                    ]
                    + structures["index_like_segments"],
                    "evidence": structures,
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "ISNAD_BODY_CONTEXT_AMBIGUITY",
                    "severity": "HIGH",
                    "evidence_count": category_counts.get(
                        "NARRATOR_CONTEXT_AMBIGUITY",
                        0,
                    ),
                    "evidence": systematic["isnad_context_analysis"],
                    "gold_confirmation_required": True,
                },
                {
                    "finding_id": "SPAN_OR_LOCATOR_INTEGRITY",
                    "severity": (
                        "CRITICAL"
                        if systematic["structural_integrity"][
                            "invalid_spans"
                        ]
                        or systematic["structural_integrity"][
                            "locator_missing_count"
                        ]
                        else "INFO"
                    ),
                    "evidence_count": systematic[
                        "structural_integrity"
                    ]["invalid_spans"],
                    "evidence": systematic["structural_integrity"],
                    "gold_confirmation_required": False,
                },
            ],
        }

    @staticmethod
    def _improvement_backlog(
        taxonomy: dict[str, Any],
    ) -> dict[str, Any]:
        items = [
            (
                "Q-001",
                "tokenizer and Arabic normalization",
                "Introduce boundary-aware Arabic tokens without altering original text.",
                "HIGH",
                "HIGH",
                "MEDIUM",
                "MEDIUM",
            ),
            (
                "Q-002",
                "entity boundary detection",
                "Stop title, kunya, work, and lineage captures at clause boundaries.",
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "HIGH",
            ),
            (
                "Q-003",
                "name parsing",
                "Model kunya, ism, nasab, laqab, and nisba as separate reviewed parts.",
                "HIGH",
                "HIGH",
                "HIGH",
                "MEDIUM",
            ),
            (
                "Q-004",
                "entity typing",
                "Separate lexical title evidence from canonical entity type evidence.",
                "HIGH",
                "MEDIUM",
                "MEDIUM",
                "HIGH",
            ),
            (
                "Q-005",
                "event trigger detection",
                "Add reviewed sira and chronicle trigger lexicons with negative contexts.",
                "CRITICAL",
                "HIGH",
                "MEDIUM",
                "HIGH",
            ),
            (
                "Q-006",
                "relation extraction",
                "Bind relation arguments by explicit local syntax, not nearest mentions alone.",
                "CRITICAL",
                "HIGH",
                "HIGH",
                "HIGH",
            ),
            (
                "Q-007",
                "temporal extraction",
                "Distinguish historical before/after from logical discourse usage.",
                "HIGH",
                "HIGH",
                "MEDIUM",
                "MEDIUM",
            ),
            (
                "Q-008",
                "isnad detection",
                "Parse narrator connectors and matn boundary with unresolved-pronoun states.",
                "CRITICAL",
                "HIGH",
                "HIGH",
                "HIGH",
            ),
            (
                "Q-009",
                "entity resolution",
                "Require reviewed name components and context compatibility before safe linking.",
                "CRITICAL",
                "HIGH",
                "HIGH",
                "HIGH",
            ),
        ]
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "source_taxonomy_status": taxonomy["status"],
            "ordering_rule": (
                "impact descending, confidence descending, cost ascending, "
                "backlog_id ascending"
            ),
            "items": [
                {
                    "backlog_id": item[0],
                    "area": item[1],
                    "action": item[2],
                    "impact": item[3],
                    "confidence": item[4],
                    "implementation_cost": item[5],
                    "regression_risk": item[6],
                    "requires_gold_validation": True,
                    "status": "PROPOSED",
                }
                for item in items
            ],
        }

    @staticmethod
    def _readiness_gate(
        baseline: dict[str, Any],
    ) -> dict[str, Any]:
        thresholds = [
            ("ENTITY_PRECISION", ">=", 0.90),
            ("ENTITY_RECALL", ">=", 0.85),
            ("EVENT_PRECISION", ">=", 0.85),
            ("EVENT_RECALL", ">=", 0.80),
            ("RELATION_PRECISION", ">=", 0.85),
            ("TEMPORAL_PRECISION", ">=", 0.90),
            ("ISNAD_DETECTION_PRECISION", ">=", 0.90),
            ("LOCATOR_INTEGRITY", "==", 1.0),
            ("SPAN_EXACT_INTEGRITY", ">=", 0.99),
            ("UNSUPPORTED_MERGE_RATE", "==", 0.0),
            ("FALSE_POSITIVE_RATE", "<=", 0.10),
            ("DETERMINISTIC_REPRODUCIBILITY", "==", 1.0),
        ]
        return {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "status": "BLOCKED_PENDING_HUMAN_GOLD_ANNOTATION",
            "knowledge_graph_build_allowed": False,
            "thresholds": [
                {
                    "gate_id": gate_id,
                    "operator": operator,
                    "threshold": threshold,
                    "measured_value": None,
                    "status": "UNVERIFIED",
                }
                for gate_id, operator, threshold in thresholds
            ],
            "baseline_evaluation_status": baseline["status"],
            "rule": (
                "No semantic threshold may pass before human-reviewed Gold "
                "annotations are evaluated."
            ),
        }

    @staticmethod
    def _gold_markdown(gold: dict[str, Any]) -> str:
        lines = [
            "# Shamela Extraction Gold Annotation Review",
            "",
            f"Status: `{PENDING_HUMAN_ANNOTATION}`",
            "",
            "Do not edit `original_text`, `source_id`, `locator`, or offsets.",
            "Fill expected fields only after reading the source segment.",
            "",
        ]
        for index, item in enumerate(gold["annotations"], 1):
            current = item["current_extraction"]
            lines.extend(
                [
                    f"## {index}. Book {item['book_id']} / Segment {item['segment_id']}",
                    "",
                    f"- Source: `{item['source_id']}`",
                    f"- Locator: `{item['locator']}`",
                    f"- Reviewer status: `{item['reviewer_status']}`",
                    (
                        "- Current counts: "
                        f"entities={len(current['entities'])}, "
                        f"events={len(current['events'])}, "
                        f"relations={len(current['relations'])}, "
                        f"temporals={len(current['temporal_mentions'])}, "
                        f"isnad={len(current['isnad_chains'])}"
                    ),
                    "",
                    "### Original text",
                    "",
                    "```text",
                    item["original_text"],
                    "```",
                    "",
                    "### Human annotation",
                    "",
                    "- Expected entities:",
                    "- Expected entity types:",
                    "- Expected events:",
                    "- Expected relations:",
                    "- Expected temporal mentions:",
                    "- Expected isnad:",
                    "- Explicitly absent items:",
                    "- Reviewer notes:",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _audit_markdown(
        manifest: dict[str, Any],
        systematic: dict[str, Any],
        review: dict[str, Any],
        baseline: dict[str, Any],
        readiness: dict[str, Any],
    ) -> str:
        lines = [
            "# Shamela Extraction Quality Audit",
            "",
            f"- Audit ID: `{manifest['audit_id']}`",
            f"- Sample size: {manifest['sample_count']}",
            f"- Gold status: `{baseline['status']}`",
            f"- Knowledge Graph gate: `{readiness['status']}`",
            "",
            "## Important interpretation",
            "",
            "The audit has created a deterministic review set, not final "
            "precision or recall scores. Semantic metrics remain unset until "
            "human annotations are completed.",
            "",
            "## Review queue",
            "",
            (
                f"- HUMAN_REVIEW_REQUIRED: "
                f"{review['human_review_required_total']}"
            ),
            (
                f"- Partial-name DO_NOT_MERGE groups: "
                f"{review['do_not_merge_partial_collision_count']}"
            ),
            "",
            "## Structural integrity",
            "",
            (
                f"- Checked spans: "
                f"{systematic['structural_integrity']['checked_spans']}"
            ),
            (
                f"- Invalid spans: "
                f"{systematic['structural_integrity']['invalid_spans']}"
            ),
            (
                f"- Missing locators: "
                f"{systematic['structural_integrity']['locator_missing_count']}"
            ),
            "",
            "## Principal diagnostic findings",
            "",
            (
                "- The history book has very high entity density and "
                "overlapping name-boundary evidence."
            ),
            (
                "- The sira book has low event yield and uncovered narrative "
                "triggers."
            ),
            (
                "- Heading text, verse, short-line structures, and paratext "
                "require separate handling."
            ),
            (
                "- Isnad/body boundaries remain conservative and require "
                "human review."
            ),
            "",
            "## Scope boundary",
            "",
            "- No extractor rules were changed.",
            "- No Knowledge Graph was built.",
            "- No external AI or network service was used.",
            "- No Shamela installation file was accessed or modified.",
        ]
        return "\n".join(lines).rstrip() + "\n"


def run_shamela_extraction_quality_audit(
    project_root: str | Path,
    pilot_root: str | Path,
    extraction_root: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    return ShamelaExtractionQualityAudit(
        project_root,
        pilot_root,
        extraction_root,
        output_root,
    ).run()


__all__ = [
    "AUDIT_SCHEMA_VERSION",
    "ShamelaExtractionQualityAudit",
    "run_shamela_extraction_quality_audit",
]
