"""Compatibility facade for the series-wide V2 production controller."""

from src.application.episode_production_control_v2 import (
    ANIMATED_STILL_SHOT_COUNT,
    EDITORIAL_SHOT_COUNT,
    GRAPHICS_SHOT_COUNT,
    HARD_CAP_USD,
    PASS_THRESHOLD,
    TARGET_SPEND_USD,
    VIDEO_PLANNED_SECONDS,
    VIDEO_SHOT_COUNT,
    VIDEO_TARGET_MAX_SECONDS,
    VIDEO_TARGET_MIN_SECONDS,
    BudgetSnapshot,
    EpisodeProductionPolicyError,
    EpisodeProgress,
    assert_budget_allows_new_paid_request,
    episode_progress,
    load_episode_plan,
    load_episode_policy,
    queue_rows,
    scan_actual_paid_spend,
)

__all__ = [
    "HARD_CAP_USD",
    "TARGET_SPEND_USD",
    "VIDEO_TARGET_MIN_SECONDS",
    "VIDEO_TARGET_MAX_SECONDS",
    "VIDEO_PLANNED_SECONDS",
    "VIDEO_SHOT_COUNT",
    "ANIMATED_STILL_SHOT_COUNT",
    "GRAPHICS_SHOT_COUNT",
    "EDITORIAL_SHOT_COUNT",
    "PASS_THRESHOLD",
    "EpisodeProductionPolicyError",
    "BudgetSnapshot",
    "EpisodeProgress",
    "load_episode_policy",
    "load_episode_plan",
    "scan_actual_paid_spend",
    "assert_budget_allows_new_paid_request",
    "episode_progress",
    "queue_rows",
]

# SIRAJ_V2_RUNTIME_TREATMENT_ALIAS
class _SirajV2TreatmentCounts(dict):
    _ALIASES = {
        "ANIMATED_STILL_COMPOSITING": (
            "DYNAMIC_STILL_SEQUENCE",
            "DYNAMIC_STILL",
        ),
        "GRAPHICS": ("AUTHORED_GRAPHICS",),
    }

    def _alias(self, key):
        names = self._ALIASES.get(key)
        if names is None:
            raise KeyError(key)
        return sum(int(dict.get(self, name, 0) or 0) for name in names)

    def __missing__(self, key):
        return self._alias(key)

    def get(self, key, default=None):
        if dict.__contains__(self, key):
            return dict.get(self, key, default)
        if key in self._ALIASES:
            return self._alias(key)
        return default


_siraj_v2_raw_load_episode_plan = load_episode_plan


def load_episode_plan(repo_root):
    plan = _siraj_v2_raw_load_episode_plan(repo_root)
    if not isinstance(plan, dict):
        return plan
    counts = plan.get("treatment_counts")
    if not isinstance(counts, dict):
        return plan
    result = dict(plan)
    result["treatment_counts"] = _SirajV2TreatmentCounts(counts)
    return result
