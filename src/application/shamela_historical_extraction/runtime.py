"""Provenance-first historical extraction over the five-book Shamela pilot."""

from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_assessment_runtime import assess_project_claims
from src.application.project_runtime import (
    load_project,
    load_sources,
    project_paths,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)

from .arabic_rules import (
    entity_candidates,
    event_candidates,
    explicit_relation_candidates,
    normalize_surface,
    resolution_key,
    temporal_candidates,
)
from .models import (
    CanonicalEntityCandidate,
    ENTITY_TYPES,
    EntityMention,
    EventMention,
    HistoricalClaim,
    IsnadChain,
    IsnadNarrator,
    RELATION_TYPES,
    RelationMention,
    TemporalMention,
    TextSpan,
)


EXTRACTOR_VERSION = "shamela-historical-extractor-v1"
EXTRACTION_SCHEMA_VERSION = "shamela-historical-extraction-pilot-v1"
EXPECTED_BOOK_COUNT = 5


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


def _atomic_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".siraj-",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name
        with handle:
            handle.write(_canonical_json(payload).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=".siraj-",
            suffix=".tmp",
            delete=False,
        )
        temporary = handle.name
        with handle:
            handle.write(text.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _modality(text: str) -> str:
    if "اختلف" in text or "على قولين" in text:
        return "DISPUTED_SOURCE_REPORT"
    if any(token in text for token in ("قيل", "يقال", "زعم", "روي", "رُوي")):
        return "REPORTED_SOURCE_ASSERTION"
    if any(token in text for token in ("لعل", "ربما", "نحو", "قرابة", "حوالي")):
        return "UNCERTAIN_SOURCE_ASSERTION"
    return "SOURCE_ASSERTION"


def _mention_payload(item: EntityMention) -> dict[str, Any]:
    return asdict(item)


class ShamelaHistoricalExtractionPilot:
    """Runs local deterministic extraction over an ingested five-book corpus."""

    def __init__(
        self,
        project_root: str | Path,
        pilot_root: str | Path,
        output_root: str | Path,
        *,
        segment_limit_per_book: int | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.pilot_root = Path(pilot_root).resolve()
        self.output_root = Path(output_root).resolve()
        self.segment_limit_per_book = segment_limit_per_book
        self.paths = project_paths(self.project_root)
        working_root = Path(self.paths.working_root).resolve()

        try:
            self.output_root.relative_to(working_root)
        except ValueError as error:
            raise ValueError("EXTRACTION_OUTPUT_MUST_BE_INSIDE_PROJECT_WORKING") from error

        if segment_limit_per_book is not None and segment_limit_per_book < 1:
            raise ValueError("INVALID_SEGMENT_LIMIT")

    def run(self) -> dict[str, Any]:
        project = load_project(self.project_root)
        source_registry = load_sources(self.project_root)
        catalog = _read_json(
            self.pilot_root / "shamela-pilot-catalog.json"
        )
        ledger = _read_json(
            self.pilot_root / "shamela-pilot-source-ledger.json"
        )
        normalized_registry = _read_json(
            Path(self.paths.working_root)
            / "shamela-pilot-ingestion"
            / "normalized-sources.json"
        )
        self._validate_inputs(
            catalog,
            ledger,
            normalized_registry,
            source_registry,
        )

        ledger_by_book = {
            int(item["book_id"]): item
            for item in ledger
        }
        entity_mentions: list[EntityMention] = []
        event_mentions: list[EventMention] = []
        historical_claims: list[HistoricalClaim] = []
        relation_mentions: list[RelationMention] = []
        temporal_mentions: list[TemporalMention] = []
        isnad_chains: list[IsnadChain] = []
        coverage: list[dict[str, Any]] = []
        segment_texts: dict[
            tuple[str, int],
            tuple[str, str],
        ] = {}

        for catalog_entry in sorted(
            catalog,
            key=lambda item: int(item["book_id"]),
        ):
            book_id = int(catalog_entry["book_id"])
            book = _read_json(
                self.pilot_root
                / str(catalog_entry["book_artifact"])
            )
            source_id = str(ledger_by_book[book_id]["source_id"])
            book_result = self._extract_book(
                book,
                source_id,
                entity_mentions,
                event_mentions,
                historical_claims,
                relation_mentions,
                temporal_mentions,
                isnad_chains,
                segment_texts,
            )
            coverage.append(
                {
                    "book_id": book_id,
                    "title": catalog_entry["title"],
                    "source_id": source_id,
                    **book_result,
                }
            )

        entity_mentions = sorted(
            entity_mentions,
            key=lambda item: item.mention_id,
        )
        event_mentions = sorted(
            event_mentions,
            key=lambda item: item.event_mention_id,
        )
        historical_claims = sorted(
            historical_claims,
            key=lambda item: item.claim_id,
        )
        relation_mentions = sorted(
            relation_mentions,
            key=lambda item: item.relation_id,
        )
        temporal_mentions = sorted(
            temporal_mentions,
            key=lambda item: item.temporal_id,
        )
        isnad_chains = sorted(
            isnad_chains,
            key=lambda item: item.chain_id,
        )

        candidates, review_queue = self._resolve_entities(
            entity_mentions
        )
        candidates = sorted(
            candidates,
            key=lambda item: item.candidate_id,
        )
        review_queue = sorted(
            review_queue,
            key=lambda item: item["review_id"],
        )

        run_id = deterministic_id(
            "shamela_historical_extraction",
            [
                project["project_id"],
                EXTRACTOR_VERSION,
                [item["book_id"] for item in coverage],
                [item.claim_id for item in historical_claims],
                [item.mention_id for item in entity_mentions],
            ],
        )
        common = {
            "schema_version": EXTRACTION_SCHEMA_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "run_id": run_id,
            "created_at": CANONICAL_TIMESTAMP,
        }

        outputs = {
            "entity-mentions.json": {
                **common,
                "count": len(entity_mentions),
                "entity_mentions": [
                    _mention_payload(item)
                    for item in entity_mentions
                ],
            },
            "canonical-entity-candidates.json": {
                **common,
                "count": len(candidates),
                "canonical_entity_candidates": [
                    asdict(item)
                    for item in candidates
                ],
            },
            "event-mentions.json": {
                **common,
                "count": len(event_mentions),
                "event_mentions": [
                    asdict(item)
                    for item in event_mentions
                ],
            },
            "historical-claims.json": {
                **common,
                "count": len(historical_claims),
                "historical_claims": [
                    asdict(item)
                    for item in historical_claims
                ],
            },
            "relation-mentions.json": {
                **common,
                "count": len(relation_mentions),
                "relation_mentions": [
                    asdict(item)
                    for item in relation_mentions
                ],
            },
            "isnad-chains.json": {
                **common,
                "count": len(isnad_chains),
                "isnad_chains": [
                    asdict(item)
                    for item in isnad_chains
                ],
                "limitations": [
                    "Chain order records source wording only.",
                    "No hadith authenticity judgment is performed.",
                ],
            },
            "temporal-mentions.json": {
                **common,
                "count": len(temporal_mentions),
                "temporal_mentions": [
                    asdict(item)
                    for item in temporal_mentions
                ],
                "limitations": [
                    "No Hijri-to-Gregorian conversion is performed.",
                    "Approximate and disputed expressions retain their precision.",
                ],
            },
            "entity-resolution-review-queue.json": {
                **common,
                "count": len(review_queue),
                "review_items": review_queue,
            },
            "extraction-coverage-report.json": {
                **common,
                "book_count": len(coverage),
                "books": coverage,
                "scope": (
                    "ALL_BODY_SEGMENTS_LIGHTWEIGHT_RULES"
                    if self.segment_limit_per_book is None
                    else "DETERMINISTIC_BOUNDED_SAMPLE"
                ),
                "footnote_policy": "PRESERVED_BUT_NOT_ANALYZED",
            },
        }

        validation = self._validate_outputs(
            outputs,
            segment_texts,
        )
        outputs["extraction-validation-report.json"] = {
            **common,
            **validation,
        }

        knowledge_bridge = self.output_root / "knowledge-bridge"
        bridge = self._build_knowledge_bridge(
            project["project_id"],
            run_id,
            historical_claims,
        )
        for filename, payload in bridge.items():
            _atomic_write(knowledge_bridge / filename, payload)

        assessment_result = assess_project_claims(
            str(self.project_root),
            knowledge_root=knowledge_bridge,
            assessment_root=self.output_root / "assessment",
        )

        manifest = {
            **common,
            "status": (
                "VALID"
                if validation["status"] == "VALID"
                else "INVALID"
            ),
            "project_id": project["project_id"],
            "input_ingestion": "shamela-pilot-ingestion",
            "pilot_book_count": len(coverage),
            "entity_mention_count": len(entity_mentions),
            "canonical_candidate_count": len(candidates),
            "event_mention_count": len(event_mentions),
            "claim_count": len(historical_claims),
            "relation_mention_count": len(relation_mentions),
            "isnad_chain_count": len(isnad_chains),
            "temporal_mention_count": len(temporal_mentions),
            "human_review_required_count": sum(
                item.review_status == "HUMAN_REVIEW_REQUIRED"
                for item in candidates
            ),
            "assessment_run_id": assessment_result[
                "assessment_run_id"
            ],
            "assessment_status": assessment_result["status"],
            "limitations": [
                "Outputs are source-attributed mentions and claims, not historical facts.",
                "Entity resolution produces proposals only; no canonical merge is executed.",
                "Footnotes remain separate and are not analyzed in this pilot.",
                "Rules are deterministic and conservative; absence of a mention is not evidence of absence.",
            ],
        }
        outputs["extraction-run-manifest.json"] = manifest

        self.output_root.mkdir(parents=True, exist_ok=True)
        for filename, payload in sorted(outputs.items()):
            _atomic_write(self.output_root / filename, payload)
        _atomic_write_text(
            self.output_root / "extraction-architecture.md",
            self._architecture_note(),
        )

        persistence_records = self._persist_outputs(
            run_id,
            outputs,
        )
        return {
            **manifest,
            "output_root": str(self.output_root),
            "coverage": coverage,
            "persistence_record_ids": persistence_records,
            "review_queue_count": len(review_queue),
        }

    def _validate_inputs(
        self,
        catalog: Any,
        ledger: Any,
        normalized_registry: Any,
        source_registry: Any,
    ) -> None:
        if not isinstance(catalog, list) or len(catalog) != EXPECTED_BOOK_COUNT:
            raise ValueError("PILOT_MUST_CONTAIN_EXACTLY_FIVE_BOOKS")
        if not isinstance(ledger, list) or len(ledger) != EXPECTED_BOOK_COUNT:
            raise ValueError("INVALID_PILOT_SOURCE_LEDGER")
        book_ids = [int(item["book_id"]) for item in catalog]
        if len(book_ids) != len(set(book_ids)):
            raise ValueError("DUPLICATE_PILOT_BOOK_ID")
        ledger_ids = {
            int(item["book_id"]): str(item["source_id"])
            for item in ledger
        }
        normalized_ids = {
            str(item["source_id"])
            for item in normalized_registry.get("sources", [])
        }
        registered_ids = {
            str(item["source_id"])
            for item in source_registry.get("sources", [])
        }
        if set(ledger_ids) != set(book_ids):
            raise ValueError("PILOT_LEDGER_BOOK_COVERAGE_MISMATCH")
        if not set(ledger_ids.values()).issubset(normalized_ids):
            raise ValueError("PILOT_SOURCE_NOT_INGESTED")
        if not set(ledger_ids.values()).issubset(registered_ids):
            raise ValueError("PILOT_SOURCE_NOT_REGISTERED")
        if any(
            item.get("source_type") != "SHAMELA_LOCAL_BOOK"
            or not item.get("source_locator")
            for item in ledger
        ):
            raise ValueError("INVALID_SHAMELA_SOURCE_PROVENANCE")

    def _extract_book(
        self,
        book: dict[str, Any],
        source_id: str,
        entity_mentions: list[EntityMention],
        event_mentions: list[EventMention],
        historical_claims: list[HistoricalClaim],
        relation_mentions: list[RelationMention],
        temporal_mentions: list[TemporalMention],
        isnad_chains: list[IsnadChain],
        segment_texts: dict[tuple[str, int], tuple[str, str]],
    ) -> dict[str, Any]:
        all_segments = sorted(
            book["segments"],
            key=lambda item: int(item["segment_id"]),
        )
        selected = (
            all_segments
            if self.segment_limit_per_book is None
            else all_segments[: self.segment_limit_per_book]
        )
        start_counts = (
            len(entity_mentions),
            len(event_mentions),
            len(relation_mentions),
            len(historical_claims),
            len(temporal_mentions),
            len(isnad_chains),
        )
        errors: list[dict[str, Any]] = []

        for segment in selected:
            try:
                self._extract_segment(
                    source_id,
                    segment,
                    entity_mentions,
                    event_mentions,
                    historical_claims,
                    relation_mentions,
                    temporal_mentions,
                    isnad_chains,
                    segment_texts,
                )
            except (KeyError, TypeError, ValueError) as error:
                errors.append(
                    {
                        "segment_id": int(segment.get("segment_id", -1)),
                        "code": type(error).__name__,
                        "detail": str(error),
                    }
                )

        end_counts = (
            len(entity_mentions),
            len(event_mentions),
            len(relation_mentions),
            len(historical_claims),
            len(temporal_mentions),
            len(isnad_chains),
        )
        analyzed = len(selected) - len(errors)
        return {
            "total_segments": len(all_segments),
            "analyzed_segments": analyzed,
            "skipped_segments": len(all_segments) - analyzed,
            "entity_mentions": end_counts[0] - start_counts[0],
            "event_mentions": end_counts[1] - start_counts[1],
            "relation_mentions": end_counts[2] - start_counts[2],
            "claims": end_counts[3] - start_counts[3],
            "temporal_mentions": end_counts[4] - start_counts[4],
            "isnad_chains": end_counts[5] - start_counts[5],
            "footnote_segments_available": sum(
                bool(item.get("foot_original", "").strip())
                for item in all_segments
            ),
            "extraction_errors": errors,
            "coverage_percentage": round(
                (analyzed / len(all_segments) * 100)
                if all_segments
                else 0.0,
                2,
            ),
        }

    def _extract_segment(
        self,
        source_id: str,
        segment: dict[str, Any],
        entity_mentions: list[EntityMention],
        event_mentions: list[EventMention],
        historical_claims: list[HistoricalClaim],
        relation_mentions: list[RelationMention],
        temporal_mentions: list[TemporalMention],
        isnad_chains: list[IsnadChain],
        segment_texts: dict[tuple[str, int], tuple[str, str]],
    ) -> None:
        segment_id = int(segment["segment_id"])
        locator = str(segment["locator"])
        original = str(segment["body_original"])
        foot = str(segment.get("foot_original", ""))
        if not original.strip() or not locator:
            raise ValueError("EMPTY_SEGMENT_OR_LOCATOR")
        segment_texts[(source_id, segment_id)] = (original, foot)

        local_mentions: list[dict[str, Any]] = []
        for raw in entity_candidates(original):
            span_text = original[raw["start"]:raw["end"]]
            if span_text != raw["surface"]:
                raise ValueError("ENTITY_SPAN_MISMATCH")
            types = sorted(set(raw["types"]))
            if any(item not in ENTITY_TYPES for item in types):
                raise ValueError("UNKNOWN_ENTITY_TYPE")
            mention_id = deterministic_id(
                "shamela_entity_mention",
                [
                    source_id,
                    locator,
                    segment_id,
                    raw["start"],
                    raw["end"],
                    span_text,
                    types,
                    raw["context"],
                ],
            )
            mention = EntityMention(
                mention_id=mention_id,
                source_id=source_id,
                locator=locator,
                segment_id=segment_id,
                original_text_span=TextSpan(
                    raw["start"],
                    raw["end"],
                    span_text,
                ),
                normalized_surface_form=normalize_surface(
                    span_text
                ),
                entity_type_candidate=types,
                extraction_confidence=float(raw["confidence"]),
                extractor_version=EXTRACTOR_VERSION,
                mention_context=str(raw["context"]),
                rule_id=str(raw["rule_id"]),
            )
            entity_mentions.append(mention)
            local_mentions.append(
                {
                    **raw,
                    "mention_id": mention_id,
                    "normalized": mention.normalized_surface_form,
                }
            )

        local_temporals: list[TemporalMention] = []
        for raw in temporal_candidates(original):
            span = TextSpan(
                raw["start"],
                raw["end"],
                original[raw["start"]:raw["end"]],
            )
            temporal = TemporalMention(
                temporal_id=deterministic_id(
                    "shamela_temporal_mention",
                    [
                        source_id,
                        locator,
                        segment_id,
                        span.start,
                        span.end,
                        raw["value"],
                        raw["calendar"],
                        raw["precision"],
                    ],
                ),
                source_id=source_id,
                locator=locator,
                segment_id=segment_id,
                original_text_span=span,
                normalized_value=str(raw["value"]),
                calendar=str(raw["calendar"]),
                temporal_type=str(raw["type"]),
                temporal_precision=str(raw["precision"]),
                rule_id=str(raw["rule_id"]),
            )
            temporal_mentions.append(temporal)
            local_temporals.append(temporal)

        mention_by_id = {
            item.mention_id: item
            for item in entity_mentions
            if item.source_id == source_id
            and item.segment_id == segment_id
        }
        local_relations: list[RelationMention] = []
        for raw in explicit_relation_candidates(
            original,
            local_mentions,
        ):
            if raw["type"] not in RELATION_TYPES:
                raise ValueError("UNKNOWN_RELATION_TYPE")
            evidence_span = TextSpan(
                raw["start"],
                raw["end"],
                original[raw["start"]:raw["end"]],
            )
            relation = RelationMention(
                relation_id=deterministic_id(
                    "shamela_relation_mention",
                    [
                        source_id,
                        locator,
                        raw["subject"]["mention_id"],
                        raw["type"],
                        raw["object"]["mention_id"],
                        evidence_span.start,
                        evidence_span.end,
                    ],
                ),
                subject_mention=raw["subject"]["mention_id"],
                relation_type=raw["type"],
                object_mention=raw["object"]["mention_id"],
                source_id=source_id,
                locator=locator,
                segment_id=segment_id,
                evidence_span=evidence_span,
                extraction_confidence=float(raw["confidence"]),
                rule_id=str(raw["rule_id"]),
            )
            relation_mentions.append(relation)
            local_relations.append(relation)
            subject = mention_by_id[relation.subject_mention]
            object_ = mention_by_id[relation.object_mention]
            historical_claims.append(
                self._claim_for_relation(
                    relation,
                    subject,
                    object_,
                )
            )

        local_events: list[EventMention] = []
        for raw in event_candidates(original):
            span = TextSpan(
                raw["start"],
                raw["end"],
                original[raw["start"]:raw["end"]],
            )
            participants = sorted(
                item["mention_id"]
                for item in local_mentions
                if item["start"] >= span.start
                and item["end"] <= span.end
                and any(
                    kind in item["types"]
                    for kind in (
                        "PERSON",
                        "GROUP",
                        "STATE",
                        "DYNASTY",
                    )
                )
            )
            places = sorted(
                item["mention_id"]
                for item in local_mentions
                if item["start"] >= span.start
                and item["end"] <= span.end
                and "PLACE" in item["types"]
            )
            event_temporal = next(
                (
                    item
                    for item in local_temporals
                    if item.original_text_span.start >= span.start
                    and item.original_text_span.end <= span.end
                ),
                None,
            )
            event = EventMention(
                event_mention_id=deterministic_id(
                    "shamela_event_mention",
                    [
                        source_id,
                        locator,
                        segment_id,
                        span.start,
                        span.end,
                        raw["event_type"],
                        participants,
                        places,
                    ],
                ),
                source_id=source_id,
                locator=locator,
                segment_id=segment_id,
                original_text_span=span,
                event_type=str(raw["event_type"]),
                participants=participants,
                places=places,
                temporal_expression=(
                    event_temporal.original_text_span.text
                    if event_temporal
                    else ""
                ),
                temporal_precision=(
                    event_temporal.temporal_precision
                    if event_temporal
                    else "UNKNOWN"
                ),
                extraction_confidence=float(raw["confidence"]),
                rule_id=str(raw["rule_id"]),
            )
            event_mentions.append(event)
            local_events.append(event)
            historical_claims.append(
                self._claim_for_event(
                    event,
                    mention_by_id,
                )
            )

        narrators = [
            mention_by_id[item["mention_id"]]
            for item in local_mentions
            if item.get("context") == "ISNAD"
        ]
        narrators.sort(
            key=lambda item: item.original_text_span.start
        )
        if len(narrators) >= 2:
            chain_relations = [
                item
                for item in local_relations
                if item.relation_type == "NARRATED_FROM"
            ]
            start = narrators[0].original_text_span.start
            end = narrators[-1].original_text_span.end
            connector_by_id = {
                item["mention_id"]: str(
                    item.get("connector", "")
                )
                for item in local_mentions
            }
            isnad_chains.append(
                IsnadChain(
                    chain_id=deterministic_id(
                        "shamela_isnad_chain",
                        [
                            source_id,
                            locator,
                            segment_id,
                            [item.mention_id for item in narrators],
                        ],
                    ),
                    source_id=source_id,
                    locator=locator,
                    segment_id=segment_id,
                    evidence_span=TextSpan(
                        start,
                        end,
                        original[start:end],
                    ),
                    narrators=[
                        IsnadNarrator(
                            mention_id=item.mention_id,
                            position=position,
                            connector=connector_by_id.get(
                                item.mention_id,
                                "",
                            ),
                        )
                        for position, item in enumerate(narrators)
                    ],
                    relation_ids=sorted(
                        item.relation_id
                        for item in chain_relations
                    ),
                )
            )

    @staticmethod
    def _claim_for_relation(
        relation: RelationMention,
        subject: EntityMention,
        object_: EntityMention,
    ) -> HistoricalClaim:
        original = relation.evidence_span.text
        normalized = (
            f"{subject.normalized_surface_form} "
            f"{relation.relation_type} "
            f"{object_.normalized_surface_form}"
        )
        evidence_id = deterministic_id(
            "shamela_claim_evidence",
            [
                relation.source_id,
                relation.locator,
                relation.evidence_span.start,
                relation.evidence_span.end,
                original,
            ],
        )
        claim_id = deterministic_id(
            "shamela_historical_claim",
            [
                relation.source_id,
                relation.locator,
                original,
                normalized,
                relation.rule_id,
            ],
        )
        return HistoricalClaim(
            claim_id=claim_id,
            source_id=relation.source_id,
            locator=relation.locator,
            segment_id=relation.segment_id,
            original_text=original,
            original_text_span=relation.evidence_span,
            normalized_claim=normalized,
            subject=subject.normalized_surface_form,
            predicate=relation.relation_type,
            object=object_.normalized_surface_form,
            claim_modality=_modality(original),
            historical_confidence="SOURCE_ATTESTED_UNVERIFIED",
            extraction_confidence=relation.extraction_confidence,
            review_status="HUMAN_REVIEW_REQUIRED",
            evidence_id=evidence_id,
            rule_id=relation.rule_id,
        )

    @staticmethod
    def _claim_for_event(
        event: EventMention,
        mention_by_id: dict[str, EntityMention],
    ) -> HistoricalClaim:
        original = event.original_text_span.text
        participant_names = [
            mention_by_id[item].normalized_surface_form
            for item in event.participants
            if item in mention_by_id
        ]
        place_names = [
            mention_by_id[item].normalized_surface_form
            for item in event.places
            if item in mention_by_id
        ]
        subject = (
            participant_names[0]
            if participant_names
            else "UNRESOLVED_SUBJECT"
        )
        object_ = (
            place_names[0]
            if place_names
            else event.temporal_expression
            or "UNRESOLVED_OBJECT"
        )
        normalized = (
            f"{subject} {event.event_type} {object_}"
        )
        evidence_id = deterministic_id(
            "shamela_claim_evidence",
            [
                event.source_id,
                event.locator,
                event.original_text_span.start,
                event.original_text_span.end,
                original,
            ],
        )
        claim_id = deterministic_id(
            "shamela_historical_claim",
            [
                event.source_id,
                event.locator,
                original,
                normalized,
                event.rule_id,
            ],
        )
        return HistoricalClaim(
            claim_id=claim_id,
            source_id=event.source_id,
            locator=event.locator,
            segment_id=event.segment_id,
            original_text=original,
            original_text_span=event.original_text_span,
            normalized_claim=normalized,
            subject=subject,
            predicate=event.event_type,
            object=object_,
            claim_modality=_modality(original),
            historical_confidence="SOURCE_ATTESTED_UNVERIFIED",
            extraction_confidence=event.extraction_confidence,
            review_status="HUMAN_REVIEW_REQUIRED",
            evidence_id=evidence_id,
            rule_id=event.rule_id,
        )

    @staticmethod
    def _resolve_entities(
        mentions: list[EntityMention],
    ) -> tuple[
        list[CanonicalEntityCandidate],
        list[dict[str, Any]],
    ]:
        groups: dict[str, list[EntityMention]] = {}
        for mention in mentions:
            groups.setdefault(
                resolution_key(
                    mention.normalized_surface_form
                ),
                [],
            ).append(mention)

        candidates: list[CanonicalEntityCandidate] = []
        review_queue: list[dict[str, Any]] = []
        for key, grouped in sorted(groups.items()):
            grouped = sorted(
                grouped,
                key=lambda item: item.mention_id,
            )
            aliases = sorted(
                {
                    item.normalized_surface_form
                    for item in grouped
                }
            )
            type_union = sorted(
                {
                    kind
                    for item in grouped
                    for kind in item.entity_type_candidate
                }
            )
            contexts = {
                item.mention_context
                for item in grouped
            }
            high_confidence = all(
                item.extraction_confidence >= 0.9
                for item in grouped
            )
            safe = (
                len(grouped) >= 2
                and high_confidence
                and "ISNAD" not in contexts
                and len(key.split()) >= 2
                and len(aliases) == 1
            )
            status = (
                "AUTO_LINK_SAFE"
                if safe
                else "HUMAN_REVIEW_REQUIRED"
            )
            confidence = (
                0.97
                if safe
                else 0.62
                if len(grouped) >= 2
                else 0.45
            )
            candidate = CanonicalEntityCandidate(
                candidate_id=deterministic_id(
                    "shamela_canonical_entity_candidate",
                    [
                        key,
                        type_union,
                        [item.mention_id for item in grouped],
                        status,
                    ],
                ),
                canonical_name=aliases[0],
                entity_type=type_union,
                aliases=aliases,
                linked_mentions=[
                    item.mention_id
                    for item in grouped
                ],
                merge_confidence=confidence,
                review_status=status,
                rule_ids=sorted(
                    {
                        item.rule_id
                        for item in grouped
                    }
                ),
            )
            candidates.append(candidate)
            if status == "HUMAN_REVIEW_REQUIRED":
                review_queue.append(
                    {
                        "review_id": deterministic_id(
                            "shamela_entity_resolution_review",
                            [candidate.candidate_id],
                        ),
                        "candidate_id": candidate.candidate_id,
                        "review_status": status,
                        "reason": (
                            "ISNAD_CONTEXT_REQUIRES_REVIEW"
                            if "ISNAD" in contexts
                            else "INSUFFICIENT_EXACT_HIGH_CONFIDENCE_SUPPORT"
                        ),
                        "mention_ids": candidate.linked_mentions,
                    }
                )

        last_token_groups: dict[str, set[str]] = {}
        for key in groups:
            if key:
                last_token_groups.setdefault(
                    key.split()[-1],
                    set(),
                ).add(key)
        for token, keys in sorted(last_token_groups.items()):
            if len(keys) < 2:
                continue
            mention_ids = sorted(
                item.mention_id
                for key in keys
                for item in groups[key]
            )
            review_queue.append(
                {
                    "review_id": deterministic_id(
                        "shamela_entity_resolution_do_not_merge",
                        [token, sorted(keys), mention_ids],
                    ),
                    "candidate_id": "",
                    "review_status": "DO_NOT_MERGE",
                    "reason": "PARTIAL_NAME_COLLISION_ONLY",
                    "mention_ids": mention_ids,
                }
            )
        return candidates, review_queue

    def _validate_outputs(
        self,
        outputs: dict[str, dict[str, Any]],
        segment_texts: dict[
            tuple[str, int],
            tuple[str, str],
        ],
    ) -> dict[str, Any]:
        issues: list[dict[str, Any]] = []
        mentions = outputs["entity-mentions.json"][
            "entity_mentions"
        ]
        events = outputs["event-mentions.json"][
            "event_mentions"
        ]
        claims = outputs["historical-claims.json"][
            "historical_claims"
        ]
        relations = outputs["relation-mentions.json"][
            "relation_mentions"
        ]
        candidates = outputs[
            "canonical-entity-candidates.json"
        ]["canonical_entity_candidates"]
        mention_ids = {
            item["mention_id"]
            for item in mentions
        }

        def check_span(
            source_id: str,
            segment_id: int,
            span: dict[str, Any],
            subject_id: str,
        ) -> None:
            body, foot = segment_texts.get(
                (source_id, segment_id),
                ("", ""),
            )
            start = span.get("start")
            end = span.get("end")
            text = span.get("text")
            if (
                not isinstance(start, int)
                or not isinstance(end, int)
                or start < 0
                or end <= start
                or body[start:end] != text
            ):
                issues.append(
                    {
                        "code": "SPAN_MISMATCH",
                        "subject_id": subject_id,
                    }
                )
            if text and text in foot and text not in body:
                issues.append(
                    {
                        "code": "FOOTNOTE_BODY_MIX",
                        "subject_id": subject_id,
                    }
                )

        for mention in mentions:
            if (
                not mention["source_id"]
                or not mention["locator"]
                or not mention["entity_type_candidate"]
            ):
                issues.append(
                    {
                        "code": "INVALID_ENTITY_PROVENANCE",
                        "subject_id": mention["mention_id"],
                    }
                )
            check_span(
                mention["source_id"],
                mention["segment_id"],
                mention["original_text_span"],
                mention["mention_id"],
            )

        for event in events:
            if (
                not event["source_id"]
                or not event["locator"]
                or not event["original_text_span"]["text"]
            ):
                issues.append(
                    {
                        "code": "INVALID_EVENT_PROVENANCE",
                        "subject_id": event["event_mention_id"],
                    }
                )
            check_span(
                event["source_id"],
                event["segment_id"],
                event["original_text_span"],
                event["event_mention_id"],
            )

        for claim in claims:
            if (
                not claim["source_id"]
                or not claim["locator"]
                or not claim["original_text"]
                or not claim["evidence_id"]
            ):
                issues.append(
                    {
                        "code": "INVALID_CLAIM_PROVENANCE",
                        "subject_id": claim["claim_id"],
                    }
                )
            check_span(
                claim["source_id"],
                claim["segment_id"],
                claim["original_text_span"],
                claim["claim_id"],
            )

        for relation in relations:
            if (
                relation["relation_type"] not in RELATION_TYPES
                or relation["subject_mention"] not in mention_ids
                or relation["object_mention"] not in mention_ids
                or not relation["locator"]
            ):
                issues.append(
                    {
                        "code": "INVALID_RELATION_REFERENCE",
                        "subject_id": relation["relation_id"],
                    }
                )
            check_span(
                relation["source_id"],
                relation["segment_id"],
                relation["evidence_span"],
                relation["relation_id"],
            )

        for candidate in candidates:
            if (
                candidate["review_status"] == "AUTO_LINK_SAFE"
                and candidate["merge_confidence"] < 0.92
            ):
                issues.append(
                    {
                        "code": "LOW_CONFIDENCE_AUTO_LINK",
                        "subject_id": candidate["candidate_id"],
                    }
                )

        all_ids: list[str] = []
        for filename, collection_key, id_key in (
            ("entity-mentions.json", "entity_mentions", "mention_id"),
            ("event-mentions.json", "event_mentions", "event_mention_id"),
            ("historical-claims.json", "historical_claims", "claim_id"),
            ("relation-mentions.json", "relation_mentions", "relation_id"),
            ("temporal-mentions.json", "temporal_mentions", "temporal_id"),
            ("isnad-chains.json", "isnad_chains", "chain_id"),
        ):
            identifiers = [
                item[id_key]
                for item in outputs[filename][collection_key]
            ]
            if len(identifiers) != len(set(identifiers)):
                issues.append(
                    {
                        "code": "DUPLICATE_IDENTIFIERS",
                        "subject_id": filename,
                    }
                )
            all_ids.extend(identifiers)

        return {
            "status": "VALID" if not issues else "INVALID",
            "issue_count": len(issues),
            "issues": sorted(
                issues,
                key=lambda item: (
                    item["code"],
                    item["subject_id"],
                ),
            ),
            "validated_object_count": len(all_ids),
        }

    @staticmethod
    def _build_knowledge_bridge(
        project_id: str,
        run_id: str,
        claims: list[HistoricalClaim],
    ) -> dict[str, dict[str, Any]]:
        common = {
            "schema_version": "siraj-knowledge-evidence-v1",
            "project_id": project_id,
            "extraction_id": run_id,
            "created_at": CANONICAL_TIMESTAMP,
        }
        evidence = []
        claim_records = []
        provenance = []
        for claim in claims:
            fingerprint = sha256(
                claim.original_text.encode("utf-8")
            ).hexdigest()
            evidence.append(
                {
                    "evidence_id": claim.evidence_id,
                    "source_id": claim.source_id,
                    "segment_id": str(claim.segment_id),
                    "text": claim.original_text,
                    "start_character": claim.original_text_span.start,
                    "end_character": claim.original_text_span.end,
                    "paragraph_index": claim.segment_id,
                    "sentence_index": 0,
                    "fingerprint": fingerprint,
                    "language": "ar",
                    "status": "PRESENT_IN_SOURCE",
                    "locator": claim.locator,
                }
            )
            claim_records.append(
                {
                    "claim_id": claim.claim_id,
                    "claim_text": claim.normalized_claim,
                    "evidence_ids": [claim.evidence_id],
                    "source_ids": [claim.source_id],
                    "status": "SUPPORTED_BY_SOURCE_TEXT",
                    "extraction_strategy": EXTRACTOR_VERSION,
                    "fingerprint": sha256(
                        claim.normalized_claim.encode("utf-8")
                    ).hexdigest(),
                }
            )
            provenance.append(
                {
                    "provenance_id": deterministic_id(
                        "shamela_claim_provenance",
                        [
                            claim.claim_id,
                            claim.evidence_id,
                            claim.source_id,
                            claim.locator,
                        ],
                    ),
                    "subject_id": claim.claim_id,
                    "subject_type": "CLAIM",
                    "evidence_id": claim.evidence_id,
                    "source_id": claim.source_id,
                    "relation": "SUPPORTED_BY",
                    "locator": claim.locator,
                }
            )
        evidence_by_id = {
            item["evidence_id"]: item
            for item in evidence
        }
        return {
            "claims.json": {
                **common,
                "claims": sorted(
                    claim_records,
                    key=lambda item: item["claim_id"],
                ),
            },
            "evidence.json": {
                **common,
                "evidence": sorted(
                    evidence_by_id.values(),
                    key=lambda item: item["evidence_id"],
                ),
            },
            "provenance.json": {
                **common,
                "provenance": sorted(
                    provenance,
                    key=lambda item: item["provenance_id"],
                ),
            },
        }

    def _persist_outputs(
        self,
        run_id: str,
        outputs: dict[str, dict[str, Any]],
    ) -> list[str]:
        artifact_records: list[
            tuple[str, str, dict[str, Any]]
        ] = []
        for filename, payload in sorted(outputs.items()):
            collection_counts = {
                key: len(value)
                for key, value in sorted(payload.items())
                if isinstance(value, list)
            }
            canonical = _canonical_json(payload).encode("utf-8")
            artifact_records.append(
                (
                    "SHAMELA_HISTORICAL_EXTRACTION_ARTIFACT",
                    deterministic_id(
                        "shamela_extraction_artifact",
                        [run_id, filename],
                    ),
                    {
                        "schema_version": EXTRACTION_SCHEMA_VERSION,
                        "run_id": run_id,
                        "artifact_name": filename,
                        "relative_path": filename,
                        "content_sha256": sha256(canonical).hexdigest(),
                        "content_size_bytes": len(canonical),
                        "collection_counts": collection_counts,
                    },
                )
            )
        records = [
            *artifact_records,
            (
                "SHAMELA_HISTORICAL_EXTRACTION_RUN",
                run_id,
                {
                    "schema_version": EXTRACTION_SCHEMA_VERSION,
                    "run_id": run_id,
                    "artifact_ids": [
                        artifact_id
                        for _, artifact_id, _ in artifact_records
                    ],
                    "artifact_hashes": {
                        payload["artifact_name"]:
                        payload["content_sha256"]
                        for _, _, payload in artifact_records
                    },
                },
            ),
        ]
        with SQLitePersistenceAdapter(
            SQLiteConnectionConfig(self.paths.database)
        ) as adapter:
            adapter.initialize()
            transaction = adapter.save_many(records)
        if not transaction.committed:
            raise RuntimeError(
                transaction.error_code
                or "SHAMELA_EXTRACTION_PERSISTENCE_FAILED"
            )
        return transaction.record_ids

    @staticmethod
    def _architecture_note() -> str:
        return """# Shamela Historical Extraction Pilot

## Boundary

This pilot consumes exactly five Shamela sources already registered and
normalized by the existing project ingestion runtime. It reads staged
`book.v1.json` records to retain volume, page, segment, body, footnote, and
locator boundaries. It never reads from or writes to the Shamela installation.

## Semantics

Every output is a source-attributed mention or claim. No claim is declared a
historical fact. Events are textual event mentions. Relations require explicit
local patterns. Temporal expressions retain their source calendar and
precision; no calendar conversion is performed.

## Isnad handling

Narrators are marked with `mention_context=ISNAD`. Ordered `NARRATED_FROM`
relations record source wording only and do not assess transmission
authenticity. Isnad and body-character mentions cannot receive automatic
cross-context resolution in this pilot.

## Resolution

Entity resolution produces candidates only. `AUTO_LINK_SAFE` requires exact
normalized multi-token identity, repeated high-confidence mentions, and no
isnad context. Partial-name collisions are `DO_NOT_MERGE`; other cases require
human review. No merge mutates source or repository entities.

## Existing pipeline integration

Historical claims are adapted into the existing
`siraj-knowledge-evidence-v1` claim/evidence/provenance contracts and assessed
by `project_assessment_runtime`. All pilot artifacts are persisted through the
existing SQLite persistence adapter. No graph, series, episode, media, network,
or external AI workflow is started.
"""


def run_shamela_historical_extraction(
    project_root: str | Path,
    pilot_root: str | Path,
    output_root: str | Path,
    *,
    segment_limit_per_book: int | None = None,
) -> dict[str, Any]:
    return ShamelaHistoricalExtractionPilot(
        project_root,
        pilot_root,
        output_root,
        segment_limit_per_book=segment_limit_per_book,
    ).run()


__all__ = [
    "EXPECTED_BOOK_COUNT",
    "EXTRACTION_SCHEMA_VERSION",
    "EXTRACTOR_VERSION",
    "ShamelaHistoricalExtractionPilot",
    "run_shamela_historical_extraction",
]
