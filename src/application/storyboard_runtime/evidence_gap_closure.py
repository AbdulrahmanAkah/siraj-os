"""Build a human-review docket for uncovered Adam evidence events.

This module is deterministic and offline. It does not research, grade, approve,
or bind evidence. It converts explicit gaps from the recovered evidence metadata
into a review docket and a non-executable decision template.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence


EVIDENCE_GAP_DOCKET_SCHEMA_VERSION = "siraj-evidence-gap-closure-docket-v1"
EVIDENCE_GAP_REVIEW_TEMPLATE_SCHEMA_VERSION = (
    "siraj-evidence-gap-review-template-v1"
)
DOCKET_STATUS = "HUMAN_REVIEW_PENDING"
TEMPLATE_STATUS = "TEMPLATE_NOT_APPROVED"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
LIVE_EXECUTION_STATUS = "BLOCKED"
RECOVERED_SCHEMA_VERSION = "siraj-recovered-evidence-knowledge-v1"
RECOVERED_STATUS = "RECOVERED_REVIEW_PENDING"

INCLUDE_ASSERTIVE = "include_assertive"
INCLUDE_QUALIFIED = "include_qualified"
OMIT_UNVERIFIED = "omit_unverified"
EDITORIAL_ONLY = "editorial_only"

_FACTUAL_ALLOWED_DISPOSITIONS = (
    INCLUDE_ASSERTIVE,
    INCLUDE_QUALIFIED,
    OMIT_UNVERIFIED,
)
_EDITORIAL_ALLOWED_DISPOSITIONS = (EDITORIAL_ONLY,)

_SECRET_FRAGMENTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credential",
)
_RAW_TEXT_FRAGMENTS = (
    "quoted_text",
    "excerpt",
    "raw_text",
    "page_text",
    "content_text",
    "full_text",
)


class EvidenceGapClosureError(ValueError):
    """Raised when recovered evidence gaps cannot form a safe review docket."""


def _canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _deterministic_id(namespace: str, payload: object) -> str:
    digest = hashlib.sha256(
        namespace.encode("utf-8") + b"\0" + _canonical_json_bytes(payload)
    ).hexdigest()[:16]
    return f"{namespace}_{digest}"


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvidenceGapClosureError(f"{key} must be a nonblank string.")
    return value.strip()


def _string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise EvidenceGapClosureError(f"{label} must be a list of nonblank strings.")
    result = [item.strip() for item in value]
    if len(set(result)) != len(result):
        raise EvidenceGapClosureError(f"{label} must not contain duplicates.")
    return result


def _object_list(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise EvidenceGapClosureError(f"{label} must be a list of objects.")
    return list(value)


def _safe_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise EvidenceGapClosureError("Artifact paths must stay repository-relative.")
    if len(normalized) >= 2 and normalized[1] == ":":
        raise EvidenceGapClosureError("Windows absolute paths are forbidden.")
    return path.as_posix()


def _assert_safe_keys(payload: object, *, path: str = "root") -> None:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in _SECRET_FRAGMENTS):
                raise EvidenceGapClosureError(
                    f"Secret-like field is forbidden in docket material: {path}.{key}"
                )
            if any(fragment in normalized for fragment in _RAW_TEXT_FRAGMENTS):
                raise EvidenceGapClosureError(
                    f"Raw evidence text field is forbidden: {path}.{key}"
                )
            _assert_safe_keys(value, path=f"{path}.{key}")
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            _assert_safe_keys(value, path=f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class EvidenceGapEntry:
    event_id: str
    order: int
    title: str
    section: str
    verification_status: str
    chronology_type: str
    importance: str
    question_ids: tuple[str, ...]
    research_questions: tuple[str, ...]
    resolution_lane: str
    allowed_dispositions: tuple[str, ...]
    recommended_disposition: str | None
    recommendation_status: str
    explicit_candidate_source_ids: tuple[str, ...]
    explicit_review_artifact_paths: tuple[str, ...]
    human_decision_required: bool = True

    def to_manifest(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "order": self.order,
            "title": self.title,
            "section": self.section,
            "verification_status": self.verification_status,
            "chronology_type": self.chronology_type,
            "importance": self.importance,
            "question_ids": list(self.question_ids),
            "research_questions": list(self.research_questions),
            "resolution_lane": self.resolution_lane,
            "allowed_dispositions": list(self.allowed_dispositions),
            "recommended_disposition": self.recommended_disposition,
            "recommendation_status": self.recommendation_status,
            "explicit_candidate_source_ids": list(
                self.explicit_candidate_source_ids
            ),
            "explicit_review_artifact_paths": list(
                self.explicit_review_artifact_paths
            ),
            "human_decision_required": self.human_decision_required,
        }


@dataclass(frozen=True, slots=True)
class EvidenceGapClosureDocket:
    docket_id: str
    episode_id: str
    recovery_id: str
    recovery_manifest_sha256: str
    entries: tuple[EvidenceGapEntry, ...]
    normalized_source_ids: tuple[str, ...]
    schema_version: str = EVIDENCE_GAP_DOCKET_SCHEMA_VERSION
    status: str = DOCKET_STATUS
    evidence_gate_status: str = EVIDENCE_GATE_STATUS
    automatic_evidence_approval: str = AUTOMATIC_APPROVAL_STATUS
    live_provider_execution: str = LIVE_EXECUTION_STATUS

    def to_manifest(self) -> dict[str, object]:
        factual = sum(item.resolution_lane == "targeted_human_review" for item in self.entries)
        editorial = sum(item.resolution_lane == "editorial_only" for item in self.entries)
        return {
            "schema_version": self.schema_version,
            "docket_id": self.docket_id,
            "episode_id": self.episode_id,
            "recovery_id": self.recovery_id,
            "recovery_manifest_sha256": self.recovery_manifest_sha256,
            "status": self.status,
            "evidence_gate_status": self.evidence_gate_status,
            "automatic_evidence_approval": self.automatic_evidence_approval,
            "live_provider_execution": self.live_provider_execution,
            "raw_source_text_copied": False,
            "counts": {
                "total_uncovered_events": len(self.entries),
                "factual_review_events": factual,
                "editorial_only_events": editorial,
                "events_with_explicit_candidate_sources": sum(
                    bool(item.explicit_candidate_source_ids) for item in self.entries
                ),
                "events_with_explicit_review_artifacts": sum(
                    bool(item.explicit_review_artifact_paths) for item in self.entries
                ),
            },
            "normalized_source_ids": list(self.normalized_source_ids),
            "entries": [item.to_manifest() for item in self.entries],
        }

    def to_json(self, *, pretty: bool = True) -> str:
        payload = self.to_manifest()
        _assert_safe_keys(payload)
        if pretty:
            return json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + "\n"
        return json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class AdamEvidenceGapClosureBuilder:
    """Build a non-approving review docket from tracked Adam metadata."""

    REQUIRED_PATHS = {
        "recovery": "evidence/recovered-evidence-knowledge-v1.json",
        "events": "editorial/event-map.json",
        "questions": "editorial/research-questions.json",
        "source_package": "contracts/source-package-v1.draft.json",
    }

    def build_from_project(self, episode_root: Path) -> EvidenceGapClosureDocket:
        episode_root = Path(episode_root)
        payloads: dict[str, object] = {}
        for key, relative in self.REQUIRED_PATHS.items():
            path = episode_root / relative
            if not path.is_file():
                raise EvidenceGapClosureError(f"Missing gap-docket input: {path}")
            try:
                payloads[key] = json.loads(path.read_text(encoding="utf-8-sig"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise EvidenceGapClosureError(
                    f"Invalid JSON gap-docket input: {path}"
                ) from error
        return self.build_from_data(
            recovery=_as_object(payloads["recovery"], "recovery"),
            event_map=_object_list(payloads["events"], "event_map"),
            research_questions=_object_list(payloads["questions"], "research_questions"),
            source_package=_as_object(payloads["source_package"], "source_package"),
        )

    def build_from_data(
        self,
        *,
        recovery: Mapping[str, object],
        event_map: Sequence[Mapping[str, object]],
        research_questions: Sequence[Mapping[str, object]],
        source_package: Mapping[str, object],
    ) -> EvidenceGapClosureDocket:
        _assert_safe_keys(recovery)
        self._validate_recovery(recovery)
        self._validate_source_package(source_package)

        episode_id = _required_text(recovery, "episode_id")
        uncovered = _string_list(recovery.get("uncovered_event_ids"), "uncovered_event_ids")
        if not uncovered:
            raise EvidenceGapClosureError("The recovered manifest contains no gaps.")

        events = {
            _required_text(item, "event_id"): item for item in event_map
        }
        if len(events) != len(event_map):
            raise EvidenceGapClosureError("Event map ids must be unique.")
        unknown = sorted(set(uncovered).difference(events))
        if unknown:
            raise EvidenceGapClosureError(
                f"Recovered gaps reference unknown events: {unknown}"
            )

        questions = {
            _required_text(item, "question_id"): item
            for item in research_questions
        }
        if len(questions) != len(research_questions):
            raise EvidenceGapClosureError("Research question ids must be unique.")

        candidate_links = _as_object(
            recovery.get("candidate_event_links"), "candidate_event_links"
        )
        reverse_candidates: dict[str, list[str]] = {event_id: [] for event_id in uncovered}
        for source_id, raw_event_ids in candidate_links.items():
            if not isinstance(source_id, str) or not source_id.strip():
                raise EvidenceGapClosureError("Candidate source ids must be nonblank.")
            linked_events = _string_list(raw_event_ids, f"candidate_event_links.{source_id}")
            for event_id in linked_events:
                if event_id in reverse_candidates:
                    reverse_candidates[event_id].append(source_id)

        review_paths: dict[str, list[str]] = {event_id: [] for event_id in uncovered}
        raw_artifacts = recovery.get("review_artifacts")
        if raw_artifacts is not None:
            for item in _object_list(raw_artifacts, "review_artifacts"):
                artifact = _as_object(item.get("artifact"), "review_artifact.artifact")
                path = _safe_relative_path(_required_text(artifact, "relative_path"))
                artifact_events = _string_list(
                    artifact.get("event_ids", []), "review_artifact.event_ids"
                )
                for event_id in artifact_events:
                    if event_id in review_paths:
                        review_paths[event_id].append(path)

        entries: list[EvidenceGapEntry] = []
        for event_id in uncovered:
            event = events[event_id]
            question_ids = tuple(
                _string_list(event.get("question_ids", []), f"{event_id}.question_ids")
            )
            missing_questions = [item for item in question_ids if item not in questions]
            if missing_questions:
                raise EvidenceGapClosureError(
                    f"{event_id} references unknown research questions: {missing_questions}"
                )
            question_texts = tuple(
                _required_text(questions[item], "question") for item in question_ids
            )
            verification_status = _required_text(event, "verification_status")
            editorial = verification_status == "editorial"
            entries.append(
                EvidenceGapEntry(
                    event_id=event_id,
                    order=_required_int(event, "order"),
                    title=_required_text(event, "title"),
                    section=_required_text(event, "section"),
                    verification_status=verification_status,
                    chronology_type=_required_text(event, "chronology_type"),
                    importance=_required_text(event, "importance"),
                    question_ids=question_ids,
                    research_questions=question_texts,
                    resolution_lane=(
                        "editorial_only" if editorial else "targeted_human_review"
                    ),
                    allowed_dispositions=(
                        _EDITORIAL_ALLOWED_DISPOSITIONS
                        if editorial
                        else _FACTUAL_ALLOWED_DISPOSITIONS
                    ),
                    recommended_disposition=(EDITORIAL_ONLY if editorial else None),
                    recommendation_status=(
                        "RECOMMENDATION_ONLY" if editorial else "NO_DEFAULT_DECISION"
                    ),
                    explicit_candidate_source_ids=tuple(
                        sorted(set(reverse_candidates[event_id]))
                    ),
                    explicit_review_artifact_paths=tuple(
                        sorted(set(review_paths[event_id]))
                    ),
                )
            )

        entries.sort(key=lambda item: (item.order, item.event_id))
        if [item.event_id for item in entries] != uncovered:
            raise EvidenceGapClosureError(
                "Recovered uncovered_event_ids must preserve event-map order."
            )

        normalized_sources = _object_list(
            recovery.get("normalized_sources", []), "normalized_sources"
        )
        normalized_source_ids = tuple(
            sorted(_required_text(item, "source_id") for item in normalized_sources)
        )
        if len(set(normalized_source_ids)) != len(normalized_source_ids):
            raise EvidenceGapClosureError("Normalized source ids must be unique.")

        recovery_id = _required_text(recovery, "recovery_id")
        recovery_sha = canonical_json_sha256(recovery)
        docket_id = _deterministic_id(
            "evidence_gap_closure_docket",
            {
                "episode_id": episode_id,
                "recovery_id": recovery_id,
                "recovery_sha256": recovery_sha,
                "entries": [item.to_manifest() for item in entries],
                "normalized_source_ids": normalized_source_ids,
            },
        )
        docket = EvidenceGapClosureDocket(
            docket_id=docket_id,
            episode_id=episode_id,
            recovery_id=recovery_id,
            recovery_manifest_sha256=recovery_sha,
            entries=tuple(entries),
            normalized_source_ids=normalized_source_ids,
        )
        validate_gap_docket(docket.to_manifest())
        return docket

    @staticmethod
    def _validate_recovery(recovery: Mapping[str, object]) -> None:
        if recovery.get("schema_version") != RECOVERED_SCHEMA_VERSION:
            raise EvidenceGapClosureError("Unexpected recovered evidence schema.")
        if recovery.get("recovery_status") != RECOVERED_STATUS:
            raise EvidenceGapClosureError("Recovered evidence status is not review pending.")
        if recovery.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
            raise EvidenceGapClosureError("Recovered evidence gate must remain withheld.")
        if recovery.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
            raise EvidenceGapClosureError("Automatic evidence approval must be forbidden.")
        if recovery.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
            raise EvidenceGapClosureError("Live provider execution must remain blocked.")
        if recovery.get("unknown_event_ids") not in ([], None):
            raise EvidenceGapClosureError("Unknown event ids must be resolved first.")
        if recovery.get("unknown_source_ids") not in ([], None):
            raise EvidenceGapClosureError("Unknown source ids must be resolved first.")

    @staticmethod
    def _validate_source_package(source_package: Mapping[str, object]) -> None:
        if source_package.get("schema_version") != "siraj-episode-source-package-v1":
            raise EvidenceGapClosureError("Unexpected source package schema.")
        if source_package.get("package_status") == "APPROVED":
            raise EvidenceGapClosureError(
                "Gap docket is for pre-approval review, not approved evidence."
            )


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceGapClosureError(f"{key} must be an integer.")
    return value


def _as_object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EvidenceGapClosureError(f"{label} must be an object.")
    return value


def gap_review_template(docket: EvidenceGapClosureDocket) -> dict[str, object]:
    payload = {
        "schema_version": EVIDENCE_GAP_REVIEW_TEMPLATE_SCHEMA_VERSION,
        "status": TEMPLATE_STATUS,
        "episode_id": docket.episode_id,
        "docket_id": docket.docket_id,
        "human_approval": False,
        "reviewer": "",
        "reviewed_at": "",
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "decisions": [
            {
                "event_id": item.event_id,
                "allowed_dispositions": list(item.allowed_dispositions),
                "recommended_disposition": item.recommended_disposition,
                "disposition": "",
                "evidence_ids": [],
                "qualification_label": "",
                "rationale": "",
                "human_decision": False,
            }
            for item in docket.entries
        ],
    }
    validate_gap_review_template(payload, docket)
    return payload


def validate_gap_review_template(
    payload: Mapping[str, object],
    docket: EvidenceGapClosureDocket | None = None,
) -> None:
    _assert_safe_keys(payload)
    if payload.get("schema_version") != EVIDENCE_GAP_REVIEW_TEMPLATE_SCHEMA_VERSION:
        raise EvidenceGapClosureError("Unexpected gap review template schema.")
    if payload.get("status") != TEMPLATE_STATUS:
        raise EvidenceGapClosureError("Gap review template must remain non-approved.")
    if payload.get("human_approval") is not False:
        raise EvidenceGapClosureError("Gap review template cannot contain approval.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise EvidenceGapClosureError("Gap review template cannot open evidence gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise EvidenceGapClosureError("Automatic evidence approval must be forbidden.")
    decisions = _object_list(payload.get("decisions"), "decisions")
    if docket is not None:
        expected_ids = [item.event_id for item in docket.entries]
        actual_ids = [_required_text(item, "event_id") for item in decisions]
        if actual_ids != expected_ids:
            raise EvidenceGapClosureError("Template decisions must match docket order.")
    for item in decisions:
        if item.get("disposition") != "":
            raise EvidenceGapClosureError("Template disposition must be blank.")
        if item.get("evidence_ids") != []:
            raise EvidenceGapClosureError("Template evidence ids must be empty.")
        if item.get("human_decision") is not False:
            raise EvidenceGapClosureError("Template human decision must be false.")


def validate_gap_docket(payload: Mapping[str, object]) -> None:
    _assert_safe_keys(payload)
    if payload.get("schema_version") != EVIDENCE_GAP_DOCKET_SCHEMA_VERSION:
        raise EvidenceGapClosureError("Unexpected evidence gap docket schema.")
    if payload.get("status") != DOCKET_STATUS:
        raise EvidenceGapClosureError("Evidence gap docket must await human review.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise EvidenceGapClosureError("Evidence gap docket cannot open the gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise EvidenceGapClosureError("Automatic evidence approval must be forbidden.")
    if payload.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
        raise EvidenceGapClosureError("Live provider execution must remain blocked.")
    if payload.get("raw_source_text_copied") is not False:
        raise EvidenceGapClosureError("Gap docket must not copy raw source text.")
    entries = _object_list(payload.get("entries"), "entries")
    if not entries:
        raise EvidenceGapClosureError("Evidence gap docket must contain entries.")
    event_ids = [_required_text(item, "event_id") for item in entries]
    if len(set(event_ids)) != len(event_ids):
        raise EvidenceGapClosureError("Gap docket event ids must be unique.")
    for item in entries:
        lane = _required_text(item, "resolution_lane")
        allowed = tuple(_string_list(item.get("allowed_dispositions"), "allowed_dispositions"))
        recommendation = item.get("recommended_disposition")
        if item.get("human_decision_required") is not True:
            raise EvidenceGapClosureError("Every gap needs an explicit human decision.")
        if lane == "editorial_only":
            if allowed != _EDITORIAL_ALLOWED_DISPOSITIONS:
                raise EvidenceGapClosureError("Editorial gaps allow only editorial_only.")
            if recommendation != EDITORIAL_ONLY:
                raise EvidenceGapClosureError("Editorial gaps require a recommendation only.")
            if item.get("recommendation_status") != "RECOMMENDATION_ONLY":
                raise EvidenceGapClosureError("Editorial recommendation must stay nonbinding.")
        elif lane == "targeted_human_review":
            if allowed != _FACTUAL_ALLOWED_DISPOSITIONS:
                raise EvidenceGapClosureError("Factual gaps expose the approved review choices.")
            if recommendation is not None:
                raise EvidenceGapClosureError("Factual gaps cannot receive a default decision.")
            if item.get("recommendation_status") != "NO_DEFAULT_DECISION":
                raise EvidenceGapClosureError("Factual gaps must remain undecided.")
        else:
            raise EvidenceGapClosureError("Unknown gap resolution lane.")
        for path in _string_list(
            item.get("explicit_review_artifact_paths", []),
            "explicit_review_artifact_paths",
        ):
            _safe_relative_path(path)


def write_gap_docket(path: Path, docket: EvidenceGapClosureDocket) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(docket.to_json(pretty=True), encoding="utf-8", newline="\n")


def write_gap_review_template(path: Path, docket: EvidenceGapClosureDocket) -> None:
    payload = gap_review_template(docket)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
