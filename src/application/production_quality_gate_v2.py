"""Final production gate combining narration, world, visual, and budget rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.application.arabic_performance_script_v2 import (
    ArabicPerformanceScriptError,
    validate_performance_script,
)
from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    validate_release_report,
    validate_shot_policy,
)
from src.application.world_continuity_policy_v1 import (
    validate_world_continuity,
)

SCHEMA_VERSION = "siraj-production-quality-gate-v2"


@dataclass(frozen=True, slots=True)
class GateIssue:
    code: str
    scope: str
    severity: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "scope": self.scope,
            "severity": self.severity,
            "detail": self.detail,
        }


def evaluate_production_quality(
    *,
    script: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    qa_report: Mapping[str, Any] | None = None,
    generated_video_spend_usd: float = 0.0,
) -> dict[str, Any]:
    issues: list[GateIssue] = []
    try:
        performance = validate_performance_script(script)
    except ArabicPerformanceScriptError as exc:
        performance = None
        issues.append(
            GateIssue(
                "ARABIC_PERFORMANCE_SCRIPT_INVALID",
                "AUDIO",
                "BLOCKING",
                str(exc),
            )
        )

    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        issues.append(
            GateIssue(
                "STORYBOARD_SHOTS_REQUIRED",
                "STORYBOARD",
                "BLOCKING",
                "Storyboard must contain shots.",
            )
        )
        shots = []
    for shot in shots:
        if not isinstance(shot, Mapping):
            issues.append(
                GateIssue(
                    "SHOT_OBJECT_REQUIRED",
                    "SHOT",
                    "BLOCKING",
                    "Shot entry is not an object.",
                )
            )
            continue
        shot_id = str(shot.get("shot_id") or "UNKNOWN")
        for code in validate_shot_policy(shot):
            issues.append(GateIssue(code, shot_id, "BLOCKING", code))

    for item in validate_world_continuity(storyboard):
        issues.append(
            GateIssue(item.code, item.shot_id, item.severity, item.detail)
        )

    if qa_report is not None:
        for code in validate_release_report(qa_report):
            issues.append(GateIssue(code, "FINAL_MASTER", "BLOCKING", code))

    if generated_video_spend_usd > HARD_GENERATED_VIDEO_SPEND_USD + 1e-9:
        issues.append(
            GateIssue(
                "GENERATED_VIDEO_HARD_CAP_EXCEEDED",
                "BUDGET",
                "BLOCKING",
                f"spent={generated_video_spend_usd:.4f}",
            )
        )

    blocking = [item for item in issues if item.severity == "BLOCKING"]
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS" if not blocking else "BLOCKED",
        "generated_video_spend_usd": round(generated_video_spend_usd, 6),
        "performance_metrics": (
            performance.get("metrics") if performance else None
        ),
        "blocking_issue_count": len(blocking),
        "issues": [item.to_dict() for item in issues],
    }
