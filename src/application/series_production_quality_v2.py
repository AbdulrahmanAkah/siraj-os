"""Series-wide production quality policy for Siraj.

V2 changes production from a fixed-seconds/slideshow model into a cost-driven,
video-first model. USD 30 is the normal generated-video target, USD 35 is the
absolute per-episode cap, and the rolling five-episode target is USD 150.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "siraj-series-production-quality-v2"
TARGET_GENERATED_VIDEO_SPEND_USD = 30.0
HARD_GENERATED_VIDEO_SPEND_USD = 35.0
ROLLING_EPISODE_WINDOW = 5
ROLLING_GENERATED_VIDEO_TARGET_USD = 150.0
TECHNICAL_GENERATED_VIDEO_CEILING_SECONDS = 25 * 60
MAX_STILL_LED_SECONDS = 7.0
MAX_LAST_FRAME_EXTENSION_SECONDS = 1.25
MAX_UNPLANNED_BLACK_SECONDS = 1.0
MAX_UNPLANNED_SILENCE_SECONDS = 3.0
MIN_TTS_DIACRITIC_COVERAGE = 0.88
MIN_NARRATION_WORDS_PER_MINUTE = 100
TARGET_NARRATION_WORDS_PER_MINUTE = 116
MAX_NARRATION_WORDS_PER_MINUTE = 128

_ARABIC_LETTER = re.compile(r"[\u0621-\u064A]")
_ARABIC_DIACRITIC = re.compile(r"[\u064B-\u0652\u0670]")


class SeriesProductionQualityError(RuntimeError):
    pass


class SceneDomain(StrEnum):
    EARTHLY_WORLD = "EARTHLY_WORLD"
    HEAVENLY_UNSEEN_SYMBOLIC = "HEAVENLY_UNSEEN_SYMBOLIC"
    TRANSITIONAL_REALM = "TRANSITIONAL_REALM"
    DOCUMENTARY_EVIDENCE = "DOCUMENTARY_EVIDENCE"
    ABSTRACT_EXPLANATION = "ABSTRACT_EXPLANATION"


class MotionNecessity(StrEnum):
    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class RepresentationMode(StrEnum):
    DOCUMENTARY = "DOCUMENTARY"
    EVIDENCE_BASED_RECONSTRUCTION = "EVIDENCE_BASED_RECONSTRUCTION"
    SYMBOLIC_UNSEEN = "SYMBOLIC_UNSEEN"
    ABSTRACT = "ABSTRACT"


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    target_generated_video_spend_usd: float = TARGET_GENERATED_VIDEO_SPEND_USD
    hard_generated_video_spend_usd: float = HARD_GENERATED_VIDEO_SPEND_USD
    rolling_episode_window: int = ROLLING_EPISODE_WINDOW
    rolling_generated_video_target_usd: float = ROLLING_GENERATED_VIDEO_TARGET_USD
    hidden_paid_retry: str = "FORBIDDEN"
    preflight_required_before_each_paid_request: bool = True

    def validate(self) -> None:
        if self.target_generated_video_spend_usd != TARGET_GENERATED_VIDEO_SPEND_USD:
            raise SeriesProductionQualityError("VIDEO_TARGET_SPEND_MUST_BE_30_USD")
        if self.hard_generated_video_spend_usd != HARD_GENERATED_VIDEO_SPEND_USD:
            raise SeriesProductionQualityError("VIDEO_HARD_CAP_MUST_BE_35_USD")
        if self.rolling_episode_window != ROLLING_EPISODE_WINDOW:
            raise SeriesProductionQualityError("ROLLING_WINDOW_MUST_BE_FIVE")
        if self.rolling_generated_video_target_usd != ROLLING_GENERATED_VIDEO_TARGET_USD:
            raise SeriesProductionQualityError("ROLLING_TARGET_MUST_BE_150_USD")
        if self.hidden_paid_retry != "FORBIDDEN":
            raise SeriesProductionQualityError("HIDDEN_PAID_RETRY_FORBIDDEN")
        if not self.preflight_required_before_each_paid_request:
            raise SeriesProductionQualityError("PAID_REQUEST_PREFLIGHT_REQUIRED")


@dataclass(frozen=True, slots=True)
class NarrationPolicy:
    fully_diacritized_tts_required: bool = True
    explicit_pause_plan_required: bool = True
    minimum_words_per_minute: int = MIN_NARRATION_WORDS_PER_MINUTE
    target_words_per_minute: int = TARGET_NARRATION_WORDS_PER_MINUTE
    maximum_words_per_minute: int = MAX_NARRATION_WORDS_PER_MINUTE
    minimum_diacritic_coverage: float = MIN_TTS_DIACRITIC_COVERAGE
    human_language_review_required: bool = True
    human_performance_review_required: bool = True

    def validate(self) -> None:
        if not self.fully_diacritized_tts_required:
            raise SeriesProductionQualityError("FULL_TTS_DIACRITIZATION_REQUIRED")
        if not self.explicit_pause_plan_required:
            raise SeriesProductionQualityError("EXPLICIT_PAUSE_PLAN_REQUIRED")
        if not (
            80 <= self.minimum_words_per_minute
            <= self.target_words_per_minute
            <= self.maximum_words_per_minute
            <= 150
        ):
            raise SeriesProductionQualityError("INVALID_NARRATION_SPEED_RANGE")
        if not 0.80 <= self.minimum_diacritic_coverage <= 1.0:
            raise SeriesProductionQualityError("INVALID_DIACRITIC_COVERAGE")
        if not self.human_language_review_required:
            raise SeriesProductionQualityError("HUMAN_LANGUAGE_REVIEW_REQUIRED")
        if not self.human_performance_review_required:
            raise SeriesProductionQualityError("HUMAN_PERFORMANCE_REVIEW_REQUIRED")


@dataclass(frozen=True, slots=True)
class VisualPolicy:
    production_mode: str = "BUDGET_DRIVEN_VIDEO_FIRST"
    generated_video_seconds_target: str = "NONE_COST_AND_QUALITY_DRIVEN"
    still_image_usage: str = "LIMITED_AND_INTENTIONAL"
    flat_slideshow: str = "FORBIDDEN"
    simple_zoom_only: str = "FORBIDDEN"
    maximum_still_led_seconds: float = MAX_STILL_LED_SECONDS
    maximum_last_frame_extension_seconds: float = MAX_LAST_FRAME_EXTENSION_SECONDS
    technical_generated_video_ceiling_seconds: int = TECHNICAL_GENERATED_VIDEO_CEILING_SECONDS

    def validate(self) -> None:
        if self.production_mode != "BUDGET_DRIVEN_VIDEO_FIRST":
            raise SeriesProductionQualityError("VIDEO_FIRST_MODE_REQUIRED")
        if self.generated_video_seconds_target != "NONE_COST_AND_QUALITY_DRIVEN":
            raise SeriesProductionQualityError("FIXED_VIDEO_SECONDS_TARGET_FORBIDDEN")
        if self.flat_slideshow != "FORBIDDEN":
            raise SeriesProductionQualityError("FLAT_SLIDESHOW_FORBIDDEN")
        if self.simple_zoom_only != "FORBIDDEN":
            raise SeriesProductionQualityError("SIMPLE_ZOOM_ONLY_FORBIDDEN")
        if self.maximum_still_led_seconds > MAX_STILL_LED_SECONDS:
            raise SeriesProductionQualityError("STILL_DURATION_TOO_LONG")
        if self.maximum_last_frame_extension_seconds > MAX_LAST_FRAME_EXTENSION_SECONDS:
            raise SeriesProductionQualityError("LAST_FRAME_EXTENSION_TOO_LONG")


@dataclass(frozen=True, slots=True)
class UnseenWorldPolicy:
    explicit_scene_domain_required: bool = True
    earthly_visual_default_for_unseen: str = "FORBIDDEN"
    representation_claim: str = "SYMBOLIC_NON_DEFINITIVE"
    unsupported_religious_detail: str = "FORBIDDEN"
    location_continuity_required: bool = True

    def validate(self) -> None:
        if not self.explicit_scene_domain_required:
            raise SeriesProductionQualityError("SCENE_DOMAIN_REQUIRED")
        if self.earthly_visual_default_for_unseen != "FORBIDDEN":
            raise SeriesProductionQualityError("EARTHLIKE_UNSEEN_DEFAULT_FORBIDDEN")
        if self.representation_claim != "SYMBOLIC_NON_DEFINITIVE":
            raise SeriesProductionQualityError("UNSEEN_REPRESENTATION_MUST_BE_SYMBOLIC")
        if self.unsupported_religious_detail != "FORBIDDEN":
            raise SeriesProductionQualityError("UNSUPPORTED_RELIGIOUS_DETAIL_FORBIDDEN")
        if not self.location_continuity_required:
            raise SeriesProductionQualityError("LOCATION_CONTINUITY_REQUIRED")


@dataclass(frozen=True, slots=True)
class ReleaseQualityPolicy:
    maximum_unplanned_black_seconds: float = MAX_UNPLANNED_BLACK_SECONDS
    maximum_unplanned_silence_seconds: float = MAX_UNPLANNED_SILENCE_SECONDS
    long_freeze: str = "BLOCKING"
    unplanned_black: str = "BLOCKING"
    unplanned_silence: str = "BLOCKING"
    narration_not_fully_diacritized: str = "BLOCKING"
    world_continuity_violation: str = "BLOCKING"
    cheap_still_montage: str = "BLOCKING"

    def validate(self) -> None:
        if self.maximum_unplanned_black_seconds > MAX_UNPLANNED_BLACK_SECONDS:
            raise SeriesProductionQualityError("BLACK_ALLOWANCE_TOO_HIGH")
        if self.maximum_unplanned_silence_seconds > MAX_UNPLANNED_SILENCE_SECONDS:
            raise SeriesProductionQualityError("SILENCE_ALLOWANCE_TOO_HIGH")
        for value in (
            self.long_freeze,
            self.unplanned_black,
            self.unplanned_silence,
            self.narration_not_fully_diacritized,
            self.world_continuity_violation,
            self.cheap_still_montage,
        ):
            if value != "BLOCKING":
                raise SeriesProductionQualityError("RELEASE_DEFECTS_MUST_BLOCK")


@dataclass(frozen=True, slots=True)
class SeriesProductionPolicyV2:
    budget: BudgetPolicy = BudgetPolicy()
    narration: NarrationPolicy = NarrationPolicy()
    visual: VisualPolicy = VisualPolicy()
    unseen_world: UnseenWorldPolicy = UnseenWorldPolicy()
    release_quality: ReleaseQualityPolicy = ReleaseQualityPolicy()
    schema_version: str = SCHEMA_VERSION
    status: str = "ACTIVE"

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise SeriesProductionQualityError("UNEXPECTED_POLICY_SCHEMA")
        if self.status != "ACTIVE":
            raise SeriesProductionQualityError("SERIES_POLICY_NOT_ACTIVE")
        self.budget.validate()
        self.narration.validate()
        self.visual.validate()
        self.unseen_world.validate()
        self.release_quality.validate()

    def to_manifest(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EpisodeVideoSpend:
    episode_id: str
    generated_video_spend_usd: float

    def validate(self) -> None:
        if not self.episode_id.strip():
            raise SeriesProductionQualityError("EPISODE_ID_REQUIRED")
        if self.generated_video_spend_usd < 0:
            raise SeriesProductionQualityError("NEGATIVE_VIDEO_SPEND_FORBIDDEN")
        if self.generated_video_spend_usd > HARD_GENERATED_VIDEO_SPEND_USD + 1e-9:
            raise SeriesProductionQualityError("EPISODE_VIDEO_HARD_CAP_EXCEEDED")


@dataclass(frozen=True, slots=True)
class RollingBudgetSnapshot:
    episode_count: int
    generated_video_spend_usd: float
    target_usd: float
    variance_usd: float
    average_usd: float
    compliant: bool


def rolling_budget_snapshot(records: Iterable[EpisodeVideoSpend]) -> RollingBudgetSnapshot:
    ordered = tuple(records)[-ROLLING_EPISODE_WINDOW:]
    for item in ordered:
        item.validate()
    spent = round(sum(item.generated_video_spend_usd for item in ordered), 6)
    target = round(TARGET_GENERATED_VIDEO_SPEND_USD * len(ordered), 6)
    average = round(spent / len(ordered), 6) if ordered else 0.0
    return RollingBudgetSnapshot(
        episode_count=len(ordered),
        generated_video_spend_usd=spent,
        target_usd=target,
        variance_usd=round(target - spent, 6),
        average_usd=average,
        compliant=spent <= target + 1e-9,
    )


def diacritic_coverage(text: str) -> float:
    """Measure linguistic vocalization coverage.

    Long-vowel letters and orthographic carriers do not require independent
    short-vowel marks. A final consonant at a pause boundary may be realized
    by waqf without a case ending.
    """
    letters = list(_ARABIC_LETTER.finditer(text))
    if not letters:
        return 1.0

    orthographic_letters = set("اويىءؤئإآأٱة")
    pause_boundaries = set(" \t\r\n،؛:.!؟…﴾)]}")
    covered = 0

    for match in letters:
        character = match.group(0)
        index = match.end()

        if index < len(text) and _ARABIC_DIACRITIC.match(text[index]):
            covered += 1
            continue

        if character in orthographic_letters:
            covered += 1
            continue

        if index >= len(text) or text[index] in pause_boundaries:
            covered += 1

    return covered / len(letters)

def assert_tts_text_ready(
    text: str,
    *,
    minimum_coverage: float = MIN_TTS_DIACRITIC_COVERAGE,
) -> None:
    value = str(text or "").strip()
    if not value:
        raise SeriesProductionQualityError("TTS_TEXT_REQUIRED")
    coverage = diacritic_coverage(value)
    if coverage + 1e-9 < minimum_coverage:
        raise SeriesProductionQualityError(
            "TTS_TEXT_NOT_FULLY_DIACRITIZED:"
            f"coverage={coverage:.4f}:required={minimum_coverage:.4f}"
        )


def words_per_minute(word_count: int, duration_seconds: float) -> float:
    if word_count < 0 or duration_seconds <= 0:
        raise SeriesProductionQualityError("INVALID_NARRATION_MEASUREMENT")
    return (word_count * 60.0) / duration_seconds


def motion_required_for_shot(shot: Mapping[str, Any]) -> bool:
    if str(shot.get("motion_necessity", "")).upper() == "REQUIRED":
        return True
    signals = " ".join(
        str(shot.get(key, ""))
        for key in (
            "label_ar",
            "dramatic_function_ar",
            "visual_brief_ar",
            "action_ar",
            "transformation_ar",
        )
    ).lower()
    terms = (
        "يتكوّن",
        "يتشكل",
        "يتحوّل",
        "يتحرك",
        "ينتقل",
        "يصعد",
        "يهبط",
        "ينفتح",
        "ينغلق",
        "تكوين",
        "تحول",
        "حركة",
        "خلق",
        "formation",
        "transform",
        "movement",
        "reveal",
    )
    return any(term in signals for term in terms)


def validate_shot_policy(shot: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    treatment = str(
        shot.get("final_budget_treatment")
        or shot.get("treatment")
        or ""
    ).upper()
    duration = float(
        shot.get("planned_seconds", shot.get("duration_seconds", 0)) or 0
    )
    if motion_required_for_shot(shot) and treatment not in {
        "GENERATED_VIDEO",
        "HYBRID_SEQUENCE",
        "DOCUMENT_OR_MAP",
        "AUTHORED_GRAPHICS",
    }:
        issues.append("MOTION_REQUIRED_BUT_NOT_VIDEO")
    if treatment in {
        "ANIMATED_STILL_COMPOSITING",
        "DYNAMIC_STILL",
        "GENERATED_IMAGE",
        "DYNAMIC_STILL_SEQUENCE",
    }:
        panel_count = int(shot.get("still_panel_count", 1) or 1)
        effective_panel_seconds = duration / max(panel_count, 1)
        if effective_panel_seconds > MAX_STILL_LED_SECONDS + 1e-9:
            issues.append("STILL_LED_DURATION_EXCEEDS_SEVEN_SECONDS")
        if str(shot.get("motion_profile", "")).upper() in {
            "",
            "SLOW_PUSH_IN",
            "ZOOM_ONLY",
        }:
            issues.append("CHEAP_STILL_MONTAGE_RISK")
    domain = str(shot.get("scene_domain", ""))
    if not domain:
        issues.append("SCENE_DOMAIN_REQUIRED")
    elif domain == SceneDomain.HEAVENLY_UNSEEN_SYMBOLIC.value:
        if str(shot.get("representation_mode", "")) != (
            RepresentationMode.SYMBOLIC_UNSEEN.value
        ):
            issues.append("UNSEEN_REPRESENTATION_MODE_INVALID")
        if shot.get("earthly_visual_default") is True:
            issues.append("UNSEEN_REALM_TOO_EARTHLIKE")
    return issues


def validate_release_report(report: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for segment in report.get("black_segments", ()) or ():
        if float(segment.get("duration", 0)) > MAX_UNPLANNED_BLACK_SECONDS:
            issues.append("UNPLANNED_BLACK_INTERVAL")
    for segment in report.get("silence_segments", ()) or ():
        if float(segment.get("duration", 0)) > MAX_UNPLANNED_SILENCE_SECONDS:
            issues.append("UNPLANNED_SILENCE_INTERVAL")
    for segment in report.get("freeze_segments", ()) or ():
        if float(segment.get("duration", 0)) > MAX_LAST_FRAME_EXTENSION_SECONDS:
            issues.append("LONG_FREEZE_INTERVAL")
    return sorted(set(issues))


def write_policy(path: Path, policy: SeriesProductionPolicyV2 | None = None) -> Path:
    resolved = policy or SeriesProductionPolicyV2()
    payload = resolved.to_manifest()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    temporary.replace(path)
    return path


def load_policy(path: Path) -> SeriesProductionPolicyV2:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeriesProductionQualityError(
            f"CANNOT_READ_SERIES_POLICY:{path}:{exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise SeriesProductionQualityError("SERIES_POLICY_OBJECT_REQUIRED")
    policy = SeriesProductionPolicyV2(
        budget=BudgetPolicy(**dict(payload.get("budget", {}))),
        narration=NarrationPolicy(**dict(payload.get("narration", {}))),
        visual=VisualPolicy(**dict(payload.get("visual", {}))),
        unseen_world=UnseenWorldPolicy(**dict(payload.get("unseen_world", {}))),
        release_quality=ReleaseQualityPolicy(
            **dict(payload.get("release_quality", {}))
        ),
        schema_version=str(payload.get("schema_version", "")),
        status=str(payload.get("status", "")),
    )
    policy.validate()
    return policy
