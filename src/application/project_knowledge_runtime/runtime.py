from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
)
from src.application.project_runtime import (
    load_project,
    project_paths,
)
from src.application.rc_hardening import (
    SQLiteConnectionConfig,
    SQLitePersistenceAdapter,
)


KNOWLEDGE_SCHEMA_VERSION = "siraj-knowledge-evidence-v1"

_SENTENCE_TERMINATORS = {".", "!", "?", "؟", "؛", "\n"}

_DATE_PATTERN = re.compile(
    r"(?<!\d)("
    r"(?:1[0-9]{3}|20[0-9]{2})"
    r"|"
    r"(?:[0-3]?[0-9][/-][01]?[0-9][/-](?:1[0-9]{3}|20[0-9]{2}))"
    r")(?!\d)"
)

_QUOTED_ENTITY_PATTERN = re.compile(
    r'[«"]\s*([^«»"\n]{2,100}?)\s*[»"]'
)

_LATIN_ENTITY_PATTERN = re.compile(
    r"\b(?:[A-Z][a-z]{2,})(?:\s+[A-Z][a-z]{2,}){0,3}\b"
)

_ARABIC_NAME_PREFIX_PATTERN = re.compile(
    r"\b(?:الملك|السلطان|الخليفة|الأمير|القائد|الرئيس|الشيخ|الدكتور|المؤرخ)"
    r"\s+([\u0600-\u06FF][\u0600-\u06FF\s]{1,60})"
)

_SPACE_PATTERN = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class TextSegment:
    segment_id: str
    source_id: str
    position: int
    text: str
    start_character: int
    end_character: int
    paragraph_index: int
    sentence_index: int
    fingerprint: str


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    source_id: str
    segment_id: str
    text: str
    start_character: int
    end_character: int
    paragraph_index: int
    sentence_index: int
    fingerprint: str
    language: str
    status: str = "PRESENT_IN_SOURCE"


@dataclass(frozen=True)
class ClaimRecord:
    claim_id: str
    claim_text: str
    evidence_ids: list[str]
    source_ids: list[str]
    status: str
    extraction_strategy: str
    fingerprint: str


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    entity_name: str
    entity_type: str
    evidence_ids: list[str]
    source_ids: list[str]
    extraction_strategy: str


@dataclass(frozen=True)
class EventRecord:
    event_id: str
    event_text: str
    date_values: list[str]
    evidence_ids: list[str]
    source_ids: list[str]
    status: str


@dataclass(frozen=True)
class ProvenanceRecord:
    provenance_id: str
    subject_id: str
    subject_type: str
    evidence_id: str
    source_id: str
    relation: str


@dataclass(frozen=True)
class KnowledgeVerificationIssue:
    code: str
    subject_id: str = ""
    detail: str = ""


@dataclass(frozen=True)
class KnowledgeVerificationReport:
    project_id: str
    status: str
    segment_count: int
    evidence_count: int
    claim_count: int
    entity_count: int
    event_count: int
    provenance_count: int
    issues: list[KnowledgeVerificationIssue]


def _absolute_path(raw: str | Path, field_name: str) -> Path:
    path = Path(raw).expanduser()

    if not path.is_absolute():
        raise ValueError(f"{field_name}_MUST_BE_ABSOLUTE")

    return path.resolve(strict=False)


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n"


def _atomic_write(path: Path, data: bytes) -> None:
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
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists():
            Path(temporary).unlink(missing_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write(path, _canonical_json(payload).encode("utf-8"))


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path}")

    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"INVALID_JSON:{path}:{error.lineno}:{error.colno}"
        ) from error


def _normalise_segment_text(value: str) -> str:
    return _SPACE_PATTERN.sub(" ", value).strip()


def _segment_text(
    source_id: str,
    text: str,
) -> list[TextSegment]:
    segments: list[TextSegment] = []
    paragraph_index = 0
    sentence_index = 0
    segment_start: int | None = None

    for position, character in enumerate(text):
        if segment_start is None:
            if character.isspace():
                if character == "\n":
                    paragraph_index += 1
                    sentence_index = 0
                continue
            segment_start = position

        if character not in _SENTENCE_TERMINATORS:
            continue

        end = position + 1
        raw = text[segment_start:end]
        normalised = _normalise_segment_text(raw)

        if normalised:
            fingerprint = sha256(
                normalised.encode("utf-8")
            ).hexdigest()

            segments.append(
                TextSegment(
                    segment_id=deterministic_id(
                        "segment",
                        [
                            source_id,
                            segment_start,
                            end,
                            fingerprint,
                        ],
                    ),
                    source_id=source_id,
                    position=len(segments),
                    text=normalised,
                    start_character=segment_start,
                    end_character=end,
                    paragraph_index=paragraph_index,
                    sentence_index=sentence_index,
                    fingerprint=fingerprint,
                )
            )

            sentence_index += 1

        segment_start = None

        if character == "\n":
            paragraph_index += 1
            sentence_index = 0

    if segment_start is not None:
        end = len(text)
        raw = text[segment_start:end]
        normalised = _normalise_segment_text(raw)

        if normalised:
            fingerprint = sha256(
                normalised.encode("utf-8")
            ).hexdigest()

            segments.append(
                TextSegment(
                    segment_id=deterministic_id(
                        "segment",
                        [
                            source_id,
                            segment_start,
                            end,
                            fingerprint,
                        ],
                    ),
                    source_id=source_id,
                    position=len(segments),
                    text=normalised,
                    start_character=segment_start,
                    end_character=end,
                    paragraph_index=paragraph_index,
                    sentence_index=sentence_index,
                    fingerprint=fingerprint,
                )
            )

    return segments


def _is_claim_candidate(text: str) -> bool:
    stripped = text.strip()

    if len(stripped) < 12:
        return False

    if stripped.startswith(("#", "-", "*", "•")):
        return False

    if stripped.endswith(("?", "؟")):
        return False

    alphanumeric_count = sum(
        character.isalnum()
        for character in stripped
    )

    return alphanumeric_count >= 8


def _extract_entity_candidates(text: str) -> list[tuple[str, str, str]]:
    candidates: set[tuple[str, str, str]] = set()

    for match in _QUOTED_ENTITY_PATTERN.finditer(text):
        value = _normalise_segment_text(match.group(1))

        if value:
            candidates.add(
                (
                    value,
                    "NAMED_TERM",
                    "EXPLICIT_QUOTATION",
                )
            )

    for match in _LATIN_ENTITY_PATTERN.finditer(text):
        value = _normalise_segment_text(match.group(0))

        if value:
            candidates.add(
                (
                    value,
                    "NAMED_ENTITY",
                    "LATIN_TITLE_CASE",
                )
            )

    for match in _ARABIC_NAME_PREFIX_PATTERN.finditer(text):
        value = _normalise_segment_text(match.group(0))
        value = re.split(
            r"[،,.;:!?؟؛]",
            value,
            maxsplit=1,
        )[0].strip()

        if 3 <= len(value) <= 80:
            candidates.add(
                (
                    value,
                    "PERSON_OR_TITLE",
                    "ARABIC_EXPLICIT_TITLE",
                )
            )

    return sorted(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )


def _load_normalized_registry(
    project_root: Path,
) -> tuple[dict[str, Any], Path]:
    paths = project_paths(project_root)
    ingestion_root = Path(paths.working_root) / "ingestion"
    registry_path = ingestion_root / "normalized-sources.json"
    registry = _read_json(registry_path)

    if not isinstance(registry, dict):
        raise ValueError("INVALID_NORMALIZED_SOURCE_REGISTRY")

    sources = registry.get("sources")

    if not isinstance(sources, list) or not sources:
        raise ValueError("NO_NORMALIZED_SOURCES")

    return registry, ingestion_root


def extract_project_knowledge(
    project_root: str,
) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    paths = project_paths(root)

    registry, ingestion_root = _load_normalized_registry(root)

    segments: list[TextSegment] = []
    evidence: list[EvidenceRecord] = []
    claims_by_fingerprint: dict[str, ClaimRecord] = {}
    entities_by_identity: dict[
        tuple[str, str],
        EntityRecord,
    ] = {}
    events_by_identity: dict[
        tuple[str, tuple[str, ...]],
        EventRecord,
    ] = {}
    provenance: list[ProvenanceRecord] = []

    for source in sorted(
        registry["sources"],
        key=lambda item: item["source_id"],
    ):
        source_id = str(source["source_id"])
        relative_path = str(source["path"])
        normalized_path = (
            ingestion_root / relative_path
        ).resolve(strict=False)

        try:
            normalized_path.relative_to(ingestion_root.resolve(strict=False))
        except ValueError as error:
            raise ValueError("NORMALIZED_SOURCE_PATH_ESCAPE") from error

        if not normalized_path.is_file():
            raise FileNotFoundError(
                f"NORMALIZED_SOURCE_NOT_FOUND:{normalized_path}"
            )

        raw = normalized_path.read_bytes()

        if sha256(raw).hexdigest() != source.get("sha256"):
            raise ValueError(
                f"NORMALIZED_SOURCE_HASH_MISMATCH:{source_id}"
            )

        text = raw.decode("utf-8")
        source_segments = _segment_text(source_id, text)
        segments.extend(source_segments)

        language = str(
            source.get("metadata", {}).get("language", "und")
        )

        for segment in source_segments:
            evidence_id = deterministic_id(
                "evidence",
                [
                    segment.source_id,
                    segment.segment_id,
                    segment.start_character,
                    segment.end_character,
                    segment.fingerprint,
                ],
            )

            evidence_record = EvidenceRecord(
                evidence_id=evidence_id,
                source_id=segment.source_id,
                segment_id=segment.segment_id,
                text=segment.text,
                start_character=segment.start_character,
                end_character=segment.end_character,
                paragraph_index=segment.paragraph_index,
                sentence_index=segment.sentence_index,
                fingerprint=segment.fingerprint,
                language=language,
            )
            evidence.append(evidence_record)

            if _is_claim_candidate(segment.text):
                claim_fingerprint = sha256(
                    segment.text.casefold().encode("utf-8")
                ).hexdigest()

                existing = claims_by_fingerprint.get(
                    claim_fingerprint
                )

                if existing is None:
                    claim_id = deterministic_id(
                        "claim",
                        [claim_fingerprint],
                    )
                    existing = ClaimRecord(
                        claim_id=claim_id,
                        claim_text=segment.text,
                        evidence_ids=[],
                        source_ids=[],
                        status="SUPPORTED_BY_SOURCE_TEXT",
                        extraction_strategy=(
                            "DECLARATIVE_SEGMENT_V1"
                        ),
                        fingerprint=claim_fingerprint,
                    )
                    claims_by_fingerprint[
                        claim_fingerprint
                    ] = existing

                if evidence_id not in existing.evidence_ids:
                    existing.evidence_ids.append(evidence_id)

                if source_id not in existing.source_ids:
                    existing.source_ids.append(source_id)

                if len(existing.source_ids) > 1:
                    object.__setattr__(
                        existing,
                        "status",
                        "MULTI_SOURCE_SUPPORTED",
                    )

                provenance.append(
                    ProvenanceRecord(
                        provenance_id=deterministic_id(
                            "provenance",
                            [
                                existing.claim_id,
                                evidence_id,
                                source_id,
                                "SUPPORTED_BY",
                            ],
                        ),
                        subject_id=existing.claim_id,
                        subject_type="CLAIM",
                        evidence_id=evidence_id,
                        source_id=source_id,
                        relation="SUPPORTED_BY",
                    )
                )

            for (
                entity_name,
                entity_type,
                strategy,
            ) in _extract_entity_candidates(segment.text):
                identity = (
                    entity_name.casefold(),
                    entity_type,
                )
                entity = entities_by_identity.get(identity)

                if entity is None:
                    entity = EntityRecord(
                        entity_id=deterministic_id(
                            "entity",
                            [
                                entity_name.casefold(),
                                entity_type,
                            ],
                        ),
                        entity_name=entity_name,
                        entity_type=entity_type,
                        evidence_ids=[],
                        source_ids=[],
                        extraction_strategy=strategy,
                    )
                    entities_by_identity[identity] = entity

                if evidence_id not in entity.evidence_ids:
                    entity.evidence_ids.append(evidence_id)

                if source_id not in entity.source_ids:
                    entity.source_ids.append(source_id)

                provenance.append(
                    ProvenanceRecord(
                        provenance_id=deterministic_id(
                            "provenance",
                            [
                                entity.entity_id,
                                evidence_id,
                                source_id,
                                "MENTIONED_IN",
                            ],
                        ),
                        subject_id=entity.entity_id,
                        subject_type="ENTITY",
                        evidence_id=evidence_id,
                        source_id=source_id,
                        relation="MENTIONED_IN",
                    )
                )

            date_values = sorted(
                set(_DATE_PATTERN.findall(segment.text))
            )

            if date_values:
                identity = (
                    segment.text.casefold(),
                    tuple(date_values),
                )
                event = events_by_identity.get(identity)

                if event is None:
                    event = EventRecord(
                        event_id=deterministic_id(
                            "event",
                            [
                                segment.text.casefold(),
                                date_values,
                            ],
                        ),
                        event_text=segment.text,
                        date_values=date_values,
                        evidence_ids=[],
                        source_ids=[],
                        status="DATE_MENTION_IN_SOURCE",
                    )
                    events_by_identity[identity] = event

                if evidence_id not in event.evidence_ids:
                    event.evidence_ids.append(evidence_id)

                if source_id not in event.source_ids:
                    event.source_ids.append(source_id)

                provenance.append(
                    ProvenanceRecord(
                        provenance_id=deterministic_id(
                            "provenance",
                            [
                                event.event_id,
                                evidence_id,
                                source_id,
                                "MENTIONED_IN",
                            ],
                        ),
                        subject_id=event.event_id,
                        subject_type="EVENT",
                        evidence_id=evidence_id,
                        source_id=source_id,
                        relation="MENTIONED_IN",
                    )
                )

    claims = sorted(
        claims_by_fingerprint.values(),
        key=lambda item: item.claim_id,
    )
    entities = sorted(
        entities_by_identity.values(),
        key=lambda item: item.entity_id,
    )
    events = sorted(
        events_by_identity.values(),
        key=lambda item: item.event_id,
    )
    segments = sorted(
        segments,
        key=lambda item: (
            item.source_id,
            item.position,
            item.segment_id,
        ),
    )
    evidence = sorted(
        evidence,
        key=lambda item: (
            item.source_id,
            item.start_character,
            item.evidence_id,
        ),
    )
    provenance = sorted(
        {
            item.provenance_id: item
            for item in provenance
        }.values(),
        key=lambda item: item.provenance_id,
    )

    knowledge_root = Path(paths.working_root) / "knowledge"
    knowledge_root.mkdir(parents=True, exist_ok=True)

    extraction_id = deterministic_id(
        "knowledge_extraction",
        [
            project["project_id"],
            [item.segment_id for item in segments],
            [item.claim_id for item in claims],
            [item.entity_id for item in entities],
            [item.event_id for item in events],
        ],
    )

    common = {
        "schema_version": KNOWLEDGE_SCHEMA_VERSION,
        "project_id": project["project_id"],
        "extraction_id": extraction_id,
        "created_at": CANONICAL_TIMESTAMP,
    }

    segments_payload = {
        **common,
        "segments": [asdict(item) for item in segments],
    }
    evidence_payload = {
        **common,
        "evidence": [asdict(item) for item in evidence],
    }
    claims_payload = {
        **common,
        "claims": [asdict(item) for item in claims],
    }
    entities_payload = {
        **common,
        "entities": [asdict(item) for item in entities],
        "limitations": [
            {
                "code": "CONSERVATIVE_ENTITY_EXTRACTION",
                "detail": (
                    "Only explicit quoted terms, Latin title-case names, "
                    "and Arabic names preceded by explicit titles are extracted."
                ),
            }
        ],
    }
    events_payload = {
        **common,
        "events": [asdict(item) for item in events],
        "limitations": [
            {
                "code": "DATE_MENTION_NOT_VERIFIED_EVENT",
                "detail": (
                    "A dated sentence is recorded as an event candidate; "
                    "historical truth is not asserted."
                ),
            }
        ],
    }
    provenance_payload = {
        **common,
        "provenance": [asdict(item) for item in provenance],
    }

    result_payload = {
        **common,
        "status": "EXTRACTED",
        "segment_count": len(segments),
        "evidence_count": len(evidence),
        "claim_count": len(claims),
        "entity_count": len(entities),
        "event_count": len(events),
        "provenance_count": len(provenance),
        "limitations": [
            "No historical truth verification is performed.",
            "Claims mean statements present in source text.",
            "Entity extraction is deliberately conservative.",
            "Events represent explicit date mentions only.",
        ],
    }

    files = {
        "segments.json": segments_payload,
        "evidence.json": evidence_payload,
        "claims.json": claims_payload,
        "entities.json": entities_payload,
        "events.json": events_payload,
        "provenance.json": provenance_payload,
        "extraction-result.json": result_payload,
    }

    for filename, payload in files.items():
        _write_json(knowledge_root / filename, payload)

    with SQLitePersistenceAdapter(
        SQLiteConnectionConfig(paths.database)
    ) as adapter:
        adapter.initialize()
        transaction = adapter.save_many(
            [
                (
                    "KNOWLEDGE_SEGMENTS",
                    extraction_id,
                    segments_payload,
                ),
                (
                    "KNOWLEDGE_EVIDENCE",
                    extraction_id,
                    evidence_payload,
                ),
                (
                    "KNOWLEDGE_CLAIMS",
                    extraction_id,
                    claims_payload,
                ),
                (
                    "KNOWLEDGE_ENTITIES",
                    extraction_id,
                    entities_payload,
                ),
                (
                    "KNOWLEDGE_EVENTS",
                    extraction_id,
                    events_payload,
                ),
                (
                    "KNOWLEDGE_PROVENANCE",
                    extraction_id,
                    provenance_payload,
                ),
                (
                    "KNOWLEDGE_EXTRACTION_RESULT",
                    extraction_id,
                    result_payload,
                ),
            ]
        )

    if not transaction.committed:
        raise RuntimeError(
            transaction.error_code
            or "KNOWLEDGE_PERSISTENCE_FAILED"
        )

    return {
        **result_payload,
        "knowledge_root": str(knowledge_root),
        "persistence_record_ids": transaction.record_ids,
    }


def _knowledge_file(
    project_root: Path,
    filename: str,
) -> dict[str, Any]:
    paths = project_paths(project_root)
    path = Path(paths.working_root) / "knowledge" / filename
    payload = _read_json(path)

    if payload.get("schema_version") != KNOWLEDGE_SCHEMA_VERSION:
        raise ValueError("INVALID_KNOWLEDGE_SCHEMA")

    return payload


def list_evidence(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    payload = _knowledge_file(root, "evidence.json")

    return {
        "project_id": payload["project_id"],
        "extraction_id": payload["extraction_id"],
        "evidence_count": len(payload["evidence"]),
        "evidence": payload["evidence"],
    }


def list_claims(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    payload = _knowledge_file(root, "claims.json")

    return {
        "project_id": payload["project_id"],
        "extraction_id": payload["extraction_id"],
        "claim_count": len(payload["claims"]),
        "claims": payload["claims"],
    }


def knowledge_status(project_root: str) -> dict[str, Any]:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    paths = project_paths(root)
    result_path = (
        Path(paths.working_root)
        / "knowledge"
        / "extraction-result.json"
    )

    if not result_path.is_file():
        return {
            "project_id": project["project_id"],
            "status": "NOT_RUN",
            "result_path": str(result_path),
        }

    result = _read_json(result_path)

    return {
        "project_id": project["project_id"],
        "status": result.get("status", "INVALID"),
        "result_path": str(result_path),
        "extraction_id": result.get("extraction_id", ""),
        "segment_count": result.get("segment_count", 0),
        "evidence_count": result.get("evidence_count", 0),
        "claim_count": result.get("claim_count", 0),
        "entity_count": result.get("entity_count", 0),
        "event_count": result.get("event_count", 0),
        "provenance_count": result.get("provenance_count", 0),
    }


def verify_knowledge(
    project_root: str,
) -> KnowledgeVerificationReport:
    root = _absolute_path(project_root, "PROJECT_ROOT")
    project = load_project(root)
    issues: list[KnowledgeVerificationIssue] = []

    try:
        segments_payload = _knowledge_file(
            root,
            "segments.json",
        )
        evidence_payload = _knowledge_file(
            root,
            "evidence.json",
        )
        claims_payload = _knowledge_file(
            root,
            "claims.json",
        )
        entities_payload = _knowledge_file(
            root,
            "entities.json",
        )
        events_payload = _knowledge_file(
            root,
            "events.json",
        )
        provenance_payload = _knowledge_file(
            root,
            "provenance.json",
        )
    except (FileNotFoundError, ValueError) as error:
        return KnowledgeVerificationReport(
            project_id=project["project_id"],
            status="INVALID",
            segment_count=0,
            evidence_count=0,
            claim_count=0,
            entity_count=0,
            event_count=0,
            provenance_count=0,
            issues=[
                KnowledgeVerificationIssue(
                    "KNOWLEDGE_ARTIFACT_INVALID",
                    detail=str(error),
                )
            ],
        )

    extraction_ids = {
        payload.get("extraction_id")
        for payload in (
            segments_payload,
            evidence_payload,
            claims_payload,
            entities_payload,
            events_payload,
            provenance_payload,
        )
    }

    if len(extraction_ids) != 1:
        issues.append(
            KnowledgeVerificationIssue(
                "EXTRACTION_ID_MISMATCH",
            )
        )

    segments = segments_payload["segments"]
    evidence = evidence_payload["evidence"]
    claims = claims_payload["claims"]
    entities = entities_payload["entities"]
    events = events_payload["events"]
    provenance = provenance_payload["provenance"]

    segment_by_id = {
        item["segment_id"]: item
        for item in segments
    }
    evidence_by_id = {
        item["evidence_id"]: item
        for item in evidence
    }

    subject_ids = {
        item["claim_id"]
        for item in claims
    } | {
        item["entity_id"]
        for item in entities
    } | {
        item["event_id"]
        for item in events
    }

    for item in evidence:
        segment = segment_by_id.get(item["segment_id"])

        if segment is None:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVIDENCE_SEGMENT_NOT_FOUND",
                    item["evidence_id"],
                )
            )
            continue

        if item["source_id"] != segment["source_id"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVIDENCE_SOURCE_MISMATCH",
                    item["evidence_id"],
                )
            )

        if item["text"] != segment["text"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVIDENCE_TEXT_MISMATCH",
                    item["evidence_id"],
                )
            )

        if sha256(
            item["text"].encode("utf-8")
        ).hexdigest() != item["fingerprint"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVIDENCE_FINGERPRINT_MISMATCH",
                    item["evidence_id"],
                )
            )

        if item["start_character"] >= item["end_character"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "INVALID_EVIDENCE_RANGE",
                    item["evidence_id"],
                )
            )

    for claim in claims:
        if not claim["evidence_ids"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "CLAIM_WITHOUT_EVIDENCE",
                    claim["claim_id"],
                )
            )

        for evidence_id in claim["evidence_ids"]:
            if evidence_id not in evidence_by_id:
                issues.append(
                    KnowledgeVerificationIssue(
                        "CLAIM_EVIDENCE_NOT_FOUND",
                        claim["claim_id"],
                        evidence_id,
                    )
                )

    for entity in entities:
        if not entity["evidence_ids"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "ENTITY_WITHOUT_EVIDENCE",
                    entity["entity_id"],
                )
            )

    for event in events:
        if not event["evidence_ids"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVENT_WITHOUT_EVIDENCE",
                    event["event_id"],
                )
            )

        if not event["date_values"]:
            issues.append(
                KnowledgeVerificationIssue(
                    "EVENT_WITHOUT_DATE",
                    event["event_id"],
                )
            )

    provenance_ids: set[str] = set()

    for record in provenance:
        provenance_id = record["provenance_id"]

        if provenance_id in provenance_ids:
            issues.append(
                KnowledgeVerificationIssue(
                    "DUPLICATE_PROVENANCE_ID",
                    provenance_id,
                )
            )

        provenance_ids.add(provenance_id)

        if record["subject_id"] not in subject_ids:
            issues.append(
                KnowledgeVerificationIssue(
                    "PROVENANCE_SUBJECT_NOT_FOUND",
                    provenance_id,
                )
            )

        if record["evidence_id"] not in evidence_by_id:
            issues.append(
                KnowledgeVerificationIssue(
                    "PROVENANCE_EVIDENCE_NOT_FOUND",
                    provenance_id,
                )
            )
        elif (
            evidence_by_id[record["evidence_id"]]["source_id"]
            != record["source_id"]
        ):
            issues.append(
                KnowledgeVerificationIssue(
                    "PROVENANCE_SOURCE_MISMATCH",
                    provenance_id,
                )
            )

    return KnowledgeVerificationReport(
        project_id=project["project_id"],
        status="VALID" if not issues else "INVALID",
        segment_count=len(segments),
        evidence_count=len(evidence),
        claim_count=len(claims),
        entity_count=len(entities),
        event_count=len(events),
        provenance_count=len(provenance),
        issues=issues,
    )


__all__ = [
    "KNOWLEDGE_SCHEMA_VERSION",
    "ClaimRecord",
    "EntityRecord",
    "EventRecord",
    "EvidenceRecord",
    "KnowledgeVerificationIssue",
    "KnowledgeVerificationReport",
    "ProvenanceRecord",
    "TextSegment",
    "extract_project_knowledge",
    "knowledge_status",
    "list_claims",
    "list_evidence",
    "verify_knowledge",
]
