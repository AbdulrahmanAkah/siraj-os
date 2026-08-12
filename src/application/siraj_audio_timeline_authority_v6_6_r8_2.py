from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping, Iterable

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"

PROMPTS_REL = Path(
    "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
)
STORYBOARD_REL = Path(
    "preproduction/audio-bound-storyboard-v6-1.json"
)
AUDIO_TIMELINE_REL = Path(
    "preproduction/audio-timestamps-and-beats-v6-1.json"
)

CANONICAL_TREATMENTS = frozenset(
    {
        "ANIMATED_STILL_COMPOSITING",
        "GENERATED_VIDEO",
        "GRAPHICS",
    }
)

DETERMINISTIC_ALIGNMENT_FINDING_TYPES = frozenset(
    {
        "timeline_duration_conflict",
        "final_shot_duration_conflict",
        "unresolved_normalization_discontinuity",
        "invalid_final_exit_validation",
        "budget_denominator_conflict",
    }
)


class AudioTimelineAuthorityV66R82Error(RuntimeError):
    pass


class AlignmentConvergenceGuardV66R82Error(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(encoding="utf-8-sig")
    )
    if not isinstance(value, dict):
        raise AudioTimelineAuthorityV66R82Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        path.name + "." + str(os.getpid()) + ".tmp"
    )
    try:
        tmp.write_text(
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
        os.replace(tmp, path)
    except Exception:
        raise


def _as_float(value: Any, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise AudioTimelineAuthorityV66R82Error(
            "FLOAT_REQUIRED:" + label
        ) from exc


def canonical_audio_duration(audio_timeline: Mapping[str, Any]) -> float:
    candidates: list[float] = []

    for key in (
        "total_duration_seconds",
        "episode_duration_seconds",
        "duration_seconds",
    ):
        if key in audio_timeline:
            try:
                candidates.append(float(audio_timeline[key]))
            except (TypeError, ValueError):
                pass

    for key in ("items", "segments", "beats"):
        raw = audio_timeline.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            if not isinstance(item, Mapping):
                continue
            for end_key in (
                "end_seconds",
                "speech_end_seconds",
            ):
                if end_key in item:
                    try:
                        candidates.append(float(item[end_key]))
                    except (TypeError, ValueError):
                        pass

    if not candidates:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_TIMELINE_DURATION_NOT_FOUND"
        )

    return max(candidates)


def storyboard_shots(
    storyboard: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw = storyboard.get("shots")
    if not isinstance(raw, list) or not raw:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_BOUND_STORYBOARD_SHOTS_REQUIRED"
        )

    result: list[dict[str, Any]] = []

    for index, shot in enumerate(raw, start=1):
        if not isinstance(shot, Mapping):
            raise AudioTimelineAuthorityV66R82Error(
                "AUDIO_BOUND_STORYBOARD_SHOT_OBJECT_REQUIRED"
            )

        row = dict(shot)
        shot_id = str(row.get("shot_id") or "").strip()
        expected = f"EP002-SH-{index:03d}"

        if shot_id != expected:
            raise AudioTimelineAuthorityV66R82Error(
                "AUDIO_BOUND_STORYBOARD_SHOT_ID_SEQUENCE_INVALID:"
                + shot_id
                + ":expected="
                + expected
            )

        audio_ref = row.get("audio_ref")
        if not isinstance(audio_ref, Mapping):
            raise AudioTimelineAuthorityV66R82Error(
                "AUDIO_BOUND_STORYBOARD_AUDIO_REF_REQUIRED:"
                + shot_id
            )

        range_seconds = audio_ref.get("range_seconds")
        if (
            not isinstance(range_seconds, list)
            or len(range_seconds) != 2
        ):
            raise AudioTimelineAuthorityV66R82Error(
                "AUDIO_BOUND_STORYBOARD_RANGE_REQUIRED:"
                + shot_id
            )

        start = _as_float(
            range_seconds[0],
            shot_id + ".start",
        )
        end = _as_float(
            range_seconds[1],
            shot_id + ".end",
        )

        if end <= start:
            raise AudioTimelineAuthorityV66R82Error(
                "AUDIO_BOUND_STORYBOARD_RANGE_INVALID:"
                + shot_id
            )

        row["_authority_start_seconds"] = start
        row["_authority_end_seconds"] = end
        result.append(row)

    return result


def validate_storyboard_authority(
    shots: list[dict[str, Any]],
    canonical_duration: float,
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    if not shots:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_BOUND_STORYBOARD_EMPTY"
        )

    first = float(shots[0]["_authority_start_seconds"])
    last = float(shots[-1]["_authority_end_seconds"])

    if abs(first) > tolerance:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_BOUND_STORYBOARD_FIRST_START_NOT_ZERO:"
            + str(first)
        )

    if abs(last - canonical_duration) > tolerance:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_BOUND_STORYBOARD_LAST_END_MISMATCH:"
            + str(last)
            + ":audio="
            + str(canonical_duration)
        )

    discontinuities: list[dict[str, Any]] = []

    for index in range(1, len(shots)):
        left = shots[index - 1]
        right = shots[index]
        left_end = float(left["_authority_end_seconds"])
        right_start = float(right["_authority_start_seconds"])
        delta = right_start - left_end

        if abs(delta) > tolerance:
            discontinuities.append(
                {
                    "previous_shot_id": left["shot_id"],
                    "shot_id": right["shot_id"],
                    "delta_seconds": delta,
                }
            )

    if discontinuities:
        raise AudioTimelineAuthorityV66R82Error(
            "AUDIO_BOUND_STORYBOARD_DISCONTINUITY:"
            + json.dumps(
                discontinuities,
                ensure_ascii=False,
                sort_keys=True,
            )
        )

    return {
        "status": "PASS",
        "first_start_seconds": first,
        "last_end_seconds": last,
        "shot_count": len(shots),
        "discontinuity_count": 0,
        "canonical_episode_duration_seconds": canonical_duration,
    }


def _prompt_text(item: Mapping[str, Any]) -> str:
    for key in (
        "runware_positive_prompt_en",
        "positive_prompt_en",
        "visual_prompt_en",
        "production_prompt_en",
        "provider_prompt_en",
        "image_prompt_en",
        "video_prompt_en",
        "prompt_en",
        "prompt_text",
        "prompt",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def _negative_prompt_text(item: Mapping[str, Any]) -> str:
    for key in (
        "runware_negative_prompt_en",
        "negative_prompt_en",
        "visual_negative_prompt_en",
        "provider_negative_prompt_en",
        "prompt_negative_en",
        "negative_prompt",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def candidate_items(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = payload.get("items")
    if not isinstance(raw, list):
        return {}

    result: dict[str, dict[str, Any]] = {}

    for item in raw:
        if not isinstance(item, Mapping):
            continue
        shot_id = str(item.get("shot_id") or "").strip()
        if not shot_id:
            continue
        result[shot_id] = dict(item)

    return result


def score_candidate_item(item: Mapping[str, Any]) -> int:
    score = 0

    if _prompt_text(item):
        score += 20
    if _negative_prompt_text(item):
        score += 8

    treatment = str(
        item.get("final_budget_treatment")
        or item.get("treatment")
        or ""
    ).strip().upper()

    if treatment in CANONICAL_TREATMENTS:
        score += 8

    for key in (
        "semantic_beat",
        "subject",
        "environment",
        "composition",
        "camera_angle",
        "camera_movement",
    ):
        if str(item.get(key) or "").strip():
            score += 2

    if item.get("contains_people") is not None:
        score += 1

    return score


def select_best_items(
    storyboard: list[dict[str, Any]],
    candidates: Iterable[
        tuple[str, Mapping[str, Any]]
    ],
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    required_ids = [
        str(shot["shot_id"])
        for shot in storyboard
    ]

    best: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    scores: dict[str, int] = {}

    for source_name, payload in candidates:
        by_id = candidate_items(payload)

        for shot_id in required_ids:
            item = by_id.get(shot_id)
            if item is None:
                continue

            score = score_candidate_item(item)

            # Prefer earlier stable R4 base material when quality is tied.
            source_bonus = (
                3
                if "visual-timeline-coverage-autorepair-v6-6-r4"
                in source_name
                and "iteration-001"
                in source_name
                else 0
            )
            score += source_bonus

            if (
                shot_id not in scores
                or score > scores[shot_id]
            ):
                best[shot_id] = item
                sources[shot_id] = source_name
                scores[shot_id] = score

    missing = [
        shot_id
        for shot_id in required_ids
        if shot_id not in best
    ]

    if missing:
        raise AudioTimelineAuthorityV66R82Error(
            "AUTHORITATIVE_PROMPT_RECOVERY_MISSING_SHOTS:"
            + ",".join(missing)
        )

    missing_prompts = [
        shot_id
        for shot_id in required_ids
        if not _prompt_text(best[shot_id])
    ]

    if missing_prompts:
        raise AudioTimelineAuthorityV66R82Error(
            "AUTHORITATIVE_PROMPT_RECOVERY_EMPTY_PROMPTS:"
            + ",".join(missing_prompts)
        )

    return best, sources


def _canonicalize_prompt_keys(item: dict[str, Any]) -> None:
    positive = _prompt_text(item)
    negative = _negative_prompt_text(item)

    if positive:
        item["runware_positive_prompt_en"] = positive
    if negative:
        item["runware_negative_prompt_en"] = negative


def _generated_video_seconds(items: list[dict[str, Any]]) -> float:
    total = 0.0

    for item in items:
        treatment = str(
            item.get("final_budget_treatment")
            or item.get("treatment")
            or ""
        ).strip().upper()

        if treatment != "GENERATED_VIDEO":
            continue

        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
        total += end - start

    return total


def rebuild_prompt_plan_from_audio_bound_storyboard(
    *,
    current_plan: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    audio_timeline: Mapping[str, Any],
    candidate_payloads: Iterable[
        tuple[str, Mapping[str, Any]]
    ],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    canonical_duration = canonical_audio_duration(
        audio_timeline
    )
    shots = storyboard_shots(storyboard)

    authority_report = validate_storyboard_authority(
        shots,
        canonical_duration,
    )

    best, sources = select_best_items(
        shots,
        candidate_payloads,
    )

    rebuilt_items: list[dict[str, Any]] = []

    for index, shot in enumerate(shots, start=1):
        shot_id = str(shot["shot_id"])
        audio_ref = shot["audio_ref"]

        item = dict(best[shot_id])

        item["shot_id"] = shot_id
        item["queue_index"] = index
        item["start_seconds"] = float(
            shot["_authority_start_seconds"]
        )
        item["end_seconds"] = float(
            shot["_authority_end_seconds"]
        )

        segment_id = str(
            audio_ref.get("segment_id")
            or ""
        ).strip()

        item["segment_ids"] = (
            [segment_id]
            if segment_id
            else []
        )

        beat_id = audio_ref.get("beat_id")
        item["beat_id"] = (
            str(beat_id)
            if beat_id is not None
            else None
        )

        item["audio_ref_authority"] = {
            "source": "audio-bound-storyboard-v6-1.json",
            "phase": audio_ref.get("phase"),
            "cue_ar": audio_ref.get("cue_ar"),
            "range_seconds": [
                float(
                    shot["_authority_start_seconds"]
                ),
                float(
                    shot["_authority_end_seconds"]
                ),
            ],
            "segment_id": (
                segment_id
                if segment_id
                else None
            ),
            "beat_id": (
                str(beat_id)
                if beat_id is not None
                else None
            ),
        }

        item.pop(
            "timeline_partition_original",
            None,
        )

        # Any subshots computed against stale parent timings must be rebuilt
        # later by the media queue from the authoritative parent interval.
        item.pop(
            "video_subshots",
            None,
        )

        _canonicalize_prompt_keys(item)
        rebuilt_items.append(item)

    # Exact adjacency proof after overlay.
    for index in range(1, len(rebuilt_items)):
        left = rebuilt_items[index - 1]
        right = rebuilt_items[index]

        if abs(
            float(left["end_seconds"])
            - float(right["start_seconds"])
        ) > 1e-6:
            raise AudioTimelineAuthorityV66R82Error(
                "REBUILT_PROMPT_PLAN_DISCONTINUITY:"
                + str(right["shot_id"])
            )

    if abs(
        float(rebuilt_items[-1]["end_seconds"])
        - canonical_duration
    ) > 1e-6:
        raise AudioTimelineAuthorityV66R82Error(
            "REBUILT_PROMPT_PLAN_END_MISMATCH"
        )

    rebuilt = dict(current_plan)
    rebuilt["status"] = "PASS"
    rebuilt["items"] = rebuilt_items
    rebuilt[
        "audio_timeline_authority_recovery_v6_6_r8_2"
    ] = {
        "status": "PASS",
        "authoritative_timing_source": (
            "preproduction/audio-bound-storyboard-v6-1.json"
        ),
        "authoritative_audio_duration_source": (
            "preproduction/audio-timestamps-and-beats-v6-1.json"
        ),
        "canonical_episode_duration_seconds": canonical_duration,
        "shot_count": len(rebuilt_items),
        "semantic_prompt_sources_by_shot": sources,
        "timeline_discontinuity_count": 0,
        "unknown_paid_attempt_retried": False,
    }

    generated_seconds = _generated_video_seconds(
        rebuilt_items
    )
    maximum_seconds = canonical_duration * (2.0 / 3.0)

    self_review = dict(
        rebuilt.get("self_review")
        if isinstance(
            rebuilt.get("self_review"),
            Mapping,
        )
        else {}
    )

    self_review[
        "canonical_episode_duration_seconds"
    ] = canonical_duration
    self_review[
        "episode_duration_seconds"
    ] = canonical_duration
    self_review["first_start_seconds"] = 0.0
    self_review["last_end_seconds"] = canonical_duration
    self_review["status"] = "PASS"
    self_review["timeline"] = {
        "coverage": "FULL",
        "gaps": 0,
        "overlaps": 0,
        "discontinuity_count": 0,
        "all_adjacent_boundaries_match": True,
        "authority": "AUDIO_BOUND_STORYBOARD_V6_1",
    }
    self_review["generated_video_budget"] = {
        "generated_video_seconds": round(
            generated_seconds,
            6,
        ),
        "generated_video_ratio": round(
            generated_seconds / canonical_duration,
            9,
        ),
        "maximum_allowed_ratio": 2.0 / 3.0,
        "maximum_allowed_seconds": round(
            maximum_seconds,
            6,
        ),
        "status": (
            "PASS"
            if generated_seconds <= maximum_seconds + 1e-6
            else "FAIL"
        ),
        "denominator_source": (
            "AUTHORITATIVE_AUDIO_TIMELINE_623_584"
        ),
    }
    self_review["prompt_completeness"] = {
        "item_count": len(rebuilt_items),
        "items_with_nonempty_runware_positive_prompt_en": sum(
            1
            for item in rebuilt_items
            if str(
                item.get("runware_positive_prompt_en")
                or ""
            ).strip()
        ),
        "items_with_nonempty_runware_negative_prompt_en": sum(
            1
            for item in rebuilt_items
            if str(
                item.get("runware_negative_prompt_en")
                or ""
            ).strip()
        ),
        "status": "PASS",
    }
    self_review["gate_state"] = {
        "independent_alignment_reaudit_required": True,
        "duplicate_gate_rerun_required": True,
        "media_cost_preflight_rerun_required": True,
        "pre_spend_status": "REQUIRES_INDEPENDENT_REAUDIT",
        "timeline_partition_normalization_status": "PASS",
        "timeline_partition_normalization_discontinuity_count": 0,
    }

    # The final exit must follow the actual PRE_OUTRO tail.
    last_item = rebuilt_items[-1]
    self_review["final_exit"] = {
        "shot_id": last_item["shot_id"],
        "start_seconds": float(
            last_item["start_seconds"]
        ),
        "end_seconds": float(
            last_item["end_seconds"]
        ),
        "duration_seconds": round(
            float(last_item["end_seconds"])
            - float(last_item["start_seconds"]),
            6,
        ),
        "authority": "AUDIO_BOUND_STORYBOARD_V6_1",
        "reopening": False,
    }

    rebuilt["self_review"] = self_review
    rebuilt["timeline_partition_normalization"] = {
        "schema_version": (
            "siraj-audio-bound-authority-partition-v6.6-r8.2"
        ),
        "status": "PASS",
        "episode_duration_seconds": canonical_duration,
        "item_count": len(rebuilt_items),
        "discontinuity_count": 0,
        "discontinuities": [],
        "normalization_strategy": (
            "AUTHORITATIVE_AUDIO_BOUND_STORYBOARD_RANGES;"
            "NO_LAST_SHOT_STRETCH"
        ),
        "semantic_content_changed": False,
        "independent_alignment_reaudit_required": True,
    }

    report = {
        **authority_report,
        "generated_video_seconds": generated_seconds,
        "generated_video_max_seconds": maximum_seconds,
        "generated_video_ratio": (
            generated_seconds / canonical_duration
        ),
        "prompt_item_count": len(rebuilt_items),
        "positive_prompt_count": sum(
            1
            for item in rebuilt_items
            if str(
                item.get("runware_positive_prompt_en")
                or ""
            ).strip()
        ),
        "negative_prompt_count": sum(
            1
            for item in rebuilt_items
            if str(
                item.get("runware_negative_prompt_en")
                or ""
            ).strip()
        ),
    }

    return rebuilt, report


def alignment_failure_signature(
    audit: Mapping[str, Any],
) -> str:
    findings = audit.get("blocking_findings")
    if not isinstance(findings, list):
        findings = []

    normalized: list[tuple[str, str, str]] = []

    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        normalized.append(
            (
                str(
                    finding.get("severity")
                    or ""
                ).upper(),
                str(
                    finding.get("type")
                    or ""
                ).strip(),
                str(
                    finding.get("location")
                    or ""
                ).strip(),
            )
        )

    return json.dumps(
        sorted(normalized),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def deterministic_alignment_failure(
    audit: Mapping[str, Any],
) -> bool:
    findings = audit.get("blocking_findings")
    if not isinstance(findings, list):
        return False

    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        if (
            str(finding.get("type") or "").strip()
            in DETERMINISTIC_ALIGNMENT_FINDING_TYPES
        ):
            return True

    return False


def guard_alignment_failure_before_luna(
    repo_root: Path,
    episode_id: str,
    audit: Mapping[str, Any],
) -> None:
    if deterministic_alignment_failure(audit):
        raise AlignmentConvergenceGuardV66R82Error(
            "DETERMINISTIC_ALIGNMENT_FAILURE_REQUIRES_LOCAL_REPAIR:"
            + alignment_failure_signature(audit)
        )

    repo = Path(repo_root).resolve()
    root = (
        repo
        / "projects"
        / episode_id
        / "orchestration"
        / "alignment-semantic-autorepair-v6-6-r3"
    )
    epoch = (
        root
        / "convergence-guard-epoch-v6-6-r8-2.json"
    )

    if not epoch.is_file():
        return

    epoch_ns = epoch.stat().st_mtime_ns
    signature = alignment_failure_signature(audit)

    for iteration in sorted(
        root.glob("iteration-*")
    ):
        try:
            if iteration.stat().st_mtime_ns < epoch_ns:
                continue
        except OSError:
            continue

        failed = iteration / "failed-audit.json"
        completed = iteration / "prompts-after.json"

        # Only completed editorial repairs count toward convergence.
        # A failed/unknown network attempt does not.
        if not failed.is_file() or not completed.is_file():
            continue

        try:
            previous = read_json(failed)
        except Exception:
            continue

        if alignment_failure_signature(previous) == signature:
            raise AlignmentConvergenceGuardV66R82Error(
                "ALIGNMENT_CONVERGENCE_NO_OBJECTIVE_PROGRESS_"
                "HUMAN_REVIEW_REQUIRED:"
                + signature
            )
