"""Cost-driven, video-first media selection for Siraj V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    TARGET_GENERATED_VIDEO_SPEND_USD,
    motion_required_for_shot,
)


class BudgetDrivenMediaPlannerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaOptionV2:
    option_id: str
    shot_id: str
    treatment: str
    estimated_cost_usd: float
    quality_score: int
    reliability_score: int
    generated_video_seconds: int = 0
    visual_fit_score: int = 0
    continuity_score: int = 0

    def validate(self) -> None:
        if not self.option_id.strip() or not self.shot_id.strip():
            raise BudgetDrivenMediaPlannerError("OPTION_AND_SHOT_ID_REQUIRED")
        if self.estimated_cost_usd < 0:
            raise BudgetDrivenMediaPlannerError("NEGATIVE_COST_FORBIDDEN")
        for value, label in (
            (self.quality_score, "quality"),
            (self.reliability_score, "reliability"),
            (self.visual_fit_score, "visual_fit"),
            (self.continuity_score, "continuity"),
        ):
            if not 0 <= value <= 100:
                raise BudgetDrivenMediaPlannerError(
                    f"OPTION_SCORE_OUT_OF_RANGE:{label}"
                )
        if self.generated_video_seconds < 0:
            raise BudgetDrivenMediaPlannerError("NEGATIVE_VIDEO_SECONDS")
        if self.treatment != "GENERATED_VIDEO" and self.generated_video_seconds:
            raise BudgetDrivenMediaPlannerError(
                "VIDEO_SECONDS_REQUIRE_GENERATED_VIDEO"
            )

    @property
    def utility(self) -> int:
        motion_bonus = 80 if self.treatment == "GENERATED_VIDEO" else 0
        return (
            self.quality_score * 5
            + self.reliability_score * 2
            + self.visual_fit_score * 4
            + self.continuity_score * 4
            + motion_bonus
        )


@dataclass(frozen=True, slots=True)
class BudgetDrivenPlanV2:
    selected: tuple[MediaOptionV2, ...]
    generated_video_spend_usd: float
    generated_video_seconds: int
    total_media_spend_usd: float
    target_headroom_usd: float
    hard_headroom_used: bool


def plan_media(
    shots: Sequence[Mapping[str, object]],
    options: Iterable[MediaOptionV2],
    *,
    allow_hard_headroom: bool = True,
) -> BudgetDrivenPlanV2:
    shot_ids = [str(item.get("shot_id") or "") for item in shots]
    if not shot_ids or any(not value for value in shot_ids):
        raise BudgetDrivenMediaPlannerError("SHOT_IDS_REQUIRED")
    if len(set(shot_ids)) != len(shot_ids):
        raise BudgetDrivenMediaPlannerError("DUPLICATE_SHOT_ID")

    groups: dict[str, list[MediaOptionV2]] = {shot_id: [] for shot_id in shot_ids}
    for option in options:
        option.validate()
        if option.shot_id not in groups:
            raise BudgetDrivenMediaPlannerError(
                f"OPTION_REFERENCES_UNKNOWN_SHOT:{option.shot_id}"
            )
        groups[option.shot_id].append(option)
    for shot_id, values in groups.items():
        if not values:
            raise BudgetDrivenMediaPlannerError(
                f"NO_MEDIA_OPTIONS_FOR_SHOT:{shot_id}"
            )

    target_cents = round(TARGET_GENERATED_VIDEO_SPEND_USD * 100)
    hard_cents = round(HARD_GENERATED_VIDEO_SPEND_USD * 100)
    limit_cents = hard_cents if allow_hard_headroom else target_cents

    states: dict[
        int,
        tuple[int, tuple[str, ...], tuple[MediaOptionV2, ...], int],
    ] = {0: (0, (), (), 0)}

    shot_by_id = {str(item.get("shot_id")): item for item in shots}
    for shot_id in shot_ids:
        next_states: dict[
            int,
            tuple[int, tuple[str, ...], tuple[MediaOptionV2, ...], int],
        ] = {}
        required_motion = motion_required_for_shot(shot_by_id[shot_id])
        eligible = groups[shot_id]
        if required_motion:
            videos = [x for x in eligible if x.treatment == "GENERATED_VIDEO"]
            if videos:
                eligible = videos
        for spent_cents, (utility, ids, chosen, video_seconds) in states.items():
            for option in eligible:
                option_video_cents = (
                    round(option.estimated_cost_usd * 100)
                    if option.treatment == "GENERATED_VIDEO"
                    else 0
                )
                new_spent = spent_cents + option_video_cents
                if new_spent > limit_cents:
                    continue
                new_utility = utility + option.utility
                candidate = (
                    new_utility,
                    ids + (option.option_id,),
                    chosen + (option,),
                    video_seconds + option.generated_video_seconds,
                )
                existing = next_states.get(new_spent)
                if existing is None or (
                    candidate[0],
                    candidate[3],
                    tuple(reversed(candidate[1])),
                ) > (
                    existing[0],
                    existing[3],
                    tuple(reversed(existing[1])),
                ):
                    next_states[new_spent] = candidate
        if not next_states:
            raise BudgetDrivenMediaPlannerError(
                f"BUDGET_CANNOT_COVER_REQUIRED_SHOT:{shot_id}"
            )
        states = next_states

    best_spent, best = max(
        states.items(),
        key=lambda item: (
            item[1][0],
            min(item[0], target_cents),
            item[1][3],
            tuple(reversed(item[1][1])),
        ),
    )
    selected = best[2]
    total = round(sum(item.estimated_cost_usd for item in selected), 6)
    video_spend = round(best_spent / 100.0, 2)
    return BudgetDrivenPlanV2(
        selected=selected,
        generated_video_spend_usd=video_spend,
        generated_video_seconds=best[3],
        total_media_spend_usd=total,
        target_headroom_usd=round(
            TARGET_GENERATED_VIDEO_SPEND_USD - video_spend, 2
        ),
        hard_headroom_used=video_spend > TARGET_GENERATED_VIDEO_SPEND_USD,
    )
