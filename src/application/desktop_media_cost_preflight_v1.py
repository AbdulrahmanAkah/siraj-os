"""Canonical local MEDIA_COST_PREFLIGHT transaction for the Desktop UI.

The executor is intentionally provider-free.  It plans request units from the
current promoted prompt plan, validates the local provider contracts, writes an
immutable result, and only then commits a ledger receipt.  A UI review carries
the ledger head and immutable input identities; a changed head fails closed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import math
import uuid

from src.application.artifact_provenance_v1 import (
    artifact_reference,
    canonical_sha256,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.cinematic_shot_contracts import structural_shots_from_storyboard
from src.application.episode_transition_ledger_v1 import (
    append_transition_if_head,
    project_state,
    read_entries,
)
from src.application.provider_model_contracts import validate_runware_task
from src.application.runware_image_model_routing_v1 import build_runware_image_task, route_image_shot
from src.application.siraj_cinematic_media_mix_policy_v2 import (
    MAX_TRUE_VIDEO_FRACTION,
    MIN_TRUE_VIDEO_FRACTION,
    validate_true_video_coverage,
)

from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    EXPECTED_OVERLAY_SHA256,
    EXPECTED_STRUCTURAL_FINGERPRINT,
    MEDIA_COST_PREFLIGHT,
    DesktopEpisodeState,
    DesktopResumeIntent,
    DesktopResumePolicyError,
    _paths as readiness_paths,
    _read_json,
    read_desktop_episode_state,
)


SCHEMA_VERSION = "siraj-desktop-media-cost-preflight-v1"
NEXT_STAGE = "PROVIDER_EXECUTION"
LOCAL_AUTH_SCOPE = "MEDIA_COST_PREFLIGHT_LOCAL_ONLY"
CONTRACT_SOURCE_RELS = (
    "src/application/provider_model_contracts.py",
    "src/application/siraj_runware_provider_contract_v6_6_r9.py",
)
POLICY_REL = "projects/_series/siraj-cinematic-media-mix-policy-v2.json"
LEGACY_POLICY_REL = "projects/_series/siraj-visual-mix-duplicate-policy-v6.2.1.json"


class MediaCostPreflightError(DesktopResumePolicyError):
    pass


@dataclass(frozen=True, slots=True)
class MediaCostPreflightReview:
    """Read-only presentation model for a committed local preflight.

    The model is deliberately built from the durable preflight result and the
    ledger-backed current state.  It never recomputes a plan and it never
    creates authorization or a paid attempt.  ``result_file_sha256`` is the
    physical artifact identity; ``result_sha256`` is the canonical payload
    identity stored inside the result.
    """

    episode_id: str
    stage: str
    next_stage: str
    result_path: str
    result_file_sha256: str
    result_sha256: str
    persisted_status: str
    completion_status: str
    current_ledger_head_sha256: str
    reviewed_ledger_head_sha256: str
    authoritative_state: dict[str, Any]
    input_artifacts: dict[str, Any]
    summary: dict[str, Any]
    units: tuple[dict[str, Any], ...]
    media_policy: dict[str, Any]
    generated_video_ceiling_seconds: float
    cost_status: str
    cost_envelope_usd: dict[str, Any]
    provider_model_counts: dict[str, int]
    production_authorization: str
    authorization_policy: str
    master_authorization_path: str | None
    master_authorization_file_sha256: str | None
    master_authorization_sha256: str | None
    # The V2 migration binds authorization to the exact approved plan and
    # provider-request inventory.  Keep this read-only authority in the
    # review model so a Desktop acknowledgement cannot float over a newer
    # plan while older fixtures remain compatible through the empty default.
    media_plan_authority: dict[str, Any] = field(default_factory=dict)
    provider_contract_status: str = "UNKNOWN"

    @property
    def generated_video_percent(self) -> float:
        duration = float(self.authoritative_state.get("duration_seconds") or 0.0)
        generated = float(self.summary.get("generated_video_seconds") or 0.0)
        return round((generated / duration) * 100.0, 6) if duration else 0.0

    @property
    def pricing_status(self) -> str:
        return "UNKNOWN" if self.cost_status.startswith("UNKNOWN") else "COMPLETE"

    @property
    def estimated_total_cost_usd(self) -> float | None:
        upper = self.cost_envelope_usd.get("upper_bound")
        return float(upper) if isinstance(upper, (int, float)) else None

    @property
    def currency(self) -> str | None:
        # The persisted schema has no currency field.  Never infer USD from a
        # missing value merely because the envelope key contains ``usd``.
        value = self.cost_envelope_usd.get("currency")
        return str(value) if value else None

    @property
    def coverage_status(self) -> str:
        result = validate_true_video_coverage(
            float(self.authoritative_state.get("duration_seconds") or 0.0),
            float(self.summary.get("generated_video_seconds") or 0.0),
        )
        return result.status

    @property
    def provider_execution_allowed(self) -> bool:
        return (
            self.coverage_status == "PASS"
            and self.pricing_status == "COMPLETE"
            and self.provider_contract_status == "PASS"
            and self.production_authorization
            in {"VALID", "VALID_BOUND_TO_CURRENT_COST_ENVELOPE"}
        )

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["generated_video_percent"] = self.generated_video_percent
        value["pricing_status"] = self.pricing_status
        value["estimated_total_cost_usd"] = self.estimated_total_cost_usd
        value["currency"] = self.currency
        value["coverage_status"] = self.coverage_status
        value["provider_execution_allowed"] = self.provider_execution_allowed
        value["cost_envelope_reack_required"] = self.production_authorization == (
            "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
        )
        return value


def _preflight_result_path(
    repo_root: Path,
    episode_id: str,
    *,
    entries: Sequence[Mapping[str, Any]] | None = None,
) -> Path:
    """Resolve the active durable preflight result from ledger provenance.

    Historical fixtures used the fixed v1 filename.  A controlled re-preflight
    may preserve that artifact and publish a new immutable result, so the
    latest completed MEDIA_COST_PREFLIGHT receipt is the authority for the
    active result path.  The v1 path remains a compatibility fallback only.
    """

    repo = Path(repo_root).resolve()
    fallback = repo / "projects" / episode_id / "orchestration" / "media-cost-preflight-v1.json"
    try:
        ledger_entries = list(entries) if entries is not None else read_entries(repo, episode_id)
    except Exception:
        ledger_entries = []
    for entry in reversed(ledger_entries):
        if entry.get("stage") != MEDIA_COST_PREFLIGHT or entry.get("status") != "COMPLETED":
            continue
        for reference in reversed(entry.get("output_artifacts") or []):
            if reference.get("logical_output") != "MEDIA_COST_PREFLIGHT_RESULT":
                continue
            raw_path = str(reference.get("path") or "")
            if not raw_path:
                continue
            candidate = Path(raw_path)
            if not candidate.is_absolute():
                candidate = repo / candidate
            candidate = candidate.resolve()
            # Once the ledger names a latest completion artifact, a missing
            # file must remain a hard missing-artifact condition; never fall
            # back to an older result and accidentally infer success.
            return candidate
    return fallback


def _validate_persisted_review_result(result: Mapping[str, Any], episode_id: str) -> None:
    if result.get("schema_version") != SCHEMA_VERSION:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_SCHEMA_INVALID")
    if result.get("episode_id") != episode_id:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_EPISODE_INVALID")
    if result.get("stage") != MEDIA_COST_PREFLIGHT:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_STAGE_INVALID")
    if result.get("next_stage") != NEXT_STAGE:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_NEXT_STAGE_INVALID")
    if result.get("provider_calls") != 0 or result.get("paid_attempts_created") != 0:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_PAID_ACTIVITY_INVALID")
    if result.get("next_stage_executed") is not False:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_DOWNSTREAM_EXECUTION_INVALID")
    expected = canonical_sha256(
        {key: value for key, value in result.items() if key != "result_sha256"}
    )
    if result.get("result_sha256") != expected:
        raise MediaCostPreflightError("PREFLIGHT_RESULT_HASH_INVALID")


def _master_authorization_review(
    repo_root: Path,
    episode_id: str,
) -> tuple[str, str, str | None, str | None, str | None]:
    """Return the existing episode-wide authorization status read-only."""

    from src.application.siraj_episode_master_authorization_v6_6 import (
        master_authorization_active,
        master_authorization_path,
    )

    path = master_authorization_path(repo_root, episode_id)
    if not path.is_file():
        return (
            "AWAITING_HUMAN_AUTHORIZATION",
            "EPISODE_WIDE_MASTER_AUTHORIZATION_V6_6",
            str(path),
            None,
            None,
        )
    payload = _read_mapping(path)
    return (
        "VALID" if master_authorization_active(repo_root, episode_id) else "AWAITING_HUMAN_AUTHORIZATION",
        "EPISODE_WIDE_MASTER_AUTHORIZATION_V6_6",
        str(path),
        sha256_file(path),
        str(payload.get("authorization_sha256") or "") or None,
    )


def read_persisted_media_cost_preflight(
    repo_root: Path,
    episode_id: str = EPISODE_002,
) -> MediaCostPreflightReview:
    """Read the canonical persisted preflight for review; never recompute."""

    repo = Path(repo_root).resolve()
    result_path = _preflight_result_path(repo, episode_id)
    if not result_path.is_file():
        raise MediaCostPreflightError("MEDIA_COST_PREFLIGHT_RESULT_MISSING")
    result = _read_mapping(result_path)
    _validate_persisted_review_result(result, episode_id)
    state = read_desktop_episode_state(repo, episode_id)
    if state.current_stage != NEXT_STAGE:
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_REQUIRES_PROVIDER_EXECUTION_STAGE")

    authoritative = result.get("authoritative_state")
    summary = result.get("summary")
    input_artifacts = result.get("input_artifacts")
    units = result.get("units")
    media_policy = result.get("media_policy")
    envelope = result.get("cost_envelope_usd")
    if not isinstance(authoritative, dict) or not isinstance(summary, dict):
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_SUMMARY_INVALID")
    if not isinstance(input_artifacts, dict) or not isinstance(units, list):
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_INPUTS_INVALID")
    if not isinstance(media_policy, dict) or not isinstance(envelope, dict):
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_POLICY_INVALID")
    for key, expected in (
        ("promoted_overlay_sha256", state.promoted_overlay_sha256),
        ("structural_fingerprint", state.authoritative_structural_fingerprint),
    ):
        if authoritative.get(key) != expected:
            raise MediaCostPreflightError("PREFLIGHT_REVIEW_AUTHORITATIVE_INPUT_MISMATCH:" + key)
    if float(authoritative.get("duration_seconds")) != state.duration_seconds:
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_AUTHORITATIVE_INPUT_MISMATCH:duration_seconds")
    if int(authoritative.get("shot_count")) != state.shot_count:
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_AUTHORITATIVE_INPUT_MISMATCH:shot_count")
    if int(authoritative.get("timeline_discontinuities")) != state.timeline_discontinuities:
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_AUTHORITATIVE_INPUT_MISMATCH:timeline_discontinuities")
    coverage = validate_true_video_coverage(
        float(authoritative.get("duration_seconds") or 0.0),
        float(summary.get("generated_video_seconds") or 0.0),
    )
    # A persisted result remains inspectable as forensic/pre-spend evidence,
    # even when V2 marks it invalid.  The provider-execution cost guard below
    # is the fail-closed enforcement boundary; review UI must show the exact
    # invalid status rather than hiding the plan.

    provider_model_counts: dict[str, int] = {}
    for unit in units:
        if not isinstance(unit, dict):
            raise MediaCostPreflightError("PREFLIGHT_REVIEW_UNIT_INVALID")
        key = f"{unit.get('provider')}/{unit.get('model')}"
        provider_model_counts[key] = provider_model_counts.get(key, 0) + 1

    auth_status, auth_policy, auth_path, auth_file_sha, auth_sha = _master_authorization_review(
        repo,
        episode_id,
    )
    # A materially changed V2 media plan is not covered by the old episode-wide
    # authorization until its exact cost envelope is re-acknowledged.  The
    # result may carry this read-only binding status; legacy results continue
    # to use the authorization file's status.
    result_authorization = result.get("preflight_authorization") or result.get("authorization")
    if isinstance(result_authorization, Mapping):
        rebinding_status = result_authorization.get("master_authorization_status_for_new_plan")
        if rebinding_status:
            auth_status = str(rebinding_status)
        elif (result.get("media_plan_authority") or {}).get("status") == "ACTIVE_V2_PLAN_FOR_REPREFLIGHT":
            # The first migration executor version stored only the local
            # execution authorization in ``authorization``.
            auth_status = "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
    elif (result.get("media_plan_authority") or {}).get("status") == "ACTIVE_V2_PLAN_FOR_REPREFLIGHT":
        # The first migration executor version stored the local execution
        # authorization in ``authorization``.  The active V2 plan marker is
        # still an immutable, explicit signal that the old master grant is not
        # bound to this new cost envelope.
        auth_status = "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
    entries = read_entries(repo, episode_id)
    completed = [
        entry
        for entry in entries
        if entry.get("stage") == MEDIA_COST_PREFLIGHT
        and entry.get("status") == "COMPLETED"
        and entry.get("metadata", {}).get("transaction_id") == result.get("transaction_id")
    ]
    if len(completed) != 1:
        raise MediaCostPreflightError("PREFLIGHT_REVIEW_COMPLETION_RECEIPT_INVALID")
    review = MediaCostPreflightReview(
        episode_id=episode_id,
        stage=MEDIA_COST_PREFLIGHT,
        next_stage=NEXT_STAGE,
        result_path=str(result_path),
        result_file_sha256=sha256_file(result_path),
        result_sha256=str(result.get("result_sha256") or ""),
        persisted_status=str(result.get("status") or ""),
        completion_status="COMPLETED_LEDGER_RECEIPT",
        current_ledger_head_sha256=state.ledger_head_sha256,
        reviewed_ledger_head_sha256=str(result.get("authoritative_state", {}).get("ledger_head_sha256") or ""),
        authoritative_state=dict(authoritative),
        input_artifacts=dict(input_artifacts),
        summary=dict(summary),
        units=tuple(dict(unit) for unit in units),
        media_policy=dict(media_policy),
        generated_video_ceiling_seconds=float(result.get("generated_video_ceiling_seconds")),
        cost_status=str(result.get("cost_status") or "UNKNOWN"),
        cost_envelope_usd=dict(envelope),
        provider_model_counts=provider_model_counts,
        production_authorization=auth_status,
        authorization_policy=auth_policy,
        master_authorization_path=auth_path,
        master_authorization_file_sha256=auth_file_sha,
        master_authorization_sha256=auth_sha,
        media_plan_authority=(
            dict(result.get("media_plan_authority"))
            if isinstance(result.get("media_plan_authority"), Mapping)
            else {}
        ),
        provider_contract_status=(
            str((result.get("provider_contract_validation") or {}).get("status"))
            if isinstance(result.get("provider_contract_validation"), Mapping)
            else "UNKNOWN"
        ),
    )
    # A cost-envelope re-acknowledgement is an append-only application
    # receipt.  It is deliberately derived only after the ordinary persisted
    # preflight validation above; a malformed receipt can never make an
    # invalid preflight appear executable.
    from src.application.desktop_cost_envelope_reack_v1 import (
        effective_reack_for_review,
    )

    effective_status = effective_reack_for_review(repo, review)
    if effective_status is not None:
        review = replace(
            review,
            production_authorization=effective_status,
        )
    return review


def validate_persisted_media_cost_preflight_review(
    repo_root: Path,
    review: MediaCostPreflightReview,
) -> MediaCostPreflightReview:
    """Re-read and compare a review snapshot before any later approval action."""

    current = read_persisted_media_cost_preflight(repo_root, review.episode_id)
    if (
        current.current_ledger_head_sha256 != review.current_ledger_head_sha256
        or current.result_file_sha256 != review.result_file_sha256
        or current.result_sha256 != review.result_sha256
        or current.authoritative_state != review.authoritative_state
        or current.input_artifacts != review.input_artifacts
    ):
        raise MediaCostPreflightError("STALE_STATE_REVIEW_REQUIRED")
    return current


@dataclass(frozen=True, slots=True)
class MediaCostPreflightOutcome:
    status: str
    episode_id: str
    stage: str
    next_stage: str
    next_stage_executed: bool
    result_path: str | None
    result_sha256: str | None
    ledger_head_sha256: str | None
    provider_calls: int
    paid_attempts_created: int
    failure_classification: str | None = None
    recovery_action: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_mapping(path: Path) -> dict[str, Any]:
    value = _read_json(path)
    return value


def _input_paths(repo: Path, episode_id: str) -> dict[str, Path]:
    paths = readiness_paths(repo, episode_id)
    # A fixture created before the V2 policy may contain only the historical
    # policy.  Keep that compatibility seam explicit; the real repository has
    # the V2 file and therefore never falls back.
    v2_policy = repo / POLICY_REL
    paths["policy"] = v2_policy if v2_policy.is_file() else repo / LEGACY_POLICY_REL
    for rel in CONTRACT_SOURCE_RELS:
        paths[rel.rsplit("/", 1)[-1]] = repo / rel
    return paths


def _planning_identity(episode_id: str, shot_id: str, payload: Mapping[str, Any]) -> str:
    # A provider task identity is not a content fingerprint.  Generate the
    # Runware UUID v4 before the request is handed to the execution boundary;
    # the caller must retain this single value for the task and unit record.
    return str(uuid.uuid4())


def _structural_join_check(
    plan_items: Sequence[Mapping[str, Any]],
    storyboard: Mapping[str, Any],
) -> None:
    structures = structural_shots_from_storyboard(storyboard)
    ordered = sorted(plan_items, key=lambda item: int(item.get("queue_index") or 0))
    if len(ordered) != len(structures):
        raise MediaCostPreflightError("PROMPT_PLAN_STORYBOARD_SHOT_COUNT_MISMATCH")
    for item, structure in zip(ordered, structures):
        expected = structure.as_dict()
        for key in ("shot_id", "queue_index", "segment_ids", "beat_id"):
            if item.get(key) != expected.get(key):
                raise MediaCostPreflightError("PROMPT_PLAN_STRUCTURAL_FIELD_MISMATCH:" + key)
        if round(float(item.get("start_seconds")), 3) != round(expected["start_ms"] / 1000.0, 3):
            raise MediaCostPreflightError("PROMPT_PLAN_STRUCTURAL_FIELD_MISMATCH:start_seconds")
        if round(float(item.get("end_seconds")), 3) != round(expected["end_ms"] / 1000.0, 3):
            raise MediaCostPreflightError("PROMPT_PLAN_STRUCTURAL_FIELD_MISMATCH:end_seconds")


def _video_task(
    episode_id: str,
    item: Mapping[str, Any],
    planning_id: str,
    *,
    requested_seconds: int,
) -> dict[str, Any]:
    prompt = str(item.get("runware_positive_prompt_en") or "").strip()
    if not prompt:
        raise MediaCostPreflightError("VIDEO_PROMPT_REQUIRED:" + str(item.get("shot_id")))
    return {
        "taskType": "videoInference",
        "taskUUID": planning_id,
        "model": "google:veo@3.1-lite",
        "positivePrompt": prompt,
        "width": 1280,
        "height": 720,
        "duration": requested_seconds,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {"google": {"generateAudio": False, "personGeneration": "allow_adult" if item.get("contains_people") else "dont_allow"}},
    }


def _planned_units(
    repo: Path,
    episode_id: str,
    items: Sequence[Mapping[str, Any]],
    *,
    episode_duration: float,
    provider_request_fallback_max_seconds: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    units: list[dict[str, Any]] = []
    payload_fingerprints: set[str] = set()
    generated_seconds = 0.0
    requested_seconds = 0.0
    counts = {"RUNWARE_IMAGE": 0, "RUNWARE_VIDEO": 0, "LOCAL_GRAPHICS": 0}
    unknown_price_count = 0
    known_cost = 0.0

    for item in sorted(items, key=lambda row: int(row.get("queue_index") or 0)):
        shot_id = str(item.get("shot_id") or "")
        treatment = str(item.get("final_budget_treatment") or "").upper()
        coverage = round(float(item.get("end_seconds")) - float(item.get("start_seconds")), 3)
        if coverage <= 0:
            raise MediaCostPreflightError("INVALID_SHOT_COVERAGE:" + shot_id)
        planning_id: str | None = None
        if treatment == "GENERATED_VIDEO":
            # Provider duration is derived from the authoritative timeline
            # interval.  The old fixed 8-second fallback was a transport
            # shortcut and caused paid unused duration; it is no longer used.
            if provider_request_fallback_max_seconds is not None:
                # Historical fixture compatibility only; canonical V2 callers
                # pass None and therefore use the contract-derived duration.
                requested_for_timeline = int(provider_request_fallback_max_seconds)
            else:
                if coverage > 8.0 + 1e-9:
                    raise MediaCostPreflightError(
                        "VIDEO_INTERVAL_REQUIRES_DISTINCT_PROVIDER_UNITS:" + shot_id
                    )
                requested_for_timeline = max(1, int(math.ceil(coverage - 1e-9)))
            planning_id = _planning_identity(episode_id, shot_id, item)
            task = _video_task(
                episode_id,
                item,
                planning_id,
                requested_seconds=requested_for_timeline,
            )
            validated = validate_runware_task(task)
            requested = int(task["duration"])
            provider = validated.provider
            model = validated.model
            media_kind = "RUNWARE_VIDEO"
            generated_seconds += coverage
            requested_seconds += requested
        elif treatment == "ANIMATED_STILL_COMPOSITING":
            route = route_image_shot(item)
            planning_id = _planning_identity(episode_id, shot_id, item)
            task = build_runware_image_task(
                item,
                planning_id,
            )
            validated = validate_runware_task(task)
            requested = 0
            provider = validated.provider
            model = validated.model
            media_kind = "RUNWARE_IMAGE"
        elif treatment == "GRAPHICS":
            if not isinstance(item.get("graphics_spec"), Mapping):
                raise MediaCostPreflightError("GRAPHICS_SPEC_REQUIRED:" + shot_id)
            task = None
            requested = 0
            provider = "LOCAL"
            model = "PYSIDE6_QT_QUICK_QML_FFMPEG"
            media_kind = "LOCAL_GRAPHICS"
        else:
            raise MediaCostPreflightError("UNSUPPORTED_VISUAL_TREATMENT:" + shot_id + ":" + treatment)

        if media_kind == "RUNWARE_VIDEO":
            # A planning identity is unique by design; duplicate protection must
            # compare the provider-bound direction without that identity or shot id.
            comparable_task = {
                key: value for key, value in (task or {}).items() if key != "taskUUID"
            }
            comparable_fingerprint = canonical_sha256(comparable_task)
            if comparable_fingerprint in payload_fingerprints:
                raise MediaCostPreflightError("REPEATED_VIDEO_PLANNING_PAYLOAD:" + shot_id)
            payload_fingerprints.add(comparable_fingerprint)
        amount = item.get("expected_cost_usd")
        if isinstance(amount, (int, float)) and not isinstance(amount, bool):
            known_cost += float(amount)
        elif media_kind != "LOCAL_GRAPHICS":
            unknown_price_count += 1
        counts[media_kind] += 1
        units.append(
            {
                "shot_id": shot_id,
                "queue_index": item.get("queue_index"),
                "media_kind": media_kind,
                "provider": provider,
                "model": model,
                "timeline_coverage_seconds": coverage,
                "provider_requested_seconds": requested,
                "timeline_required_seconds": coverage,
                "expected_usable_seconds": coverage,
                "expected_unused_seconds": round(requested - coverage, 3),
                "planning_identity": planning_id,
                "provider_submission": False,
                "paid_attempt_created": False,
                "expected_cost_usd": float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) else None,
                "payload_sha256": canonical_sha256(task) if task is not None else None,
                "route": asdict(route) if treatment == "ANIMATED_STILL_COMPOSITING" else None,
            }
        )

    summary = {
        "generated_video_seconds": round(generated_seconds, 3),
        "generated_video_ratio": round(generated_seconds / episode_duration, 9),
        "provider_requested_seconds": round(requested_seconds, 3),
        "planned_provider_requests": counts["RUNWARE_IMAGE"] + counts["RUNWARE_VIDEO"],
        "planned_image_requests": counts["RUNWARE_IMAGE"],
        "planned_video_requests": counts["RUNWARE_VIDEO"],
        "planned_local_graphics": counts["LOCAL_GRAPHICS"],
        "known_estimated_cost_usd": round(known_cost, 8),
        "unknown_provider_price_item_count": unknown_price_count,
    }
    return units, summary


def compute_media_cost_preflight(
    repo_root: Path,
    episode_id: str,
    *,
    state: DesktopEpisodeState | None = None,
) -> dict[str, Any]:
    """Compute a complete local plan without writing or contacting providers."""

    repo = Path(repo_root).resolve()
    state = state or read_desktop_episode_state(repo, episode_id)
    if state.current_stage != MEDIA_COST_PREFLIGHT:
        raise MediaCostPreflightError("INVALID_CURRENT_STAGE:" + state.current_stage)
    paths = _input_paths(repo, episode_id)
    storyboard = _read_mapping(paths["storyboard"])
    timeline = _read_mapping(paths["timeline"])
    overlay = _read_mapping(paths["overlay"])
    plan = _read_mapping(paths["plan"])
    policy = _read_mapping(paths["policy"])
    if policy.get("status") != "ACTIVE":
        raise MediaCostPreflightError("MEDIA_POLICY_NOT_ACTIVE")
    legacy_policy_mode = policy.get("schema_version") != "siraj-cinematic-media-mix-policy-v2"
    if legacy_policy_mode:
        # Compatibility-only path for isolated historical fixtures.  The
        # canonical repository always has the V2 policy artifact above.
        try:
            generated_video_min_ratio = 0.0
            generated_video_max_ratio = float(policy["generated_video_max_ratio"])
            selection_mode = "LEGACY_FIXTURE_COMPATIBILITY_ONLY"
            provider_request_fallback = float(policy["provider_request_fallback_max_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MediaCostPreflightError("MEDIA_POLICY_NUMERIC_FIELDS_INVALID") from exc
        if not 0 < generated_video_max_ratio <= 1:
            raise MediaCostPreflightError("MEDIA_POLICY_VIDEO_CEILING_INVALID")
        if not provider_request_fallback.is_integer() or not 0 < provider_request_fallback <= 8:
            raise MediaCostPreflightError("MEDIA_POLICY_PROVIDER_REQUEST_UNIT_INVALID")
    else:
        try:
            generated_video_min_ratio = float(policy["min_true_video_fraction"])
            generated_video_max_ratio = float(policy["max_true_video_fraction"])
            selection_mode = str(policy["selection_mode"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MediaCostPreflightError("MEDIA_POLICY_NUMERIC_FIELDS_INVALID") from exc
        if not MIN_TRUE_VIDEO_FRACTION <= generated_video_min_ratio <= MAX_TRUE_VIDEO_FRACTION:
            raise MediaCostPreflightError("MEDIA_POLICY_VIDEO_FLOOR_INVALID")
        if not generated_video_min_ratio <= generated_video_max_ratio <= MAX_TRUE_VIDEO_FRACTION:
            raise MediaCostPreflightError("MEDIA_POLICY_VIDEO_CEILING_INVALID")
    if canonical_sha256(overlay) != EXPECTED_OVERLAY_SHA256:
        raise MediaCostPreflightError("PROMOTED_OVERLAY_HASH_MISMATCH")
    if _required_structural_fingerprint_local(storyboard) != EXPECTED_STRUCTURAL_FINGERPRINT:
        raise MediaCostPreflightError("AUTHORITATIVE_STRUCTURAL_FINGERPRINT_MISMATCH")
    if plan.get("creative_overlay_sha256") != EXPECTED_OVERLAY_SHA256:
        raise MediaCostPreflightError("PROMPT_PLAN_OVERLAY_HASH_MISMATCH")
    items = plan.get("items")
    if not isinstance(items, list) or len(items) != 55:
        raise MediaCostPreflightError("PROMPT_PLAN_ITEMS_REQUIRED")
    _structural_join_check(items, storyboard)
    duration = float(timeline.get("total_duration_seconds"))
    if duration != 623.584:
        raise MediaCostPreflightError("AUTHORITATIVE_DURATION_MISMATCH")
    units, summary = _planned_units(
        repo,
        episode_id,
        items,
        episode_duration=duration,
        provider_request_fallback_max_seconds=(
            int(provider_request_fallback) if legacy_policy_mode else None
        ),
    )
    ceiling = duration * generated_video_max_ratio
    coverage = validate_true_video_coverage(duration, summary["generated_video_seconds"])
    if legacy_policy_mode:
        if summary["generated_video_seconds"] > ceiling + 1e-9:
            raise MediaCostPreflightError("GENERATED_VIDEO_LEGACY_CEILING_EXCEEDED")
    elif coverage.status != "PASS":
        raise MediaCostPreflightError(coverage.reason or coverage.status)
    input_refs = {
        key: artifact_reference(path, base=repo)
        for key, path in paths.items()
        if path.is_file()
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "episode_id": episode_id,
        "stage": MEDIA_COST_PREFLIGHT,
        "created_at_utc": utc_now(),
        "authoritative_state": {
            "ledger_head_sha256": state.ledger_head_sha256,
            "current_stage": state.current_stage,
            "promoted_overlay_sha256": EXPECTED_OVERLAY_SHA256,
            "structural_fingerprint": EXPECTED_STRUCTURAL_FINGERPRINT,
            "duration_seconds": duration,
            "shot_count": 55,
            "timeline_discontinuities": 0,
        },
        "input_artifacts": input_refs,
        "media_policy": {
            "policy_id": policy.get("policy_id") or "LEGACY_FIXTURE_COMPATIBILITY_ONLY",
            "schema_version": policy.get("schema_version"),
            "min_true_video_fraction": generated_video_min_ratio,
            "generated_video_max_ratio": generated_video_max_ratio,
            "max_true_video_fraction": generated_video_max_ratio,
            "selection_mode": selection_mode,
            "two_thirds_policy_active": legacy_policy_mode,
            "long_scene_strategy": "PROGRESSIVE_DISTINCT_SUBSHOTS",
            "automatic_paid_retry": False,
        },
        "summary": summary,
        "generated_video_floor_seconds": round(duration * generated_video_min_ratio, 3),
        "generated_video_ceiling_seconds": round(ceiling, 3),
        "cost_status": "UNKNOWN_PROVIDER_PRICE_NO_NETWORK_LOOKUP" if summary["unknown_provider_price_item_count"] else "KNOWN_LOCAL_PRICES",
        "cost_envelope_usd": {"lower_bound": 0.0, "upper_bound": None if summary["unknown_provider_price_item_count"] else summary["known_estimated_cost_usd"]},
        "units": units,
        "paid_attempts_created": 0,
        "provider_calls": 0,
        "next_stage": NEXT_STAGE,
        "next_stage_executed": False,
        "production_resume_entrypoint": "DESKTOP_UI_ONLY",
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }
    result["result_sha256"] = canonical_sha256(result)
    return result


def _required_structural_fingerprint_local(storyboard: Mapping[str, Any]) -> str:
    structures = structural_shots_from_storyboard(storyboard)
    manifest = [
        {
            "shot_id": item.shot_id,
            "queue_order": item.queue_index,
            "start_seconds": item.start_ms / 1000.0,
            "end_seconds": item.end_ms / 1000.0,
            "segment_ids": list(item.segment_ids),
            "beat_id": item.beat_id,
        }
        for item in structures
    ]
    return canonical_sha256(manifest)


class CanonicalMediaCostPreflightExecutor:
    """Transactional executor; no provider transport is reachable here."""

    def __init__(
        self,
        repo_root: Path,
        episode_id: str = EPISODE_002,
        *,
        result_writer: Callable[[Path, Mapping[str, Any]], None] = write_new_json,
        failure_writer: Callable[[Path, Mapping[str, Any]], None] = write_new_json,
        ledger_appender: Callable[..., dict[str, Any]] = append_transition_if_head,
        preflight_builder: Callable[..., dict[str, Any]] = compute_media_cost_preflight,
        input_paths_provider: Callable[[Path, str], Sequence[Path]] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id
        self.result_writer = result_writer
        self.failure_writer = failure_writer
        self.ledger_appender = ledger_appender
        self.preflight_builder = preflight_builder
        self.input_paths_provider = input_paths_provider

    @property
    def result_path(self) -> Path:
        return self.repo_root / "projects" / self.episode_id / "orchestration" / "media-cost-preflight-v1.json"

    def _verify_intent(self, intent: DesktopResumeIntent, authorization: Mapping[str, Any]) -> DesktopEpisodeState:
        if intent.source != DESKTOP_SOURCE:
            raise MediaCostPreflightError("PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY")
        if intent.episode_id != self.episode_id:
            raise MediaCostPreflightError("RESUME_EPISODE_MISMATCH")
        if intent.first_stage != MEDIA_COST_PREFLIGHT:
            raise MediaCostPreflightError("INVALID_RESUME_STAGE:" + intent.first_stage)
        if (
            authorization.get("source") != DESKTOP_SOURCE
            or authorization.get("scope") != LOCAL_AUTH_SCOPE
            or authorization.get("episode_id") != self.episode_id
            or authorization.get("paid_operation") is not False
            or authorization.get("provider_calls") != 0
        ):
            raise MediaCostPreflightError("DESKTOP_LOCAL_AUTHORIZATION_INVALID")
        state = read_desktop_episode_state(self.repo_root, self.episode_id)
        if state.ledger_head_sha256 != intent.ledger_head_sha256:
            raise MediaCostPreflightError("AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED")
        if state.promoted_overlay_sha256 != intent.promoted_overlay_sha256:
            raise MediaCostPreflightError("REVIEWED_OVERLAY_CHANGED")
        if state.authoritative_structural_fingerprint != intent.structural_fingerprint:
            raise MediaCostPreflightError("REVIEWED_STRUCTURAL_FINGERPRINT_CHANGED")
        return state

    def _failure_evidence(
        self,
        tx_id: str,
        classification: str,
        message: str,
        state: DesktopEpisodeState | None,
        *,
        result_path: Path,
    ) -> Path:
        path = result_path.with_name(f"media-cost-preflight-failure-{tx_id}.json")
        payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "FAILED",
            "episode_id": self.episode_id,
            "stage": MEDIA_COST_PREFLIGHT,
            "transaction_id": tx_id,
            "failure_classification": classification,
            "error": message,
            "reviewed_ledger_head_sha256": state.ledger_head_sha256 if state else None,
            "provider_calls": 0,
            "paid_attempts_created": 0,
            "next_stage_executed": False,
            "created_at_utc": utc_now(),
        }
        self.failure_writer(path, payload)
        return path

    @staticmethod
    def _validate_result_record(result: Mapping[str, Any]) -> None:
        if result.get("schema_version") != SCHEMA_VERSION:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_SCHEMA_INVALID")
        if result.get("stage") != MEDIA_COST_PREFLIGHT:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_STAGE_INVALID")
        if result.get("provider_calls") != 0 or result.get("paid_attempts_created") != 0:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_PAID_ACTIVITY_INVALID")
        if result.get("next_stage_executed") is not False:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_DOWNSTREAM_EXECUTION_INVALID")
        expected = canonical_sha256(
            {key: value for key, value in result.items() if key != "result_sha256"}
        )
        if result.get("result_sha256") != expected:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_HASH_INVALID")

    def execute(
        self,
        intent: DesktopResumeIntent,
        *,
        authorization: Mapping[str, Any],
        result_path: Path | None = None,
    ) -> MediaCostPreflightOutcome:
        result_path = Path(result_path) if result_path is not None else self.result_path
        transaction_id = "desktop-preflight-" + uuid.uuid4().hex
        state: DesktopEpisodeState | None = None
        started_entry: dict[str, Any] | None = None
        try:
            state = self._verify_intent(intent, authorization)
            if result_path.exists():
                raise MediaCostPreflightError("PREFLIGHT_RESULT_ALREADY_EXISTS_FAIL_CLOSED")
            if self.input_paths_provider is None:
                input_paths = tuple(_input_paths(self.repo_root, self.episode_id).values())
            else:
                input_paths = tuple(self.input_paths_provider(self.repo_root, self.episode_id))
            input_refs = [artifact_reference(path, base=self.repo_root) for path in input_paths if path.is_file()]
            started_entry = self.ledger_appender(
                self.repo_root,
                self.episode_id,
                expected_ledger_sha256=intent.ledger_head_sha256,
                stage=MEDIA_COST_PREFLIGHT,
                previous_stage="PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
                status="STARTED",
                input_artifacts=input_refs,
                authorization_references=[dict(authorization)],
                schema_versions=[SCHEMA_VERSION],
                metadata={
                    "event": "DESKTOP_MEDIA_COST_PREFLIGHT_STARTED",
                    "transaction_id": transaction_id,
                    "expected_previous_ledger_head_sha256": intent.ledger_head_sha256,
                    "provider_calls": 0,
                },
            )
            started_head = sha256_file(Path(state.ledger_path))
            result = self.preflight_builder(self.repo_root, self.episode_id, state=state)
            result["transaction_id"] = transaction_id
            result["status"] = "PERSISTED_AWAITING_TRANSITION_COMMIT"
            existing_authorization = result.get("authorization")
            if isinstance(existing_authorization, Mapping) and existing_authorization.get(
                "master_authorization_status_for_new_plan"
            ):
                result["preflight_authorization"] = dict(existing_authorization)
            result["execution_authorization"] = dict(authorization)
            if not isinstance(existing_authorization, Mapping) or not existing_authorization.get(
                "master_authorization_status_for_new_plan"
            ):
                result["authorization"] = dict(authorization)
            result["started_transition_id"] = started_entry.get("transition_id")
            result["expected_previous_ledger_head_sha256"] = intent.ledger_head_sha256
            result["ledger_head_after_start_sha256"] = started_head
            result["result_sha256"] = canonical_sha256({key: value for key, value in result.items() if key != "result_sha256"})
            self.result_writer(result_path, result)
            persisted_ref = artifact_reference(result_path, base=self.repo_root)
            persisted_ref["logical_output"] = "MEDIA_COST_PREFLIGHT_RESULT"
            self.ledger_appender(
                self.repo_root,
                self.episode_id,
                expected_ledger_sha256=started_head,
                stage=MEDIA_COST_PREFLIGHT,
                previous_stage="PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
                status="COMPLETED",
                input_artifacts=input_refs,
                output_artifacts=[persisted_ref],
                authorization_references=[dict(authorization)],
                schema_versions=[SCHEMA_VERSION],
                metadata={
                    "event": "DESKTOP_MEDIA_COST_PREFLIGHT_COMPLETED",
                    "transaction_id": transaction_id,
                    "expected_previous_ledger_head_sha256": started_head,
                    "result_sha256": result["result_sha256"],
                    "next_stage_projection": NEXT_STAGE,
                    "next_stage_executed": False,
                    "provider_calls": 0,
                },
            )
            final_head = sha256_file(Path(state.ledger_path))
            return MediaCostPreflightOutcome(
                status="PASS",
                episode_id=self.episode_id,
                stage=MEDIA_COST_PREFLIGHT,
                next_stage=NEXT_STAGE,
                next_stage_executed=False,
                result_path=str(result_path),
                result_sha256=result["result_sha256"],
                ledger_head_sha256=final_head,
                provider_calls=0,
                paid_attempts_created=0,
            )
        except Exception as exc:
            classification = str(exc).split(":", 1)[0]
            persisted_result_is_valid = False
            if result_path.is_file():
                try:
                    self._validate_result_record(_read_mapping(result_path))
                    persisted_result_is_valid = True
                except Exception:
                    persisted_result_is_valid = False
            if started_entry is not None and not persisted_result_is_valid:
                failure_commit_error: Exception | None = None
                try:
                    failure_path = self._failure_evidence(
                        transaction_id,
                        classification,
                        str(exc),
                        state,
                        result_path=result_path,
                    )
                    current_head = sha256_file(Path(state.ledger_path)) if state else ""
                    self.ledger_appender(
                        self.repo_root,
                        self.episode_id,
                        expected_ledger_sha256=current_head,
                        stage=MEDIA_COST_PREFLIGHT,
                        previous_stage="PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
                        status="FAILED",
                        output_artifacts=[
                            {
                                **artifact_reference(failure_path, base=self.repo_root),
                                "logical_output": "MEDIA_COST_PREFLIGHT_FAILURE_EVIDENCE",
                            }
                        ],
                        authorization_references=[dict(authorization)],
                        schema_versions=[SCHEMA_VERSION],
                        failure_classification=classification,
                        metadata={"event": "DESKTOP_MEDIA_COST_PREFLIGHT_FAILED", "transaction_id": transaction_id, "provider_calls": 0},
                    )
                except Exception as failure_exc:
                    failure_commit_error = failure_exc
                if failure_commit_error is not None:
                    raise MediaCostPreflightError(
                        "FAILURE_EVIDENCE_OR_LEDGER_COMMIT_FAILED:"
                        + str(failure_commit_error)
                    ) from exc
            raise

    def recover(self, *, result_path: Path | None = None) -> MediaCostPreflightOutcome:
        """Detect persisted-but-uncommitted output without recomputing it."""

        path = Path(result_path) if result_path is not None else self.result_path
        if not path.is_file():
            return MediaCostPreflightOutcome(
                status="NO_PERSISTED_RESULT",
                episode_id=self.episode_id,
                stage=MEDIA_COST_PREFLIGHT,
                next_stage=MEDIA_COST_PREFLIGHT,
                next_stage_executed=False,
                result_path=None,
                result_sha256=None,
                ledger_head_sha256=None,
                provider_calls=0,
                paid_attempts_created=0,
            )
        result = _read_mapping(path)
        self._validate_result_record(result)
        if result.get("episode_id") != self.episode_id:
            raise MediaCostPreflightError("PREFLIGHT_RESULT_EPISODE_INVALID")
        state = project_state(self.repo_root, self.episode_id)
        entries = read_entries(self.repo_root, self.episode_id)
        transaction_id = str(result.get("transaction_id") or "")
        started = [
            entry
            for entry in entries
            if entry.get("stage") == MEDIA_COST_PREFLIGHT
            and entry.get("status") == "STARTED"
            and entry.get("metadata", {}).get("transaction_id") == transaction_id
        ]
        completed = [
            entry
            for entry in entries
            if entry.get("stage") == MEDIA_COST_PREFLIGHT
            and entry.get("status") == "COMPLETED"
            and entry.get("metadata", {}).get("transaction_id") == transaction_id
        ]
        if state.current_stage == MEDIA_COST_PREFLIGHT and state.status == "RUNNING" and result.get("status") == "PERSISTED_AWAITING_TRANSITION_COMMIT":
            if len(started) != 1 or completed:
                raise MediaCostPreflightError("PREFLIGHT_RECOVERY_PROVENANCE_INVALID")
            return MediaCostPreflightOutcome(
                status="RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED",
                episode_id=self.episode_id,
                stage=MEDIA_COST_PREFLIGHT,
                next_stage=MEDIA_COST_PREFLIGHT,
                next_stage_executed=False,
                result_path=str(path),
                result_sha256=str(result.get("result_sha256") or ""),
                ledger_head_sha256=sha256_file(Path(readiness_paths(self.repo_root, self.episode_id)["ledger"])),
                provider_calls=0,
                paid_attempts_created=0,
                recovery_action="HUMAN_REVIEW_REQUIRED_NO_RERUN",
            )
        if state.current_stage == NEXT_STAGE and state.status == "READY":
            if result.get("status") != "PERSISTED_AWAITING_TRANSITION_COMMIT":
                raise MediaCostPreflightError("PREFLIGHT_RESULT_STATUS_INVALID")
            if len(started) != 1 or len(completed) != 1:
                raise MediaCostPreflightError("PREFLIGHT_COMPLETION_PROVENANCE_INVALID")
            output_refs = completed[0].get("output_artifacts") or []
            result_ref = next(
                (ref for ref in output_refs if str(ref.get("path", "")).endswith(path.name)),
                None,
            )
            if result_ref is None or result_ref.get("sha256") != sha256_file(path):
                raise MediaCostPreflightError("PREFLIGHT_RESULT_ARTIFACT_HASH_INVALID")
            return MediaCostPreflightOutcome(
                status="ALREADY_COMMITTED",
                episode_id=self.episode_id,
                stage=MEDIA_COST_PREFLIGHT,
                next_stage=NEXT_STAGE,
                next_stage_executed=False,
                result_path=str(path),
                result_sha256=str(result.get("result_sha256") or ""),
                ledger_head_sha256=sha256_file(Path(readiness_paths(self.repo_root, self.episode_id)["ledger"])),
                provider_calls=0,
                paid_attempts_created=0,
            )
        raise MediaCostPreflightError("PREFLIGHT_RECOVERY_STATE_UNRECONCILED")
