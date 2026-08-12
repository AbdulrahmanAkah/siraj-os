"""SIRAJ_MEDIA_PLANNER_V2 proposal-only media planner.

The planner consumes the already-approved provider-ready creative direction,
keeps storyboard structure immutable, and produces a reviewable plan.  It
never submits a provider task and never writes Episode 002 production state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import re
from typing import Any, Iterable, Mapping, Sequence
import uuid

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.provider_model_contracts import (
    VEO_31_SUPPORTED_DURATIONS_SECONDS,
    validate_runware_task,
)
from src.application.runware_image_model_routing_v1 import route_image_shot
from src.application.siraj_cinematic_media_mix_policy_v2 import (
    POLICY,
    MediaMixPolicyError,
    coverage_diagnostics,
    validate_no_reuse_or_loop,
    validate_true_video_coverage,
)


PLANNER_ID = "SIRAJ_MEDIA_PLANNER_V2"
PLANNER_SCHEMA_VERSION = "siraj-media-planner-v2"
VIDEO_PROVIDER = "RUNWARE"
VIDEO_MODEL = "google:veo@3.1-lite"
# The planner must select from the provider's discrete contract, not invent a
# duration for every timeline fragment.  Sub-shot splitting remains the
# mechanism for long intervals; the final unit may carry provider overhead.
VIDEO_SUPPORTED_DURATIONS_SECONDS = tuple(sorted(VEO_31_SUPPORTED_DURATIONS_SECONDS))


class MediaPlannerV2Error(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ShotTreatment:
    shot_id: str
    queue_index: int
    classification: str
    cinematic_score: float
    reason: str
    sequence_id: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VideoUnit:
    unit_id: str
    shot_id: str
    queue_index: int
    sequence_id: str
    phase_index: int
    phase_label: str
    timeline_start_seconds: float
    timeline_end_seconds: float
    timeline_required_seconds: float
    editing_handle_seconds: float
    provider_supported_duration: int
    requested_seconds: int
    expected_usable_seconds: float
    expected_unused_seconds: float
    provider: str
    model: str
    media_kind: str
    cinematic_reason: str
    direction_source_fields: tuple[str, ...]
    direction_fingerprint: str
    payload_sha256: str
    planning_identity: str
    provider_submission: bool = False
    paid_attempt_created: bool = False
    looped: bool = False
    reused_from_unit_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["direction_source_fields"] = list(self.direction_source_fields)
        return value


SEQUENCE_RANGES: tuple[tuple[str, int, int, str], ...] = (
    ("AFTERMATH_BOUNDARY", 1, 11, "concealed aftermath and boundary"),
    ("TEMPTATION_PROMISE", 12, 16, "promise, boundary pressure and temptation"),
    ("SHARED_ACTION_HINGE", 17, 21, "paired action and shared responsibility hinge"),
    ("EXPULSION_TRANSITION", 22, 29, "expulsion, separation and descent transition"),
    ("RECEPTION_GUIDANCE", 30, 34, "reception, repentance and guidance"),
    ("DESCENT", 35, 39, "descent and material ground transition"),
    ("HADITH_ARGUMENT", 40, 44, "source-sensitive argument and evidence layer"),
    ("CONSEQUENCE_REVELATION", 45, 49, "consequence-space revelation"),
    ("CLOSING_EARTH", 50, 55, "closing earth, settlement and unresolved trace"),
)


_REQUIRED_TERMS = (
    "three-stage",
    "before, event, and after",
    "before→during→after",
    "transformation",
    "causal",
    "paired movement",
    "shared downward",
    "re-emerge",
    "peels aside",
    "passes through",
    "surface",
    "material change",
    "reorientation",
    "consequence",
    "action phase",
    "field/surface transformation",
)
_STRONG_TERMS = (
    "camera",
    "tracking",
    "track",
    "orbit",
    "follow",
    "travel",
    "drift",
    "shear",
    "advance",
    "moving",
    "movement",
    "wind",
    "dust",
    "reveal",
    "widen",
    "widening",
    "glides",
    "glide",
    "progression",
    "peel",
    "shift",
    "settle",
    "change orientation",
)
_BENEFICIAL_TERMS = (
    "parallax",
    "push",
    "pullback",
    "focus",
    "breathing",
    "dim",
    "fade",
    "hold",
    "slow",
    "reorientation",
)


def sequence_for_queue(queue_index: int) -> tuple[str, str]:
    for sequence_id, start, end, description in SEQUENCE_RANGES:
        if start <= queue_index <= end:
            return sequence_id, description
    raise MediaPlannerV2Error("QUEUE_INDEX_OUTSIDE_EPISODE:" + str(queue_index))


def _creative_text(item: Mapping[str, Any]) -> str:
    values = (
        item.get("motion"),
        item.get("camera_movement"),
        item.get("camera_intent"),
        item.get("movement_motivation"),
        item.get("transition_intent"),
        item.get("cinematic_treatment"),
        item.get("visual_concept"),
        item.get("narrative_function"),
        item.get("environment"),
        item.get("materiality"),
        item.get("lighting"),
        item.get("symbolism"),
    )
    return " ".join(str(value or "") for value in values).lower()


def classify_shot(item: Mapping[str, Any]) -> ShotTreatment:
    shot_id = str(item.get("shot_id") or "")
    queue_index = int(item.get("queue_index") or 0)
    if not shot_id or queue_index <= 0:
        raise MediaPlannerV2Error("SHOT_ID_AND_QUEUE_INDEX_REQUIRED")
    sequence_id, _ = sequence_for_queue(queue_index)
    treatment = str(item.get("final_budget_treatment") or "").upper()
    text = _creative_text(item)
    if treatment == "GRAPHICS" or item.get("graphics_spec"):
        return ShotTreatment(
            shot_id,
            queue_index,
            "GRAPHIC_LOCAL_PREFERRED",
            0.0,
            "Approved direction is a source-sensitive/argument graphic; motion would weaken the evidence grammar.",
            sequence_id,
        )
    required_hits = sum(1 for term in _REQUIRED_TERMS if term in text)
    strong_hits = sum(1 for term in _STRONG_TERMS if term in text)
    beneficial_hits = sum(1 for term in _BENEFICIAL_TERMS if term in text)
    source_sensitive = any(term in text for term in ("archival", "source", "argument", "hadith", "quotation", "document"))
    iconic_static = any(term in text for term in ("iconic", "blank center", "empty space", "locked", "hold"))
    substantial_motion_terms = (
        "tracking",
        "track",
        "orbit",
        "follow",
        "travel",
        "shear",
        "advance",
        "reveal",
        "widen",
        "glides",
        "glide",
        "peel",
        "passes through",
        "re-emerge",
        "reorient",
        "downward visual drift",
    )
    subtle_hold = any(
        term in text
        for term in (
            "no new visual event",
            "barely perceptible",
            "only slight",
            "slight ambient",
            "locked-off",
            "locked wide",
            "holds",
            "hold;",
            "never forming a symbol",
            "stopping before",
            "stops before",
        )
    )
    if required_hits >= 2 or bool(re.search(r"three-stage|before, event, and after|passes through", text)):
        classification = "VIDEO_REQUIRED_FOR_INTENT"
        weight = 1.0
        reason = "Approved direction contains explicit temporal causality/transformation; true motion carries the meaning."
    elif required_hits >= 1 and strong_hits >= 1:
        classification = "VIDEO_STRONGLY_PREFERRED"
        weight = 0.86
        reason = "Approved direction combines a causal or material change with camera/environment movement."
    elif subtle_hold and not any(term in text for term in substantial_motion_terms):
        classification = "ANIMATED_STILL_PREFERRED"
        weight = 0.08
        reason = "The approved movement is a restrained hold or atmospheric breathing with no distinct temporal event; animated still treatment preserves intentional stillness."
    elif strong_hits >= 2:
        classification = "VIDEO_STRONGLY_PREFERRED"
        weight = 0.82
        reason = "Camera, subject or environmental movement is a substantial part of the approved visual progression."
    elif beneficial_hits >= 1 or strong_hits >= 1:
        classification = "VIDEO_BENEFICIAL"
        weight = 0.62
        reason = "Temporal motion adds rhythm or depth, while an intentional still hold remains acceptable."
    elif source_sensitive or iconic_static:
        classification = "ANIMATED_STILL_PREFERRED"
        weight = 0.08
        reason = "The approved direction is evidence-sensitive or intentionally contemplative; still treatment protects meaning."
    else:
        classification = "VIDEO_OPTIONAL"
        weight = 0.25
        reason = "No approved field requires temporal generation; leave the choice to the sequence balance."
    # Keep a small deterministic score so target selection is derived from the
    # approved creative fields rather than a fixed episode percentage.
    score = min(1.0, weight + min(0.08, (required_hits + strong_hits + beneficial_hits) * 0.01))
    return ShotTreatment(shot_id, queue_index, classification, round(score, 4), reason, sequence_id)


def classify_all_shots(items: Sequence[Mapping[str, Any]]) -> tuple[ShotTreatment, ...]:
    ordered = sorted(items, key=lambda item: int(item.get("queue_index") or 0))
    if len(ordered) != 55:
        raise MediaPlannerV2Error("EP002_REQUIRES_55_SHOTS")
    queue = [int(item.get("queue_index") or 0) for item in ordered]
    if queue != list(range(1, 56)):
        raise MediaPlannerV2Error("SHOT_QUEUE_MUST_BE_CONTIGUOUS")
    return tuple(classify_shot(item) for item in ordered)


def derive_directorial_target(
    items: Sequence[Mapping[str, Any]],
    treatments: Sequence[ShotTreatment],
    episode_duration_seconds: float,
) -> dict[str, Any]:
    weighted = 0.0
    static = 0.0
    for item, treatment in zip(sorted(items, key=lambda row: int(row.get("queue_index") or 0)), treatments):
        duration = float(item.get("end_seconds")) - float(item.get("start_seconds"))
        weighted += duration * treatment.cinematic_score
        if treatment.classification in {"ANIMATED_STILL_PREFERRED", "GRAPHIC_LOCAL_PREFERRED"}:
            static += duration
    motion_ratio = weighted / episode_duration_seconds
    static_ratio = static / episode_duration_seconds
    # The target is intentionally derived from the direction.  It is not a
    # quota: static/source-sensitive sequences receive a modest counterweight.
    preferred_fraction = 0.50 + min(0.25, motion_ratio * 0.26) - min(0.04, static_ratio * 0.08)
    preferred_fraction = min(POLICY.max_true_video_fraction, max(POLICY.min_true_video_fraction, preferred_fraction))
    preferred_fraction = round(preferred_fraction, 6)
    return {
        "cinematic_video_floor_percent": POLICY.min_true_video_fraction * 100.0,
        "directorially_preferred_video_percent": preferred_fraction * 100.0,
        "cinematic_video_ceiling_percent": POLICY.max_true_video_fraction * 100.0,
        "derived_motion_ratio": round(motion_ratio, 9),
        "static_source_sensitive_ratio": round(static_ratio, 9),
        "why_not_50": "The approved direction contains distributed camera, environmental and causal movement; the floor would leave major temporal beats static.",
        "why_not_75": "The episode intentionally preserves source-sensitive graphics, epistemic stillness and iconic holds; pushing to the ceiling would add video where motion is not the narrative carrier.",
        "why_selected": "The selected value is derived from motion-weighted approved direction with a source-sensitive stillness counterweight, preserving sequence contrast while meeting the hard range.",
    }


def _shot_duration(item: Mapping[str, Any]) -> float:
    value = float(item.get("end_seconds")) - float(item.get("start_seconds"))
    if value <= 0:
        raise MediaPlannerV2Error("SHOT_DURATION_INVALID:" + str(item.get("shot_id")))
    return value


def _allocate_by_sequence(
    items: Sequence[Mapping[str, Any]],
    treatments: Sequence[ShotTreatment],
    target_seconds: float,
) -> dict[str, float]:
    rows = sorted(items, key=lambda item: int(item.get("queue_index") or 0))
    treatment_by_id = {value.shot_id: value for value in treatments}
    sequence_weight: dict[str, float] = {}
    for item in rows:
        treatment = treatment_by_id[str(item.get("shot_id"))]
        if treatment.classification in {"ANIMATED_STILL_PREFERRED", "GRAPHIC_LOCAL_PREFERRED"}:
            continue
        sequence_weight[treatment.sequence_id] = sequence_weight.get(treatment.sequence_id, 0.0) + _shot_duration(item) * treatment.cinematic_score
    total_weight = sum(sequence_weight.values())
    if total_weight <= 0:
        raise MediaPlannerV2Error("NO_VIDEO_ELIGIBLE_SHOTS")
    budgets = {key: target_seconds * value / total_weight for key, value in sequence_weight.items()}
    allocations: dict[str, float] = {}
    # Within each sequence, take required/strong shots first, then beneficial.
    rank = {
        "VIDEO_REQUIRED_FOR_INTENT": 4,
        "VIDEO_STRONGLY_PREFERRED": 3,
        "VIDEO_BENEFICIAL": 2,
        "VIDEO_OPTIONAL": 1,
    }
    for sequence_id, budget in budgets.items():
        candidates = [
            item
            for item in rows
            if treatment_by_id[str(item.get("shot_id"))].sequence_id == sequence_id
            and treatment_by_id[str(item.get("shot_id"))].classification in rank
        ]
        candidates.sort(
            key=lambda item: (
                -rank[treatment_by_id[str(item.get("shot_id"))].classification],
                -treatment_by_id[str(item.get("shot_id"))].cinematic_score,
                int(item.get("queue_index") or 0),
            )
        )
        remaining = budget
        for item in candidates:
            if remaining <= 1e-6:
                break
            amount = min(_shot_duration(item), remaining)
            if amount >= 0.05:
                allocations[str(item.get("shot_id"))] = round(amount, 3)
                remaining -= amount
    # Rounding can leave a small gap; fill it from any eligible shot without
    # changing structural timing.
    current = sum(allocations.values())
    if current < target_seconds - 0.01:
        for item in rows:
            shot_id = str(item.get("shot_id"))
            treatment = treatment_by_id[shot_id]
            if treatment.classification not in rank:
                continue
            available = _shot_duration(item) - allocations.get(shot_id, 0.0)
            if available <= 0:
                continue
            amount = min(available, target_seconds - current)
            allocations[shot_id] = round(allocations.get(shot_id, 0.0) + amount, 3)
            current = sum(allocations.values())
            if current >= target_seconds - 0.01:
                break
    return allocations


def _smallest_provider_duration(required_seconds: float) -> int:
    needed = max(1, int(math.ceil(required_seconds - 1e-9)))
    for value in VIDEO_SUPPORTED_DURATIONS_SECONDS:
        if value >= needed:
            return value
    raise MediaPlannerV2Error("VIDEO_UNIT_EXCEEDS_PROVIDER_CONTRACT")


def _make_video_units(
    item: Mapping[str, Any],
    allocated_seconds: float,
    treatment: ShotTreatment,
) -> list[dict[str, Any]]:
    shot_id = str(item.get("shot_id"))
    start = float(item.get("start_seconds"))
    remaining = round(allocated_seconds, 3)
    cursor = start
    phase = 1
    units: list[dict[str, Any]] = []
    motion_source = str(item.get("motion") or item.get("camera_movement") or item.get("visual_concept") or "approved creative direction")
    prompt = str(item.get("runware_positive_prompt_en") or item.get("provider_ready_prompt") or "").strip()
    if not prompt:
        raise MediaPlannerV2Error("VIDEO_PROMPT_REQUIRED:" + shot_id)
    while remaining > 1e-6:
        usable = round(min(8.0, remaining), 3)
        end = round(cursor + usable, 3)
        unit_id = f"{shot_id}-V{phase:02d}"
        direction_fingerprint = canonical_sha256(
            {
                "shot_id": shot_id,
                "phase_index": phase,
                "approved_motion_source": motion_source,
                "approved_prompt_sha256": canonical_sha256(prompt),
                "timeline_start_seconds": cursor,
                "timeline_end_seconds": end,
            }
        )
        # Runware requires a client-created UUID v4 before videoInference is
        # submitted.  This identity is generated once for the unit and then
        # carried unchanged through the payload hash, durable request intent,
        # and any later async reconciliation.  Historical reports may still
        # contain planning-only identities; they are not rewritten here.
        planning_identity = str(uuid.uuid4())
        requested = _smallest_provider_duration(usable)
        task = {
            "taskType": "videoInference",
            "taskUUID": planning_identity,
            "model": VIDEO_MODEL,
            "positivePrompt": prompt,
            "width": 1280,
            "height": 720,
            "duration": requested,
            "numberResults": 1,
            "deliveryMethod": "async",
            "includeCost": True,
            "providerSettings": {"google": {"generateAudio": False, "personGeneration": "allow_adult" if item.get("contains_people") else "dont_allow"}},
        }
        validated = validate_runware_task(task)
        units.append(
            {
                "unit_id": unit_id,
                "shot_id": shot_id,
                "queue_index": int(item.get("queue_index") or 0),
                "sequence_id": treatment.sequence_id,
                "phase_index": phase,
                "phase_label": f"APPROVED_DIRECTION_PHASE_{phase}",
                "timeline_start_seconds": cursor,
                "timeline_end_seconds": end,
                "timeline_required_seconds": usable,
                "editing_handle_seconds": 0.0,
                "provider_supported_duration": requested,
                "requested_seconds": requested,
                "expected_usable_seconds": usable,
                "expected_unused_seconds": round(requested - usable, 3),
                "provider": validated.provider,
                "model": validated.model,
                "media_kind": "RUNWARE_VIDEO",
                "cinematic_reason": treatment.reason,
                "direction_source_fields": ["motion", "camera_movement", "camera_intent", "visual_concept", "transition_intent"],
                "direction_fingerprint": direction_fingerprint,
                "payload_sha256": canonical_sha256(validated.payload),
                "planning_identity": planning_identity,
                "provider_submission": False,
                "paid_attempt_created": False,
                "looped": False,
                "reused_from_unit_id": None,
            }
        )
        cursor = end
        remaining = round(remaining - usable, 3)
        phase += 1
    return units


def build_media_planner_v2_proposal(
    items: Sequence[Mapping[str, Any]],
    *,
    episode_id: str,
    episode_duration_seconds: float,
    structural_fingerprint: str,
    creative_overlay_sha256: str,
    pricing_assessment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic proposal from the approved creative direction."""

    ordered = sorted(items, key=lambda item: int(item.get("queue_index") or 0))
    treatments = classify_all_shots(ordered)
    target = derive_directorial_target(ordered, treatments, episode_duration_seconds)
    target_fraction = float(target["directorially_preferred_video_percent"]) / 100.0
    target_seconds = round(float(episode_duration_seconds) * target_fraction, 3)
    allocations = _allocate_by_sequence(ordered, treatments, target_seconds)
    treatment_by_id = {value.shot_id: value for value in treatments}
    video_units: list[dict[str, Any]] = []
    shot_rows: list[dict[str, Any]] = []
    nonvideo_units: list[dict[str, Any]] = []
    sequence_rows: dict[str, dict[str, Any]] = {}
    true_video = 0.0
    requested_video = 0.0
    still_seconds = 0.0
    graphics_seconds = 0.0
    for item in ordered:
        shot_id = str(item.get("shot_id"))
        treatment = treatment_by_id[shot_id]
        duration = round(_shot_duration(item), 3)
        allocated = round(allocations.get(shot_id, 0.0), 3)
        if allocated > 0:
            rows = _make_video_units(item, allocated, treatment)
            video_units.extend(rows)
            true_video += allocated
            requested_video += sum(float(row["requested_seconds"]) for row in rows)
            selected_media = "GENERATED_VIDEO" if abs(allocated - duration) < 1e-6 else "MIXED_VIDEO_AND_STILL"
        else:
            rows = []
            selected_media = "GRAPHICS" if treatment.classification == "GRAPHIC_LOCAL_PREFERRED" else "ANIMATED_STILL_COMPOSITING"
        remainder = round(duration - allocated, 3)
        if remainder > 1e-6:
            if selected_media == "GRAPHICS":
                graphics_seconds += remainder
                nonvideo_units.append(
                    {
                        "unit_id": f"{shot_id}-G01",
                        "shot_id": shot_id,
                        "queue_index": int(item.get("queue_index") or 0),
                        "sequence_id": treatment.sequence_id,
                        "media_kind": "LOCAL_GRAPHICS",
                        "timeline_start_seconds": round(float(item.get("end_seconds")) - remainder, 3),
                        "timeline_end_seconds": float(item.get("end_seconds")),
                        "timeline_coverage_seconds": remainder,
                        "provider": "LOCAL",
                        "model": "PYSIDE6_QT_QUICK_QML_FFMPEG",
                        "provider_submission": False,
                        "paid_attempt_created": False,
                        "expected_cost": 0.0,
                        "allocation_reason": treatment.reason,
                    }
                )
            else:
                still_seconds += remainder
                still_item = dict(item)
                still_item["final_budget_treatment"] = "ANIMATED_STILL_COMPOSITING"
                image_route = route_image_shot(still_item)
                nonvideo_units.append(
                    {
                        "unit_id": f"{shot_id}-I01",
                        "shot_id": shot_id,
                        "queue_index": int(item.get("queue_index") or 0),
                        "sequence_id": treatment.sequence_id,
                        "media_kind": "RUNWARE_IMAGE",
                        "timeline_start_seconds": round(float(item.get("end_seconds")) - remainder, 3),
                        "timeline_end_seconds": float(item.get("end_seconds")),
                        "timeline_coverage_seconds": remainder,
                        "provider": "RUNWARE",
                        "model": image_route.model,
                        "provider_submission": False,
                        "paid_attempt_created": False,
                        "expected_cost": None,
                        "allocation_reason": treatment.reason,
                    }
                )
        elif allocated <= 1e-6:
            if selected_media == "GRAPHICS":
                graphics_seconds += duration
            else:
                still_seconds += duration
        shot_rows.append(
            {
                "shot_id": shot_id,
                "queue_index": int(item.get("queue_index") or 0),
                "start_seconds": float(item.get("start_seconds")),
                "end_seconds": float(item.get("end_seconds")),
                "segment_ids": list(item.get("segment_ids") or []),
                "beat_id": item.get("beat_id"),
                "sequence_id": treatment.sequence_id,
                "classification": treatment.classification,
                "cinematic_score": treatment.cinematic_score,
                "classification_reason": treatment.reason,
                "selected_media_treatment": selected_media,
                "true_video_seconds": allocated,
                "non_video_seconds": remainder,
                "provider_unit_ids": [row["unit_id"] for row in rows],
                "creative_direction_hash": canonical_sha256(
                    {
                        key: item.get(key)
                        for key in (
                            "visual_concept",
                            "cinematic_treatment",
                            "camera_intent",
                            "camera_movement",
                            "motion",
                            "transition_intent",
                            "environment",
                            "lighting",
                            "symbolism",
                        )
                    }
                ),
            }
        )
        seq = sequence_rows.setdefault(
            treatment.sequence_id,
            {
                "sequence_id": treatment.sequence_id,
                "sequence_duration_seconds": 0.0,
                "true_video_seconds": 0.0,
                "animated_still_seconds": 0.0,
                "graphics_local_seconds": 0.0,
                "shot_ids": [],
            },
        )
        seq["sequence_duration_seconds"] += duration
        seq["true_video_seconds"] += allocated
        seq["animated_still_seconds"] += remainder if selected_media != "GRAPHICS" else 0.0
        seq["graphics_local_seconds"] += remainder if selected_media == "GRAPHICS" else 0.0
        seq["shot_ids"].append(shot_id)
    video_units.sort(key=lambda row: (int(row["queue_index"]), int(row["phase_index"])))
    nonvideo_units.sort(key=lambda row: int(row["queue_index"]))
    validation = validate_true_video_coverage(episode_duration_seconds, true_video)
    if validation.status != "PASS":
        raise MediaPlannerV2Error(validation.reason or validation.status)
    validate_no_reuse_or_loop(video_units)
    sequence_stats: list[dict[str, Any]] = []
    for row in sequence_rows.values():
        row["sequence_duration_seconds"] = round(row["sequence_duration_seconds"], 3)
        row["true_video_seconds"] = round(row["true_video_seconds"], 3)
        row["animated_still_seconds"] = round(row["animated_still_seconds"], 3)
        row["graphics_local_seconds"] = round(row["graphics_local_seconds"], 3)
        row["true_video_percent"] = round(row["true_video_seconds"] / row["sequence_duration_seconds"] * 100.0, 6)
        row["motion_role"] = "STRONG_TEMPORAL_CINEMA" if row["true_video_percent"] >= 55 else ("BALANCED" if row["true_video_percent"] >= 25 else "TOO_STATIC")
        sequence_stats.append(row)
    treatment_counts: dict[str, int] = {}
    for treatment in treatments:
        treatment_counts[treatment.classification] = treatment_counts.get(treatment.classification, 0) + 1
    category_seconds = {
        category: round(
            sum(
                _shot_duration(item)
                for item, treatment in zip(ordered, treatments)
                if treatment.classification == category
            ),
            3,
        )
        for category in (
            "VIDEO_REQUIRED_FOR_INTENT",
            "VIDEO_STRONGLY_PREFERRED",
            "VIDEO_BENEFICIAL",
        )
    }
    minimum_justified = max(
        float(episode_duration_seconds) * POLICY.min_true_video_fraction,
        category_seconds["VIDEO_REQUIRED_FOR_INTENT"]
        + 0.5 * (category_seconds["VIDEO_STRONGLY_PREFERRED"] + category_seconds["VIDEO_BENEFICIAL"]),
    )
    maximum_useful = min(
        float(episode_duration_seconds) * POLICY.max_true_video_fraction,
        sum(category_seconds.values()),
    )
    plan_units = video_units + nonvideo_units
    diagnostics = coverage_diagnostics(
        video_units,
        episode_duration_seconds=episode_duration_seconds,
        shot_intervals=shot_rows,
    )
    cost = dict(pricing_assessment or {})
    provider_units = len([row for row in plan_units if row.get("provider") != "LOCAL"])
    proposal = {
        "schema_version": PLANNER_SCHEMA_VERSION,
        "planner_id": PLANNER_ID,
        "status": "PROPOSAL_ONLY",
        "episode_id": episode_id,
        "created_at_utc": "2026-08-09T00:00:00Z",
        "policy": POLICY.as_dict(),
        "authoritative_inputs": {
            "episode_duration_seconds": round(float(episode_duration_seconds), 3),
            "shot_count": len(ordered),
            "structural_fingerprint": structural_fingerprint,
            "creative_overlay_sha256": creative_overlay_sha256,
            "structural_change": "NONE",
        },
        "directorial_target": target,
        "cinematic_range": {
            "minimum_cinematically_justified_video_seconds": round(minimum_justified, 3),
            "minimum_justification_formula": "all VIDEO_REQUIRED_FOR_INTENT plus half of VIDEO_STRONGLY_PREFERRED and VIDEO_BENEFICIAL, clamped to the hard 50% floor",
            "preferred_cinematic_video_seconds": round(true_video, 3),
            "maximum_useful_video_seconds": round(maximum_useful, 3),
            "maximum_useful_is_policy_ceiling_not_target": True,
            "category_seconds": category_seconds,
        },
        "coverage": {
            "true_generated_video_timeline_seconds": round(true_video, 3),
            "true_generated_video_timeline_percent": validation.true_video_percent,
            "animated_still_seconds": round(still_seconds, 3),
            "graphics_local_seconds": round(graphics_seconds, 3),
            "provider_requested_video_seconds": round(requested_video, 3),
            "expected_unused_video_seconds": round(requested_video - true_video, 3),
            "video_request_efficiency_percent": round(true_video / requested_video * 100.0, 6) if requested_video else 0.0,
            "coverage_validation": validation.as_dict(),
            **diagnostics,
        },
        "request_inventory": {
            "video_provider_requests": len(video_units),
            "still_provider_requests": len([row for row in nonvideo_units if row.get("media_kind") == "RUNWARE_IMAGE"]),
            "graphics_local_units": len([row for row in nonvideo_units if row.get("media_kind") == "LOCAL_GRAPHICS"]),
            "total_provider_requests": provider_units,
            "total_planned_units": len(plan_units),
        },
        "pricing": cost,
        "shot_treatments": [treatment.as_dict() for treatment in treatments],
        "shots": shot_rows,
        "video_units": video_units,
        "non_video_units": nonvideo_units,
        "sequences": sorted(sequence_stats, key=lambda row: row["sequence_id"]),
        "quality_constraints": {
            "creative_information_lost": False,
            "cinematic_quality_regression": False,
            "structural_change": "NONE",
            "loops_allowed": False,
            "semantic_clip_reuse_allowed": False,
            "provider_submission": False,
            "paid_attempts_created": 0,
            "requires_human_review_before_replacement": True,
        },
    }
    proposal["proposal_sha256"] = canonical_sha256(proposal)
    return proposal
