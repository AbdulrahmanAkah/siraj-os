"""Strict human-approved evidence adjudication and storyboard binding.

This module never researches, grades, approves, or downloads evidence.  It only
validates explicit human-approved records and binds them to an already generated
editorial cinematic blueprint.  All provider execution remains blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
from pathlib import Path
import re
from typing import Iterable, Mapping

from src.application.documentary_intelligence import deterministic_id

from .cinematic_compiler import (
    CinematicBudgetGuardrails,
    CinematicCompilationPolicy,
    CinematicSeriesCompiler,
    CompiledCinematicEpisode,
)
from .cinematic_series import (
    RUNWARE_EXECUTION_STATUS,
    CinematicSeriesError,
    EpisodeSeriesContract,
)
from .models import Storyboard, StoryboardFrame


APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION = "siraj-approved-evidence-package-v1"
EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION = (
    "siraj-event-evidence-adjudication-v1"
)
EVIDENCE_BOUND_BLUEPRINT_SCHEMA_VERSION = (
    "siraj-evidence-bound-cinematic-blueprint-v1"
)
EVIDENCE_GATE_WITHHELD = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
EVIDENCE_GATE_OPEN = "OPEN_APPROVED_EVIDENCE_PACKAGE_BOUND"
HUMAN_APPROVAL_STATUS = "APPROVED"
LIVE_EXECUTION_STATUS = "BLOCKED"
TEMPLATE_STATUS = "TEMPLATE_NOT_APPROVED"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ClaimClassification(StrEnum):
    QURAN_EXPLICIT = "quran_explicit"
    AUTHENTIC_SUNNAH = "authentic_sunnah"
    ACCEPTED_ATHAR = "accepted_athar"
    SCHOLARLY_INTERPRETATION = "scholarly_interpretation"
    DISPUTED_VIEW = "disputed_view"
    HISTORICAL_REPORT = "historical_report"
    ISRAILIYYAT = "israiliyyat"
    WEAK_REPORT = "weak_report"


class EventDisposition(StrEnum):
    INCLUDE_ASSERTIVE = "include_assertive"
    INCLUDE_QUALIFIED = "include_qualified"
    OMIT_UNVERIFIED = "omit_unverified"
    EDITORIAL_ONLY = "editorial_only"


_ASSERTIVE_CLASSES = frozenset(
    {
        ClaimClassification.QURAN_EXPLICIT,
        ClaimClassification.AUTHENTIC_SUNNAH,
        ClaimClassification.ACCEPTED_ATHAR,
    }
)


@dataclass(frozen=True, slots=True)
class HumanApprovalRecord:
    approval_id: str
    approved_by: str
    approved_at: str
    approval_status: str
    human_approval: bool
    notes: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "HumanApprovalRecord":
        record = cls(
            approval_id=_required_text(payload, "approval_id"),
            approved_by=_required_text(payload, "approved_by"),
            approved_at=_required_text(payload, "approved_at"),
            approval_status=_required_text(payload, "approval_status"),
            human_approval=_required_bool(payload, "human_approval"),
            notes=_optional_text(payload.get("notes")) or "",
        )
        record.validate()
        return record

    def validate(self) -> None:
        if self.approval_status != HUMAN_APPROVAL_STATUS:
            raise CinematicSeriesError("Evidence approval status must be APPROVED.")
        if not self.human_approval:
            raise CinematicSeriesError("Evidence approval must be explicitly human.")
        normalized = self.approved_by.strip().lower()
        if normalized in {"system", "automatic", "automation", "ai", "model"}:
            raise CinematicSeriesError(
                "An automated identity cannot approve historical evidence."
            )
        if "t" not in self.approved_at.lower() or not self.approved_at.endswith("Z"):
            raise CinematicSeriesError(
                "approved_at must be an explicit UTC timestamp ending in Z."
            )

    def to_manifest(self) -> dict[str, object]:
        return {
            "approval_id": self.approval_id,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "approval_status": self.approval_status,
            "human_approval": self.human_approval,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class ApprovedEvidenceItem:
    evidence_id: str
    event_id: str
    source_id: str
    claim_classification: ClaimClassification
    claim_summary: str
    locator: str
    source_checksum_sha256: str
    excerpt_sha256: str
    quotation_allowed: bool
    visual_reconstruction_allowed: bool
    usage_restrictions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ApprovedEvidenceItem":
        try:
            classification = ClaimClassification(
                _required_text(payload, "claim_classification")
            )
        except ValueError as error:
            raise CinematicSeriesError(
                "Unknown evidence claim classification."
            ) from error
        item = cls(
            evidence_id=_required_text(payload, "evidence_id"),
            event_id=_required_text(payload, "event_id"),
            source_id=_required_text(payload, "source_id"),
            claim_classification=classification,
            claim_summary=_required_text(payload, "claim_summary"),
            locator=_required_text(payload, "locator"),
            source_checksum_sha256=_required_text(
                payload, "source_checksum_sha256"
            ).lower(),
            excerpt_sha256=_required_text(payload, "excerpt_sha256").lower(),
            quotation_allowed=_required_bool(payload, "quotation_allowed"),
            visual_reconstruction_allowed=_required_bool(
                payload, "visual_reconstruction_allowed"
            ),
            usage_restrictions=_string_tuple(
                payload.get("usage_restrictions", []), "usage_restrictions"
            ),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if not _SHA256_RE.fullmatch(self.source_checksum_sha256):
            raise CinematicSeriesError(
                "Evidence source checksum must be a lowercase SHA-256 digest."
            )
        if not _SHA256_RE.fullmatch(self.excerpt_sha256):
            raise CinematicSeriesError(
                "Evidence excerpt checksum must be a lowercase SHA-256 digest."
            )
        if len(set(self.usage_restrictions)) != len(self.usage_restrictions):
            raise CinematicSeriesError("Evidence usage restrictions must be unique.")

    def to_manifest(self) -> dict[str, object]:
        return {
            "evidence_id": self.evidence_id,
            "event_id": self.event_id,
            "source_id": self.source_id,
            "claim_classification": self.claim_classification.value,
            "claim_summary": self.claim_summary,
            "locator": self.locator,
            "source_checksum_sha256": self.source_checksum_sha256,
            "excerpt_sha256": self.excerpt_sha256,
            "quotation_allowed": self.quotation_allowed,
            "visual_reconstruction_allowed": self.visual_reconstruction_allowed,
            "usage_restrictions": list(self.usage_restrictions),
        }


@dataclass(frozen=True, slots=True)
class ApprovedEvidencePackage:
    package_id: str
    episode_id: str
    source_package_fingerprint: str
    approval: HumanApprovalRecord
    evidence_items: tuple[ApprovedEvidenceItem, ...]
    schema_version: str = APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "ApprovedEvidencePackage":
        if payload.get("schema_version") != APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected approved evidence package schema.")
        approval_payload = _object(payload.get("approval"), "approval")
        raw_items = payload.get("evidence_items")
        if not isinstance(raw_items, list):
            raise CinematicSeriesError("evidence_items must be a list.")
        package = cls(
            package_id=_required_text(payload, "package_id"),
            episode_id=_required_text(payload, "episode_id"),
            source_package_fingerprint=_required_text(
                payload, "source_package_fingerprint"
            ),
            approval=HumanApprovalRecord.from_mapping(approval_payload),
            evidence_items=tuple(
                ApprovedEvidenceItem.from_mapping(
                    _object(item, f"evidence_items[{index}]")
                )
                for index, item in enumerate(raw_items)
            ),
        )
        package.validate()
        return package

    def validate(self) -> None:
        if self.schema_version != APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected approved evidence package schema.")
        self.approval.validate()
        if not self.evidence_items:
            raise CinematicSeriesError(
                "An approved evidence package must contain evidence items."
            )
        ids = [item.evidence_id for item in self.evidence_items]
        if len(set(ids)) != len(ids):
            raise CinematicSeriesError("Evidence ids must be unique.")
        for item in self.evidence_items:
            item.validate()

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_id": self.package_id,
            "episode_id": self.episode_id,
            "source_package_fingerprint": self.source_package_fingerprint,
            "approval": self.approval.to_manifest(),
            "evidence_items": [item.to_manifest() for item in self.evidence_items],
        }


@dataclass(frozen=True, slots=True)
class EventEvidenceDecision:
    event_id: str
    disposition: EventDisposition
    evidence_ids: tuple[str, ...]
    qualification_label: str | None
    rationale: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "EventEvidenceDecision":
        try:
            disposition = EventDisposition(_required_text(payload, "disposition"))
        except ValueError as error:
            raise CinematicSeriesError("Unknown event evidence disposition.") from error
        decision = cls(
            event_id=_required_text(payload, "event_id"),
            disposition=disposition,
            evidence_ids=_string_tuple(payload.get("evidence_ids", []), "evidence_ids"),
            qualification_label=_optional_text(payload.get("qualification_label")),
            rationale=_required_text(payload, "rationale"),
        )
        decision.validate()
        return decision

    def validate(self) -> None:
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise CinematicSeriesError("Decision evidence ids must be unique.")
        if self.disposition in {
            EventDisposition.INCLUDE_ASSERTIVE,
            EventDisposition.INCLUDE_QUALIFIED,
        } and not self.evidence_ids:
            raise CinematicSeriesError(
                "Included events require at least one approved evidence id."
            )
        if self.disposition in {
            EventDisposition.OMIT_UNVERIFIED,
            EventDisposition.EDITORIAL_ONLY,
        } and self.evidence_ids:
            raise CinematicSeriesError(
                "Omitted or editorial-only events cannot reference evidence ids."
            )
        if (
            self.disposition is EventDisposition.INCLUDE_QUALIFIED
            and not self.qualification_label
        ):
            raise CinematicSeriesError(
                "Qualified inclusion requires an explicit audience-facing label."
            )
        if (
            self.disposition is not EventDisposition.INCLUDE_QUALIFIED
            and self.qualification_label is not None
        ):
            raise CinematicSeriesError(
                "Only qualified inclusion may carry a qualification label."
            )

    def to_manifest(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "disposition": self.disposition.value,
            "evidence_ids": list(self.evidence_ids),
            "qualification_label": self.qualification_label,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class ApprovedEventEvidenceAdjudication:
    adjudication_id: str
    episode_id: str
    evidence_package_id: str
    approval: HumanApprovalRecord
    decisions: tuple[EventEvidenceDecision, ...]
    schema_version: str = EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object]
    ) -> "ApprovedEventEvidenceAdjudication":
        if payload.get("schema_version") != EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION:
            raise CinematicSeriesError("Unexpected event adjudication schema.")
        raw_decisions = payload.get("decisions")
        if not isinstance(raw_decisions, list):
            raise CinematicSeriesError("Adjudication decisions must be a list.")
        adjudication = cls(
            adjudication_id=_required_text(payload, "adjudication_id"),
            episode_id=_required_text(payload, "episode_id"),
            evidence_package_id=_required_text(payload, "evidence_package_id"),
            approval=HumanApprovalRecord.from_mapping(
                _object(payload.get("approval"), "approval")
            ),
            decisions=tuple(
                EventEvidenceDecision.from_mapping(
                    _object(item, f"decisions[{index}]")
                )
                for index, item in enumerate(raw_decisions)
            ),
        )
        adjudication.validate()
        return adjudication

    def validate(self) -> None:
        self.approval.validate()
        if not self.decisions:
            raise CinematicSeriesError(
                "Approved adjudication must contain event decisions."
            )
        event_ids = [item.event_id for item in self.decisions]
        if len(set(event_ids)) != len(event_ids):
            raise CinematicSeriesError("Adjudication event ids must be unique.")
        for decision in self.decisions:
            decision.validate()

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "adjudication_id": self.adjudication_id,
            "episode_id": self.episode_id,
            "evidence_package_id": self.evidence_package_id,
            "approval": self.approval.to_manifest(),
            "decisions": [item.to_manifest() for item in self.decisions],
        }


@dataclass(frozen=True, slots=True)
class EvidenceBoundCinematicBlueprint:
    binding_id: str
    original_bridge_id: str
    evidence_package_id: str
    adjudication_id: str
    evidence_package_fingerprint: str
    adjudication_fingerprint: str
    storyboard: Storyboard
    compiled_episode: CompiledCinematicEpisode
    approval_records: tuple[HumanApprovalRecord, HumanApprovalRecord]
    included_event_ids: tuple[str, ...]
    qualified_event_ids: tuple[str, ...]
    omitted_event_ids: tuple[str, ...]
    editorial_event_ids: tuple[str, ...]
    schema_version: str = EVIDENCE_BOUND_BLUEPRINT_SCHEMA_VERSION
    evidence_gate_status: str = EVIDENCE_GATE_OPEN
    live_execution_status: str = LIVE_EXECUTION_STATUS

    def to_manifest(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "binding_id": self.binding_id,
            "original_bridge_id": self.original_bridge_id,
            "episode_id": self.compiled_episode.plan.contract.episode_id,
            "evidence_package_id": self.evidence_package_id,
            "adjudication_id": self.adjudication_id,
            "evidence_package_fingerprint": self.evidence_package_fingerprint,
            "adjudication_fingerprint": self.adjudication_fingerprint,
            "evidence_gate_status": self.evidence_gate_status,
            "live_execution_status": self.live_execution_status,
            "runware_execution_status": (
                self.compiled_episode.plan.runware_execution_status
            ),
            "approval_records": [item.to_manifest() for item in self.approval_records],
            "event_resolution": {
                "included_event_ids": list(self.included_event_ids),
                "qualified_event_ids": list(self.qualified_event_ids),
                "omitted_event_ids": list(self.omitted_event_ids),
                "editorial_event_ids": list(self.editorial_event_ids),
            },
            "storyboard": _storyboard_manifest(self.storyboard),
            "cinematic_compilation": self.compiled_episode.to_manifest(),
        }

    def to_json(self, *, pretty: bool = False) -> str:
        if pretty:
            return json.dumps(
                self.to_manifest(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + "\n"
        return json.dumps(
            self.to_manifest(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


class ApprovedEvidenceBinder:
    """Open the evidence gate only from complete human-approved records."""

    def __init__(self, compiler: CinematicSeriesCompiler | None = None) -> None:
        self._compiler = compiler or CinematicSeriesCompiler()

    def bind_from_project(
        self,
        *,
        episode_root: Path,
        editorial_blueprint_path: Path,
        approved_source_package_path: Path,
        approved_evidence_package_path: Path,
        approved_adjudication_path: Path,
    ) -> EvidenceBoundCinematicBlueprint:
        episode_root = Path(episode_root)
        files = {
            "episode_definition": episode_root / "contracts/episode-definition-v1.json",
            "event_map": episode_root / "editorial/event-map.json",
            "editorial_blueprint": Path(editorial_blueprint_path),
            "source_package": Path(approved_source_package_path),
            "evidence_package": Path(approved_evidence_package_path),
            "adjudication": Path(approved_adjudication_path),
        }
        payloads: dict[str, bytes] = {}
        for key, path in files.items():
            if not path.is_file():
                raise CinematicSeriesError(f"Missing evidence binding input: {path}")
            payloads[key] = path.read_bytes()
        parsed = {key: _load_json_bytes(value, key) for key, value in payloads.items()}
        return self.bind_from_data(
            episode_definition=_object(parsed["episode_definition"], "episode_definition"),
            event_map=_object_list(parsed["event_map"], "event_map"),
            editorial_blueprint=_object(
                parsed["editorial_blueprint"], "editorial_blueprint"
            ),
            approved_source_package=_object(
                parsed["source_package"], "source_package"
            ),
            evidence_package=ApprovedEvidencePackage.from_mapping(
                _object(parsed["evidence_package"], "evidence_package")
            ),
            adjudication=ApprovedEventEvidenceAdjudication.from_mapping(
                _object(parsed["adjudication"], "adjudication")
            ),
            evidence_package_fingerprint=canonical_json_sha256(
                parsed["evidence_package"]
            ),
            adjudication_fingerprint=canonical_json_sha256(parsed["adjudication"]),
        )

    def bind_from_data(
        self,
        *,
        episode_definition: Mapping[str, object],
        event_map: Iterable[Mapping[str, object]],
        editorial_blueprint: Mapping[str, object],
        approved_source_package: Mapping[str, object],
        evidence_package: ApprovedEvidencePackage,
        adjudication: ApprovedEventEvidenceAdjudication,
        evidence_package_fingerprint: str,
        adjudication_fingerprint: str,
    ) -> EvidenceBoundCinematicBlueprint:
        events = tuple(event_map)
        event_by_id = {
            _required_text(item, "event_id"): item for item in events
        }
        required_event_ids = _required_string_list(
            _object(episode_definition.get("historical_scope"), "historical_scope"),
            "required_event_ids",
        )
        self._validate_top_level_contracts(
            episode_definition=episode_definition,
            editorial_blueprint=editorial_blueprint,
            approved_source_package=approved_source_package,
            evidence_package=evidence_package,
            adjudication=adjudication,
            evidence_package_fingerprint=evidence_package_fingerprint,
            required_event_ids=required_event_ids,
            event_by_id=event_by_id,
        )
        evidence_by_id = {
            item.evidence_id: item for item in evidence_package.evidence_items
        }
        decisions_by_event = {
            item.event_id: item for item in adjudication.decisions
        }
        source_by_id = {
            _required_text(item, "source_id"): item
            for item in _object_list(
                approved_source_package.get("source_items"), "source_items"
            )
        }
        self._validate_sources_and_decisions(
            required_event_ids=required_event_ids,
            event_by_id=event_by_id,
            evidence_by_id=evidence_by_id,
            decisions_by_event=decisions_by_event,
            source_by_id=source_by_id,
            approved_source_package=approved_source_package,
            evidence_package=evidence_package,
        )

        original_storyboard = _storyboard_from_manifest(
            _object(editorial_blueprint.get("storyboard"), "storyboard")
        )
        contract, policy, budget = _compilation_contracts_from_manifest(
            _object(
                editorial_blueprint.get("cinematic_compilation"),
                "cinematic_compilation",
            )
        )
        bound_frames = tuple(
            self._bind_frame(frame, decisions_by_event, evidence_by_id)
            for frame in original_storyboard.frames
        )
        bound_storyboard_id = deterministic_id(
            "evidence_bound_storyboard",
            [
                original_storyboard.storyboard_id,
                evidence_package.package_id,
                adjudication.adjudication_id,
                [
                    [frame.frame_id, frame.referenced_evidence_ids]
                    for frame in bound_frames
                ],
            ],
        )
        bound_storyboard = Storyboard(
            storyboard_id=bound_storyboard_id,
            scene_plan_id=original_storyboard.scene_plan_id,
            frames=list(bound_frames),
            frame_count=len(bound_frames),
            position=original_storyboard.position,
            trace_metadata={
                **original_storyboard.trace_metadata,
                "evidence_package_ids": [evidence_package.package_id],
                "adjudication_ids": [adjudication.adjudication_id],
                "evidence_gate_statuses": [EVIDENCE_GATE_OPEN],
            },
            validation_state="VALID",
        )
        compiled = self._compiler.compile(
            bound_storyboard,
            contract,
            policy=policy,
            budget=budget,
        )
        self._validate_compilation_preserved(
            original_compilation=_object(
                editorial_blueprint.get("cinematic_compilation"),
                "cinematic_compilation",
            ),
            compiled=compiled,
        )

        included = tuple(
            event_id
            for event_id in required_event_ids
            if decisions_by_event[event_id].disposition
            in {
                EventDisposition.INCLUDE_ASSERTIVE,
                EventDisposition.INCLUDE_QUALIFIED,
            }
        )
        qualified = tuple(
            event_id
            for event_id in required_event_ids
            if decisions_by_event[event_id].disposition
            is EventDisposition.INCLUDE_QUALIFIED
        )
        omitted = tuple(
            event_id
            for event_id in required_event_ids
            if decisions_by_event[event_id].disposition
            is EventDisposition.OMIT_UNVERIFIED
        )
        editorial = tuple(
            event_id
            for event_id in required_event_ids
            if decisions_by_event[event_id].disposition
            is EventDisposition.EDITORIAL_ONLY
        )
        original_bridge_id = _required_text(editorial_blueprint, "bridge_id")
        binding_id = deterministic_id(
            "approved_evidence_binding",
            [
                EVIDENCE_BOUND_BLUEPRINT_SCHEMA_VERSION,
                original_bridge_id,
                bound_storyboard.storyboard_id,
                compiled.compilation_id,
                evidence_package.package_id,
                adjudication.adjudication_id,
                evidence_package_fingerprint,
                adjudication_fingerprint,
                included,
                qualified,
                omitted,
                editorial,
            ],
        )
        result = EvidenceBoundCinematicBlueprint(
            binding_id=binding_id,
            original_bridge_id=original_bridge_id,
            evidence_package_id=evidence_package.package_id,
            adjudication_id=adjudication.adjudication_id,
            evidence_package_fingerprint=evidence_package_fingerprint,
            adjudication_fingerprint=adjudication_fingerprint,
            storyboard=bound_storyboard,
            compiled_episode=compiled,
            approval_records=(evidence_package.approval, adjudication.approval),
            included_event_ids=included,
            qualified_event_ids=qualified,
            omitted_event_ids=omitted,
            editorial_event_ids=editorial,
        )
        self._validate_result(result, decisions_by_event)
        return result

    @staticmethod
    def _validate_top_level_contracts(
        *,
        episode_definition: Mapping[str, object],
        editorial_blueprint: Mapping[str, object],
        approved_source_package: Mapping[str, object],
        evidence_package: ApprovedEvidencePackage,
        adjudication: ApprovedEventEvidenceAdjudication,
        evidence_package_fingerprint: str,
        required_event_ids: list[str],
        event_by_id: Mapping[str, Mapping[str, object]],
    ) -> None:
        episode_id = _required_text(episode_definition, "episode_id")
        if evidence_package.episode_id != episode_id or adjudication.episode_id != episode_id:
            raise CinematicSeriesError(
                "Episode definition, evidence package, and adjudication must match."
            )
        if _required_text(editorial_blueprint, "episode_id") != episode_id:
            raise CinematicSeriesError("Editorial blueprint references another episode.")
        if editorial_blueprint.get("evidence_gate_status") != EVIDENCE_GATE_WITHHELD:
            raise CinematicSeriesError(
                "Only a withheld editorial blueprint can receive approved evidence."
            )
        if editorial_blueprint.get("live_execution_status") != LIVE_EXECUTION_STATUS:
            raise CinematicSeriesError("Editorial blueprint enabled live execution.")
        if editorial_blueprint.get("runware_execution_status") != RUNWARE_EXECUTION_STATUS:
            raise CinematicSeriesError("Editorial blueprint changed the Runware gate.")
        if adjudication.evidence_package_id != evidence_package.package_id:
            raise CinematicSeriesError(
                "Adjudication must point to the exact approved evidence package."
            )
        source_ref = _object(episode_definition.get("source_package"), "source_package")
        if source_ref.get("approval_status") != HUMAN_APPROVAL_STATUS:
            raise CinematicSeriesError(
                "Episode source package must be explicitly APPROVED before binding."
            )
        evidence_ref = _object(
            episode_definition.get("evidence_package"), "evidence_package"
        )
        if not _required_text(evidence_ref, "path"):
            raise CinematicSeriesError("Episode evidence package path must be recorded.")
        if _required_text(evidence_ref, "input_fingerprint") != (
            evidence_package_fingerprint
        ):
            raise CinematicSeriesError(
                "Episode evidence package fingerprint does not match the approved file."
            )
        if approved_source_package.get("package_status") != HUMAN_APPROVAL_STATUS:
            raise CinematicSeriesError("Source package payload must be APPROVED.")
        if approved_source_package.get("episode_id") != episode_id:
            raise CinematicSeriesError("Approved source package references another episode.")
        source_fp = _required_text(approved_source_package, "input_fingerprint")
        if evidence_package.source_package_fingerprint != source_fp:
            raise CinematicSeriesError(
                "Evidence package was not approved against this source package."
            )
        if len(event_by_id) != len(required_event_ids):
            raise CinematicSeriesError("Event ids must be unique and complete.")
        if list(event_by_id) != required_event_ids:
            raise CinematicSeriesError(
                "Event map must preserve the approved required-event order."
            )

    @staticmethod
    def _validate_sources_and_decisions(
        *,
        required_event_ids: list[str],
        event_by_id: Mapping[str, Mapping[str, object]],
        evidence_by_id: Mapping[str, ApprovedEvidenceItem],
        decisions_by_event: Mapping[str, EventEvidenceDecision],
        source_by_id: Mapping[str, Mapping[str, object]],
        approved_source_package: Mapping[str, object],
        evidence_package: ApprovedEvidencePackage,
    ) -> None:
        if list(decisions_by_event) != required_event_ids:
            raise CinematicSeriesError(
                "Adjudication must resolve every event exactly once in approved order."
            )
        raw_source_items = _object_list(
            approved_source_package.get("source_items"), "source_items"
        )
        if len(source_by_id) != len(raw_source_items):
            raise CinematicSeriesError("Approved source ids must be unique.")

        referenced_evidence_ids: list[str] = []
        for event_id in required_event_ids:
            event = event_by_id[event_id]
            decision = decisions_by_event[event_id]
            verification_status = _required_text(event, "verification_status")
            if verification_status == "editorial":
                if decision.disposition is not EventDisposition.EDITORIAL_ONLY:
                    raise CinematicSeriesError(
                        "Editorial events must use the editorial_only disposition."
                    )
            elif decision.disposition is EventDisposition.EDITORIAL_ONLY:
                raise CinematicSeriesError(
                    "Only editorial events may use the editorial_only disposition."
                )
            if verification_status == "quran_explicit":
                if decision.disposition is not EventDisposition.INCLUDE_ASSERTIVE:
                    raise CinematicSeriesError(
                        "Quran-explicit events require assertive approved inclusion."
                    )
            for evidence_id in decision.evidence_ids:
                if evidence_id not in evidence_by_id:
                    raise CinematicSeriesError(
                        f"Decision references unknown evidence id: {evidence_id}"
                    )
                evidence = evidence_by_id[evidence_id]
                if evidence.event_id != event_id:
                    raise CinematicSeriesError(
                        "Evidence may only bind to the event it was approved for."
                    )
                referenced_evidence_ids.append(evidence_id)
            if decision.disposition is EventDisposition.INCLUDE_ASSERTIVE:
                classes = {
                    evidence_by_id[evidence_id].claim_classification
                    for evidence_id in decision.evidence_ids
                }
                if not classes.issubset(_ASSERTIVE_CLASSES):
                    raise CinematicSeriesError(
                        "Assertive inclusion requires only assertive evidence classes."
                    )
                if verification_status == "quran_explicit" and (
                    ClaimClassification.QURAN_EXPLICIT not in classes
                ):
                    raise CinematicSeriesError(
                        "Quran-explicit events require Quran-explicit evidence."
                    )

        if len(referenced_evidence_ids) != len(set(referenced_evidence_ids)):
            raise CinematicSeriesError(
                "An evidence item cannot be assigned to multiple event decisions."
            )
        if set(referenced_evidence_ids) != set(evidence_by_id):
            raise CinematicSeriesError(
                "Approved evidence items must be referenced exactly once; orphans are forbidden."
            )
        if not referenced_evidence_ids:
            raise CinematicSeriesError("Evidence gate cannot open with zero evidence.")

        for evidence in evidence_package.evidence_items:
            if evidence.source_id not in source_by_id:
                raise CinematicSeriesError(
                    f"Evidence references unknown approved source: {evidence.source_id}"
                )
            source = source_by_id[evidence.source_id]
            if source.get("access_status") not in {"ACQUIRED", "VERIFIED", "APPROVED"}:
                raise CinematicSeriesError(
                    "Evidence sources must be acquired or verified, not merely planned."
                )
            if source.get("allowed_for_extraction") is not True:
                raise CinematicSeriesError(
                    "Evidence source must be approved for extraction."
                )
            source_checksum = _required_text(source, "checksum").lower()
            if source_checksum != evidence.source_checksum_sha256:
                raise CinematicSeriesError(
                    "Evidence source checksum differs from the approved source record."
                )
            notes = _object(source.get("notes"), "source notes")
            supports = _required_string_list(notes, "supports_event_ids")
            if evidence.event_id not in supports:
                raise CinematicSeriesError(
                    "Approved source record does not support the bound event."
                )
            if (
                evidence.claim_classification is ClaimClassification.QURAN_EXPLICIT
                and source.get("source_type") != "QURAN"
            ):
                raise CinematicSeriesError(
                    "Quran-explicit evidence must reference a Quran source."
                )
            if evidence.quotation_allowed and source.get("allowed_for_quotation") is not True:
                raise CinematicSeriesError(
                    "Evidence cannot allow quotation when its source forbids quotation."
                )

    @staticmethod
    def _bind_frame(
        frame: StoryboardFrame,
        decisions_by_event: Mapping[str, EventEvidenceDecision],
        evidence_by_id: Mapping[str, ApprovedEvidenceItem],
    ) -> StoryboardFrame:
        event_ids = tuple(frame.trace_metadata.get("event_ids", []))
        evidence_ids: list[str] = []
        included: list[str] = []
        qualified: list[str] = []
        omitted: list[str] = []
        editorial: list[str] = []
        qualification_labels: list[str] = []
        for event_id in event_ids:
            if event_id not in decisions_by_event:
                raise CinematicSeriesError(
                    f"Storyboard frame references unadjudicated event: {event_id}"
                )
            decision = decisions_by_event[event_id]
            if decision.disposition in {
                EventDisposition.INCLUDE_ASSERTIVE,
                EventDisposition.INCLUDE_QUALIFIED,
            }:
                included.append(event_id)
                evidence_ids.extend(decision.evidence_ids)
            if decision.disposition is EventDisposition.INCLUDE_QUALIFIED:
                qualified.append(event_id)
                qualification_labels.append(decision.qualification_label or "")
            elif decision.disposition is EventDisposition.OMIT_UNVERIFIED:
                omitted.append(event_id)
            elif decision.disposition is EventDisposition.EDITORIAL_ONLY:
                editorial.append(event_id)
        for evidence_id in evidence_ids:
            if evidence_id not in evidence_by_id:
                raise CinematicSeriesError("Frame binding references unknown evidence.")
        trace = dict(frame.trace_metadata)
        trace.update(
            {
                "approved_included_event_ids": included,
                "qualified_event_ids": qualified,
                "omitted_event_ids": omitted,
                "editorial_only_event_ids": editorial,
                "qualification_labels": qualification_labels,
                "evidence_gate_statuses": [EVIDENCE_GATE_OPEN],
            }
        )
        return StoryboardFrame(
            frame_id=frame.frame_id,
            scene_id=frame.scene_id,
            frame_purpose=frame.frame_purpose,
            referenced_evidence_ids=_ordered_unique(evidence_ids),
            created_at=frame.created_at,
            position=frame.position,
            trace_metadata=trace,
        )

    @staticmethod
    def _validate_compilation_preserved(
        *,
        original_compilation: Mapping[str, object],
        compiled: CompiledCinematicEpisode,
    ) -> None:
        original_frames = _object_list(original_compilation.get("frames"), "frames")
        new_frames = compiled.to_manifest()["frames"]
        if len(original_frames) != len(new_frames):
            raise CinematicSeriesError("Evidence binding changed storyboard frame count.")
        for original, new in zip(original_frames, new_frames, strict=True):
            for key in (
                "frame_id",
                "narrative_function",
                "spectacle_level",
                "planned_seconds",
                "generated_video_seconds",
                "callback_to_frame_id",
            ):
                if original.get(key) != new.get(key):
                    raise CinematicSeriesError(
                        f"Evidence binding unexpectedly changed cinematic field {key}."
                    )
        if compiled.plan.generated_video_seconds != 0:
            raise CinematicSeriesError(
                "Evidence binding must not pre-allocate generated video."
            )

    @staticmethod
    def _validate_result(
        result: EvidenceBoundCinematicBlueprint,
        decisions_by_event: Mapping[str, EventEvidenceDecision],
    ) -> None:
        if result.evidence_gate_status != EVIDENCE_GATE_OPEN:
            raise CinematicSeriesError("Bound evidence gate did not open.")
        if result.live_execution_status != LIVE_EXECUTION_STATUS:
            raise CinematicSeriesError("Evidence binding enabled live execution.")
        if result.compiled_episode.plan.runware_execution_status != RUNWARE_EXECUTION_STATUS:
            raise CinematicSeriesError("Evidence binding changed the Runware gate.")
        referenced = {
            evidence_id
            for frame in result.storyboard.frames
            for evidence_id in frame.referenced_evidence_ids
        }
        expected = {
            evidence_id
            for decision in decisions_by_event.values()
            for evidence_id in decision.evidence_ids
        }
        if referenced != expected:
            raise CinematicSeriesError(
                "Bound storyboard evidence references do not match adjudication."
            )


def approved_evidence_package_template(episode_id: str) -> dict[str, object]:
    return {
        "schema_version": APPROVED_EVIDENCE_PACKAGE_SCHEMA_VERSION,
        "template_status": TEMPLATE_STATUS,
        "package_id": "REPLACE_AFTER_HUMAN_APPROVAL",
        "episode_id": episode_id,
        "source_package_fingerprint": "REPLACE_WITH_APPROVED_SOURCE_PACKAGE_FINGERPRINT",
        "approval": {
            "approval_id": "",
            "approved_by": "",
            "approved_at": "",
            "approval_status": "NOT_APPROVED",
            "human_approval": False,
            "notes": "",
        },
        "evidence_items": [],
    }


def event_evidence_adjudication_template(episode_id: str) -> dict[str, object]:
    return {
        "schema_version": EVENT_EVIDENCE_ADJUDICATION_SCHEMA_VERSION,
        "template_status": TEMPLATE_STATUS,
        "adjudication_id": "REPLACE_AFTER_HUMAN_APPROVAL",
        "episode_id": episode_id,
        "evidence_package_id": "REPLACE_WITH_APPROVED_EVIDENCE_PACKAGE_ID",
        "approval": {
            "approval_id": "",
            "approved_by": "",
            "approved_at": "",
            "approval_status": "NOT_APPROVED",
            "human_approval": False,
            "notes": "",
        },
        "decisions": [],
    }


def validate_non_executable_templates(
    evidence_template: Mapping[str, object],
    adjudication_template: Mapping[str, object],
) -> bool:
    if evidence_template.get("template_status") != TEMPLATE_STATUS:
        return False
    if adjudication_template.get("template_status") != TEMPLATE_STATUS:
        return False
    for payload in (evidence_template, adjudication_template):
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        if any(secret in serialized for secret in ("api_key", "authorization", "bearer ")):
            return False
        approval = payload.get("approval")
        if not isinstance(approval, Mapping):
            return False
        if approval.get("approval_status") == HUMAN_APPROVAL_STATUS:
            return False
        if approval.get("human_approval") is True:
            return False
    return True


def write_evidence_bound_blueprint(
    path: Path,
    blueprint: EvidenceBoundCinematicBlueprint,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = blueprint.to_json(pretty=True).replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(text.encode("utf-8"))


def canonical_json_sha256(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _storyboard_from_manifest(payload: Mapping[str, object]) -> Storyboard:
    raw_frames = _object_list(payload.get("frames"), "storyboard frames")
    frames = [
        StoryboardFrame(
            frame_id=_required_text(item, "frame_id"),
            scene_id=_required_text(item, "scene_id"),
            frame_purpose=_required_text(item, "frame_purpose"),
            referenced_evidence_ids=list(
                _string_tuple(
                    item.get("referenced_evidence_ids", []),
                    "referenced_evidence_ids",
                )
            ),
            position=_required_int(item, "position"),
            trace_metadata=_trace_metadata(item.get("trace_metadata", {})),
        )
        for item in raw_frames
    ]
    storyboard = Storyboard(
        storyboard_id=_required_text(payload, "storyboard_id"),
        scene_plan_id=_required_text(payload, "scene_plan_id"),
        frames=frames,
        frame_count=_required_int(payload, "frame_count"),
        position=int(payload.get("position", 0)),
        trace_metadata=_trace_metadata(payload.get("trace_metadata", {})),
        validation_state=_required_text(payload, "validation_state"),
    )
    if storyboard.frame_count != len(storyboard.frames):
        raise CinematicSeriesError("Storyboard manifest frame count is inconsistent.")
    return storyboard


def _storyboard_manifest(storyboard: Storyboard) -> dict[str, object]:
    return {
        "storyboard_id": storyboard.storyboard_id,
        "scene_plan_id": storyboard.scene_plan_id,
        "frame_count": storyboard.frame_count,
        "position": storyboard.position,
        "validation_state": storyboard.validation_state,
        "trace_metadata": storyboard.trace_metadata,
        "frames": [
            {
                "frame_id": frame.frame_id,
                "scene_id": frame.scene_id,
                "frame_purpose": frame.frame_purpose,
                "referenced_evidence_ids": list(frame.referenced_evidence_ids),
                "position": frame.position,
                "trace_metadata": frame.trace_metadata,
            }
            for frame in storyboard.frames
        ],
    }


def _compilation_contracts_from_manifest(
    payload: Mapping[str, object],
) -> tuple[EpisodeSeriesContract, CinematicCompilationPolicy, CinematicBudgetGuardrails]:
    contract_payload = _object(payload.get("episode_contract"), "episode_contract")
    contract = EpisodeSeriesContract(
        series_title=_required_text(contract_payload, "series_title"),
        season_title=_required_text(contract_payload, "season_title"),
        episode_id=_required_text(contract_payload, "episode_id"),
        season_question=_required_text(contract_payload, "season_question"),
        central_question=_required_text(contract_payload, "central_question"),
        emotional_promise=_required_text(contract_payload, "emotional_promise"),
        knowledge_promise=_required_text(contract_payload, "knowledge_promise"),
        next_episode_question=_required_text(contract_payload, "next_episode_question"),
        unresolved_thread_from_previous=_optional_text(
            contract_payload.get("unresolved_thread_from_previous")
        ),
    )
    duration = _object(payload.get("duration"), "duration")
    policy = CinematicCompilationPolicy(
        target_episode_seconds=_required_int(duration, "target_episode_seconds")
    )
    budget_payload = _object(payload.get("budget_guardrails_usd"), "budget_guardrails_usd")
    budget = CinematicBudgetGuardrails(
        target_total_usd=float(budget_payload.get("target_total")),
        hard_total_usd=float(budget_payload.get("hard_total")),
    )
    contract.validate()
    policy.validate()
    budget.validate()
    return contract, policy, budget


def _load_json_bytes(data: bytes, label: str) -> object:
    try:
        return json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CinematicSeriesError(f"Invalid JSON in {label}: {error}") from error


def _required_text(
    payload: Mapping[str, object], key: str, fallback: str | None = None
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise CinematicSeriesError(f"{key} must be a nonblank string.")
    return value.strip()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CinematicSeriesError("Optional text values must be strings or null.")
    stripped = value.strip()
    return stripped or None


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise CinematicSeriesError(f"{key} must be a boolean.")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CinematicSeriesError(f"{key} must be an integer.")
    return value


def _required_string_list(payload: Mapping[str, object], key: str) -> list[str]:
    return list(_string_tuple(payload.get(key), key))


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CinematicSeriesError(f"{label} must be a list of strings.")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CinematicSeriesError(f"{label} must contain nonblank strings.")
        result.append(item.strip())
    return tuple(result)


def _object(value: object, label: str = "object") -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise CinematicSeriesError(f"{label} must be an object.")
    return value


def _object_list(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise CinematicSeriesError(f"{label} must be a list.")
    return [_object(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _trace_metadata(value: object) -> dict[str, list[str]]:
    payload = _object(value, "trace_metadata")
    result: dict[str, list[str]] = {}
    for key, items in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise CinematicSeriesError("Trace metadata keys must be nonblank strings.")
        result[key] = list(_string_tuple(items, f"trace_metadata.{key}"))
    return result
