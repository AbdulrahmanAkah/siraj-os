"""Canonical SIRAJ cinematic media-mix policy (V2).

The policy is deliberately small and dependency free so every planner and
pre-spend gate can use the same definition of *true generated-video
coverage*.  Requested provider seconds, animated stills, graphics and local
composites never count toward coverage.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence


POLICY_ID = "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2"
POLICY_SCHEMA_VERSION = "siraj-cinematic-media-mix-policy-v2"
MIN_TRUE_VIDEO_FRACTION = 0.50
MAX_TRUE_VIDEO_FRACTION = 0.75
VIDEO_COVERAGE_SELECTION_MODE = "DIRECTORIAL_OPTIMIZATION"
OLD_TWO_THIRDS_POLICY_ACTIVE = False
# Duplicate-gate thresholds are policy metadata, not coverage arithmetic.
PROMPT_NEAR_DUPLICATE_THRESHOLD = 0.92
SEMANTIC_NEAR_DUPLICATE_THRESHOLD = 0.94
PERCEPTUAL_HASH_MAX_AVG_HAMMING = 3.0
PERCEPTUAL_HASH_MAX_SAMPLE_HAMMING = 4


class MediaMixPolicyError(ValueError):
    """Raised when a media proposal violates the canonical mix policy."""


@dataclass(frozen=True, slots=True)
class CoverageValidation:
    status: str
    true_video_seconds: float
    episode_duration_seconds: float
    true_video_fraction: float
    true_video_percent: float
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class CinematicMediaMixPolicyV2:
    policy_id: str = POLICY_ID
    schema_version: str = POLICY_SCHEMA_VERSION
    min_true_video_fraction: float = MIN_TRUE_VIDEO_FRACTION
    max_true_video_fraction: float = MAX_TRUE_VIDEO_FRACTION
    selection_mode: str = VIDEO_COVERAGE_SELECTION_MODE
    old_two_thirds_policy_active: bool = OLD_TWO_THIRDS_POLICY_ACTIVE
    generated_video_is_timeline_coverage: bool = True
    provider_requested_seconds_count_as_coverage: bool = False
    animated_stills_count_as_coverage: bool = False
    local_graphics_count_as_coverage: bool = False
    clip_reuse_counts_as_coverage: bool = False
    looped_video_counts_as_coverage: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


POLICY = CinematicMediaMixPolicyV2()


def validate_true_video_coverage(
    episode_duration_seconds: float,
    true_video_seconds: float,
    *,
    tolerance_seconds: float = 1e-6,
) -> CoverageValidation:
    """Validate true timeline coverage against the hard 50--75% range."""

    duration = float(episode_duration_seconds)
    seconds = float(true_video_seconds)
    if duration <= 0:
        raise MediaMixPolicyError("EPISODE_DURATION_MUST_BE_POSITIVE")
    if seconds < -tolerance_seconds:
        raise MediaMixPolicyError("TRUE_VIDEO_SECONDS_NEGATIVE")
    fraction = seconds / duration
    percent = fraction * 100.0
    if fraction < MIN_TRUE_VIDEO_FRACTION - tolerance_seconds:
        return CoverageValidation(
            "FAIL_UNDER_VIDEO_FLOOR",
            round(seconds, 6),
            round(duration, 6),
            round(fraction, 9),
            round(percent, 6),
            "MEDIA_PLAN_INVALID_UNDER_VIDEO_FLOOR",
        )
    if fraction > MAX_TRUE_VIDEO_FRACTION + tolerance_seconds:
        return CoverageValidation(
            "FAIL_OVER_VIDEO_CEILING",
            round(seconds, 6),
            round(duration, 6),
            round(fraction, 9),
            round(percent, 6),
            "MEDIA_PLAN_INVALID_OVER_VIDEO_CEILING",
        )
    return CoverageValidation(
        "PASS",
        round(seconds, 6),
        round(duration, 6),
        round(fraction, 9),
        round(percent, 6),
    )


def assert_true_video_coverage(
    episode_duration_seconds: float,
    true_video_seconds: float,
) -> CoverageValidation:
    result = validate_true_video_coverage(episode_duration_seconds, true_video_seconds)
    if result.status != "PASS":
        raise MediaMixPolicyError(result.reason or result.status)
    return result


def _clean_intervals(
    intervals: Iterable[Mapping[str, Any]],
    *,
    episode_duration_seconds: float,
) -> list[tuple[float, float, str]]:
    values: list[tuple[float, float, str]] = []
    for row in intervals:
        start = float(row.get("start_seconds", row.get("timeline_start_seconds", 0.0)))
        end = float(row.get("end_seconds", row.get("timeline_end_seconds", 0.0)))
        label = str(row.get("shot_id") or row.get("unit_id") or "unknown")
        if start < -1e-6 or end > episode_duration_seconds + 1e-6 or end <= start:
            raise MediaMixPolicyError("VIDEO_INTERVAL_OUT_OF_TIMELINE:" + label)
        values.append((max(0.0, start), min(episode_duration_seconds, end), label))
    values.sort(key=lambda value: (value[0], value[1], value[2]))
    previous_end = 0.0
    for start, end, label in values:
        if start < previous_end - 1e-6:
            raise MediaMixPolicyError("VIDEO_INTERVAL_OVERLAP:" + label)
        previous_end = max(previous_end, end)
    return values


def true_video_seconds_from_intervals(
    intervals: Sequence[Mapping[str, Any]],
    *,
    episode_duration_seconds: float,
) -> float:
    """Return authoritative timeline coverage; never provider request time."""

    clean = _clean_intervals(intervals, episode_duration_seconds=episode_duration_seconds)
    return round(sum(end - start for start, end, _ in clean), 6)


def true_video_seconds_from_units(
    units: Sequence[Mapping[str, Any]],
    *,
    episode_duration_seconds: float,
) -> float:
    """Count only distinct RUNWARE_VIDEO timeline intervals.

    Provider request time, animated stills, graphics/local units and unused
    duration are intentionally ignored.
    """

    return true_video_seconds_from_intervals(
        [
            unit
            for unit in units
            if str(unit.get("media_kind") or "") == "RUNWARE_VIDEO"
            and unit.get("looped") is not True
            and not unit.get("reused_from_unit_id")
        ],
        episode_duration_seconds=episode_duration_seconds,
    )


def coverage_diagnostics(
    intervals: Sequence[Mapping[str, Any]],
    *,
    episode_duration_seconds: float,
    shot_intervals: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate no-video spans and fatigue diagnostics from timeline intervals."""

    clean = _clean_intervals(intervals, episode_duration_seconds=episode_duration_seconds)
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end, _ in clean:
        if start > cursor + 1e-6:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < episode_duration_seconds - 1e-6:
        gaps.append((cursor, episode_duration_seconds))
    durations = [round(end - start, 6) for start, end in gaps]
    shot_rows = list(shot_intervals or [])
    consecutive_max = 0
    current = 0
    for row in sorted(shot_rows, key=lambda item: int(item.get("queue_index") or 0)):
        treatment = str(row.get("selected_media_treatment") or row.get("final_budget_treatment") or "")
        if treatment in {"ANIMATED_STILL_PREFERRED", "ANIMATED_STILL_COMPOSITING", "GRAPHIC_LOCAL_PREFERRED", "GRAPHICS"}:
            current += 1
            consecutive_max = max(consecutive_max, current)
        else:
            current = 0
    return {
        "longest_no_true_video_span_seconds": round(max(durations, default=0.0), 6),
        "number_of_20s_plus_no_true_video_spans": sum(1 for value in durations if value >= 20.0 - 1e-6),
        "number_of_30s_plus_no_true_video_spans": sum(1 for value in durations if value >= 30.0 - 1e-6),
        "number_of_60s_plus_no_true_video_spans": sum(1 for value in durations if value >= 60.0 - 1e-6),
        "no_true_video_spans": [
            {"start_seconds": start, "end_seconds": end, "duration_seconds": round(end - start, 6)}
            for start, end in gaps
        ],
        "consecutive_still_shot_count_max": consecutive_max,
    }


def validate_no_reuse_or_loop(units: Sequence[Mapping[str, Any]]) -> None:
    """Reject duplicate provider directions and explicit loop/reuse markers."""

    identities: set[str] = set()
    payloads: set[str] = set()
    for unit in units:
        if str(unit.get("media_kind")) != "RUNWARE_VIDEO":
            continue
        if unit.get("looped") is True or unit.get("reused_from_unit_id"):
            raise MediaMixPolicyError("VIDEO_LOOP_OR_REUSE_FORBIDDEN")
        identity = str(unit.get("unit_id") or "")
        if not identity or identity in identities:
            raise MediaMixPolicyError("DUPLICATE_VIDEO_UNIT_ID")
        identities.add(identity)
        payload_hash = str(unit.get("direction_fingerprint") or unit.get("payload_sha256") or "")
        if payload_hash and payload_hash in payloads:
            raise MediaMixPolicyError("DUPLICATE_VIDEO_DIRECTION")
        if payload_hash:
            payloads.add(payload_hash)
