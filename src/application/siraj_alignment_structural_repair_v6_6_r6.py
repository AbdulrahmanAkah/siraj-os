from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import record_invalidation

from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path,
)
# SIRAJ_VISUAL_TREATMENT_NORMALIZATION_V6_6_R8
from src.application.siraj_visual_treatment_normalization_v6_6_r8 import (
    normalize_visual_treatments,
)
from src.application.siraj_media_queue_v6_2_1 import (
    _expand_items,
    _validate_full_timeline,
)
from src.application.siraj_cinematic_media_mix_policy_v2 import (
    MAX_TRUE_VIDEO_FRACTION as MAX_GENERATED_VIDEO_RATIO,
    MIN_TRUE_VIDEO_FRACTION,
    validate_true_video_coverage,
)

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
QUEUE_REL = Path(
    "orchestration/media-production-queue-v6-2-1.json"
)
COST_REL = Path(
    "orchestration/media-cost-preflight-v6-2-1.json"
)
RETRY_GUARD_REL = Path(
    "orchestration/paid-retry-required-v6-6.json"
)

R3_ROOT_REL = Path(
    "orchestration/alignment-semantic-autorepair-v6-6-r3"
)
R6_ROOT_REL = Path(
    "orchestration/alignment-structural-repair-v6-6-r6"
)

ALIGNMENT_STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"


class AlignmentStructuralRepairV66R6Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AlignmentStructuralRepairV66R6Error(
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


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _extract_candidate(result: Mapping[str, Any]) -> dict[str, Any]:
    if str(result.get("status") or "").upper() != "PASS":
        raise AlignmentStructuralRepairV66R6Error(
            "ALIGNMENT_REPAIR_DID_NOT_RETURN_PASS"
        )
    nested = result.get("repaired_prompt_plan")
    candidate = (
        dict(nested)
        if isinstance(nested, Mapping)
        else dict(result)
    )
    items = candidate.get("items")
    if not isinstance(items, list) or not items:
        raise AlignmentStructuralRepairV66R6Error(
            "ALIGNMENT_REPAIR_ITEMS_REQUIRED"
        )
    return candidate


def _episode_duration(repo: Path, episode_id: str) -> float:
    timeline = _read(
        repo / "projects" / episode_id / TIMELINE_REL
    )
    value = timeline.get("total_duration_seconds")
    if not isinstance(value, (int, float)) or float(value) <= 0:
        raise AlignmentStructuralRepairV66R6Error(
            "EPISODE_DURATION_REQUIRED"
        )
    return float(value)


def _normalize_items(
    candidate: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw = candidate.get("items")
    if not isinstance(raw, list) or not raw:
        raise AlignmentStructuralRepairV66R6Error(
            "ALIGNMENT_REPAIR_ITEMS_REQUIRED"
        )

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw_item in raw:
        if not isinstance(raw_item, Mapping):
            raise AlignmentStructuralRepairV66R6Error(
                "ALIGNMENT_REPAIR_ITEM_OBJECT_REQUIRED"
            )

        item = dict(raw_item)
        shot_id = str(item.get("shot_id") or "").strip()
        if not shot_id:
            raise AlignmentStructuralRepairV66R6Error(
                "ALIGNMENT_REPAIR_SHOT_ID_REQUIRED"
            )
        if shot_id in seen:
            raise AlignmentStructuralRepairV66R6Error(
                "ALIGNMENT_REPAIR_DUPLICATE_SHOT_ID:" + shot_id
            )
        seen.add(shot_id)

        try:
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AlignmentStructuralRepairV66R6Error(
                "ALIGNMENT_REPAIR_TIMING_REQUIRED:" + shot_id
            ) from exc

        if end <= start:
            raise AlignmentStructuralRepairV66R6Error(
                "ALIGNMENT_REPAIR_DURATION_INVALID:" + shot_id
            )

        item["start_seconds"] = start
        item["end_seconds"] = end
        items.append(item)

    items.sort(
        key=lambda row: (
            float(row["start_seconds"]),
            float(row["end_seconds"]),
            str(row["shot_id"]),
        )
    )

    for index, item in enumerate(items, start=1):
        item["queue_index"] = index

    return items



# SIRAJ_ALIGNMENT_TIMELINE_PARTITION_RECOVERY_V6_6_R6_1
def _remap_video_subshots(
    item: dict[str, Any],
    old_start: float,
    old_end: float,
    new_start: float,
    new_end: float,
) -> None:
    raw = item.get("video_subshots")
    if not isinstance(raw, list) or not raw:
        return

    old_duration = old_end - old_start
    new_duration = new_end - new_start
    if old_duration <= 0 or new_duration <= 0:
        raise AlignmentStructuralRepairV66R6Error(
            "TIMELINE_PARTITION_SUBSHOT_PARENT_DURATION_INVALID:"
            + str(item.get("shot_id"))
        )

    remapped: list[dict[str, Any]] = []
    for sub in raw:
        if not isinstance(sub, Mapping):
            raise AlignmentStructuralRepairV66R6Error(
                "TIMELINE_PARTITION_SUBSHOT_OBJECT_REQUIRED:"
                + str(item.get("shot_id"))
            )
        row = dict(sub)
        try:
            sub_start = float(row["start_seconds"])
            sub_end = float(row["end_seconds"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AlignmentStructuralRepairV66R6Error(
                "TIMELINE_PARTITION_SUBSHOT_TIMING_REQUIRED:"
                + str(item.get("shot_id"))
            ) from exc

        start_ratio = (sub_start - old_start) / old_duration
        end_ratio = (sub_end - old_start) / old_duration

        row["start_seconds"] = (
            new_start + start_ratio * new_duration
        )
        row["end_seconds"] = (
            new_start + end_ratio * new_duration
        )
        remapped.append(row)

    if remapped:
        remapped[0]["start_seconds"] = new_start
        remapped[-1]["end_seconds"] = new_end
        for index in range(1, len(remapped)):
            left = remapped[index - 1]
            right = remapped[index]
            boundary = (
                float(left["end_seconds"])
                + float(right["start_seconds"])
            ) / 2.0
            if (
                boundary <= float(left["start_seconds"])
                or boundary >= float(right["end_seconds"])
            ):
                raise AlignmentStructuralRepairV66R6Error(
                    "TIMELINE_PARTITION_SUBSHOT_NORMALIZATION_UNSAFE:"
                    + str(item.get("shot_id"))
                )
            left["end_seconds"] = boundary
            right["start_seconds"] = boundary

    item["video_subshots"] = remapped


def canonicalize_timeline_partition(
    raw_items: list[dict[str, Any]],
    episode_duration: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if episode_duration <= 0:
        raise AlignmentStructuralRepairV66R6Error(
            "TIMELINE_PARTITION_EPISODE_DURATION_REQUIRED"
        )
    if not raw_items:
        raise AlignmentStructuralRepairV66R6Error(
            "TIMELINE_PARTITION_ITEMS_REQUIRED"
        )

    items = [
        dict(item)
        for item in sorted(
            raw_items,
            key=lambda row: (
                float(row["start_seconds"]),
                float(row["end_seconds"]),
                str(row.get("shot_id") or ""),
            ),
        )
    ]

    original_times = [
        (
            float(item["start_seconds"]),
            float(item["end_seconds"]),
        )
        for item in items
    ]

    discontinuities: list[dict[str, Any]] = []

    first_old_start = float(items[0]["start_seconds"])
    if first_old_start != 0.0:
        discontinuities.append(
            {
                "kind": "START_OFFSET",
                "shot_id": str(items[0].get("shot_id") or ""),
                "delta_seconds": first_old_start,
            }
        )
        items[0]["start_seconds"] = 0.0

    for index in range(1, len(items)):
        left = items[index - 1]
        right = items[index]
        left_end = float(left["end_seconds"])
        right_start = float(right["start_seconds"])
        delta = right_start - left_end

        if abs(delta) <= 1e-9:
            continue

        boundary = (left_end + right_start) / 2.0
        left_start = float(left["start_seconds"])
        right_end = float(right["end_seconds"])

        if boundary <= left_start or boundary >= right_end:
            raise AlignmentStructuralRepairV66R6Error(
                "TIMELINE_PARTITION_NORMALIZATION_UNSAFE:"
                + str(right.get("shot_id"))
                + f":delta={delta:.6f}"
            )

        discontinuities.append(
            {
                "kind": (
                    "GAP"
                    if delta > 0
                    else "OVERLAP"
                ),
                "previous_shot_id": str(
                    left.get("shot_id") or ""
                ),
                "shot_id": str(
                    right.get("shot_id") or ""
                ),
                "previous_end_seconds": left_end,
                "current_start_seconds": right_start,
                "delta_seconds": delta,
                "normalized_boundary_seconds": boundary,
            }
        )

        left["end_seconds"] = boundary
        right["start_seconds"] = boundary

    # SIRAJ_AUDIO_TIMELINE_AUTHORITY_V6_6_R8_2
    last_old_end = float(items[-1]["end_seconds"])
    if abs(last_old_end - episode_duration) > 1e-6:
        raise AlignmentStructuralRepairV66R6Error(
            "TIMELINE_PARTITION_LAST_END_MISMATCH_REQUIRES_AUDIO_BOUND_REPAIR:"
            + str(items[-1].get("shot_id"))
            + f":last_end={last_old_end:.6f}"
            + f":episode={episode_duration:.6f}"
        )

    for index, item in enumerate(items):
        new_start = float(item["start_seconds"])
        new_end = float(item["end_seconds"])
        old_start, old_end = original_times[index]

        if new_end <= new_start:
            raise AlignmentStructuralRepairV66R6Error(
                "TIMELINE_PARTITION_NONPOSITIVE_DURATION:"
                + str(item.get("shot_id"))
            )

        if (
            abs(new_start - old_start) > 1e-9
            or abs(new_end - old_end) > 1e-9
        ):
            item[
                "timeline_partition_original"
            ] = {
                "start_seconds": old_start,
                "end_seconds": old_end,
            }
            _remap_video_subshots(
                item,
                old_start,
                old_end,
                new_start,
                new_end,
            )

        item["queue_index"] = index + 1

    report = {
        "schema_version": (
            "siraj-alignment-timeline-partition-recovery-v6.6-r6.1"
        ),
        "status": "PASS",
        "episode_duration_seconds": episode_duration,
        "item_count": len(items),
        "discontinuity_count": len(discontinuities),
        "discontinuities": discontinuities,
        "normalization_strategy": (
            "ADJACENT_BOUNDARY_MIDPOINT;"
            "FIRST_START_ZERO;"
            "LAST_END_FAIL_CLOSED_AUDIO_BOUND_AUTHORITY"
        ),
        "semantic_content_changed": False,
        "independent_alignment_reaudit_required": True,
    }
    return items, report


def validate_structural_repair_candidate(
    repo_root: Path,
    episode_id: str,
    original: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    candidate = _extract_candidate(result)
    items = _normalize_items(candidate)
    items = normalize_visual_treatments(items)
    duration = _episode_duration(repo, episode_id)
    items, partition_report = canonicalize_timeline_partition(
        items,
        duration,
    )

    expanded = _expand_items(
        episode_id,
        items,
    )
    _validate_full_timeline(
        expanded,
        duration,
    )

    generated_video_seconds = sum(
        float(item["end_seconds"]) - float(item["start_seconds"])
        for item in expanded
        if str(
            item.get("final_budget_treatment")
            or item.get("treatment")
            or ""
        ).upper()
        == "GENERATED_VIDEO"
    )
    max_video_seconds = duration * MAX_GENERATED_VIDEO_RATIO
    coverage = validate_true_video_coverage(duration, generated_video_seconds)
    if coverage.status != "PASS":
        raise AlignmentStructuralRepairV66R6Error(
            coverage.reason or coverage.status
        )

    original_items = original.get("items")
    original_ids = (
        [
            str(item.get("shot_id") or "")
            for item in original_items
            if isinstance(item, Mapping)
        ]
        if isinstance(original_items, list)
        else []
    )
    repaired_ids = [str(item["shot_id"]) for item in items]

    candidate["items"] = items
    candidate["status"] = "PASS"
    candidate["alignment_repair_applied"] = True
    candidate["alignment_repair_version"] = "V6.6-R6"
    candidate["alignment_structural_change"] = (
        original_ids != repaired_ids
    )
    candidate["alignment_repair_hard_validation"] = {
        "status": "PASS",
        "full_timeline_coverage": True,
        "episode_duration_seconds": duration,
        "generated_video_seconds": round(
            generated_video_seconds,
            3,
        ),
        "generated_video_max_seconds": round(
            max_video_seconds,
            3,
        ),
        "generated_video_max_ratio": (
            MAX_GENERATED_VIDEO_RATIO
        ),
        "generated_video_min_ratio": MIN_TRUE_VIDEO_FRACTION,
        "generated_video_coverage_validation": coverage.as_dict(),
        "original_shot_count": len(original_ids),
        "repaired_shot_count": len(repaired_ids),
        "independent_alignment_reaudit_required": True,
        "duplicate_gate_rerun_required": True,
        "media_cost_preflight_rerun_required": True,
    }
    candidate["timeline_partition_normalization"] = partition_report

    return candidate


def next_iteration_number(
    root: Path,
    journal_rows: list[dict[str, Any]],
) -> int:
    used: set[int] = set()

    for row in journal_rows:
        try:
            used.add(int(row.get("iteration")))
        except (TypeError, ValueError):
            pass

    if root.is_dir():
        for path in root.glob("iteration-*"):
            try:
                used.add(
                    int(path.name.rsplit("-", 1)[1])
                )
            except (IndexError, ValueError):
                continue

    return (max(used) + 1) if used else 1


def _archive_and_remove(
    source: Path,
    destination_root: Path,
    repo: Path,
    episode_id: str,
) -> bool:
    if not source.is_file():
        return False

    destination_root.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination = destination_root / source.name

    if destination.exists():
        destination = (
            destination_root
            / (
                source.stem
                + "-"
                + hashlib.sha256(
                    source.read_bytes()
                ).hexdigest()[:12]
                + source.suffix
            )
        )

    shutil.copy2(
        source,
        destination,
    )
    record_invalidation(
        repo,
        episode_id,
        source,
        reason="STRUCTURAL_REPAIR_INPUT_CHANGED",
        classification="STALE_BUT_PRESERVED",
    )
    return True


def _latest_unaccepted_r3_response(ep: Path) -> Path:
    root = ep / R3_ROOT_REL
    candidates = [
        path
        for path in root.glob(
            "iteration-*/repaired-prompt-plan.json"
        )
        if path.is_file()
    ]

    if not candidates:
        raise AlignmentStructuralRepairV66R6Error(
            "NO_EXISTING_R3_REPAIR_RESPONSE_FOUND"
        )

    candidates.sort(
        key=lambda path: (
            path.stat().st_mtime_ns,
            str(path),
        ),
        reverse=True,
    )
    return candidates[0]


def resolve_local_guard_if_exact(ep: Path) -> str:
    path = ep / RETRY_GUARD_REL
    if not path.is_file():
        return "NOT_PRESENT"

    value = _read(path)
    error = str(value.get("error") or "")

    if (
        value.get("status") == "RETRY_AUTHORIZATION_REQUIRED"
        and (
            "ALIGNMENT_REPAIR_SHOT_ID_OR_ORDER_CHANGE_FORBIDDEN"
            in error
        )
    ):
        value["status"] = (
            "RESOLVED_LOCAL_STRUCTURAL_REPAIR_POLICY"
        )
        value["resolution"] = (
            "LOCAL_POLICY_REJECTED_ALREADY_PAID_VALID_LUNA_RESPONSE;"
            "NO_PROVIDER_RETRY_REQUIRED"
        )
        value["resolved_at_utc"] = _now()
        _write(path, value)
        return "RESOLVED"

    return "PRESERVED"


def recover_latest_already_paid_structural_response(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    prompts_path = ep / PROMPTS_REL

    original = _read(prompts_path)
    response_path = _latest_unaccepted_r3_response(ep)
    result = _read(response_path)

    repaired = validate_structural_repair_candidate(
        repo,
        episode_id,
        original,
        result,
    )

    old_items = original.get("items")
    old_count = (
        len(old_items)
        if isinstance(old_items, list)
        else 0
    )
    new_items = repaired.get("items")
    new_count = (
        len(new_items)
        if isinstance(new_items, list)
        else 0
    )

    if _canonical_sha(original) == _canonical_sha(repaired):
        return {
            "status": "ALREADY_ADOPTED",
            "old_shot_count": old_count,
            "new_shot_count": new_count,
            "response_path": str(response_path),
        }

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    recovery_root = (
        ep / R6_ROOT_REL / ("recovery-" + stamp)
    )
    recovery_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    shutil.copy2(
        prompts_path,
        recovery_root / "prompt-plan-before.json",
    )
    shutil.copy2(
        response_path,
        recovery_root / "already-paid-luna-response.json",
    )

    _write(
        prompts_path,
        repaired,
    )
    _write(
        recovery_root / "prompt-plan-after.json",
        repaired,
    )

    stale_root = recovery_root / "stale-artifacts"
    cleared = {}

    for label, relative in (
        ("alignment", ALIGNMENT_REL),
        ("duplicate", DUPLICATE_REL),
        ("queue", QUEUE_REL),
        ("cost", COST_REL),
    ):
        cleared[label] = _archive_and_remove(
            ep / relative,
            stale_root,
            repo,
            episode_id,
        )

    auth_path = authorization_path(
        repo,
        episode_id,
        ALIGNMENT_STAGE,
    )
    cleared["alignment_authorization"] = _archive_and_remove(
        auth_path,
        stale_root,
        repo,
        episode_id,
    )

    guard_status = resolve_local_guard_if_exact(ep)

    record = {
        "schema_version": (
            "siraj-alignment-structural-repair-recovery-v6.6-r6"
        ),
        "status": "PASS",
        "episode_id": episode_id,
        "reused_existing_paid_response": True,
        "new_network_call": False,
        "new_paid_provider_request": False,
        "original_shot_count": old_count,
        "repaired_shot_count": new_count,
        "structural_change": repaired.get(
            "alignment_structural_change"
        ),
        "response_path": str(
            response_path.relative_to(repo)
        ),
        "cleared_stale_artifacts": cleared,
        "retry_guard_resolution": guard_status,
        "prompt_plan_sha256": _canonical_sha(repaired),
        "created_at_utc": _now(),
    }

    _write(
        recovery_root / "recovery.json",
        record,
    )

    journal = ep / R6_ROOT_REL / "journal.jsonl"
    journal.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with journal.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

    return {
        **record,
        "recovery_root": str(recovery_root),
    }
