from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import record_invalidation

from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_active,
    master_authorization_reference,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path,
    authorize_stage,
    canonical_sha256,
    execute_authorized_stage,
)

PROMPT_STAGE = "LUNA_SEMANTIC_PROMPT_DIRECTION"
ALIGNMENT_STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
LUNA_CONFIRMATION_PHRASE = "أوافق على تنفيذ مرحلة لونا المدفوعة"

PROMPTS_REL = Path(
    "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
)
TIMELINE_REL = Path(
    "preproduction/audio-timestamps-and-beats-v6-1.json"
)
ALIGNMENT_REL = Path(
    "preproduction/narration-visual-alignment-gate-v6-2-1.json"
)
DUPLICATE_REL = Path(
    "preproduction/prompt-similarity-duplicate-gate-v6-1.json"
)

TIMELINE_TOLERANCE_SECONDS = 0.75


class VisualTimelineCoverageAutoRepairV66R4Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        path.name
        + "."
        + str(os.getpid())
        + "."
        + hashlib.sha256(
            (_now() + str(path)).encode("utf-8")
        ).hexdigest()[:16]
        + ".tmp"
    )
    try:
        temp.write_text(
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp, path)
    except Exception:
        raise


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def is_visual_timeline_coverage_failure(exc: Exception) -> bool:
    return "VISUAL_TIMELINE_DOES_NOT_COVER_EPISODE:" in str(exc)


def _items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("items")
    if not isinstance(raw, list) or not raw:
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "PROMPT_ITEMS_REQUIRED"
        )
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "PROMPT_ITEM_OBJECT_REQUIRED"
            )
        result.append(dict(item))
    return result


def _validate_existing_timeline(
    prompt_plan: Mapping[str, Any],
    episode_duration: float,
) -> tuple[list[dict[str, Any]], float, float]:
    items = sorted(
        _items(prompt_plan),
        key=lambda x: (
            float(x.get("start_seconds", 0) or 0),
            float(x.get("end_seconds", 0) or 0),
        ),
    )
    if not items:
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "EMPTY_VISUAL_TIMELINE"
        )

    first_start = float(items[0].get("start_seconds", 0) or 0)
    if abs(first_start) > TIMELINE_TOLERANCE_SECONDS:
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "VISUAL_TIMELINE_NOT_STARTING_AT_ZERO"
        )

    cursor = 0.0
    seen_ids: set[str] = set()
    for item in items:
        shot_id = str(item.get("shot_id") or "").strip()
        if not shot_id:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "SHOT_ID_REQUIRED"
            )
        if shot_id in seen_ids:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "DUPLICATE_SHOT_ID:" + shot_id
            )
        seen_ids.add(shot_id)

        start = float(item.get("start_seconds"))
        end = float(item.get("end_seconds"))
        if end <= start:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "SHOT_TIMING_INVALID:" + shot_id
            )
        if abs(start - cursor) > TIMELINE_TOLERANCE_SECONDS:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "INTERNAL_VISUAL_TIMELINE_GAP_OR_OVERLAP:"
                + shot_id
            )
        cursor = end

    if cursor >= episode_duration - TIMELINE_TOLERANCE_SECONDS:
        return items, cursor, 0.0

    gap = episode_duration - cursor
    return items, cursor, gap


def _max_queue_index(items: list[dict[str, Any]]) -> int:
    result = 0
    for item in items:
        try:
            result = max(
                result,
                int(item.get("queue_index", 0) or 0),
            )
        except (TypeError, ValueError):
            pass
    return result


def _existing_generated_video_seconds(
    items: list[dict[str, Any]],
) -> float:
    total = 0.0
    for item in items:
        treatment = str(
            item.get("final_budget_treatment")
            or item.get("treatment")
            or ""
        ).upper()
        if treatment != "GENERATED_VIDEO":
            continue
        total += (
            float(item["end_seconds"])
            - float(item["start_seconds"])
        )
    return total


def _archive_authorization(
    repo: Path,
    episode_id: str,
    stage: str,
    iteration_dir: Path,
    label: str,
) -> None:
    path = authorization_path(
        repo,
        episode_id,
        stage,
    )
    if not path.is_file():
        return
    destination = (
        iteration_dir
        / f"{label}-{stage.lower()}-paid-authorization.json"
    )
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination.write_bytes(path.read_bytes())
    record_invalidation(
        repo,
        episode_id,
        path,
        reason="PAID_AUTHORIZATION_SUPERSEDED_BY_TIMELINE_COVERAGE_REPAIR",
        classification="SUPERSEDED",
    )


def _annotate_master(
    repo: Path,
    episode_id: str,
    path: Path,
    intent: str,
) -> None:
    value = _read(path)
    master = master_authorization_reference(
        repo,
        episode_id,
    )
    value[
        "authorization_source"
    ] = "DERIVED_FROM_EPISODE_MASTER_AUTHORIZATION"
    value[
        "episode_master_authorization_path"
    ] = master["path"]
    value[
        "episode_master_authorization_sha256"
    ] = master["sha256"]
    value["editorial_iteration_intent"] = intent
    value["automatic_retry"] = False
    value["automatic_resubmission"] = False
    _write(path, value)


def _authorize_derived(
    repo: Path,
    episode_id: str,
    stage: str,
    payload: Mapping[str, Any],
    iteration_dir: Path,
    label: str,
    intent: str,
) -> Path:
    _archive_authorization(
        repo,
        episode_id,
        stage,
        iteration_dir,
        label,
    )
    path = authorize_stage(
        repo,
        episode_id,
        stage,
        payload,
        LUNA_CONFIRMATION_PHRASE,
    )
    _annotate_master(
        repo,
        episode_id,
        path,
        intent,
    )
    return path


def _journal_path(
    repo: Path,
    episode_id: str,
) -> Path:
    return (
        repo
        / "projects"
        / episode_id
        / "orchestration/"
        "visual-timeline-coverage-autorepair-v6-6-r4/journal.jsonl"
    )


def _journal_rows(
    repo: Path,
    episode_id: str,
) -> list[dict[str, Any]]:
    path = _journal_path(repo, episode_id)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _append_journal(
    repo: Path,
    episode_id: str,
    value: Mapping[str, Any],
) -> None:
    path = _journal_path(repo, episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )


def _normalize_tail_items(
    result: Mapping[str, Any],
    existing: list[dict[str, Any]],
    tail_start: float,
    episode_duration: float,
) -> list[dict[str, Any]]:
    if str(result.get("status") or "").upper() != "PASS":
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "COVERAGE_REPAIR_DID_NOT_RETURN_PASS"
        )

    raw = result.get("tail_items")
    if not isinstance(raw, list) or not raw:
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "COVERAGE_REPAIR_TAIL_ITEMS_REQUIRED"
        )

    existing_ids = {
        str(item.get("shot_id") or "")
        for item in existing
    }
    max_queue_index = _max_queue_index(existing)
    normalized: list[dict[str, Any]] = []

    for ordinal, raw_item in enumerate(raw, start=1):
        if not isinstance(raw_item, Mapping):
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_ITEM_OBJECT_REQUIRED"
            )
        item = dict(raw_item)
        shot_id = str(
            item.get("shot_id")
            or f"TAIL-COVERAGE-{ordinal:03d}"
        ).strip()
        if (
            not shot_id
            or shot_id in existing_ids
            or any(
                str(row.get("shot_id")) == shot_id
                for row in normalized
            )
        ):
            shot_id = f"TAIL-COVERAGE-{ordinal:03d}"
        item["shot_id"] = shot_id
        item["queue_index"] = max_queue_index + ordinal

        required = (
            "beat_id",
            "segment_ids",
            "start_seconds",
            "end_seconds",
            "final_budget_treatment",
            "semantic_beat",
            "subject",
            "environment",
            "composition",
            "camera_angle",
            "camera_movement",
            "scene_continuity_id",
            "visual_progression_id",
            "runware_positive_prompt_en",
            "runware_negative_prompt_en",
            "contains_people",
        )
        missing = [
            key
            for key in required
            if key not in item
        ]
        if missing:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_ITEM_REQUIRED_FIELDS_MISSING:"
                + shot_id
                + ":"
                + ",".join(missing)
            )

        treatment = str(
            item.get("final_budget_treatment")
            or ""
        ).upper()
        if treatment not in {
            "ANIMATED_STILL_COMPOSITING",
            "GENERATED_VIDEO",
            "GRAPHICS",
        }:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_ITEM_TREATMENT_INVALID:"
                + shot_id
            )

        if treatment == "GRAPHICS" and not isinstance(
            item.get("graphics_spec"),
            Mapping,
        ):
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_GRAPHICS_SPEC_REQUIRED:"
                + shot_id
            )

        normalized.append(item)

    ordered = sorted(
        normalized,
        key=lambda x: (
            float(x["start_seconds"]),
            float(x["end_seconds"]),
        ),
    )

    cursor = tail_start
    for item in ordered:
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
        if end <= start:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_ITEM_TIMING_INVALID:"
                + str(item["shot_id"])
            )
        if abs(start - cursor) > TIMELINE_TOLERANCE_SECONDS:
            raise VisualTimelineCoverageAutoRepairV66R4Error(
                "TAIL_COVERAGE_GAP_OR_OVERLAP:"
                + str(item["shot_id"])
            )
        cursor = end

    if (
        abs(cursor - episode_duration)
        > TIMELINE_TOLERANCE_SECONDS
    ):
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "TAIL_ITEMS_DO_NOT_REACH_EPISODE_END:"
            f"tail={cursor:.3f}:episode={episode_duration:.3f}"
        )

    return ordered


def repair_visual_timeline_coverage(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    if not master_authorization_active(
        repo,
        episode_id,
    ):
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "EPISODE_MASTER_AUTHORIZATION_REQUIRED"
        )

    ep = repo / "projects" / episode_id
    prompts_path = ep / PROMPTS_REL
    timeline_path = ep / TIMELINE_REL

    prompts = _read(prompts_path)
    timeline = _read(timeline_path)

    episode_duration = float(
        timeline.get("total_duration_seconds") or 0
    )
    if episode_duration <= 0:
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "EPISODE_DURATION_REQUIRED"
        )

    existing, tail_start, gap = (
        _validate_existing_timeline(
            prompts,
            episode_duration,
        )
    )

    if gap <= TIMELINE_TOLERANCE_SECONDS:
        return {
            "status": "ALREADY_COVERED",
            "changed": False,
            "tail_start_seconds": tail_start,
            "episode_duration_seconds": episode_duration,
        }

    fingerprint = _sha(
        {
            "prompt_plan": prompts,
            "audio_timeline": timeline,
            "tail_start_seconds": tail_start,
            "episode_duration_seconds": episode_duration,
        }
    )
    prior = _journal_rows(
        repo,
        episode_id,
    )
    if any(
        row.get("input_fingerprint") == fingerprint
        for row in prior
    ):
        raise VisualTimelineCoverageAutoRepairV66R4Error(
            "VISUAL_TIMELINE_COVERAGE_NO_PROGRESS_HUMAN_REVIEW_REQUIRED"
        )

    iteration = len(prior) + 1
    root = (
        ep
        / "orchestration/"
        "visual-timeline-coverage-autorepair-v6-6-r4"
        / f"iteration-{iteration:03d}"
    )
    root.mkdir(
        parents=True,
        exist_ok=False,
    )
    (root / "prompt-plan-before.json").write_bytes(
        prompts_path.read_bytes()
    )
    (root / "audio-timeline.json").write_bytes(
        timeline_path.read_bytes()
    )

    existing_video_seconds = (
        _existing_generated_video_seconds(existing)
    )
    max_video_seconds = episode_duration * (2 / 3)
    remaining_video_allowance = max(
        0.0,
        max_video_seconds - existing_video_seconds,
    )

    repair_payload = {
        "episode_id": episode_id,
        "current_prompt_plan": prompts,
        "audio_timeline": timeline,
        "coverage_defect": {
            "visual_timeline_end_seconds": tail_start,
            "episode_duration_seconds": episode_duration,
            "uncovered_tail_seconds": gap,
        },
        "visual_mix_state": {
            "existing_generated_video_seconds": (
                existing_video_seconds
            ),
            "maximum_generated_video_seconds": (
                max_video_seconds
            ),
            "remaining_generated_video_allowance_seconds": (
                remaining_video_allowance
            ),
        },
        "repair_contract": {
            "existing_items_are_immutable": True,
            "append_tail_items_only": True,
            "first_new_start_seconds": tail_start,
            "final_new_end_seconds": episode_duration,
            "no_internal_tail_gaps_or_overlaps": True,
            "map_tail_to_actual_audio_timeline_content": True,
            "no_unsupported_event_or_theological_invention": True,
            "media_mix_policy": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "generated_video_min_ratio": 0.50,
            "generated_video_max_ratio": 0.75,
            "video_allowance_is_ceiling_not_target": True,
            "prefer_animated_still_when_equally_effective": True,
            "no_duplicate_or_looped_visual_function": True,
            "no_generated_arabic_text": True,
            "no_fixed_tail_shot_count": True,
        },
    }

    _authorize_derived(
        repo,
        episode_id,
        PROMPT_STAGE,
        repair_payload,
        root,
        "before-tail-repair",
        "TARGETED_VISUAL_TIMELINE_TAIL_COVERAGE_REPAIR",
    )

    raw_output = root / "luna-tail-coverage-repair.json"
    execute_authorized_stage(
        repo,
        episode_id,
        PROMPT_STAGE,
        system_prompt="""
أنت Luna، المديرة البصرية المركزية لسراج في وضع MAX/PRO.

الخطة البصرية الحالية اجتازت المراجعات السابقة، لكنها تنتهي قبل نهاية الصوت.
هذا ليس طلبًا لإعادة بناء الخطة من الصفر.

المطلوب فقط:
- لا تغيّر أي item موجود حاليًا ولا توقيته ولا shot_id.
- أضف tail_items جديدة فقط لتغطية الفترة غير المغطاة من
  visual_timeline_end_seconds حتى episode_duration_seconds.
- اقرأ audio_timeline الفعلي وحدد ما يُقال في هذه الفترة، واجعل كل لقطة
  تخدم السرد الحقيقي فيها.
- يجب أن تبدأ أول لقطة جديدة عند بداية الفجوة بالضبط، وأن تنتهي آخر لقطة
  عند نهاية الحلقة، من دون فجوات أو تداخل.
- استخدم عدد اللقطات الذي يحتاجه السرد فقط، بلا عدد ثابت.
- التزم بسياسة SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2: تغطية الفيديو الحقيقي بين 50% و75% من الحلقة؛ النطاق قيد صلب وليس هدفًا عدديًا.
- فضّل ANIMATED_STILL_COMPOSITING عندما يكون مساويًا سينمائيًا.
- لا LOOP ولا تكرار بصري ولا إعادة صياغة لنفس اللقطة.
- حافظ على الضبط الديني والمصدري.
- لا تولد نصًا عربيًا داخل الوسائط.

كل tail item يجب أن يحتوي:
shot_id, beat_id, segment_ids, start_seconds, end_seconds,
final_budget_treatment, semantic_beat, subject, environment, composition,
camera_angle, camera_movement, scene_continuity_id, visual_progression_id,
runware_positive_prompt_en, runware_negative_prompt_en, contains_people.
وعند GRAPHICS أضف graphics_spec.
وعند فيديو طويل التزم ببنية subshots المعتمدة إن لزم.

أخرج JSON فقط:
status=PASS
tail_items=[...]
repair_rationale_ar="..."
self_review={}
""",
        input_payload=repair_payload,
        output_path_relative=str(
            raw_output.relative_to(ep)
        ).replace("\\", "/"),
        use_web_search=False,
    )

    result = _read(raw_output)
    tail_items = _normalize_tail_items(
        result,
        existing,
        tail_start,
        episode_duration,
    )

    repaired = dict(prompts)
    repaired["items"] = existing + tail_items
    repaired["status"] = "PASS"
    repaired[
        "visual_timeline_tail_coverage_repair"
    ] = {
        "version": "V6.6-R4",
        "tail_start_seconds": tail_start,
        "episode_duration_seconds": episode_duration,
        "added_item_count": len(tail_items),
        "input_fingerprint": fingerprint,
    }

    _write(
        root / "prompt-plan-after.json",
        repaired,
    )
    _write(
        prompts_path,
        repaired,
    )

    row = {
        "schema_version": (
            "siraj-visual-timeline-coverage-autorepair-v6.6-r4"
        ),
        "episode_id": episode_id,
        "iteration": iteration,
        "input_fingerprint": fingerprint,
        "tail_start_seconds": tail_start,
        "episode_duration_seconds": episode_duration,
        "uncovered_tail_seconds": gap,
        "added_item_count": len(tail_items),
        "prompt_before_sha256": canonical_sha256(
            prompts
        ),
        "prompt_after_sha256": canonical_sha256(
            repaired
        ),
        "editorial_iteration_under_master_authorization": True,
        "paid_retry": False,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "created_at_utc": _now(),
    }
    _append_journal(
        repo,
        episode_id,
        row,
    )

    return {
        "status": "REPAIRED_FOR_REVALIDATION",
        "changed": True,
        "iteration": iteration,
        "tail_start_seconds": tail_start,
        "episode_duration_seconds": episode_duration,
        "uncovered_tail_seconds": gap,
        "added_item_count": len(tail_items),
    }
