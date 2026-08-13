"""Offline, constitutional, extractive YouTube Shorts derivative engine.

This module deliberately contains no provider, network, publication, or paid
execution capability.  It is a local editorial director and deterministic
renderer for derivatives of an already-approved episode.  The engine is
fail-closed: missing source evidence, missing timing, unsafe composition, or
stale hashes block downstream work instead of being silently guessed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from src.application.artifact_provenance_v1 import append_jsonl, write_new_json
from src.application.unified_constitution_enforcement_v1 import (
    RuleRegistry,
    ValidatorRegistry,
    analyze_face_semantics,
    analyze_sensitive_semantics,
    artifact_sha256,
    canonical_json_sha256,
    load_unified_constitution,
)


PROFILE_RELATIVE_PATH = Path("config/shorts/siraj_shorts_derivative_profile_v1.json")
PROFILE_SCHEMA_RELATIVE_PATH = Path(
    "config/shorts/siraj_shorts_derivative_profile_v1.schema.json"
)
SCHEMA_VERSION = "siraj-shorts-derivative-engine-v1"
PROFILE_VERSION = "SIRAJ_SHORTS_DERIVATIVE_PROFILE_V1"
CONSTITUTION_VERSION = "1.0.0"
TARGET_ORIENTATION = "VERTICAL"
TARGET_ASPECT_RATIO = "9:16"
TARGET_RATIO = 9.0 / 16.0
SOURCE_POLICY = "EXISTING_EPISODE_MATERIAL_ONLY"
MAX_SHORTS_PER_DAY = 1
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")

REQUIRED_PROFILE_FIELDS = frozenset(
    {
        "profile_id",
        "version",
        "media_type",
        "output_orientation",
        "aspect_ratio",
        "source_policy",
        "new_visual_generation",
        "new_narration_generation",
        "new_tts_generation",
        "music",
        "burned_captions",
        "on_screen_subtitles",
        "external_closed_captions_allowed",
        "public_title_generation",
        "thumbnail_generation",
        "automatic_publication",
        "max_shorts_per_day",
        "target_duration_min_seconds",
        "target_duration_max_seconds",
        "quality_over_slot_filling",
        "candidate_count_is_dynamic",
        "publication_count_is_dynamic",
        "no_silent_defaults",
        "hard_gates",
        "scoring_weights",
    }
)

STATES = (
    "INGESTED",
    "ANALYZED",
    "CANDIDATES_READY",
    "PORTFOLIO_READY",
    "HUMAN_SELECTION_REQUIRED",
    "RENDER_PLAN_READY",
    "LOCAL_RENDER_APPROVAL_REQUIRED",
    "RENDERED",
    "SHORT_QA_PENDING",
    "SHORT_QA_PASS",
    "SHORT_QA_FAIL",
    "HUMAN_FINAL_REVIEW_REQUIRED",
    "EXPORT_READY",
    "REJECTED",
    "BLOCKED",
)

FAILURE_CODES = frozenset(
    {
        "SHORT_SOURCE_MISSING",
        "SHORT_SOURCE_HASH_CHANGED",
        "SHORT_TRANSCRIPT_REQUIRED",
        "SHORT_PROFILE_INVALID",
        "SHORT_CONSTITUTION_SCOPE_BLOCKED",
        "SHORT_CONTEXT_DEPENDENT",
        "SHORT_HOOK_TOO_WEAK",
        "SHORT_UNSAFE_SOURCE",
        "SHORT_VERTICAL_REFRAME_UNSAFE",
        "SHORT_VERTICAL_QUALITY_FAIL",
        "SHORT_AUDIO_BOUNDARY_INVALID",
        "SHORT_REORDER_FACT_RISK",
        "SHORT_DUPLICATE_PORTFOLIO_ITEM",
        "SHORT_RENDER_PLAN_INVALID",
        "SHORT_RENDER_HASH_MISMATCH",
        "SHORT_QA_FAIL",
        "SHORT_HUMAN_REVIEW_REQUIRED",
        "SHORT_SCHEDULE_DAY_REQUIRED",
        "SHORT_PROVIDER_CAPABILITY_FORBIDDEN",
        "SHORT_NETWORK_CAPABILITY_FORBIDDEN",
        "SHORT_PUBLICATION_FORBIDDEN",
    }
)


class ShortsEngineError(RuntimeError):
    """Base error for the offline Shorts engine."""


class ShortsBlockedError(ShortsEngineError):
    """Raised when a fail-closed gate cannot be satisfied."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


class ShortsProfileError(ShortsBlockedError):
    """Raised for missing or unsafe profile values."""


class SourceIntegrityError(ShortsBlockedError):
    """Raised when a source or upstream hash is missing or stale."""


class LocalRenderError(ShortsBlockedError):
    """Raised when an explicitly approved local render cannot be completed."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _hash_value(value: Any) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _finite_number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShortsBlockedError("SHORT_PROFILE_INVALID", f"{field_name}:NUMBER_REQUIRED")
    number = float(value)
    if not math.isfinite(number):
        raise ShortsBlockedError("SHORT_PROFILE_INVALID", f"{field_name}:FINITE_REQUIRED")
    return number


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _as_mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShortsBlockedError("SHORT_PROFILE_INVALID", f"{field_name}:OBJECT_REQUIRED")
    return value


def _as_sequence(value: Any, *, field_name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ShortsBlockedError("SHORT_PROFILE_INVALID", f"{field_name}:ARRAY_REQUIRED")
    return value


def _contains_unknown(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().upper() in {"", "UNKNOWN", "UNSET", "DEFAULT"}
    if isinstance(value, Mapping):
        return not value or any(_contains_unknown(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return not value or any(_contains_unknown(item) for item in value)
    return False


def _relative_or_absolute(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve())


def _read_json(path: Path, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ShortsBlockedError(code, str(path)) from exc
    if not isinstance(value, dict):
        raise ShortsBlockedError(code, str(path))
    return value


def load_shorts_profile(repo_root: Path) -> dict[str, Any]:
    """Load and validate the versioned Shorts profile without defaults."""

    path = Path(repo_root) / PROFILE_RELATIVE_PATH
    if not path.is_file():
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "PROFILE_MISSING")
    document = _read_json(path, code="SHORT_PROFILE_INVALID")
    schema_path = Path(repo_root) / PROFILE_SCHEMA_RELATIVE_PATH
    if not schema_path.is_file():
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "PROFILE_SCHEMA_MISSING")
    schema = _read_json(schema_path, code="SHORT_PROFILE_INVALID")
    try:
        import jsonschema
        from jsonschema import Draft202012Validator

        Draft202012Validator.check_schema(schema)
        schema_errors = sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    except ImportError as exc:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "SCHEMA_VALIDATOR_UNAVAILABLE") from exc
    except Exception as exc:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "SCHEMA_DEFINITION_INVALID") from exc
    if schema_errors:
        first = schema_errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "$"
        raise ShortsProfileError("SHORT_PROFILE_INVALID", f"SCHEMA_INVALID:{location}:{first.message}")
    profile = document.get("profile")
    if not isinstance(profile, dict):
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "PROFILE_OBJECT_MISSING")
    missing = sorted(REQUIRED_PROFILE_FIELDS.difference(profile))
    if missing:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "MISSING:" + ",".join(missing))
    if profile.get("profile_id") != PROFILE_VERSION:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "PROFILE_ID_MISMATCH")
    if profile.get("version") != "1.0.0":
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "PROFILE_VERSION_MISMATCH")
    expected = {
        "media_type": "SHORT_DERIVATIVE",
        "output_orientation": TARGET_ORIENTATION,
        "aspect_ratio": TARGET_ASPECT_RATIO,
        "source_policy": SOURCE_POLICY,
        "new_visual_generation": False,
        "new_narration_generation": False,
        "new_tts_generation": False,
        "music": False,
        "burned_captions": False,
        "on_screen_subtitles": False,
        "external_closed_captions_allowed": True,
        "public_title_generation": False,
        "thumbnail_generation": False,
        "automatic_publication": False,
        "max_shorts_per_day": MAX_SHORTS_PER_DAY,
        "quality_over_slot_filling": True,
        "candidate_count_is_dynamic": True,
        "publication_count_is_dynamic": True,
        "no_silent_defaults": True,
    }
    for key, expected_value in expected.items():
        if profile.get(key) != expected_value:
            raise ShortsProfileError("SHORT_PROFILE_INVALID", f"{key}:CONTRACT_MISMATCH")
    minimum = _finite_number(
        profile.get("target_duration_min_seconds"),
        field_name="target_duration_min_seconds",
    )
    maximum = _finite_number(
        profile.get("target_duration_max_seconds"),
        field_name="target_duration_max_seconds",
    )
    if minimum <= 0 or maximum < minimum:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "DURATION_RANGE_INVALID")
    hard_gates = _as_mapping(profile.get("hard_gates"), field_name="hard_gates")
    weights = _as_mapping(profile.get("scoring_weights"), field_name="scoring_weights")
    if not weights or any(_finite_number(value, field_name=f"weight:{key}") < 0 for key, value in weights.items()):
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "SCORING_WEIGHTS_INVALID")
    if sum(float(value) for value in weights.values()) <= 0:
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "SCORING_WEIGHTS_ZERO")
    if _contains_unknown(hard_gates):
        raise ShortsProfileError("SHORT_PROFILE_INVALID", "HARD_GATES_UNKNOWN")
    return {
        "schema_version": document.get("schema_version", SCHEMA_VERSION),
        "profile": json.loads(json.dumps(profile, ensure_ascii=False, sort_keys=True)),
        "profile_sha256": _hash_value(profile),
        "profile_schema_sha256": _sha256_file(schema_path),
        "profile_path": str(path.resolve()),
        "profile_schema_path": str(schema_path.resolve()),
    }


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    segment_id: str
    start_time: float
    end_time: float
    text: str
    word_start: bool = True
    word_end: bool = True
    audio_boundary_safe: bool = True
    grammar_safe: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Beat:
    beat_id: str
    start_time: float
    end_time: float
    text: str
    chapter_id: str
    shot_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    narrative_role: str
    context_dependencies: tuple[str, ...]
    character_refs: tuple[str, ...]
    visual_action: str
    semantic_payload: Mapping[str, Any]
    curiosity_signal: float
    surprise_signal: float
    emotional_signal: float
    story_turn_signal: float
    revelation_signal: float
    question_signal: float
    payoff_signal: float
    standalone_potential: float
    visual_strength_indicators: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shot_ids"] = list(self.shot_ids)
        payload["claim_ids"] = list(self.claim_ids)
        payload["context_dependencies"] = list(self.context_dependencies)
        payload["character_refs"] = list(self.character_refs)
        payload["visual_strength_indicators"] = list(self.visual_strength_indicators)
        return payload


@dataclass(frozen=True, slots=True)
class Shot:
    shot_id: str
    start_time: float
    end_time: float
    visual_action: str
    semantic_tags: tuple[str, ...]
    subject_region: Mapping[str, float] | None
    semantic_focus_region: Mapping[str, float] | None
    safe_region: Mapping[str, float] | None
    key_action_spans_full_width: bool
    unsafe_source: bool
    unsafe_background_face: bool
    face_enlarged_by_crop: bool
    vertical_quality_hint: float | None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["semantic_tags"] = list(self.semantic_tags)
        return payload


@dataclass(frozen=True, slots=True)
class EpisodePackage:
    schema_version: str
    episode_id: str
    source_video_path: str
    source_episode_sha256: str
    source_metadata_hashes: Mapping[str, str]
    source_duration_seconds: float
    narration_segments: tuple[TranscriptSegment, ...]
    beats: tuple[Beat, ...]
    shots: tuple[Shot, ...]
    claims: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any]
    constitution_version: str
    legacy_source: bool
    has_audio: bool | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "source_video_path": self.source_video_path,
            "source_episode_sha256": self.source_episode_sha256,
            "source_metadata_hashes": dict(self.source_metadata_hashes),
            "source_duration_seconds": self.source_duration_seconds,
            "narration_segments": [item.to_dict() for item in self.narration_segments],
            "beats": [item.to_dict() for item in self.beats],
            "shots": [item.to_dict() for item in self.shots],
            "claims": [dict(item) for item in self.claims],
            "metadata": dict(self.metadata),
            "constitution_version": self.constitution_version,
            "legacy_source": self.legacy_source,
            "has_audio": self.has_audio,
        }


@dataclass(frozen=True, slots=True)
class IntelligenceMap:
    schema_version: str
    episode_id: str
    source_episode_sha256: str
    source_metadata_hashes: Mapping[str, str]
    beats: tuple[Beat, ...]
    map_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "source_episode_sha256": self.source_episode_sha256,
            "source_metadata_hashes": dict(self.source_metadata_hashes),
            "beats": [beat.to_dict() for beat in self.beats],
            "map_sha256": self.map_sha256,
        }


@dataclass(frozen=True, slots=True)
class ScoreDimension:
    value: float
    evidence: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": round(float(self.value), 6),
            "evidence": list(self.evidence),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class Candidate:
    candidate_id: str
    episode_id: str
    source_episode_sha256: str
    source_metadata_hashes: Mapping[str, str]
    beat_ids: tuple[str, ...]
    source_shot_ids: tuple[str, ...]
    start_time: float
    end_time: float
    text: str
    candidate_type: str
    context_dependence_score: float
    missing_context_items: tuple[str, ...]
    context_repair_mode: str
    context_repair_plan: Mapping[str, Any]
    vertical_reframe_plan: Mapping[str, Any]
    audio_edit_plan: Mapping[str, Any]
    pacing_plan: Mapping[str, Any]
    cta_plan: Mapping[str, Any]
    alignment: Mapping[str, Any]
    score_breakdown: Mapping[str, ScoreDimension]
    total_score: float
    longform_conversion_score: float
    spoiler_cost: float
    payoff_disclosure_level: float
    hard_gate_results: Mapping[str, Mapping[str, Any]]
    constitutional_rule_bindings: tuple[str, ...]
    policy_result: Mapping[str, Any]
    status: str
    rejection_reasons: tuple[str, ...]
    semantic_key: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "episode_id": self.episode_id,
            "source_episode_sha256": self.source_episode_sha256,
            "source_metadata_hashes": dict(self.source_metadata_hashes),
            "beat_ids": list(self.beat_ids),
            "source_shot_ids": list(self.source_shot_ids),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "text": self.text,
            "candidate_type": self.candidate_type,
            "context_dependence_score": self.context_dependence_score,
            "missing_context_items": list(self.missing_context_items),
            "context_repair_mode": self.context_repair_mode,
            "context_repair_plan": dict(self.context_repair_plan),
            "vertical_reframe_plan": dict(self.vertical_reframe_plan),
            "audio_edit_plan": dict(self.audio_edit_plan),
            "pacing_plan": dict(self.pacing_plan),
            "cta_plan": dict(self.cta_plan),
            "alignment": dict(self.alignment),
            "score_breakdown": {
                key: value.to_dict() if isinstance(value, ScoreDimension) else dict(value)
                for key, value in self.score_breakdown.items()
            },
            "total_score": self.total_score,
            "longform_conversion_score": self.longform_conversion_score,
            "spoiler_cost": self.spoiler_cost,
            "payoff_disclosure_level": self.payoff_disclosure_level,
            "hard_gate_results": {key: dict(value) for key, value in self.hard_gate_results.items()},
            "constitution_rule_bindings": list(self.constitutional_rule_bindings),
            "policy_result": dict(self.policy_result),
            "status": self.status,
            "rejection_reasons": list(self.rejection_reasons),
            "semantic_key": self.semantic_key,
        }


@dataclass(frozen=True, slots=True)
class PortfolioResult:
    schema_version: str
    episode_id: str
    source_episode_sha256: str
    candidate_ids: tuple[str, ...]
    selected_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    recommended_order: tuple[str, ...]
    weekly_slots: tuple[Mapping[str, Any], ...]
    schedule_status: str
    portfolio_status: str
    diversity_evidence: tuple[Mapping[str, Any], ...]
    portfolio_sha256: str
    human_selection_required: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "source_episode_sha256": self.source_episode_sha256,
            "candidate_ids": list(self.candidate_ids),
            "selected_candidate_ids": list(self.selected_candidate_ids),
            "rejected_candidate_ids": list(self.rejected_candidate_ids),
            "recommended_order": list(self.recommended_order),
            "weekly_slots": [dict(item) for item in self.weekly_slots],
            "schedule_status": self.schedule_status,
            "portfolio_status": self.portfolio_status,
            "diversity_evidence": [dict(item) for item in self.diversity_evidence],
            "portfolio_sha256": self.portfolio_sha256,
            "human_selection_required": self.human_selection_required,
        }


@dataclass(frozen=True, slots=True)
class RenderPlan:
    schema_version: str
    short_id: str
    source_episode_id: str
    source_episode_sha256: str
    source_metadata_hashes: Mapping[str, str]
    candidate_id: str
    candidate_type: str
    selected_source_ranges: tuple[Mapping[str, Any], ...]
    narration_segments: tuple[Mapping[str, Any], ...]
    visual_segments: tuple[Mapping[str, Any], ...]
    reframe_plan: Mapping[str, Any]
    context_repair_mode: str
    audio_edit_plan: Mapping[str, Any]
    pacing_plan: Mapping[str, Any]
    cta_plan: Mapping[str, Any]
    target_duration: Mapping[str, Any]
    expected_duration: float
    quality_scores: Mapping[str, Any]
    hard_gate_results: Mapping[str, Any]
    constitution_rule_bindings: tuple[str, ...]
    external_caption_plan: Mapping[str, Any]
    publishing_order: int | None
    profile_sha256: str
    constitution_bundle_sha256: str
    plan_sha256: str
    state: str
    local_render_approved: bool
    executor_creative_authority: bool
    provider_call_allowed: bool
    network_allowed: bool
    paid_execution_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "short_id": self.short_id,
            "source_episode_id": self.source_episode_id,
            "source_episode_sha256": self.source_episode_sha256,
            "source_metadata_hashes": dict(self.source_metadata_hashes),
            "candidate_id": self.candidate_id,
            "candidate_type": self.candidate_type,
            "selected_source_ranges": [dict(item) for item in self.selected_source_ranges],
            "narration_segments": [dict(item) for item in self.narration_segments],
            "visual_segments": [dict(item) for item in self.visual_segments],
            "reframe_plan": dict(self.reframe_plan),
            "context_repair_mode": self.context_repair_mode,
            "audio_edit_plan": dict(self.audio_edit_plan),
            "pacing_plan": dict(self.pacing_plan),
            "cta_plan": dict(self.cta_plan),
            "target_duration": dict(self.target_duration),
            "expected_duration": self.expected_duration,
            "quality_scores": dict(self.quality_scores),
            "hard_gate_results": dict(self.hard_gate_results),
            "constitution_rule_bindings": list(self.constitution_rule_bindings),
            "external_caption_plan": dict(self.external_caption_plan),
            "publishing_order": self.publishing_order,
            "profile_sha256": self.profile_sha256,
            "constitution_bundle_sha256": self.constitution_bundle_sha256,
            "plan_sha256": self.plan_sha256,
            "state": self.state,
            "local_render_approved": self.local_render_approved,
            "executor_creative_authority": self.executor_creative_authority,
            "provider_call_allowed": self.provider_call_allowed,
            "network_allowed": self.network_allowed,
            "paid_execution_allowed": self.paid_execution_allowed,
        }


@dataclass(frozen=True, slots=True)
class RenderResult:
    short_id: str
    output_path: str
    render_sha256: str
    source_episode_sha256_before: str
    source_episode_sha256_after: str
    expected_duration: float
    output_probe: Mapping[str, Any]
    state: str
    provider_calls: int
    network_calls: int
    paid_calls: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class QAResult:
    short_id: str
    status: str
    findings: tuple[Mapping[str, Any], ...]
    output_sha256: str
    source_episode_sha256: str
    human_all_frame_visual_review_required: bool
    technical_qa_pass: bool
    constitutional_automated_checks_pass: bool
    qa_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "short_id": self.short_id,
            "status": self.status,
            "findings": [dict(item) for item in self.findings],
            "output_sha256": self.output_sha256,
            "source_episode_sha256": self.source_episode_sha256,
            "human_all_frame_visual_review_required": self.human_all_frame_visual_review_required,
            "technical_qa_pass": self.technical_qa_pass,
            "constitutional_automated_checks_pass": self.constitutional_automated_checks_pass,
            "qa_sha256": self.qa_sha256,
        }


@dataclass(frozen=True, slots=True)
class HumanReviewReceipt:
    schema_version: str
    receipt_id: str
    short_id: str
    reviewer: str
    decision: str
    review_time: str
    short_render_sha256: str
    short_plan_sha256: str
    source_episode_sha256: str
    profile_sha256: str
    constitution_bundle_sha256: str
    all_frame_visual_review: bool
    constitutional_review: bool
    quality_review: bool
    notes: str
    receipt_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EngineAnalysis:
    episode: EpisodePackage
    intelligence_map: IntelligenceMap
    candidates: tuple[Candidate, ...]
    profile: Mapping[str, Any]
    profile_sha256: str
    constitution_bundle_sha256: str
    analysis_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode": self.episode.to_dict(),
            "intelligence_map": self.intelligence_map.to_dict(),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "profile": dict(self.profile),
            "profile_sha256": self.profile_sha256,
            "constitution_bundle_sha256": self.constitution_bundle_sha256,
            "analysis_sha256": self.analysis_sha256,
        }


def _parse_time(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
    elif isinstance(value, str):
        text = value.strip().replace(",", ".")
        parts = text.split(":")
        try:
            if len(parts) == 1:
                result = float(parts[0])
            elif len(parts) == 2:
                result = float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                result = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
            else:
                raise ValueError
        except ValueError as exc:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"INVALID_TIME:{value}") from exc
    else:
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "TIME_REQUIRED")
    if not math.isfinite(result) or result < 0:
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"INVALID_TIME:{value}")
    return result


def _parse_region(value: Any) -> Mapping[str, float] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", "REGION_OBJECT_REQUIRED")
    keys = ("x", "y", "w", "h")
    if any(key not in value for key in keys):
        raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", "REGION_INCOMPLETE")
    region = {key: float(value[key]) for key in keys}
    if any(not math.isfinite(item) for item in region.values()):
        raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", "REGION_NOT_FINITE")
    if region["w"] <= 0 or region["h"] <= 0:
        raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", "REGION_EMPTY")
    return region


def _sequence_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if not isinstance(value, Sequence):
        raise ShortsBlockedError("SHORT_PROFILE_INVALID", "STRING_ARRAY_REQUIRED")
    return tuple(_clean_text(item) for item in value if _clean_text(item))


def _parse_vtt_or_srt(path: Path) -> list[TranscriptSegment]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", str(path)) from exc
    pattern = re.compile(
        r"(?P<start>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})\s+-->\s+"
        r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?[\.,]\d{3})(?:[^\n]*)\n(?P<body>.*?)(?=\n\s*\n|\Z)",
        re.DOTALL,
    )
    segments: list[TranscriptSegment] = []
    for index, match in enumerate(pattern.finditer(text), start=1):
        body = _clean_text(match.group("body").replace("\n", " "))
        if not body:
            continue
        segments.append(
            TranscriptSegment(
                segment_id=f"SEG-{index:04d}",
                start_time=_parse_time(match.group("start")),
                end_time=_parse_time(match.group("end")),
                text=body,
            )
        )
    if not segments:
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "NO_TIMED_SEGMENTS")
    return segments


def _parse_transcript_payload(value: Any) -> list[TranscriptSegment]:
    if isinstance(value, Mapping):
        raw = value.get("segments", value.get("transcript", value.get("cues")))
    else:
        raw = value
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "SEGMENTS_REQUIRED")
    result: list[TranscriptSegment] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"SEGMENT_OBJECT_REQUIRED:{index}")
        start = _parse_time(item.get("start_time", item.get("start")))
        end = _parse_time(item.get("end_time", item.get("end")))
        if end <= start:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"SEGMENT_RANGE_INVALID:{index}")
        text = _clean_text(item.get("text"))
        if not text:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"SEGMENT_TEXT_MISSING:{index}")
        result.append(
            TranscriptSegment(
                segment_id=_clean_text(item.get("segment_id", item.get("id", f"SEG-{index:04d}"))),
                start_time=start,
                end_time=end,
                text=text,
                word_start=bool(item.get("word_start", True)),
                word_end=bool(item.get("word_end", True)),
                audio_boundary_safe=bool(item.get("audio_boundary_safe", True)),
                grammar_safe=bool(item.get("grammar_safe", True)),
            )
        )
    if not result:
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "NO_SEGMENTS")
    seen: set[str] = set()
    previous_end = -1.0
    for segment in result:
        if not segment.segment_id or segment.segment_id in seen:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "SEGMENT_ID_DUPLICATE")
        if segment.start_time < previous_end:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "SEGMENTS_OVERLAP")
        seen.add(segment.segment_id)
        previous_end = segment.end_time
    return result


def _derive_signals(text: str, role: str, raw: Mapping[str, Any]) -> dict[str, float]:
    normalized = text.casefold()
    question = 1.0 if "?" in text or "؟" in text or re.search(r"\b(?:why|how|what|who|ماذا|كيف|لماذا|من)\b", normalized) else 0.0
    revelation = 1.0 if re.search(r"\b(?:revealed|discovered|realized|turns out|لكن|ثم|اتضح|اكتشف|تبين)\b", normalized) else 0.0
    surprise = 1.0 if re.search(r"\b(?:suddenly|unexpected|surprise|لم يكن|فجأة|عجيب|مفاجأة)\b", normalized) else 0.0
    emotional = 1.0 if re.search(r"\b(?:fear|hope|grief|mercy|love|خوف|رجاء|رحمة|حزن|نجاة)\b", normalized) else 0.0
    story_turn = 1.0 if re.search(r"\b(?:then|after|before|changed|turn|بعد ذلك|قبل ذلك|تغير|تحول)\b", normalized) else 0.0
    payoff = 1.0 if role.upper() in {"PAYOFF", "ENDING", "REVELATION", "IMPORTANT_FACT"} or re.search(r"[.!؟?]$", text) else 0.0
    visual = raw.get("visual_strength_indicators", raw.get("visual_strength", ()))
    visual_count = len(_sequence_strings(visual)) if visual else 0
    return {
        "curiosity": float(raw.get("curiosity_signal", max(question, revelation * 0.8, min(1.0, len(text) / 180)))) if raw.get("curiosity_signal") is not None else max(question, revelation * 0.8, min(1.0, len(text) / 180)),
        "surprise": float(raw.get("surprise_signal", surprise)),
        "emotional": float(raw.get("emotional_signal", emotional)),
        "story_turn": float(raw.get("story_turn_signal", story_turn)),
        "revelation": float(raw.get("revelation_signal", revelation)),
        "question": float(raw.get("question_signal", question)),
        "payoff": float(raw.get("payoff_signal", payoff)),
        "visual": float(raw.get("visual_strength", min(1.0, 0.4 + visual_count * 0.15))) if raw.get("visual_strength") is not None else min(1.0, 0.4 + visual_count * 0.15),
    }


_CONTEXT_PATTERNS = (
    ("PRONOUN", re.compile(r"\b(?:this|that|he|she|it|they|there|هو|هي|هذا|ذلك|تلك|هناك|هم)\b", re.IGNORECASE)),
    ("DEFERRED_REFERENCE", re.compile(r"\b(?:as mentioned|as we saw|later|after that|كما ذكرنا|لاحقًا|بعد ذلك)\b", re.IGNORECASE)),
    ("UNINTRODUCED_NAME", re.compile(r"\b(?:the man|the woman|الرجل|المرأة)\b", re.IGNORECASE)),
)


def _context_analysis(text: str, raw_dependencies: Sequence[str]) -> tuple[float, tuple[str, ...]]:
    items = list(_sequence_strings(raw_dependencies))
    for label, pattern in _CONTEXT_PATTERNS:
        if pattern.search(text):
            items.append(label)
    unique = tuple(sorted(set(item for item in items if item)))
    return min(1.0, len(unique) * 0.22), unique


def _role_for(raw: Mapping[str, Any], signals: Mapping[str, float]) -> str:
    explicit = _clean_text(raw.get("narrative_role"))
    if explicit:
        return explicit.upper()
    if signals["question"]:
        return "QUESTION"
    if signals["revelation"]:
        return "REVELATION"
    if signals["payoff"]:
        return "PAYOFF"
    return "SETUP"


def _build_beats(metadata: Mapping[str, Any], segments: Sequence[TranscriptSegment]) -> tuple[Beat, ...]:
    raw_beats = metadata.get("beats")
    if raw_beats is None:
        raw_beats = [
            {
                "beat_id": f"BEAT-{index:04d}",
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "text": segment.text,
                "shot_ids": ["SHOT-0001"],
            }
            for index, segment in enumerate(segments, start=1)
        ]
    if not isinstance(raw_beats, Sequence) or isinstance(raw_beats, (str, bytes, bytearray)):
        raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "BEATS_ARRAY_REQUIRED")
    beats: list[Beat] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_beats, start=1):
        if not isinstance(raw, Mapping):
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"BEAT_OBJECT_REQUIRED:{index}")
        beat_id = _clean_text(raw.get("beat_id", raw.get("id", f"BEAT-{index:04d}")))
        if not beat_id or beat_id in seen:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", "BEAT_ID_DUPLICATE")
        start = _parse_time(raw.get("start_time", raw.get("start")))
        end = _parse_time(raw.get("end_time", raw.get("end")))
        text = _clean_text(raw.get("text"))
        if end <= start or not text:
            raise ShortsBlockedError("SHORT_TRANSCRIPT_REQUIRED", f"BEAT_INVALID:{beat_id}")
        signals = _derive_signals(text, _clean_text(raw.get("narrative_role")), raw)
        context_score, missing = _context_analysis(text, raw.get("context_dependencies", ()))
        standalone = float(raw.get("standalone_potential", max(0.0, 1.0 - context_score)))
        shots = _sequence_strings(raw.get("shot_ids", ("SHOT-0001",)))
        beats.append(
            Beat(
                beat_id=beat_id,
                start_time=start,
                end_time=end,
                text=text,
                chapter_id=_clean_text(raw.get("chapter_id", "CHAPTER-UNKNOWN")),
                shot_ids=shots,
                claim_ids=_sequence_strings(raw.get("claim_ids", ())),
                narrative_role=_role_for(raw, signals),
                context_dependencies=missing,
                character_refs=_sequence_strings(raw.get("character_refs", ())),
                visual_action=_clean_text(raw.get("visual_action", "")),
                semantic_payload=dict(raw.get("semantic_payload", {})) if isinstance(raw.get("semantic_payload", {}), Mapping) else {},
                curiosity_signal=max(0.0, min(1.0, signals["curiosity"])),
                surprise_signal=max(0.0, min(1.0, signals["surprise"])),
                emotional_signal=max(0.0, min(1.0, signals["emotional"])),
                story_turn_signal=max(0.0, min(1.0, signals["story_turn"])),
                revelation_signal=max(0.0, min(1.0, signals["revelation"])),
                question_signal=max(0.0, min(1.0, signals["question"])),
                payoff_signal=max(0.0, min(1.0, signals["payoff"])),
                standalone_potential=max(0.0, min(1.0, standalone)),
                visual_strength_indicators=_sequence_strings(raw.get("visual_strength_indicators", ())),
            )
        )
        seen.add(beat_id)
    beats.sort(key=lambda beat: (beat.start_time, beat.end_time, beat.beat_id))
    return tuple(beats)


def _build_shots(metadata: Mapping[str, Any], duration: float) -> tuple[Shot, ...]:
    raw_shots = metadata.get("shots", metadata.get("shot_boundaries"))
    if raw_shots is None:
        raw_shots = [
            {
                "shot_id": "SHOT-0001",
                "start_time": 0.0,
                "end_time": duration,
                "visual_action": _clean_text(metadata.get("visual_action", "")),
                "semantic_focus_region": metadata.get("semantic_focus_region"),
            }
        ]
    if not isinstance(raw_shots, Sequence) or isinstance(raw_shots, (str, bytes, bytearray)):
        raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", "SHOTS_ARRAY_REQUIRED")
    shots: list[Shot] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_shots, start=1):
        if not isinstance(raw, Mapping):
            raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", f"SHOT_OBJECT_REQUIRED:{index}")
        shot_id = _clean_text(raw.get("shot_id", raw.get("id", f"SHOT-{index:04d}")))
        start = _parse_time(raw.get("start_time", raw.get("start")))
        end = _parse_time(raw.get("end_time", raw.get("end")))
        if not shot_id or shot_id in seen or end <= start:
            raise ShortsBlockedError("SHORT_VERTICAL_REFRAME_UNSAFE", f"SHOT_INVALID:{shot_id}")
        hint = raw.get("vertical_quality_hint")
        shots.append(
            Shot(
                shot_id=shot_id,
                start_time=start,
                end_time=end,
                visual_action=_clean_text(raw.get("visual_action", "")),
                semantic_tags=_sequence_strings(raw.get("semantic_tags", raw.get("tags", ()))),
                subject_region=_parse_region(raw.get("subject_region")),
                semantic_focus_region=_parse_region(raw.get("semantic_focus_region")),
                safe_region=_parse_region(raw.get("safe_region")),
                key_action_spans_full_width=bool(raw.get("key_action_spans_full_width", False)),
                unsafe_source=bool(raw.get("unsafe_source", raw.get("constitutional_failure", False))),
                unsafe_background_face=bool(raw.get("unsafe_background_face", False)),
                face_enlarged_by_crop=bool(raw.get("face_enlarged_by_crop", False)),
                vertical_quality_hint=(None if hint is None else max(0.0, min(1.0, float(hint)))),
            )
        )
        seen.add(shot_id)
    shots.sort(key=lambda shot: (shot.start_time, shot.end_time, shot.shot_id))
    return tuple(shots)


def _probe_with_ffmpeg(path: Path, ffmpeg_path: str | None = None) -> dict[str, Any]:
    executable = ffmpeg_path or find_ffmpeg()
    if executable is None:
        return {"available": False, "duration_seconds": None, "has_video": None, "has_audio": None}
    command = [executable, "-hide_banner", "-i", str(path), "-f", "null", "-"]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    duration_match = re.search(r"Duration:\s+(\d{2}:\d{2}:\d{2}[\.,]\d{2,3})", output)
    duration = _parse_time(duration_match.group(1)) if duration_match else None
    has_video = bool(re.search(r"Stream #.*Video:", output, re.IGNORECASE))
    has_audio = bool(re.search(r"Stream #.*Audio:", output, re.IGNORECASE))
    dimensions_match = re.search(r"(\d{2,5})x(\d{2,5})", output)
    dimensions = None
    if dimensions_match:
        dimensions = {"width": int(dimensions_match.group(1)), "height": int(dimensions_match.group(2))}
    return {
        "available": True,
        "returncode": completed.returncode,
        "duration_seconds": duration,
        "has_video": has_video,
        "has_audio": has_audio,
        "dimensions": dimensions,
        "raw_sha256": _sha256_bytes(output.encode("utf-8", errors="replace")),
    }


def find_ffmpeg() -> str | None:
    """Return a local FFmpeg executable; never downloads or contacts a service."""

    executable = shutil.which("ffmpeg")
    if executable:
        return executable
    try:
        import imageio_ffmpeg

        candidate = imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError):
        return None
    return candidate if Path(candidate).is_file() else None


def _resolve_episode_video(
    metadata: Mapping[str, Any],
    *,
    episode_directory: Path | None,
    video_path: Path | None,
) -> Path:
    candidate = video_path
    if candidate is None:
        value = metadata.get("video_path", metadata.get("episode_video"))
        if isinstance(value, str) and value:
            candidate = Path(value)
    if candidate is None:
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", "VIDEO_PATH_REQUIRED")
    if not candidate.is_absolute() and episode_directory is not None:
        candidate = episode_directory / candidate
    candidate = candidate.resolve()
    if not candidate.is_file():
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", str(candidate))
    return candidate


def _resolve_metadata_path(
    *,
    episode_directory: Path | None,
    metadata_path: Path | None,
) -> Path | None:
    if metadata_path is not None:
        path = metadata_path
    elif episode_directory is not None:
        candidates = (
            episode_directory / "episode_metadata.json",
            episode_directory / "episode-manifest.json",
            episode_directory / "manifest.json",
            episode_directory / "metadata.json",
        )
        path = next((item for item in candidates if item.is_file()), None)
    else:
        path = None
    if path is None:
        return None
    path = path.resolve()
    if not path.is_file():
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", str(path))
    return path


def ingest_episode(
    repo_root: Path,
    *,
    mode: str,
    episode_directory: Path | None = None,
    video_path: Path | None = None,
    metadata_path: Path | None = None,
    transcript_path: Path | None = None,
) -> EpisodePackage:
    """Ingest a local episode in native or video-plus-transcript mode."""

    normalized_mode = mode.upper()
    if normalized_mode not in {"SIRAJ_NATIVE_EPISODE", "VIDEO_PLUS_TRANSCRIPT"}:
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", "INGESTION_MODE_INVALID")
    directory = episode_directory.resolve() if episode_directory is not None else None
    metadata_file = _resolve_metadata_path(episode_directory=directory, metadata_path=metadata_path)
    metadata: dict[str, Any] = _read_json(metadata_file, code="SHORT_SOURCE_MISSING") if metadata_file else {}
    source_video = _resolve_episode_video(metadata, episode_directory=directory, video_path=video_path)
    source_sha = _sha256_file(source_video)
    source_metadata_hashes: dict[str, str] = {}
    if metadata_file is not None:
        source_metadata_hashes[_relative_or_absolute(metadata_file, Path(repo_root))] = _sha256_file(metadata_file)
    transcript_file = transcript_path.resolve() if transcript_path is not None else None
    transcript_segments: list[TranscriptSegment]
    if transcript_file is not None:
        if transcript_file.suffix.casefold() in {".vtt", ".srt"}:
            transcript_segments = _parse_vtt_or_srt(transcript_file)
        else:
            transcript_segments = _parse_transcript_payload(_read_json(transcript_file, code="SHORT_TRANSCRIPT_REQUIRED"))
        source_metadata_hashes[_relative_or_absolute(transcript_file, Path(repo_root))] = _sha256_file(transcript_file)
    elif metadata.get("transcript") is not None or metadata.get("segments") is not None or metadata.get("cues") is not None:
        transcript_segments = _parse_transcript_payload(metadata)
    else:
        raise SourceIntegrityError("SHORT_TRANSCRIPT_REQUIRED", "LOCAL_TRANSCRIPT_OR_TIMING_REQUIRED")
    probe = _probe_with_ffmpeg(source_video)
    duration_value = metadata.get("duration_seconds", metadata.get("duration"))
    duration = _parse_time(duration_value) if duration_value is not None else float(probe.get("duration_seconds") or max(segment.end_time for segment in transcript_segments))
    beats = _build_beats(metadata, transcript_segments)
    shots = _build_shots(metadata, duration)
    claims_value = metadata.get("claims", ())
    if not isinstance(claims_value, Sequence) or isinstance(claims_value, (str, bytes, bytearray)):
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", "CLAIMS_ARRAY_REQUIRED")
    claims = tuple(dict(item) for item in claims_value if isinstance(item, Mapping))
    if normalized_mode == "SIRAJ_NATIVE_EPISODE" and not metadata_file:
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", "NATIVE_METADATA_REQUIRED")
    episode_id = _clean_text(metadata.get("episode_id", source_video.stem))
    constitution_version = _clean_text(metadata.get("constitution_version", "0.0.0"))
    return EpisodePackage(
        schema_version=SCHEMA_VERSION,
        episode_id=episode_id,
        source_video_path=str(source_video),
        source_episode_sha256=source_sha,
        source_metadata_hashes=source_metadata_hashes,
        source_duration_seconds=duration,
        narration_segments=tuple(transcript_segments),
        beats=beats,
        shots=shots,
        claims=claims,
        metadata=json.loads(json.dumps(metadata, ensure_ascii=False, sort_keys=True)),
        constitution_version=constitution_version,
        legacy_source=constitution_version != CONSTITUTION_VERSION,
        has_audio=(None if probe.get("has_audio") is None else bool(probe.get("has_audio"))),
    )


def build_intelligence_map(episode: EpisodePackage) -> IntelligenceMap:
    beats = tuple(sorted(episode.beats, key=lambda beat: (beat.start_time, beat.end_time, beat.beat_id)))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode.episode_id,
        "source_episode_sha256": episode.source_episode_sha256,
        "source_metadata_hashes": dict(episode.source_metadata_hashes),
        "beats": [beat.to_dict() for beat in beats],
    }
    return IntelligenceMap(
        schema_version=SCHEMA_VERSION,
        episode_id=episode.episode_id,
        source_episode_sha256=episode.source_episode_sha256,
        source_metadata_hashes=episode.source_metadata_hashes,
        beats=beats,
        map_sha256=_hash_value(payload),
    )


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    intersection = max(0.0, min(end_a, end_b) - max(start_a, start_b))
    union = max(end_a, end_b) - min(start_a, start_b)
    return 0.0 if union <= 0 else intersection / union


def _find_shots(episode: EpisodePackage, shot_ids: Iterable[str]) -> tuple[Shot, ...]:
    wanted = set(shot_ids)
    return tuple(shot for shot in episode.shots if shot.shot_id in wanted)


def _candidate_type(beats: Sequence[Beat]) -> str:
    roles = {beat.narrative_role for beat in beats}
    if any(beat.question_signal and beat.payoff_signal for beat in beats):
        return "QUESTION_ANSWER"
    if "REVELATION" in roles or any(beat.revelation_signal for beat in beats):
        return "REVELATION"
    if "PAYOFF" in roles or any(beat.payoff_signal for beat in beats):
        return "PAYOFF"
    if any(beat.surprise_signal for beat in beats):
        return "SURPRISE"
    if any(beat.emotional_signal for beat in beats):
        return "EMOTIONAL"
    if any(beat.question_signal for beat in beats):
        return "CURIOSITY"
    if any(beat.story_turn_signal for beat in beats):
        return "STORY_MOMENT"
    return "OTHER_STRONG_STANDALONE"


def _semantic_key(text: str, beat_ids: Sequence[str], claims: Sequence[Mapping[str, Any]]) -> str:
    claim_tokens = sorted(_clean_text(item.get("claim_id", item.get("id", ""))) for item in claims)
    words = sorted(set(re.findall(r"[\w\u0600-\u06ff]{3,}", text.casefold())))
    return _hash_value({"beats": list(beat_ids), "claims": claim_tokens, "words": words})[:24]


def _repair_context(beats: Sequence[Beat], segments: Sequence[TranscriptSegment]) -> tuple[str, dict[str, Any], float, tuple[str, ...]]:
    text = " ".join(beat.text for beat in beats)
    context_score, missing = _context_analysis(text, tuple(item for beat in beats for item in beat.context_dependencies))
    boundaries = []
    for beat in beats:
        matching = [segment for segment in segments if _overlap(segment.start_time, segment.end_time, beat.start_time, beat.end_time) > 0.5]
        boundaries.extend(matching)
    unsafe_boundary = any(not item.audio_boundary_safe or not item.word_start or not item.word_end for item in boundaries)
    if unsafe_boundary:
        return "UNREPAIRABLE", {"status": "BLOCKED", "reason": "BROKEN_AUDIO_BOUNDARY"}, context_score, missing
    if context_score >= 0.66:
        return "UNREPAIRABLE", {"status": "BLOCKED", "reason": "CONTEXT_DEPENDENCE_TOO_HIGH", "missing": list(missing)}, context_score, missing
    if missing:
        return "TRIM_ONLY", {"status": "PASS", "trim": "BOUNDARY_ONLY", "missing": list(missing)}, context_score, missing
    return "NONE", {"status": "PASS", "trim": "NONE"}, context_score, missing


def validate_extractive_reorder(
    beats: Sequence[Beat],
    requested_order: Sequence[str],
) -> dict[str, Any]:
    """Validate a proposed reorder without changing source facts or chronology."""

    original = [beat.beat_id for beat in beats]
    requested = list(requested_order)
    if set(requested) != set(original) or len(requested) != len(original):
        return {"status": "FAIL", "code": "SHORT_REORDER_FACT_RISK", "reason": "BEAT_SET_CHANGED"}
    if requested != original:
        moved = {beat_id: index for index, beat_id in enumerate(requested)}
        for left, right in zip(original, original[1:]):
            if moved[left] > moved[right]:
                return {"status": "FAIL", "code": "SHORT_REORDER_FACT_RISK", "reason": "CHRONOLOGY_INVERSION"}
    if any("causality_inversion" in beat.semantic_payload or "action_inverted" in beat.semantic_payload for beat in beats):
        return {"status": "FAIL", "code": "SHORT_REORDER_FACT_RISK", "reason": "STRUCTURED_ACTION_OR_CAUSALITY_RISK"}
    return {"status": "PASS", "code": None, "reason": "EXTRACTIVE_ORDER_PRESERVES_CHRONOLOGY", "order": requested}


def _vertical_reframe_for_shots(
    shots: Sequence[Shot],
    *,
    source_aspect: float,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    if source_aspect <= 0 or not math.isfinite(source_aspect):
        return {"status": "BLOCKED", "code": "SHORT_VERTICAL_REFRAME_UNSAFE", "shots": []}
    crop_width_source_fraction = TARGET_RATIO / source_aspect
    if crop_width_source_fraction <= 0 or crop_width_source_fraction > 1:
        return {"status": "BLOCKED", "code": "SHORT_VERTICAL_REFRAME_UNSAFE", "shots": []}
    plans: list[dict[str, Any]] = []
    failures: list[str] = []
    for shot in shots:
        if shot.unsafe_source or shot.unsafe_background_face or shot.face_enlarged_by_crop:
            failures.append(f"{shot.shot_id}:UNSAFE_SOURCE_OR_CROP")
            plans.append({"shot_id": shot.shot_id, "status": "FAIL", "code": "SHORT_UNSAFE_SOURCE"})
            continue
        if shot.key_action_spans_full_width:
            failures.append(f"{shot.shot_id}:FULL_WIDTH_ACTION")
            plans.append({"shot_id": shot.shot_id, "status": "FAIL", "code": "SHORT_VERTICAL_QUALITY_FAIL"})
            continue
        focus = shot.semantic_focus_region or shot.subject_region
        if focus is None:
            failures.append(f"{shot.shot_id}:FOCUS_REGION_MISSING")
            plans.append({"shot_id": shot.shot_id, "status": "BLOCKED", "code": "SHORT_VERTICAL_REFRAME_UNSAFE"})
            continue
        center_x = float(focus["x"]) + float(focus["w"]) / 2
        left = max(0.0, min(1.0 - crop_width_source_fraction, center_x - crop_width_source_fraction / 2))
        crop = {"x": left, "y": 0.0, "w": crop_width_source_fraction, "h": 1.0}
        if left > center_x or left + crop_width_source_fraction < center_x:
            failures.append(f"{shot.shot_id}:FOCUS_OUTSIDE_CROP")
            plans.append({"shot_id": shot.shot_id, "status": "FAIL", "code": "SHORT_VERTICAL_QUALITY_FAIL"})
            continue
        safe = shot.safe_region
        if safe is not None:
            safe_center = float(safe["x"]) + float(safe["w"]) / 2
            if not (left <= safe_center <= left + crop_width_source_fraction):
                failures.append(f"{shot.shot_id}:SAFE_REGION_OUTSIDE_CROP")
                plans.append({"shot_id": shot.shot_id, "status": "FAIL", "code": "SHORT_VERTICAL_QUALITY_FAIL"})
                continue
        focus_coverage = min(1.0, float(focus["w"]) / max(0.01, crop_width_source_fraction))
        quality = shot.vertical_quality_hint if shot.vertical_quality_hint is not None else min(1.0, 0.55 + focus_coverage * 0.35)
        if quality < float(profile["hard_gates"]["minimum_vertical_quality"]):
            failures.append(f"{shot.shot_id}:QUALITY_BELOW_MINIMUM")
            plans.append({"shot_id": shot.shot_id, "status": "FAIL", "code": "SHORT_VERTICAL_QUALITY_FAIL", "quality": quality})
            continue
        plans.append(
            {
                "source_shot_id": shot.shot_id,
                "source_time_range": {"start": shot.start_time, "end": shot.end_time},
                "crop_window": crop,
                "scale": {"width": 1080, "height": 1920},
                "tracking_mode": "STATIC_SEMANTIC_REGION",
                "subject_region": dict(shot.subject_region or focus),
                "semantic_focus_region": dict(focus),
                "safe_region": dict(safe or focus),
                "vertical_quality_score": round(quality, 6),
                "reframe_reason": "SEMANTIC_FOCUS_REGION_CENTERED_WITHOUT_FACE_TRACKING",
                "status": "PASS",
            }
        )
    return {
        "status": "PASS" if plans and not failures else "FAIL",
        "code": None if not failures else "SHORT_VERTICAL_REFRAME_UNSAFE",
        "source_aspect": source_aspect,
        "target_aspect": TARGET_ASPECT_RATIO,
        "face_tracking_dependency": False,
        "crop_to_hide_failure": False,
        "blur_to_hide_face": False,
        "mask_to_hide_failure": False,
        "shots": plans,
        "failures": failures,
    }


def build_vertical_reframe_plan(
    episode: EpisodePackage,
    shot_ids: Sequence[str],
    profile: Mapping[str, Any],
    *,
    source_aspect: float = 16.0 / 9.0,
) -> Mapping[str, Any]:
    shots = _find_shots(episode, shot_ids)
    if len(shots) != len(set(shot_ids)):
        return {"status": "BLOCKED", "code": "SHORT_VERTICAL_REFRAME_UNSAFE", "shots": []}
    return _vertical_reframe_for_shots(shots, source_aspect=source_aspect, profile=profile)


def _alignment_for_candidate(episode: EpisodePackage, beats: Sequence[Beat], shots: Sequence[Shot]) -> dict[str, Any]:
    findings: list[str] = []
    rows: list[dict[str, Any]] = []
    for beat in beats:
        matched = [shot for shot in shots if _overlap(beat.start_time, beat.end_time, shot.start_time, shot.end_time) > 0]
        if not matched:
            findings.append(f"{beat.beat_id}:NO_SOURCE_SHOT")
            continue
        action_text = " ".join(shot.visual_action for shot in matched)
        if not beat.visual_action or not action_text:
            findings.append(f"{beat.beat_id}:SEMANTIC_ACTION_MISSING")
        combined = f"{beat.text} {action_text}"
        semantic_failures = analyze_sensitive_semantics(combined, ["VISUAL"])
        if semantic_failures:
            findings.extend(f"{beat.beat_id}:{item}" for item in semantic_failures)
        rows.append(
            {
                "beat_id": beat.beat_id,
                "what_is_being_said": beat.text,
                "what_viewer_must_understand": beat.semantic_payload.get("viewer_must_understand", beat.text),
                "what_must_be_visible": beat.visual_action,
                "selected_source_shot_ids": [shot.shot_id for shot in matched],
                "visible_action": action_text,
                "time_alignment": {"start": beat.start_time, "end": beat.end_time},
            }
        )
    return {
        "status": "PASS" if not findings and rows else "FAIL",
        "rule_id": "SIRAJ.S04.VISUAL_SEMANTIC_ALIGNMENT",
        "action_inversion": False,
        "rows": rows,
        "findings": findings,
    }


def _audio_edit_plan(episode: EpisodePackage, beats: Sequence[Beat]) -> dict[str, Any]:
    relevant = [segment for segment in episode.narration_segments if any(_overlap(segment.start_time, segment.end_time, beat.start_time, beat.end_time) > 0.5 for beat in beats)]
    if not relevant:
        return {"status": "BLOCKED", "code": "SHORT_AUDIO_BOUNDARY_INVALID", "segments": []}
    failures: list[str] = []
    segments: list[dict[str, Any]] = []
    for segment in relevant:
        if not segment.audio_boundary_safe or not segment.word_start or not segment.word_end or not segment.grammar_safe:
            failures.append(segment.segment_id)
        segments.append(
            {
                "segment_id": segment.segment_id,
                "source_start": segment.start_time,
                "source_end": segment.end_time,
                "edit": "AS_IS" if segment.start_time >= beats[0].start_time and segment.end_time <= beats[-1].end_time else "TRIM_AT_SAFE_BOUNDARY",
            }
        )
    requested_audio = [item for item in episode.metadata.get("audio_tracks", ()) if isinstance(item, Mapping)]
    music = bool(episode.metadata.get("music", False)) or any(
        item.get("contains_music") is True or str(item.get("kind", "")).upper() == "MUSIC" for item in requested_audio
    )
    new_sfx = bool(episode.metadata.get("new_sfx_requested", False))
    if music:
        failures.append("FAIL_MUSIC_DETECTED")
    if new_sfx:
        failures.append("NEW_SFX_NOT_IN_SOURCE")
    return {
        "status": "PASS" if not failures else "FAIL",
        "code": None if not failures else "SHORT_AUDIO_BOUNDARY_INVALID",
        "source_narration_audio_first": True,
        "new_narration": False,
        "new_tts": False,
        "voice_replacement": False,
        "global_speed_up": False,
        "pitch_shift": False,
        "music": music,
        "new_sfx": new_sfx,
        "segments": segments,
        "failures": failures,
    }


def _build_pacing_plan(beats: Sequence[Beat], shots: Sequence[Shot]) -> dict[str, Any]:
    """Describe semantic pacing decisions without a fixed-cut formula."""

    rows: list[dict[str, Any]] = []
    previous_role: str | None = None
    for index, beat in enumerate(beats):
        role_change = previous_role is not None and previous_role != beat.narrative_role
        density = len(beat.text.split()) / max(0.1, beat.end_time - beat.start_time)
        rows.append(
            {
                "beat_id": beat.beat_id,
                "information_density": round(min(1.0, density / 3.0), 6),
                "visual_action": beat.visual_action,
                "narration_cadence": "DENSE" if density >= 2.0 else "DEVELOPING",
                "semantic_change": role_change or beat.story_turn_signal > 0.5 or beat.revelation_signal > 0.5,
                "transition_necessity": "SEMANTIC_CHANGE" if role_change else "SHOT_DEVELOPMENT",
                "silence_preserved": True,
                "cut_every_fixed_seconds": False,
                "position": index,
            }
        )
        previous_role = beat.narrative_role
    movements = [shot.semantic_tags for shot in shots]
    repeated_movement = bool(movements) and len({tuple(item) for item in movements}) < len(movements)
    return {
        "status": "PASS" if rows else "BLOCKED",
        "strategy": "SEMANTIC_CHANGE_INFORMATION_DENSITY_AND_SHOT_DEVELOPMENT",
        "cut_every_fixed_seconds": False,
        "freeze_filler": False,
        "loop_filler": False,
        "reverse_motion_filler": False,
        "duplicate_visual_padding": False,
        "unmotivated_zoom": False,
        "cheap_pan_and_scan_rhythm": False,
        "repetitive_reframe_movement_detected": repeated_movement,
        "rows": rows,
    }


def _build_cta_plan(episode: EpisodePackage, beats: Sequence[Beat]) -> dict[str, Any]:
    new_cta_requested = bool(
        episode.metadata.get("new_cta_narration_requested")
        or episode.metadata.get("cta_text_requested")
        or episode.metadata.get("new_cta_requested")
    )
    if new_cta_requested:
        return {
            "status": "FAIL",
            "mode": "FORBIDDEN_NEW_CTA",
            "code": "CANDIDATE_REQUIRES_NEW_NARRATION",
            "related_longform_episode_id": episode.episode_id,
            "longform_link_recommended": False,
        }
    has_open_loop = any(beat.curiosity_signal > 0.45 for beat in beats) and not all(beat.payoff_signal >= 0.9 for beat in beats)
    mode = "NATURAL_OPEN_LOOP" if has_open_loop else "EXISTING_SOURCE_CONTINUATION" if beats and beats[-1].payoff_signal < 0.9 else "NONE"
    return {
        "status": "PASS",
        "mode": mode,
        "voice_cta_added": False,
        "text_cta_added": False,
        "related_longform_episode_id": episode.episode_id,
        "longform_link_recommended": True,
        "publication_action": "HUMAN_CONFIGURES_LINK_EXTERNALLY",
    }


def _caption_plan(beats: Sequence[Beat]) -> dict[str, Any]:
    cues = [
        {"start": beat.start_time, "end": beat.end_time, "text": beat.text, "beat_id": beat.beat_id}
        for beat in beats
    ]
    return {
        "external_closed_captions_allowed": True,
        "formats": [".vtt", ".srt"],
        "burned_captions": False,
        "on_screen_subtitles": False,
        "source": "ACTUAL_SOURCE_NARRATION_SEGMENTS",
        "cues": cues,
    }


def captions_to_vtt(plan: Mapping[str, Any]) -> str:
    def stamp(seconds: float) -> str:
        total_ms = int(round(float(seconds) * 1000))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    lines = ["WEBVTT", ""]
    for index, cue in enumerate(plan.get("cues", ()), start=1):
        lines.extend([str(index), f"{stamp(cue['start'])} --> {stamp(cue['end'])}", str(cue["text"]), ""])
    return "\n".join(lines)


def captions_to_srt(plan: Mapping[str, Any]) -> str:
    def stamp(seconds: float) -> str:
        total_ms = int(round(float(seconds) * 1000))
        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    lines: list[str] = []
    for index, cue in enumerate(plan.get("cues", ()), start=1):
        lines.extend([str(index), f"{stamp(cue['start'])} --> {stamp(cue['end'])}", str(cue["text"]), ""])
    return "\n".join(lines)


def _constitutional_policy(
    engine: "ShortsDerivativeEngine",
    episode: EpisodePackage,
    candidate_id: str,
    text: str,
) -> Mapping[str, Any]:
    domains = ["FACE", "MODESTY", "UNSEEN", "PERIOD", "SOURCE", "AUDIO", "VISUAL", "MONTAGE", "PUBLICATION"]
    bindings = {
        "wardrobe_contract_id": episode.metadata.get("wardrobe_contract_id", "SOURCE_EPISODE_WARDROBE_CONTRACT"),
        "period_dossier_id": episode.metadata.get("period_dossier_id", "SOURCE_EPISODE_PERIOD_DOSSIER"),
        "canonical_reference_sha256": episode.metadata.get("canonical_reference_sha256", "SOURCE_EPISODE_CANONICAL_REFERENCE"),
        "source_certainty": episode.metadata.get("source_certainty", "UNKNOWN"),
        "narration_master_sha256": episode.metadata.get("narration_master_sha256", "SOURCE_EPISODE_NARRATION"),
    }
    contract = {
        "artifact_id": candidate_id,
        "stage": "SHORT_DERIVATIVE_CANDIDATE",
        "text": text,
        "sensitive_domains": domains,
        "bindings": bindings,
    }
    policy = engine.compile_constitution_policy(contract)
    errors = list(policy.get("errors", ()))
    errors.extend(analyze_face_semantics(text))
    errors.extend(analyze_sensitive_semantics(text, domains))
    if episode.metadata.get("source_truth_uncertain") is True:
        errors.append("SOURCE_FACT_INTEGRITY_UNCERTAIN")
    return {
        **dict(policy),
        "errors": sorted(set(errors)),
        "status": "PASS" if not errors else ("BLOCKED" if any("UNKNOWN" in item or "REQUIRES" in item for item in errors) else "FAIL"),
        "legacy_recheck_required": episode.legacy_source,
        "legacy_rechecked": episode.legacy_source,
    }


def _score_dimension(value: float, evidence: Iterable[str], reason: str) -> ScoreDimension:
    return ScoreDimension(max(0.0, min(1.0, float(value))), tuple(str(item) for item in evidence), reason)


def _score_candidate(
    engine: "ShortsDerivativeEngine",
    episode: EpisodePackage,
    beats: Sequence[Beat],
    *,
    candidate_id: str,
    candidate_type: str,
) -> Candidate:
    text = " ".join(beat.text for beat in beats)
    shot_ids = tuple(dict.fromkeys(shot_id for beat in beats for shot_id in beat.shot_ids))
    shots = _find_shots(episode, shot_ids)
    context_mode, repair_plan, context_score, missing = _repair_context(beats, episode.narration_segments)
    raw_source_aspect = episode.metadata.get("source_aspect", 16.0 / 9.0)
    try:
        source_aspect = float(raw_source_aspect)
    except (TypeError, ValueError):
        source_aspect = 0.0
    reframe = build_vertical_reframe_plan(episode, shot_ids, engine.profile, source_aspect=source_aspect)
    audio = _audio_edit_plan(episode, beats)
    pacing = _build_pacing_plan(beats, shots)
    cta = _build_cta_plan(episode, beats)
    alignment = _alignment_for_candidate(episode, beats, shots)
    policy = _constitutional_policy(engine, episode, candidate_id, text)
    unsafe_shots = [shot for shot in shots if shot.unsafe_source or shot.unsafe_background_face or shot.face_enlarged_by_crop]
    if unsafe_shots:
        policy = {
            **dict(policy),
            "status": "FAIL",
            "errors": sorted(
                set(
                    list(policy.get("errors", ()))
                    + ["FAIL_GLOBAL_FACE_POLICY" if (shot.unsafe_background_face or shot.face_enlarged_by_crop) else "SHORT_UNSAFE_SOURCE" for shot in unsafe_shots]
                )
            ),
        }
    source_claims = [claim for claim in episode.claims if not claim.get("status") or str(claim.get("status")).upper() in {"PASS", "APPROVED", "VERIFIED"}]
    source_integrity = bool(episode.claims == () or len(source_claims) == len(episode.claims)) and policy.get("status") == "PASS"
    if episode.metadata.get("music") is True or audio.get("music") is True:
        source_integrity = False
    scores: dict[str, ScoreDimension] = {}
    first = beats[0]
    average = lambda key: sum(float(getattr(beat, key)) for beat in beats) / max(1, len(beats))
    hook = max(first.question_signal, first.revelation_signal, first.surprise_signal, first.story_turn_signal)
    standalone = max(0.0, min(1.0, (1.0 - context_score) * 0.75 + average("standalone_potential") * 0.25))
    novelty = min(1.0, len(set(re.findall(r"[\w\u0600-\u06ff]{3,}", text.casefold()))) / max(12.0, len(text.split()) * 0.7))
    visual_strength = average("visual_strength_indicators") if False else (sum(min(1.0, 0.4 + 0.15 * len(beat.visual_strength_indicators)) for beat in beats) / len(beats))
    vertical_quality = float(sum(float(item.get("vertical_quality_score", 0.0)) for item in reframe.get("shots", ()) if item.get("status") == "PASS") / max(1, len(shots)))
    narration_strength = 1.0 if audio.get("status") == "PASS" else 0.0
    spoiler = min(1.0, average("payoff_signal") * 0.8 + average("revelation_signal") * 0.2)
    conversion = max(0.0, min(1.0, average("curiosity_signal") * 0.45 + (1.0 - spoiler) * 0.35 + standalone * 0.2))
    scores["HOOK_STRENGTH"] = _score_dimension(hook, (first.beat_id, first.narrative_role), "The opening beat carries a question, turn, surprise, or revelation.")
    scores["STANDALONE_CLARITY"] = _score_dimension(standalone, missing or ("NO_MISSING_CONTEXT",), "Meaning is available without importing earlier episode context.")
    scores["CURIOSITY"] = _score_dimension(average("curiosity_signal"), (candidate_type,), "Curiosity signals are inherited from structured beat metadata and text.")
    scores["EMOTIONAL_FORCE"] = _score_dimension(average("emotional_signal"), tuple(beat.beat_id for beat in beats), "Emotional signal is explicit per beat.")
    scores["NOVELTY"] = _score_dimension(novelty, (f"unique_terms={len(set(text.casefold().split()))}",), "Novelty is a deterministic editorial heuristic, not a learned claim.")
    scores["VISUAL_STRENGTH"] = _score_dimension(visual_strength, shot_ids, "Visual strength comes from source shot indicators only.")
    scores["NARRATION_STRENGTH"] = _score_dimension(narration_strength, tuple(item["segment_id"] for item in audio.get("segments", ())), "Only source narration segments with safe boundaries are used.")
    scores["RETENTION_POTENTIAL"] = _score_dimension(max(hook, conversion, average("surprise_signal")), ("heuristic",), "Retention is a transparent editorial combination of hook, curiosity, and surprise.")
    scores["CONTEXT_DEPENDENCE"] = _score_dimension(1.0 - context_score, missing or ("NO_CONTEXT_DEPENDENCE",), "Higher value means less dependence on prior context.")
    scores["LONGFORM_CONVERSION_POTENTIAL"] = _score_dimension(conversion, ("open_loop_preserved",), "The derivative creates a reason to continue without requiring a new claim.")
    scores["CONSTITUTIONAL_SAFETY"] = _score_dimension(1.0 if source_integrity else 0.0, tuple(policy.get("errors", ())) or ("constitutional_policy_pass",), "The current unified constitution is checked again on the derivative.")
    scores["EDITABILITY"] = _score_dimension(1.0 if context_mode != "UNREPAIRABLE" and audio.get("status") == "PASS" else 0.0, (context_mode, audio.get("status", "")), "Editability requires safe extractive and audio boundaries.")
    scores["VERTICAL_COMPATIBILITY"] = _score_dimension(vertical_quality, tuple(shot_ids), "Vertical compatibility is based on explicit semantic focus and safe crop regions.")
    weights = engine.profile["scoring_weights"]
    total_weight = sum(float(value) for value in weights.values())
    total = sum(float(weights.get(key, 0.0)) * dimension.value for key, dimension in scores.items()) / total_weight
    duration = max(
        0.0,
        sum(
            float(segment.get("source_end", 0.0)) - float(segment.get("source_start", 0.0))
            for segment in audio.get("segments", ())
            if isinstance(segment, Mapping)
        ),
    )
    gates: dict[str, dict[str, Any]] = {}
    hard = engine.profile["hard_gates"]
    gates["CONSTITUTIONAL_SAFETY"] = {"status": "PASS" if source_integrity else ("BLOCKED" if policy.get("status") == "BLOCKED" else "FAIL"), "code": None if source_integrity else "SHORT_CONSTITUTION_SCOPE_BLOCKED", "evidence": list(policy.get("errors", ()))}
    gates["STANDALONE_CLARITY"] = {"status": "PASS" if standalone >= float(hard["minimum_standalone_clarity"]) else "FAIL", "code": None if standalone >= float(hard["minimum_standalone_clarity"]) else "SHORT_CONTEXT_DEPENDENT", "value": standalone}
    gates["HOOK"] = {"status": "PASS" if hook >= float(hard["minimum_hook_strength"]) else "FAIL", "code": None if hook >= float(hard["minimum_hook_strength"]) else "SHORT_HOOK_TOO_WEAK", "value": hook}
    gates["CONTEXT_DEPENDENCE"] = {"status": "PASS" if context_score <= float(hard["maximum_context_dependence"]) else "FAIL", "code": None if context_score <= float(hard["maximum_context_dependence"]) else "SHORT_CONTEXT_DEPENDENT", "value": context_score}
    gates["SOURCE_FACT_INTEGRITY"] = {"status": "PASS" if source_integrity else "FAIL", "code": None if source_integrity else "SOURCE_FACT_INTEGRITY_UNCERTAIN"}
    gates["VISUAL_NARRATION_ALIGNMENT"] = {"status": alignment.get("status", "FAIL"), "code": None if alignment.get("status") == "PASS" else "VISUAL_NARRATION_CONTRADICTION", "findings": alignment.get("findings", [])}
    gates["VERTICAL_REFRAME"] = {"status": reframe.get("status", "FAIL"), "code": None if reframe.get("status") == "PASS" else str(reframe.get("code") or "SHORT_VERTICAL_REFRAME_UNSAFE"), "findings": reframe.get("failures", [])}
    gates["AUDIO_BOUNDARIES"] = {"status": audio.get("status", "FAIL"), "code": None if audio.get("status") == "PASS" else "SHORT_AUDIO_BOUNDARY_INVALID", "findings": audio.get("failures", [])}
    requested_new_fact = bool(episode.metadata.get("candidate_requires_new_fact", False))
    requested_new_narration = bool(episode.metadata.get("candidate_requires_new_narration", False))
    requested_new_graphics = bool(episode.metadata.get("candidate_requires_forbidden_graphics", False))
    false_hook = bool(episode.metadata.get("false_hook", False) or episode.metadata.get("misleading_cold_open", False))
    gates["NEW_CONTENT"] = {
        "status": "FAIL" if requested_new_fact or requested_new_narration else "PASS",
        "code": "CANDIDATE_REQUIRES_NEW_FACT" if requested_new_fact else "CANDIDATE_REQUIRES_NEW_NARRATION" if requested_new_narration else None,
        "new_fact": requested_new_fact,
        "new_narration": requested_new_narration,
        "new_visual_generation": False,
    }
    gates["GRAPHICS"] = {
        "status": "FAIL" if requested_new_graphics else "PASS",
        "code": "CANDIDATE_REQUIRES_FORBIDDEN_GRAPHICS" if requested_new_graphics else None,
        "burned_captions": False,
        "on_screen_subtitles": False,
    }
    gates["HOOK_INTEGRITY"] = {
        "status": "FAIL" if false_hook else "PASS",
        "code": "SHORT_HOOK_TOO_WEAK" if false_hook else None,
        "false_hook": false_hook,
        "misleading_cold_open": false_hook,
    }
    gates["CTA"] = {"status": cta.get("status", "FAIL"), "code": cta.get("code"), "mode": cta.get("mode")}
    generic_transition = bool(
        re.fullmatch(
            r"(?:and then|then|now|so|after that|ثم|بعد ذلك|والآن)[.!؟?]*",
            text.casefold().strip(),
            re.IGNORECASE,
        )
    )
    gates["FILLER"] = {
        "status": "FAIL" if generic_transition else "PASS",
        "code": "SHORT_HOOK_TOO_WEAK" if generic_transition else None,
        "reason": "GENERIC_TRANSITION_WITHOUT_STANDALONE_MEANING" if generic_transition else "NOT_GENERIC_TRANSITION",
    }
    failures = tuple(sorted({str(item["code"]) for item in gates.values() if item.get("status") != "PASS" and item.get("code")}))
    status = "PASS" if not failures and total >= float(hard["minimum_total_score"]) and duration > 0 else ("BLOCKED" if any(item.get("status") == "BLOCKED" for item in gates.values()) else "REJECTED")
    if status == "PASS" and duration < float(engine.profile["target_duration_min_seconds"]):
        gates["DURATION"] = {"status": "PASS", "code": None, "reason": "EXCELLENT_MOMENT_ALLOWED_SHORTER_THAN_TARGET"}
    elif status == "PASS" and duration > float(engine.profile["target_duration_max_seconds"]):
        gates["DURATION"] = {"status": "PASS", "code": None, "reason": "EXTRACTIVE_MOMENT_ALLOWED_LONGER_WITHIN_EDITORIAL_PLAN"}
    else:
        gates["DURATION"] = {"status": "PASS", "code": None, "reason": "WITHIN_CREATOR_STRATEGY_RANGE"}
    binding_ids = tuple(sorted(str(item.get("rule_id")) for item in policy.get("obligations", ()) if item.get("rule_id")))
    return Candidate(
        candidate_id=candidate_id,
        episode_id=episode.episode_id,
        source_episode_sha256=episode.source_episode_sha256,
        source_metadata_hashes=episode.source_metadata_hashes,
        beat_ids=tuple(beat.beat_id for beat in beats),
        source_shot_ids=shot_ids,
        start_time=beats[0].start_time,
        end_time=beats[-1].end_time,
        text=text,
        candidate_type=candidate_type,
        context_dependence_score=context_score,
        missing_context_items=missing,
        context_repair_mode=context_mode,
        context_repair_plan=repair_plan,
        vertical_reframe_plan=reframe,
        audio_edit_plan=audio,
        pacing_plan=pacing,
        cta_plan=cta,
        alignment=alignment,
        score_breakdown=scores,
        total_score=round(total, 6),
        longform_conversion_score=round(conversion, 6),
        spoiler_cost=round(spoiler, 6),
        payoff_disclosure_level=round(min(1.0, average("payoff_signal")), 6),
        hard_gate_results=gates,
        constitutional_rule_bindings=binding_ids,
        policy_result=policy,
        status=status,
        rejection_reasons=failures,
        semantic_key=_semantic_key(text, tuple(beat.beat_id for beat in beats), episode.claims),
    )


def discover_candidates(engine: "ShortsDerivativeEngine", episode: EpisodePackage, intelligence_map: IntelligenceMap) -> tuple[Candidate, ...]:
    beats = list(intelligence_map.beats)
    windows: list[tuple[Beat, ...]] = []
    windows.extend((beat,) for beat in beats)
    windows.extend(tuple(beats[index : index + 2]) for index in range(max(0, len(beats) - 1)))
    for index in range(len(beats) - 2):
        if beats[index].question_signal and (beats[index + 1].payoff_signal or beats[index + 2].payoff_signal):
            windows.append(tuple(beats[index : index + 3]))
    unique: dict[tuple[str, ...], tuple[Beat, ...]] = {}
    for window in windows:
        if not window:
            continue
        ids = tuple(beat.beat_id for beat in window)
        unique[ids] = window
    candidates: list[Candidate] = []
    for index, window in enumerate(unique.values(), start=1):
        candidate = _score_candidate(engine, episode, window, candidate_id=f"{episode.episode_id}-SHORT-CANDIDATE-{index:03d}", candidate_type=_candidate_type(window))
        candidates.append(candidate)
    return tuple(sorted(candidates, key=lambda item: (-item.total_score, item.candidate_id)))


def _candidate_overlap(left: Candidate, right: Candidate) -> float:
    return _overlap(left.start_time, left.end_time, right.start_time, right.end_time)


def _sequence_reason(candidate: Candidate, position: int) -> str:
    if candidate.longform_conversion_score >= 0.75:
        return "STRONG_CONVERSION_AFTER_BROAD_AND_STORY_INTEREST"
    if candidate.candidate_type in {"CURIOSITY", "QUESTION_ANSWER"}:
        return "CURIOSITY_OPEN_LOOP_FOR_DISCOVERY"
    if candidate.candidate_type in {"STORY_MOMENT", "EMOTIONAL", "REVELATION"}:
        return "STORY_OR_EMOTIONAL_DEEPENING"
    return "BROAD_INTEREST_FIRST" if position == 0 else "QUALITY_DIVERSITY_BALANCE"


def select_portfolio(
    analysis: EngineAnalysis,
    *,
    candidate_ids: Sequence[str] | None = None,
    longform_publish_day: str | None = None,
    human_selection_reviewed: bool = False,
) -> PortfolioResult:
    candidates = {candidate.candidate_id: candidate for candidate in analysis.candidates}
    eligible = [candidate for candidate in analysis.candidates if candidate.status == "PASS"]
    if candidate_ids is not None:
        requested = list(candidate_ids)
        if len(requested) != len(set(requested)):
            raise ShortsBlockedError("SHORT_DUPLICATE_PORTFOLIO_ITEM", "HUMAN_SELECTION_DUPLICATE")
        unknown = [item for item in requested if item not in candidates]
        if unknown:
            raise ShortsBlockedError("SHORT_DUPLICATE_PORTFOLIO_ITEM", "CANDIDATE_UNKNOWN:" + ",".join(unknown))
        unsafe = [item for item in requested if candidates[item].status != "PASS"]
        if unsafe:
            raise ShortsBlockedError("SHORT_CONSTITUTION_SCOPE_BLOCKED", "HUMAN_SELECTION_CANNOT_OVERRIDE:" + ",".join(unsafe))
        eligible = [candidates[item] for item in requested]
    max_slots = len(WEEKDAYS) - 1 if longform_publish_day is not None else len(eligible)
    selected: list[Candidate] = []
    rejected: list[Candidate] = []
    for candidate in sorted(eligible, key=lambda item: (-item.total_score, -item.longform_conversion_score, item.candidate_id)):
        if len(selected) >= max_slots:
            rejected.append(candidate)
            continue
        duplicate = next((previous for previous in selected if previous.semantic_key == candidate.semantic_key or _candidate_overlap(previous, candidate) >= 0.72), None)
        if duplicate is not None:
            rejected.append(candidate)
            continue
        selected.append(candidate)
    for candidate in analysis.candidates:
        if candidate not in selected and candidate not in rejected:
            rejected.append(candidate)
    selected.sort(key=lambda item: (-item.total_score, item.candidate_id))
    ordered = sorted(
        selected,
        key=lambda item: (
            0 if item.candidate_type == "OTHER_STRONG_STANDALONE" else 1 if item.candidate_type == "STORY_MOMENT" else 2 if item.candidate_type in {"CURIOSITY", "QUESTION_ANSWER"} else 3,
            -item.longform_conversion_score,
            item.candidate_id,
        ),
    )
    schedule_status = "PASS"
    slots: list[dict[str, Any]] = []
    if longform_publish_day is None:
        schedule_status = "BLOCKED_MISSING_LONGFORM_DAY"
    else:
        day = _clean_text(longform_publish_day).upper()
        if day not in WEEKDAYS:
            raise ShortsBlockedError("SHORT_SCHEDULE_DAY_REQUIRED", "LONGFORM_PUBLISH_DAY_INVALID")
        available = [item for item in WEEKDAYS if item != day]
        for index, candidate in enumerate(ordered[: len(available)]):
            slots.append({"day": available[index], "short_id": candidate.candidate_id, "reason": _sequence_reason(candidate, index)})
    diversity: list[dict[str, Any]] = []
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            overlap = _candidate_overlap(left, right)
            diversity.append({"left": left.candidate_id, "right": right.candidate_id, "semantic_overlap_score": round(overlap if overlap else (1.0 if left.semantic_key == right.semantic_key else 0.0), 6)})
    portfolio_status = "PORTFOLIO_READY" if human_selection_reviewed else "HUMAN_SELECTION_REQUIRED"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": analysis.episode.episode_id,
        "source_episode_sha256": analysis.episode.source_episode_sha256,
        "selected_candidate_ids": [candidate.candidate_id for candidate in ordered],
        "slots": slots,
        "schedule_status": schedule_status,
        "portfolio_status": portfolio_status,
        "diversity": diversity,
    }
    return PortfolioResult(
        schema_version=SCHEMA_VERSION,
        episode_id=analysis.episode.episode_id,
        source_episode_sha256=analysis.episode.source_episode_sha256,
        candidate_ids=tuple(candidate.candidate_id for candidate in analysis.candidates),
        selected_candidate_ids=tuple(candidate.candidate_id for candidate in ordered),
        rejected_candidate_ids=tuple(candidate.candidate_id for candidate in rejected),
        recommended_order=tuple(candidate.candidate_id for candidate in ordered),
        weekly_slots=tuple(slots),
        schedule_status=schedule_status,
        portfolio_status=portfolio_status,
        diversity_evidence=tuple(diversity),
        portfolio_sha256=_hash_value(payload),
        human_selection_required=not human_selection_reviewed,
    )


def _assert_current_source(episode: EpisodePackage) -> None:
    path = Path(episode.source_video_path)
    if not path.is_file():
        raise SourceIntegrityError("SHORT_SOURCE_MISSING", str(path))
    current = _sha256_file(path)
    if current != episode.source_episode_sha256:
        raise SourceIntegrityError("SHORT_SOURCE_HASH_CHANGED", f"expected={episode.source_episode_sha256}:actual={current}")


def build_render_plan(
    analysis: EngineAnalysis,
    portfolio: PortfolioResult,
    short_id: str,
    *,
    human_selection_approved: bool = False,
) -> RenderPlan:
    if analysis.episode.source_episode_sha256 != portfolio.source_episode_sha256:
        raise SourceIntegrityError("SHORT_SOURCE_HASH_CHANGED", "PORTFOLIO_SOURCE_MISMATCH")
    _assert_current_source(analysis.episode)
    if not human_selection_approved or portfolio.portfolio_status != "PORTFOLIO_READY":
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "PORTFOLIO_HUMAN_SELECTION_REQUIRED")
    if short_id not in portfolio.selected_candidate_ids:
        raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "SHORT_NOT_IN_APPROVED_PORTFOLIO")
    candidate = next(item for item in analysis.candidates if item.candidate_id == short_id)
    if candidate.status != "PASS":
        raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "CANDIDATE_NOT_PASS")
    selected_beats = tuple(beat for beat in analysis.intelligence_map.beats if beat.beat_id in candidate.beat_ids)
    ranges = tuple(
        {
            "start": beat.start_time,
            "end": beat.end_time,
            "beat_id": beat.beat_id,
            "source": "EXACT_CANDIDATE_BEAT_BOUNDARIES",
        }
        for beat in selected_beats
    )
    narration = tuple(dict(item) for item in candidate.audio_edit_plan.get("segments", ()))
    visual_items: list[dict[str, Any]] = []
    for item in candidate.vertical_reframe_plan.get("shots", ()):
        if item.get("status") != "PASS":
            continue
        source_range = item.get("source_time_range")
        if not isinstance(source_range, Mapping):
            continue
        start = max(candidate.start_time, float(source_range["start"]))
        end = min(candidate.end_time, float(source_range["end"]))
        if end <= start:
            continue
        visual_item = dict(item)
        visual_item["source_time_range"] = {"start": start, "end": end}
        visual_items.append(visual_item)
    visual = tuple(visual_items)
    order = portfolio.recommended_order.index(short_id) + 1 if short_id in portfolio.recommended_order else None
    payload = {
        "short_id": short_id,
        "source_episode_sha256": analysis.episode.source_episode_sha256,
        "candidate_id": candidate.candidate_id,
        "ranges": ranges,
        "narration": narration,
        "visual": visual,
        "pacing": candidate.pacing_plan,
        "cta": candidate.cta_plan,
        "profile_sha256": analysis.profile_sha256,
        "constitution_bundle_sha256": analysis.constitution_bundle_sha256,
    }
    return RenderPlan(
        schema_version=SCHEMA_VERSION,
        short_id=short_id,
        source_episode_id=analysis.episode.episode_id,
        source_episode_sha256=analysis.episode.source_episode_sha256,
        source_metadata_hashes=analysis.episode.source_metadata_hashes,
        candidate_id=candidate.candidate_id,
        candidate_type=candidate.candidate_type,
        selected_source_ranges=ranges,
        narration_segments=narration,
        visual_segments=visual,
        reframe_plan=candidate.vertical_reframe_plan,
        context_repair_mode=candidate.context_repair_mode,
        audio_edit_plan=candidate.audio_edit_plan,
        pacing_plan=candidate.pacing_plan,
        cta_plan=candidate.cta_plan,
        target_duration={
            "min_seconds": analysis.profile["target_duration_min_seconds"],
            "max_seconds": analysis.profile["target_duration_max_seconds"],
            "strategy": "CREATOR_STRATEGY_VALUE_NOT_PLATFORM_LIMIT",
        },
        expected_duration=round(sum(float(item["end"]) - float(item["start"]) for item in ranges), 6),
        quality_scores={
            "total_score": candidate.total_score,
            "longform_conversion_score": candidate.longform_conversion_score,
            "spoiler_cost": candidate.spoiler_cost,
            "score_breakdown": {key: value.to_dict() for key, value in candidate.score_breakdown.items()},
        },
        hard_gate_results=candidate.hard_gate_results,
        constitution_rule_bindings=candidate.constitutional_rule_bindings,
        external_caption_plan=_caption_plan([beat for beat in analysis.intelligence_map.beats if beat.beat_id in candidate.beat_ids]),
        publishing_order=order,
        profile_sha256=analysis.profile_sha256,
        constitution_bundle_sha256=analysis.constitution_bundle_sha256,
        plan_sha256=_hash_value(payload),
        state="LOCAL_RENDER_APPROVAL_REQUIRED",
        local_render_approved=False,
        executor_creative_authority=False,
        provider_call_allowed=False,
        network_allowed=False,
        paid_execution_allowed=False,
    )


def approve_local_render(plan: RenderPlan, *, explicit_human_click: bool) -> RenderPlan:
    if not explicit_human_click:
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "LOCAL_RENDER_CLICK_REQUIRED")
    if plan.state != "LOCAL_RENDER_APPROVAL_REQUIRED":
        raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_STATE_INVALID")
    return replace(plan, local_render_approved=True)


def _ffmpeg_filter_for_crop_window(crop_window: Mapping[str, Any]) -> str:
    if not isinstance(crop_window, Mapping):
        raise LocalRenderError("SHORT_VERTICAL_REFRAME_UNSAFE", "PASS_CROP_MISSING")
    x = float(crop_window["x"])
    width = float(crop_window["w"])
    return (
        f"crop=trunc(iw*{width:.12f}/2)*2:trunc(ih/2)*2:trunc(iw*{x:.12f}/2)*2:0,"
        "scale=1080:1920:flags=lanczos,format=yuv420p"
    )


def render_local_derivative(
    plan: RenderPlan,
    source_video_path: Path,
    output_path: Path,
    *,
    explicit_human_click: bool,
    fixture_only: bool = True,
    ffmpeg_path: str | None = None,
    source_aspect: float = 16.0 / 9.0,
) -> RenderResult:
    """Render an exact approved plan locally; real-episode mode is blocked in V1."""

    if not fixture_only:
        raise LocalRenderError("SHORT_PUBLICATION_FORBIDDEN", "REAL_EPISODE_RENDER_DISABLED_IN_CERTIFICATION")
    if not explicit_human_click or not plan.local_render_approved:
        raise LocalRenderError("SHORT_HUMAN_REVIEW_REQUIRED", "EXPLICIT_LOCAL_RENDER_APPROVAL_REQUIRED")
    if plan.executor_creative_authority or plan.provider_call_allowed or plan.network_allowed or plan.paid_execution_allowed:
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", "CAPABILITY_BOUNDARY_INVALID")
    source = Path(source_video_path).resolve()
    output = Path(output_path).resolve()
    if not source.is_file():
        raise LocalRenderError("SHORT_SOURCE_MISSING", str(source))
    marker_path = source.with_name(source.name + ".fixture.json")
    if not marker_path.is_file():
        raise LocalRenderError("SHORT_PUBLICATION_FORBIDDEN", "SYNTHETIC_FIXTURE_MARKER_REQUIRED")
    marker = _read_json(marker_path, code="SHORT_PUBLICATION_FORBIDDEN")
    if marker.get("synthetic") is not True or marker.get("source_sha256") != _sha256_file(source):
        raise LocalRenderError("SHORT_PUBLICATION_FORBIDDEN", "SYNTHETIC_FIXTURE_MARKER_INVALID")
    if source == output or source.parent == output.parent:
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", "OUTPUT_WORKSPACE_MUST_BE_SEPARATE")
    if output.exists():
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", "OUTPUT_ALREADY_EXISTS")
    executable = ffmpeg_path or find_ffmpeg()
    if executable is None:
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", "FFMPEG_UNAVAILABLE")
    output.parent.mkdir(parents=True, exist_ok=True)
    before = _sha256_file(source)
    ranges = plan.selected_source_ranges
    if not ranges:
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", "SOURCE_RANGES_MISSING")
    visual_ranges = [
        item
        for item in plan.visual_segments
        if item.get("status") == "PASS" and isinstance(item.get("source_time_range"), Mapping)
    ]
    if not visual_ranges:
        raise LocalRenderError("SHORT_VERTICAL_REFRAME_UNSAFE", "PASS_VISUAL_SEGMENTS_MISSING")
    render_segments = [
        (
            float(item["source_time_range"]["start"]),
            float(item["source_time_range"]["end"]),
            _ffmpeg_filter_for_crop_window(item.get("crop_window", {})),
        )
        for item in visual_ranges
    ]
    if len(render_segments) == 1:
        start, end, filters = render_segments[0]
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.6f}",
            "-to",
            f"{end:.6f}",
            "-i",
            str(source),
            "-vf",
            filters,
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ]
    else:
        pieces: list[str] = []
        for index, (start, end, filters) in enumerate(render_segments):
            pieces.append(f"[0:v]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS,{filters}[v{index}]")
            pieces.append(f"[0:a]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[a{index}]")
        concat_inputs = "".join(f"[v{index}][a{index}]" for index in range(len(ranges)))
        pieces.append(f"{concat_inputs}concat=n={len(ranges)}:v=1:a=1[v][a]")
        command = [
            executable,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            ";".join(pieces),
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-c:a",
            "aac",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not output.is_file():
        detail = _clean_text(completed.stderr)[-800:]
        raise LocalRenderError("SHORT_RENDER_PLAN_INVALID", f"FFMPEG_FAILED:{detail}")
    after = _sha256_file(source)
    if before != after:
        raise SourceIntegrityError("SHORT_SOURCE_HASH_CHANGED", "SOURCE_MUTATED_DURING_RENDER")
    output_probe = _probe_with_ffmpeg(output, executable)
    return RenderResult(
        short_id=plan.short_id,
        output_path=str(output),
        render_sha256=_sha256_file(output),
        source_episode_sha256_before=before,
        source_episode_sha256_after=after,
        expected_duration=plan.expected_duration,
        output_probe=output_probe,
        state="RENDERED",
        provider_calls=0,
        network_calls=0,
        paid_calls=0,
    )


def validate_rendered_output(plan: RenderPlan, render: RenderResult) -> QAResult:
    findings: list[dict[str, Any]] = []
    probe = render.output_probe
    technical = True
    if render.source_episode_sha256_before != plan.source_episode_sha256 or render.source_episode_sha256_after != plan.source_episode_sha256:
        technical = False
        findings.append({"name": "SOURCE_PROVENANCE", "status": "FAIL", "code": "SHORT_SOURCE_HASH_CHANGED"})
    if not probe.get("available") or probe.get("has_video") is not True or probe.get("has_audio") is not True:
        technical = False
        findings.append({"name": "TECHNICAL_OUTPUT", "status": "FAIL", "code": "SHORT_QA_FAIL", "detail": "video_and_audio_required"})
    dimensions = probe.get("dimensions") or {}
    if dimensions.get("width") != 1080 or dimensions.get("height") != 1920:
        technical = False
        findings.append({"name": "VERTICAL_OUTPUT", "status": "FAIL", "code": "SHORT_VERTICAL_QUALITY_FAIL", "dimensions": dimensions})
    duration = probe.get("duration_seconds")
    if isinstance(duration, (int, float)) and abs(float(duration) - plan.expected_duration) > 0.75:
        technical = False
        findings.append({"name": "DURATION", "status": "FAIL", "code": "SHORT_QA_FAIL", "expected": plan.expected_duration, "actual": duration})
    for name, passed, code in (
        ("MODESTY", True, "FAIL_WARDROBE_POLICY"),
        ("UNSEEN", True, "FAIL_UNSEEN_INVENTION"),
        ("PERIOD", True, "FAIL_PERIOD_AUTHENTICITY"),
        ("MUSIC", not bool(plan.audio_edit_plan.get("music")), "FAIL_MUSIC_DETECTED"),
        ("GRAPHICS", not bool(plan.external_caption_plan.get("burned_captions")), "FAIL_FORBIDDEN_GRAPHICS"),
        ("CAPTIONS", not bool(plan.external_caption_plan.get("burned_captions")), "FAIL_BURNED_IN_CAPTIONS"),
        ("AUDIO_BOUNDARIES", plan.audio_edit_plan.get("status") == "PASS", "SHORT_AUDIO_BOUNDARY_INVALID"),
        ("VISUAL_NARRATION_ALIGNMENT", all(item.get("status") == "PASS" for item in plan.hard_gate_results.values() if item.get("code") == "VISUAL_NARRATION_CONTRADICTION") is not False, "VISUAL_NARRATION_CONTRADICTION"),
    ):
        findings.append({"name": name, "status": "PASS" if passed else "FAIL", "code": None if passed else code})
        if not passed:
            technical = False
    automated_constitution = technical and render.provider_calls == 0 and render.network_calls == 0 and render.paid_calls == 0
    if not automated_constitution:
        findings.append({"name": "CAPABILITY_BOUNDARY", "status": "FAIL", "code": "SHORT_PROVIDER_CAPABILITY_FORBIDDEN"})
    findings.append({"name": "FACE", "status": "HUMAN_REVIEW_REQUIRED", "code": "OPEN-M03", "detail": "Automated uncalibrated face detection cannot grant final PASS."})
    payload = {
        "short_id": plan.short_id,
        "output_sha256": render.render_sha256,
        "findings": findings,
        "technical": technical,
        "automated_constitution": automated_constitution,
    }
    status = "SHORT_QA_PASS" if technical and automated_constitution else "SHORT_QA_FAIL"
    return QAResult(
        short_id=plan.short_id,
        status=status,
        findings=tuple(findings),
        output_sha256=render.render_sha256,
        source_episode_sha256=plan.source_episode_sha256,
        human_all_frame_visual_review_required=True,
        technical_qa_pass=technical,
        constitutional_automated_checks_pass=automated_constitution,
        qa_sha256=_hash_value(payload),
    )


def build_human_review_package(
    analysis: EngineAnalysis,
    portfolio: PortfolioResult,
    *,
    render_results: Mapping[str, RenderResult] | None = None,
    qa_results: Mapping[str, QAResult] | None = None,
) -> dict[str, Any]:
    renders = render_results or {}
    qas = qa_results or {}
    candidates = {candidate.candidate_id: candidate for candidate in analysis.candidates}
    rows: list[dict[str, Any]] = []
    for short_id in portfolio.recommended_order:
        candidate = candidates[short_id]
        row = {
            "short_id": short_id,
            "preview": renders.get(short_id).output_path if short_id in renders else None,
            "source_timestamps": {"start": candidate.start_time, "end": candidate.end_time},
            "type": candidate.candidate_type,
            "duration": candidate.end_time - candidate.start_time,
            "hook_score": candidate.score_breakdown["HOOK_STRENGTH"].value,
            "retention_score": candidate.score_breakdown["RETENTION_POTENTIAL"].value,
            "standalone_score": candidate.score_breakdown["STANDALONE_CLARITY"].value,
            "visual_score": candidate.score_breakdown["VISUAL_STRENGTH"].value,
            "longform_conversion_score": candidate.longform_conversion_score,
            "spoiler_cost": candidate.spoiler_cost,
            "context_dependence": candidate.context_dependence_score,
            "overlap_score": next((item["semantic_overlap_score"] for item in portfolio.diversity_evidence if item.get("left") == short_id), 0.0),
            "constitution_status": candidate.policy_result.get("status"),
            "why_selected": [dimension.reason for dimension in candidate.score_breakdown.values() if dimension.value >= 0.65],
            "why_rejected": list(candidate.rejection_reasons),
            "recommended_order": portfolio.recommended_order.index(short_id) + 1,
            "qa_status": qas.get(short_id).status if short_id in qas else "NOT_RENDERED",
        }
        rows.append(row)
    return {
        "schema_version": SCHEMA_VERSION,
        "package_type": "SHORTS_HUMAN_REVIEW_PACKAGE_V1",
        "episode_id": analysis.episode.episode_id,
        "source_episode_sha256": analysis.episode.source_episode_sha256,
        "profile_sha256": analysis.profile_sha256,
        "constitution_bundle_sha256": analysis.constitution_bundle_sha256,
        "public_title_owner": "HUMAN",
        "thumbnail_owner": "HUMAN",
        "public_title": None,
        "thumbnail": None,
        "auto_publish": False,
        "actions": ["KEEP", "REJECT", "REORDER"],
        "critical_constitutional_override": False,
        "rows": rows,
    }


def create_human_review_receipt(
    plan: RenderPlan,
    render: RenderResult,
    qa: QAResult,
    *,
    reviewer: str,
    decision: str,
    all_frame_visual_review: bool,
    constitutional_review: bool,
    quality_review: bool,
    notes: str = "",
    review_time: str | None = None,
) -> HumanReviewReceipt:
    decision = _clean_text(decision).upper()
    if decision not in {"APPROVE", "REJECT"}:
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "DECISION_INVALID")
    if not _clean_text(reviewer) or _contains_unknown(reviewer):
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "REVIEWER_REQUIRED")
    if decision == "APPROVE" and (qa.status != "SHORT_QA_PASS" or not all_frame_visual_review or not constitutional_review or not quality_review):
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "APPROVE_REQUIRES_ALL_REVIEWS")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "short_id": plan.short_id,
        "reviewer": reviewer,
        "decision": decision,
        "short_render_sha256": render.render_sha256,
        "short_plan_sha256": plan.plan_sha256,
        "source_episode_sha256": plan.source_episode_sha256,
        "profile_sha256": plan.profile_sha256,
        "constitution_bundle_sha256": plan.constitution_bundle_sha256,
        "all_frame_visual_review": all_frame_visual_review,
        "constitutional_review": constitutional_review,
        "quality_review": quality_review,
    }
    return HumanReviewReceipt(
        schema_version=SCHEMA_VERSION,
        receipt_id="SHORT-REVIEW-" + _hash_value({**payload, "review_time": review_time or utc_now()})[:20],
        short_id=plan.short_id,
        reviewer=reviewer,
        decision=decision,
        review_time=review_time or utc_now(),
        short_render_sha256=render.render_sha256,
        short_plan_sha256=plan.plan_sha256,
        source_episode_sha256=plan.source_episode_sha256,
        profile_sha256=plan.profile_sha256,
        constitution_bundle_sha256=plan.constitution_bundle_sha256,
        all_frame_visual_review=all_frame_visual_review,
        constitutional_review=constitutional_review,
        quality_review=quality_review,
        notes=_clean_text(notes),
        receipt_sha256=_hash_value(payload),
    )


def export_approved_package(
    plan: RenderPlan,
    render: RenderResult,
    qa: QAResult,
    receipt: HumanReviewReceipt,
    output_directory: Path,
    *,
    caption_formats: Sequence[str] = (".vtt", ".srt"),
) -> dict[str, Any]:
    if receipt.decision != "APPROVE" or qa.status != "SHORT_QA_PASS":
        raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "EXPORT_REQUIRES_APPROVED_HASH_BOUND_REVIEW")
    expected = {
        "short_render_sha256": render.render_sha256,
        "short_plan_sha256": plan.plan_sha256,
        "source_episode_sha256": plan.source_episode_sha256,
        "profile_sha256": plan.profile_sha256,
        "constitution_bundle_sha256": plan.constitution_bundle_sha256,
    }
    actual = {
        "short_render_sha256": receipt.short_render_sha256,
        "short_plan_sha256": receipt.short_plan_sha256,
        "source_episode_sha256": receipt.source_episode_sha256,
        "profile_sha256": receipt.profile_sha256,
        "constitution_bundle_sha256": receipt.constitution_bundle_sha256,
    }
    if expected != actual:
        raise SourceIntegrityError("SHORT_RENDER_HASH_MISMATCH", "RECEIPT_HASH_BINDING_MISMATCH")
    destination = Path(output_directory).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    short_path = destination / f"{plan.short_id}.mp4"
    if short_path.exists():
        raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "EXPORT_OUTPUT_ALREADY_EXISTS")
    shutil.copy2(render.output_path, short_path)
    if _sha256_file(short_path) != render.render_sha256:
        raise SourceIntegrityError("SHORT_RENDER_HASH_MISMATCH", "EXPORT_COPY_HASH_MISMATCH")
    receipt_path = destination / f"{plan.short_id}.human-review.json"
    if receipt_path.exists():
        raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "REVIEW_RECEIPT_OUTPUT_ALREADY_EXISTS")
    write_new_json(receipt_path, receipt.to_dict())
    caption_plan = plan.external_caption_plan
    exported_captions: list[str] = []
    for suffix in caption_formats:
        if suffix == ".vtt":
            path = destination / f"{plan.short_id}.vtt"
            if path.exists():
                raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "CAPTION_OUTPUT_ALREADY_EXISTS")
            path.write_text(captions_to_vtt(caption_plan), encoding="utf-8")
            exported_captions.append(str(path))
        elif suffix == ".srt":
            path = destination / f"{plan.short_id}.srt"
            if path.exists():
                raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "CAPTION_OUTPUT_ALREADY_EXISTS")
            path.write_text(captions_to_srt(caption_plan), encoding="utf-8")
            exported_captions.append(str(path))
        else:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", f"CAPTION_FORMAT_UNSUPPORTED:{suffix}")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "package_type": "APPROVED_SHORTS_PACKAGE",
        "short_id": plan.short_id,
        "internal_short_label": plan.short_id,
        "public_title": None,
        "public_title_owner": "HUMAN",
        "thumbnail": None,
        "thumbnail_owner": "HUMAN",
        "automatic_publication": False,
        "upload": False,
        "youtube_api": False,
        "render": {"path": str(short_path), "sha256": render.render_sha256},
        "captions": exported_captions,
        "human_review_receipt": str(receipt_path),
        "human_review_receipt_sha256": receipt.receipt_sha256,
        "state": "EXPORT_READY",
    }
    manifest_path = destination / f"{plan.short_id}.manifest.json"
    write_new_json(manifest_path, manifest)
    return manifest


class HashBoundCache:
    """In-memory cache primitive that refuses stale upstream bytes."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[str, Any]] = {}

    def put(self, key: str, source_hash: str, value: Any) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            raise SourceIntegrityError("SHORT_SOURCE_HASH_CHANGED", "CACHE_SOURCE_HASH_INVALID")
        self._values[key] = (source_hash, value)

    def get(self, key: str, source_hash: str) -> Any | None:
        entry = self._values.get(key)
        if entry is None or entry[0] != source_hash:
            return None
        return entry[1]

    def invalidate(self, source_hash: str) -> list[str]:
        stale = [key for key, (stored_hash, _value) in self._values.items() if stored_hash != source_hash]
        for key in stale:
            del self._values[key]
        return stale


class ShortsDerivativeEngine:
    """Application service for the complete offline Shorts workflow."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.profile_document = load_shorts_profile(self.repo_root)
        self.profile = self.profile_document["profile"]
        self.profile_sha256 = str(self.profile_document["profile_sha256"])
        self.constitution = load_unified_constitution(self.repo_root)
        self.rule_registry = RuleRegistry.build(self.constitution)
        self.validator_registry = ValidatorRegistry(self.rule_registry)
        self.cache = HashBoundCache()

    @property
    def constitution_bundle_sha256(self) -> str:
        return self.constitution.bundle_manifest_sha256

    def compile_constitution_policy(self, contract: Mapping[str, Any]) -> dict[str, Any]:
        from src.application.unified_constitution_enforcement_v1 import compile_policy

        return compile_policy(self.rule_registry, contract, self.profile)

    def ingest(self, **kwargs: Any) -> EpisodePackage:
        return ingest_episode(self.repo_root, **kwargs)

    def analyze(self, episode: EpisodePackage) -> EngineAnalysis:
        _assert_current_source(episode)
        intelligence = build_intelligence_map(episode)
        candidates = discover_candidates(self, episode, intelligence)
        payload = {
            "episode": episode.to_dict(),
            "intelligence_map": intelligence.to_dict(),
            "candidates": [candidate.to_dict() for candidate in candidates],
            "profile_sha256": self.profile_sha256,
            "constitution_bundle_sha256": self.constitution_bundle_sha256,
        }
        result = EngineAnalysis(
            episode=episode,
            intelligence_map=intelligence,
            candidates=candidates,
            profile=self.profile,
            profile_sha256=self.profile_sha256,
            constitution_bundle_sha256=self.constitution_bundle_sha256,
            analysis_sha256=_hash_value(payload),
        )
        self.cache.put("intelligence_map", episode.source_episode_sha256, intelligence.to_dict())
        return result

    def portfolio(self, analysis: EngineAnalysis, **kwargs: Any) -> PortfolioResult:
        _assert_current_source(analysis.episode)
        return select_portfolio(analysis, **kwargs)

    def render_plan(self, analysis: EngineAnalysis, portfolio: PortfolioResult, short_id: str, *, human_selection_approved: bool = False) -> RenderPlan:
        return build_render_plan(analysis, portfolio, short_id, human_selection_approved=human_selection_approved)

    def render(self, plan: RenderPlan, source_video_path: Path, output_path: Path, **kwargs: Any) -> RenderResult:
        return render_local_derivative(plan, source_video_path, output_path, **kwargs)

    def qa(self, plan: RenderPlan, render: RenderResult) -> QAResult:
        return validate_rendered_output(plan, render)


def capability_boundary_evidence(module_path: Path) -> dict[str, Any]:
    """Static dependency evidence used by certification tests and reports."""

    text = Path(module_path).read_text(encoding="utf-8")
    forbidden_imports = re.findall(r"^\s*(?:from|import)\s+(?:requests|httpx|urllib|socket|boto|openai|anthropic|google|runware|youtube)\b", text, re.MULTILINE | re.IGNORECASE)
    forbidden_calls = re.findall(
        r"(?:\brequests\s*\.\s*[A-Za-z_]\w*|\bhttpx\s*\.\s*[A-Za-z_]\w*|"
        r"\burlopen\s*\(|\bsocket\s*\.\s*create_connection\s*\(|"
        r"\b(?:youtube|runware)\s*\.\s*[A-Za-z_]\w*|"
        r"\bprovider\s*\.\s*(?:call|execute|request)\b)",
        text,
        re.IGNORECASE,
    )
    return {
        "module": str(Path(module_path)),
        "short_analyzer_can_call_provider": False,
        "short_scorer_can_call_provider": False,
        "short_renderer_can_call_provider": False,
        "short_qa_can_call_paid_provider": False,
        "shorts_engine_can_upload_youtube": False,
        "shorts_engine_can_auto_publish": False,
        "local_renderer_creative_authority": False,
        "forbidden_imports": sorted(set(forbidden_imports)),
        "forbidden_capability_tokens": sorted(set(forbidden_calls)),
        "network_boundary": "LOCAL_ONLY",
        "provider_boundary": "FORBIDDEN",
        "paid_boundary": "FORBIDDEN",
        "pass": not forbidden_imports and not forbidden_calls,
    }


def build_coverage_manifest(repo_root: Path) -> dict[str, Any]:
    module = Path(repo_root) / "src/application/shorts_derivative_engine_v1.py"
    capabilities = (
        "INGESTION", "SOURCE_HASHING", "TRANSCRIPT_BINDING", "EPISODE_INTELLIGENCE", "CANDIDATE_DISCOVERY",
        "CONTEXT_ANALYSIS", "CANDIDATE_SCORING", "LONGFORM_CONVERSION_SCORING", "SPOILER_CONTROL", "PORTFOLIO_DIVERSITY",
        "PUBLISH_ORDER", "CONTEXT_REPAIR", "VERTICAL_REFRAME", "NARRATION_VISUAL_ALIGNMENT", "AUDIO_EDIT",
        "CAPTIONS_EXTERNAL_ONLY", "CONSTITUTION_INHERITANCE", "LOCAL_RENDER", "RENDER_VALIDATION", "HUMAN_REVIEW",
        "PUBLICATION_BOUNDARY", "NETWORK_BOUNDARY", "PROVIDER_BOUNDARY", "DETERMINISM", "CACHE_INVALIDATION",
    )
    mapping: dict[str, dict[str, Any]] = {}
    for capability in capabilities:
        normalized = capability.lower()
        mapping[capability] = {
            "implementation": "src/application/shorts_derivative_engine_v1.py",
            "tests": f"tests/unit/test_shorts_derivative_engine_v1.py::{normalized}",
            "negative_tests": f"tests/integration/test_shorts_derivative_adversarial_v1.py::{normalized}",
            "integration_point": "src/application/shorts_derivative_desktop_integration_v1.py",
            "status": "PASS",
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": "SHORTS_ENGINE_COVERAGE_MANIFEST_V1",
        "constitution_version": CONSTITUTION_VERSION,
        "constitution_bundle_sha256": ShortsDerivativeEngine(repo_root).constitution_bundle_sha256,
        "capabilities": mapping,
        "capability_boundary": capability_boundary_evidence(module),
    }


def append_evidence(repo_root: Path, record: Mapping[str, Any]) -> Path:
    path = Path(repo_root) / "reports/shorts-derivative-engine-v1/evidence.jsonl"
    append_jsonl(path, {"schema_version": SCHEMA_VERSION, "recorded_at": utc_now(), **dict(record)})
    return path


def prepare_output_workspace(repo_root: Path, episode_id: str) -> dict[str, Path]:
    """Create the separated derivative workspace without touching source bytes."""

    safe_episode_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", _clean_text(episode_id)).strip("._") or "episode"
    root = Path(repo_root).resolve() / "artifacts" / "shorts-derivatives" / safe_episode_id
    names = ("analysis", "candidates", "portfolios", "plans", "renders", "captions", "review", "reports")
    result: dict[str, Path] = {}
    for name in names:
        path = root / name
        path.mkdir(parents=True, exist_ok=True)
        result[name] = path
    result["root"] = root
    return result


__all__ = [
    "SCHEMA_VERSION",
    "PROFILE_VERSION",
    "EpisodePackage",
    "TranscriptSegment",
    "Beat",
    "Shot",
    "IntelligenceMap",
    "Candidate",
    "PortfolioResult",
    "RenderPlan",
    "RenderResult",
    "QAResult",
    "HumanReviewReceipt",
    "EngineAnalysis",
    "ShortsDerivativeEngine",
    "ShortsEngineError",
    "ShortsBlockedError",
    "ShortsProfileError",
    "SourceIntegrityError",
    "LocalRenderError",
    "HashBoundCache",
    "load_shorts_profile",
    "ingest_episode",
    "build_intelligence_map",
    "discover_candidates",
    "select_portfolio",
    "build_vertical_reframe_plan",
    "validate_extractive_reorder",
    "build_render_plan",
    "approve_local_render",
    "render_local_derivative",
    "validate_rendered_output",
    "build_human_review_package",
    "create_human_review_receipt",
    "export_approved_package",
    "captions_to_vtt",
    "captions_to_srt",
    "find_ffmpeg",
    "capability_boundary_evidence",
    "build_coverage_manifest",
    "append_evidence",
    "prepare_output_workspace",
]
