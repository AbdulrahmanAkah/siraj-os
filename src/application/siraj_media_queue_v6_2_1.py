"""Compatibility media queue using the canonical V2 cinematic mix policy."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping
import uuid
from src.application.artifact_provenance_v1 import atomic_write_json, canonical_sha256

from src.application.runware_image_model_routing_v1 import (
    build_runware_image_task,
    route_image_shot,
)
from src.application.siraj_duplicate_gates_v6_2_1 import (
    validate_pre_spend_duplicates,
)

VIDEO_MODEL = "google:veo@3.1-lite"
TIMELINE_TOLERANCE_SECONDS = 0.75


# SIRAJ_VISUAL_TREATMENT_NORMALIZATION_V6_6_R8
from src.application.siraj_visual_treatment_normalization_v6_6_r8 import (
    normalize_visual_treatments,
)
from src.application.siraj_cinematic_media_mix_policy_v2 import (
    MAX_TRUE_VIDEO_FRACTION,
    MIN_TRUE_VIDEO_FRACTION,
    validate_true_video_coverage,
)

MAX_PROVIDER_DURATION_SECONDS = 8.0
# Import-compatible name for historical repair adapters.  Canonical queue
# validation uses the V2 floor/ceiling below; this alias is not a second
# policy source.
MAX_GENERATED_VIDEO_RATIO = MAX_TRUE_VIDEO_FRACTION

class MediaQueueV621Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise MediaQueueV621Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(Path(path), value, preserve_previous=True)


def _canonical_sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _task_uuid(
    episode_id: str,
    kind: str,
    identity: str,
) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"siraj:v6.2.1:{episode_id}:{kind}:{identity}:attempt-1",
        )
    )


def _bind_task_uuid(episode_id: str, kind: str, task: Mapping[str, Any]) -> tuple[str, str]:
    identity_payload = {key: value for key, value in task.items() if key != "taskUUID"}
    payload_sha = canonical_sha256(identity_payload)
    task_uuid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"siraj:provider-payload:{episode_id}:{kind}:{payload_sha}"))
    return task_uuid, payload_sha


def _timeline_duration(ep: Path) -> float:
    timeline = _read(
        ep / "preproduction/audio-timestamps-and-beats-v6-1.json"
    )
    value = timeline.get("total_duration_seconds")
    if not isinstance(value, (int, float)) or float(value) <= 0:
        raise MediaQueueV621Error(
            "AUDIO_TIMELINE_TOTAL_DURATION_REQUIRED"
        )
    return float(value)


def _video_task(
    episode_id: str,
    item: Mapping[str, Any],
    identity: str,
    duration_seconds: float,
    positive_prompt: str,
) -> dict[str, Any]:
    required = max(1, int(math.ceil(float(duration_seconds) - 1e-9)))
    if required > int(MAX_PROVIDER_DURATION_SECONDS):
        raise MediaQueueV621Error(
            "VIDEO_UNIT_REQUIRES_DISTINCT_PROGRESSIVE_SUBSHOT:" + identity
        )
    return {
        "taskType": "videoInference",
        "taskUUID": _task_uuid(
            episode_id,
            "video",
            identity,
        ),
        "model": VIDEO_MODEL,
        "positivePrompt": positive_prompt,
        "width": 1280,
        "height": 720,
        "duration": required,
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {
            "google": {
                "generateAudio": False,
                "personGeneration": (
                    "allow_adult"
                    if bool(item.get("contains_people"))
                    else "dont_allow"
                ),
            }
        },
    }


def _validate_subshots(
    parent: Mapping[str, Any],
    scene_start: float,
    scene_end: float,
) -> list[dict[str, Any]]:
    raw = parent.get("video_subshots")
    if not isinstance(raw, list) or not raw:
        raise MediaQueueV621Error(
            "LONG_VIDEO_SCENE_REQUIRES_PROGRESSIVE_SUBSHOTS:"
            + str(parent.get("shot_id"))
        )

    result: list[dict[str, Any]] = []
    cursor = scene_start
    seen_progression: set[str] = set()

    for index, value in enumerate(raw, 1):
        if not isinstance(value, Mapping):
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_OBJECT_REQUIRED"
            )
        sub = dict(value)
        start = sub.get("start_seconds")
        end = sub.get("end_seconds")
        if not isinstance(start, (int, float)) or not isinstance(
            end, (int, float)
        ):
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_TIMING_REQUIRED"
            )
        start = float(start)
        end = float(end)

        if abs(start - cursor) > TIMELINE_TOLERANCE_SECONDS:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_TIMELINE_GAP_OR_OVERLAP"
            )
        if end <= start:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_DURATION_INVALID"
            )
        duration = end - start
        if duration > MAX_PROVIDER_DURATION_SECONDS + 1e-9:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_EXCEEDS_CURRENT_PROVIDER_REQUEST_PROFILE:"
                f"{duration:.3f}"
            )

        prompt = str(
            sub.get("runware_positive_prompt_en")
            or sub.get("prompt_en")
            or sub.get("prompt")
            or ""
        ).strip()
        if not prompt:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_PROMPT_REQUIRED"
            )

        progression = str(
            sub.get("visual_progression_id") or ""
        ).strip()
        if not progression:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_VISUAL_PROGRESSION_ID_REQUIRED"
            )
        if progression in seen_progression:
            raise MediaQueueV621Error(
                "VIDEO_SUBSHOT_VISUAL_PROGRESSION_ID_DUPLICATE"
            )
        seen_progression.add(progression)

        sub["start_seconds"] = start
        sub["end_seconds"] = end
        sub["runware_positive_prompt_en"] = prompt
        result.append(sub)
        cursor = end

    if abs(cursor - scene_end) > TIMELINE_TOLERANCE_SECONDS:
        raise MediaQueueV621Error(
            "VIDEO_SUBSHOTS_DO_NOT_COVER_LONG_SCENE"
        )

    duplicate_problems = validate_pre_spend_duplicates(result)
    if duplicate_problems:
        raise MediaQueueV621Error(
            "LONG_SCENE_SUBSHOT_DUPLICATE_GATE_FAILED:"
            + json.dumps(
                duplicate_problems,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    return result


def _expand_items(
    episode_id: str,
    raw_items: list[Any],
) -> list[dict[str, Any]]:
    raw_items = normalize_visual_treatments(raw_items)
    expanded: list[dict[str, Any]] = []

    for ordinal, raw in enumerate(raw_items, 1):
        if not isinstance(raw, Mapping):
            raise MediaQueueV621Error(
                "SEMANTIC_PROMPT_ITEM_OBJECT_REQUIRED"
            )
        item = dict(raw)
        shot_id = str(item.get("shot_id") or "").strip()
        if not shot_id:
            raise MediaQueueV621Error("SHOT_ID_REQUIRED")

        start = item.get("start_seconds")
        end = item.get("end_seconds")
        if not isinstance(start, (int, float)) or not isinstance(
            end, (int, float)
        ):
            raise MediaQueueV621Error(
                "SHOT_TIMING_REQUIRED:" + shot_id
            )
        start = float(start)
        end = float(end)
        if end <= start:
            raise MediaQueueV621Error(
                "SHOT_TIMING_INVALID:" + shot_id
            )

        treatment = str(
            item.get("final_budget_treatment")
            or item.get("treatment")
            or ""
        ).strip().upper()
        if treatment not in {
            "ANIMATED_STILL_COMPOSITING",
            "GENERATED_VIDEO",
            "GRAPHICS",
        }:
            raise MediaQueueV621Error(
                "UNSUPPORTED_VISUAL_TREATMENT:"
                + shot_id
                + ":"
                + treatment
            )

        item.setdefault("queue_index", ordinal)
        duration = end - start

        if (
            treatment == "GENERATED_VIDEO"
            and duration > MAX_PROVIDER_DURATION_SECONDS + 1e-9
        ):
            subs = _validate_subshots(item, start, end)
            continuity = str(
                item.get("scene_continuity_id")
                or ("SCENE-" + shot_id)
            )
            for sub_index, sub in enumerate(subs, 1):
                child = dict(item)
                child.update(sub)
                child["shot_id"] = (
                    shot_id + f"-P{sub_index:02d}"
                )
                child["parent_shot_id"] = shot_id
                child["scene_continuity_id"] = continuity
                child["queue_index"] = (
                    int(item["queue_index"]) * 100 + sub_index
                )
                expanded.append(child)
        else:
            expanded.append(item)

    return expanded


def _validate_full_timeline(
    items: list[dict[str, Any]],
    total_duration: float,
) -> None:
    ordered = sorted(
        items,
        key=lambda x: (
            float(x.get("start_seconds", 0)),
            float(x.get("end_seconds", 0)),
        ),
    )

    if abs(float(ordered[0]["start_seconds"])) > TIMELINE_TOLERANCE_SECONDS:
        raise MediaQueueV621Error(
            "VISUAL_TIMELINE_MUST_START_AT_ZERO"
        )

    cursor = 0.0
    for item in ordered:
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
        if abs(start - cursor) > TIMELINE_TOLERANCE_SECONDS:
            raise MediaQueueV621Error(
                "VISUAL_TIMELINE_GAP_OR_OVERLAP:"
                + str(item.get("shot_id"))
            )
        cursor = end

    if abs(cursor - total_duration) > TIMELINE_TOLERANCE_SECONDS:
        raise MediaQueueV621Error(
            "VISUAL_TIMELINE_DOES_NOT_COVER_EPISODE:"
            f"timeline={cursor:.3f}:episode={total_duration:.3f}"
        )


def materialize_v6_media_queue(
    repo_root: Path,
    episode_id: str,
    prompt_plan_relative: str = (
        "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
    ),
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    prompt_payload = _read(ep / prompt_plan_relative)

    if prompt_payload.get("status") != "PASS":
        raise MediaQueueV621Error(
            "SEMANTIC_PROMPT_PLAN_NOT_PASS"
        )

    raw_items = prompt_payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise MediaQueueV621Error(
            "SEMANTIC_PROMPT_ITEMS_REQUIRED"
        )

    expanded = _expand_items(episode_id, raw_items)
    duplicate_problems = validate_pre_spend_duplicates(expanded)
    if duplicate_problems:
        raise MediaQueueV621Error(
            "PRE_SPEND_DUPLICATE_GATE_FAILED:"
            + json.dumps(
                duplicate_problems,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )

    episode_duration = _timeline_duration(ep)
    _validate_full_timeline(expanded, episode_duration)

    planned_video_seconds = sum(
        float(item["end_seconds"])
        - float(item["start_seconds"])
        for item in expanded
        if str(
            item.get("final_budget_treatment")
            or item.get("treatment")
            or ""
        ).upper()
        == "GENERATED_VIDEO"
    )
    non_video_seconds = episode_duration - planned_video_seconds
    max_video_seconds = episode_duration * MAX_TRUE_VIDEO_FRACTION
    min_video_seconds = episode_duration * MIN_TRUE_VIDEO_FRACTION
    coverage = validate_true_video_coverage(episode_duration, planned_video_seconds)
    if coverage.status != "PASS":
        raise MediaQueueV621Error(coverage.reason or coverage.status)

    queue_items: list[dict[str, Any]] = []

    for index, item in enumerate(
        sorted(
            expanded,
            key=lambda x: (
                float(x["start_seconds"]),
                float(x["end_seconds"]),
            ),
        ),
        1,
    ):
        shot_id = str(item["shot_id"])
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
        duration = end - start
        treatment = str(
            item.get("final_budget_treatment")
            or item.get("treatment")
        ).upper()

        common = {
            "queue_index": index,
            "shot_id": shot_id,
            "parent_shot_id": item.get("parent_shot_id"),
            "scene_continuity_id": item.get(
                "scene_continuity_id"
            ),
            "visual_progression_id": item.get(
                "visual_progression_id"
            ),
            "beat_id": item.get("beat_id"),
            "segment_ids": list(
                item.get("segment_ids") or []
            ),
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(duration, 3),
            "treatment": treatment,
            "automatic_paid_retry": False,
            "assistant_authored_cost_cap_usd": None,
            "reuse_justification": item.get(
                "reuse_justification"
            ),
        }

        if treatment == "ANIMATED_STILL_COMPOSITING":
            shot = dict(item)
            shot["final_budget_treatment"] = treatment
            shot["runware_positive_prompt_en"] = str(
                item.get("runware_positive_prompt_en")
                or item.get("prompt_en")
                or item.get("prompt")
                or ""
            ).strip()
            route = route_image_shot(shot)
            task_uuid = _task_uuid(
                episode_id,
                "image",
                shot_id,
            )
            task = build_runware_image_task(
                shot,
                task_uuid,
            )
            task_uuid, provider_payload_sha = _bind_task_uuid(episode_id, "image", task)
            task["taskUUID"] = task_uuid
            queue_items.append(
                {
                    **common,
                    "queue_id": "IMG-" + shot_id,
                    "media_kind": "RUNWARE_IMAGE",
                    "provider": "RUNWARE",
                    "selected_model": route.model,
                    "task_uuid": task_uuid,
                    "task_draft": task,
                    "provider_payload_sha256": provider_payload_sha,
                    "status": (
                        "AWAITING_EXPLICIT_PAID_AUTHORIZATION"
                    ),
                    "expected_cost_usd": None,
                    "output_path_relative": (
                        f"projects/{episode_id}/cinematic/"
                        f"v6-assets/{index:04d}-{shot_id}.jpg"
                    ),
                }
            )

        elif treatment == "GENERATED_VIDEO":
            prompt = str(
                item.get("runware_positive_prompt_en")
                or item.get("prompt_en")
                or item.get("prompt")
                or ""
            ).strip()
            if not prompt:
                raise MediaQueueV621Error(
                    "VIDEO_PROMPT_REQUIRED:" + shot_id
                )
            task = _video_task(
                episode_id,
                item,
                shot_id,
                duration,
                prompt,
            )
            task_uuid, provider_payload_sha = _bind_task_uuid(episode_id, "video", task)
            task["taskUUID"] = task_uuid
            queue_items.append(
                {
                    **common,
                    "queue_id": "VID-" + shot_id,
                    "media_kind": "RUNWARE_VIDEO",
                    "provider": "RUNWARE",
                    "selected_model": VIDEO_MODEL,
                    "task_uuid": task_uuid,
                    "task_draft": task,
                    "provider_payload_sha256": provider_payload_sha,
                    "provider_requested_seconds": int(task["duration"]),
                    "timeline_coverage_seconds": round(duration, 3),
                    "status": (
                        "AWAITING_EXPLICIT_PAID_AUTHORIZATION"
                    ),
                    "expected_cost_usd": None,
                    "output_path_relative": (
                        f"projects/{episode_id}/cinematic/"
                        f"v6-assets/{index:04d}-{shot_id}.mp4"
                    ),
                }
            )

        else:
            spec = item.get("graphics_spec")
            if not isinstance(spec, Mapping):
                raise MediaQueueV621Error(
                    "GRAPHICS_SPEC_REQUIRED:" + shot_id
                )
            spec_relative = (
                f"projects/{episode_id}/cinematic/"
                f"v6-graphics/specs/{index:04d}-{shot_id}.json"
            )
            _write(repo / spec_relative, dict(spec))
            queue_items.append(
                {
                    **common,
                    "queue_id": "LOCAL-" + shot_id,
                    "media_kind": "LOCAL_GRAPHICS",
                    "provider": "LOCAL",
                    "selected_model": (
                        "PYSIDE6_QT_QUICK_QML_FFMPEG"
                    ),
                    "spec_path_relative": spec_relative,
                    "status": "READY_LOCAL_RENDER",
                    "expected_cost_usd": 0.0,
                    "output_path_relative": (
                        f"projects/{episode_id}/cinematic/"
                        f"v6-assets/{index:04d}-{shot_id}.mp4"
                    ),
                }
            )

    core = {
        "schema_version": (
            "siraj-media-production-queue-v6.2.1"
        ),
        "status": (
            "READY_AWAITING_EXPLICIT_PAID_EXECUTION"
        ),
        "episode_id": episode_id,
        "episode_duration_seconds": round(
            episode_duration,
            3,
        ),
        "generated_video_policy": {
            "policy_id": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "minimum_ratio": MIN_TRUE_VIDEO_FRACTION,
            "maximum_ratio": MAX_TRUE_VIDEO_FRACTION,
            "maximum_seconds": round(
                max_video_seconds,
                3,
            ),
            "planned_seconds": round(
                planned_video_seconds,
                3,
            ),
            "planned_ratio": round(
                planned_video_seconds / episode_duration,
                6,
            ),
            "minimum_seconds": round(min_video_seconds, 3),
            "non_generated_video_planned_seconds": round(non_video_seconds, 3),
            "selection_mode": "DIRECTORIAL_OPTIMIZATION",
            "coverage_validation": coverage.as_dict(),
            "long_scene_transport_strategy": (
                "PROGRESSIVE_DISTINCT_SUBSHOTS"
            ),
            "provider_duration_selection": "SMALLEST_SUPPORTED_DURATION_FOR_TIMELINE_USE",
            "provider_request_limit_is_creative_scene_limit": False,
        },
        "duplicate_policy": {
            "prompt_gate": "PASS",
            "semantic_gate": "PASS",
            "adjacent_shot_gate": "PASS",
            "asset_reuse_without_justification": "FORBIDDEN",
            "post_generation_perceptual_gate": "REQUIRED",
        },
        "automatic_paid_retry": False,
        "assistant_authored_cost_cap_usd": None,
        "paid_submission_requires_explicit_authorization": True,
        "recover_existing_task_uuid_without_resubmission": True,
        "local_graphics_may_render_automatically": True,
        "items": queue_items,
    }
    core["immutable_manifest_sha256"] = _canonical_sha(core)
    core["created_at_utc"] = _now()

    out = (
        ep
        / "orchestration/media-production-queue-v6-2-1.json"
    )
    _write(out, core)
    return out
