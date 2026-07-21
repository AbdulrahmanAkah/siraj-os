"""Deterministic production storyboard planning from mastered audio and subtitle cues.

This module produces planning artifacts only.  It never invokes a media, TTS, or
network provider, and its asset references are requirements rather than files.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from .episode_render_v2 import EPISODE_RENDER_MANIFEST_V2, validate_episode_render_manifest_v2
from .production_tts_v1 import inspect_pcm_wav
from .voice_provider_v1 import atomic_write_json, file_sha256


STORYBOARD_SCHEMA_V1 = "siraj-production-storyboard-generator-v1"
STORYBOARD_VALIDATION_SCHEMA_V1 = "siraj-production-storyboard-validation-v1"
_GENERATOR_REVISION = "1"
_LOCATION_WORDS = ("بغداد", "العراق", "دجلة", "خراسان", "مصر", "الشام", "مكة", "المدينة")
_TIME_WORDS = ("سنة", "عام", "قرن", "بعد", "قبل", "ثم", "عندما")
_HISTORICAL_WORDS = ("الخليفة", "الدولة", "التاريخ", "العباسية", "معركة", "تولى", "عزل")


@dataclass(frozen=True)
class StoryboardConfig:
    aspect_ratio: str = "16:9"
    pacing_profile: str = "documentary"
    minimum_shot_duration_ms: int = 900
    preferred_shot_duration_ms: int = 2600
    maximum_shot_duration_ms: int = 6000
    maximum_repeated_shot_type: int = 2
    maximum_consecutive_static_duration_ms: int = 5000
    transition_duration_ms: int = 220
    subtitle_safe_bottom_percent: int = 22
    deterministic_seed: str = "storyboard-v1"


@dataclass(frozen=True)
class StoryboardRequest:
    mastered_audio_path: Path
    subtitle_manifest_path: Path
    output_directory: Path
    manifest_path: Path | None = None
    config: StoryboardConfig = field(default_factory=StoryboardConfig)


@dataclass(frozen=True)
class NarrativeSection:
    section_id: str
    title: str
    narrative_function: str
    start_ms: int
    end_ms: int
    cue_ids: tuple[str, ...]


@dataclass(frozen=True)
class StoryBeat:
    beat_id: str
    scene_id: str
    transcript_span: str
    subtitle_cue_ids: tuple[str, ...]
    start_ms: int
    end_ms: int
    narrative_function: str
    emotional_tone: str
    emotional_intensity: float
    recommended_visual_treatment: str


@dataclass(frozen=True)
class ShotTiming:
    start_ms: int
    end_ms: int
    duration_ms: int


@dataclass(frozen=True)
class ShotComposition:
    framing: str
    subject_placement: str
    visual_hierarchy: str
    depth: str
    lens_feel: str
    camera_angle: str
    screen_direction: str
    subtitle_safe: bool


@dataclass(frozen=True)
class CameraPlan:
    movement: str
    movement_speed: str
    justification: str
    focus_behavior: str


@dataclass(frozen=True)
class LightingPlan:
    style: str
    time_of_day: str
    palette: str
    contrast: str
    atmosphere: str


@dataclass(frozen=True)
class EnvironmentPlan:
    geographic_location: str
    time_period: str
    weather: str
    foreground: str
    midground: str
    background: str


@dataclass(frozen=True)
class CharacterPlan:
    character_id: str
    name: str
    role: str
    historical_period: str
    status: str
    prohibited_inconsistencies: tuple[str, ...]


@dataclass(frozen=True)
class VisualContinuityPlan:
    continuity_anchor: str
    character_identity: str
    wardrobe: str
    environment: str
    time_of_day: str
    palette: str
    prop_positions: str


@dataclass(frozen=True)
class VisualAssetRequirement:
    asset_id: str
    asset_type: str
    priority: str
    reuse_allowed: bool
    generation_cost_class: str
    complexity: str
    dependency: str | None
    approval_required: bool
    reuse_count: int
    variation_plan: str


@dataclass(frozen=True)
class GenerationPromptPackage:
    core_prompt: str
    negative_prompt: str
    continuity_block: str
    motion_prompt: str
    image_prompt: str
    video_prompt: str


@dataclass(frozen=True)
class StoryboardShot:
    shot_id: str
    scene_id: str
    sequence_index: int
    narrative_function: str
    timing: ShotTiming
    subtitle_cue_ids: tuple[str, ...]
    transcript_span: str
    speaker_id: str | None
    role: str
    visual_type: str
    shot_type: str
    composition: ShotComposition
    camera: CameraPlan
    subject: str
    action: str
    environment: EnvironmentPlan
    lighting: LightingPlan
    color_mood: str
    emotional_tone: str
    continuity_requirements: VisualContinuityPlan
    required_assets: tuple[VisualAssetRequirement, ...]
    prompts: GenerationPromptPackage
    factual_confidence: str
    reconstruction_status: str
    source_support: str
    speculative_visual: bool
    disclaimer_required: bool
    transition_in: str
    transition_out: str
    motion_notes: str
    sound_design_notes: str
    sound_priority: str
    text_overlay_policy: str
    confidence: str
    rationale: str


@dataclass(frozen=True)
class StoryboardScene:
    scene_id: str
    title: str
    narrative_purpose: str
    start_ms: int
    end_ms: int
    duration_ms: int
    location: str
    period: str
    characters: tuple[str, ...]
    emotional_curve: str
    visual_strategy: str
    continuity_anchor: str
    source_cue_ids: tuple[str, ...]
    shots: tuple[StoryboardShot, ...]


@dataclass(frozen=True)
class StoryboardValidationResult:
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    timing_coverage_ms: int
    drift_ms: int
    continuity_status: str
    historical_status: str
    subtitle_safety_status: str
    prompt_quality_status: str
    diversity_metrics: dict[str, float]
    quality_score: float
    quality_grade: str
    score_deductions: tuple[str, ...]


@dataclass(frozen=True)
class StoryboardExportResult:
    status: str
    storyboard_path: Path
    markdown_path: Path
    asset_plan_path: Path
    character_bible_path: Path
    location_bible_path: Path
    validation_path: Path
    manifest_path: Path
    cache_hit: bool


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("STORYBOARD_JSON_OBJECT_REQUIRED")
    return value


def _parse_srt(path: Path) -> list[dict[str, Any]]:
    content = path.read_text(encoding="utf-8")
    blocks = [block.strip() for block in re.split(r"\r?\n\r?\n", content) if block.strip()]
    cues: list[dict[str, Any]] = []
    for position, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        if len(lines) < 3 or " --> " not in lines[1]:
            raise ValueError(f"STORYBOARD_SRT_INVALID:{position}")
        start, end = lines[1].split(" --> ", 1)
        cues.append({"cue_id": f"cue-{position:03}", "start_ms": _parse_srt_time(start), "end_ms": _parse_srt_time(end), "text": " ".join(lines[2:]).strip()})
    if not cues:
        raise ValueError("STORYBOARD_SUBTITLE_CUES_REQUIRED")
    return cues


def _parse_srt_time(value: str) -> int:
    hours, minutes, remainder = value.strip().split(":")
    seconds, milliseconds = remainder.split(",")
    return (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000 + int(milliseconds)


def _location(text: str) -> str:
    for value in _LOCATION_WORDS:
        if value in text:
            return value
    return "UNSPECIFIED_REQUIRES_ART_DIRECTION"


def _period(text: str) -> str:
    return "HISTORICAL_PERIOD_REQUIRES_SOURCE_CONFIRMATION" if any(item in text for item in _HISTORICAL_WORDS) else "UNSPECIFIED_REQUIRES_ART_DIRECTION"


def _function(index: int, total: int, text: str) -> str:
    if index == 0:
        return "OPENING_HOOK"
    if index == total - 1:
        return "CLOSING_IMAGE"
    if any(value in text for value in ("لكن", "غير أن", "تحول", "أزمة", "صراع")):
        return "ESCALATION"
    if any(value in text for value in ("اكتشف", "كشف", "ظهر", "تبين")):
        return "REVELATION"
    if any(value in text for value in _TIME_WORDS):
        return "TIMELINE_EXPLANATION"
    return "DEVELOPMENT"


def _visual_type(function: str, text: str, ordinal: int) -> tuple[str, str, str]:
    if function == "OPENING_HOOK":
        return "AERIAL_VIEW", "Aerial", "ESTABLISHING"
    if any(value in text for value in ("خريطة", "إقليم", "مدينة", "نهر", "دجلة")):
        return "MAP_ANIMATION", "Top-down", "WIDE"
    if any(value in text for value in ("مخطوط", "وثيقة", "كتاب", "ترجمة", "علم")):
        return "MANUSCRIPT_CLOSE_UP", "Macro detail", "INSERT"
    if any(value in text for value in ("قال", "أجاب", "سأل", "روى")):
        return "MEDIUM_DIALOGUE_SHOT", "Medium Shot", "MEDIUM"
    if function in {"ESCALATION", "REVELATION"}:
        return "HISTORICAL_RECONSTRUCTION", "Medium Wide", "TRACKING"
    choices = (("CITY_RECONSTRUCTION", "Wide Shot", "WIDE"), ("ARCHIVAL_DOCUMENT", "Close-Up", "INSERT"), ("ENVIRONMENTAL_ESTABLISHING", "Extreme Wide Shot", "ESTABLISHING"))
    return choices[ordinal % len(choices)]


def _movement(function: str, visual_type: str, ordinal: int) -> tuple[str, str]:
    if visual_type == "AERIAL_VIEW": return "SLOW_PUSH_IN", "Reveal scale and episode promise."
    if visual_type == "MAP_ANIMATION": return "CONTROLLED_PAN", "Trace the geographic explanation."
    if visual_type == "MANUSCRIPT_CLOSE_UP": return "STATIC", "Protect readable evidence detail."
    if function == "ESCALATION": return "SLOW_TRACK", "Increase tension without visual noise."
    return ("STATIC", "Allow visual breathing room.") if ordinal % 2 else ("GENTLE_PUSH_IN", "Move from context to detail.")


def _asset_type(visual_type: str) -> tuple[str, str, str]:
    if visual_type == "MAP_ANIMATION": return "MAP", "MEDIUM", "LOW"
    if visual_type in {"MANUSCRIPT_CLOSE_UP", "ARCHIVAL_DOCUMENT"}: return "DOCUMENT", "MEDIUM", "LOW"
    if visual_type == "AERIAL_VIEW": return "REUSABLE_ESTABLISHING_SHOT", "HIGH", "MEDIUM"
    if visual_type == "HISTORICAL_RECONSTRUCTION": return "GENERATED_IMAGE", "HIGH", "HIGH"
    return "GENERATED_IMAGE", "MEDIUM", "MEDIUM"


def _prompt(subject: str, action: str, environment: EnvironmentPlan, composition: ShotComposition, camera: CameraPlan, lighting: LightingPlan, continuity: VisualContinuityPlan) -> GenerationPromptPackage:
    core = (f"Subject: {subject}. Action: {action}. Environment: {environment.geographic_location}; {environment.time_period}. "
            f"Composition: {composition.framing}, {composition.subject_placement}, {composition.depth}. "
            f"Camera: {composition.camera_angle}, {camera.movement}. Lighting: {lighting.style}; palette {lighting.palette}. "
            "Provider-neutral historical documentary visual, single coherent moment, no text overlay.")
    negative = "modern objects, logos, watermark, readable invented text, wrong period props, duplicate characters, warped faces, incorrect anatomy, conflicting camera angles"
    continuity_block = f"Anchor: {continuity.continuity_anchor}; environment: {continuity.environment}; palette: {continuity.palette}; wardrobe: {continuity.wardrobe}."
    motion = f"Subject motion: restrained. Camera motion: {camera.movement}. Environmental motion: subtle. Start and end preserve continuity."
    return GenerationPromptPackage(core, negative, continuity_block, motion, core, f"{core} {motion}")


def _cue_speakers(subtitle_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = subtitle_manifest.get("cue_metadata", [])
    return {str(item.get("cue_id")): item for item in raw if isinstance(item, dict)}


def _build_scenes(cues: list[dict[str, Any]], cue_metadata: dict[str, dict[str, Any]]) -> tuple[NarrativeSection, ...]:
    sections: list[NarrativeSection] = []
    start = 0
    for index, cue in enumerate(cues):
        previous = cues[index - 1] if index else None
        speaker = cue_metadata.get(cue["cue_id"], {}).get("speaker_id")
        previous_speaker = cue_metadata.get(previous["cue_id"], {}).get("speaker_id") if previous else speaker
        boundary = index > 0 and (speaker != previous_speaker or _location(cue["text"]) != _location(previous["text"]) or any(word in cue["text"] for word in _TIME_WORDS))
        if boundary:
            group = cues[start:index]
            sections.append(NarrativeSection(f"scene-{len(sections)+1:03}", f"Scene {len(sections)+1}", _function(start, len(cues), group[0]["text"]), group[0]["start_ms"], group[-1]["end_ms"], tuple(item["cue_id"] for item in group)))
            start = index
    group = cues[start:]
    sections.append(NarrativeSection(f"scene-{len(sections)+1:03}", f"Scene {len(sections)+1}", _function(start, len(cues), group[0]["text"]), group[0]["start_ms"], group[-1]["end_ms"], tuple(item["cue_id"] for item in group)))
    return tuple(sections)


def _allocate_shot_durations(duration: int, config: StoryboardConfig, split: bool) -> list[int]:
    if split and duration >= config.minimum_shot_duration_ms * 2:
        first = duration // 2
        return [first, duration - first]
    return [duration]


def _build_storyboard(subtitle_manifest: dict[str, Any], request: StoryboardRequest) -> tuple[tuple[NarrativeSection, ...], tuple[StoryBeat, ...], tuple[StoryboardScene, ...], tuple[CharacterPlan, ...], tuple[dict[str, Any], ...]]:
    exports = subtitle_manifest.get("exports", {})
    srt_path = Path(str(exports.get("srt", "")))
    if not srt_path.is_file(): raise FileNotFoundError("STORYBOARD_SUBTITLE_SRT_NOT_FOUND")
    cues = _parse_srt(srt_path)
    cue_metadata = _cue_speakers(subtitle_manifest)
    sections = _build_scenes(cues, cue_metadata)
    beats: list[StoryBeat] = []
    scenes: list[StoryboardScene] = []
    characters: dict[str, CharacterPlan] = {}
    assets: list[dict[str, Any]] = []
    sequence = 0
    for section in sections:
        scene_cues = [cue for cue in cues if cue["cue_id"] in section.cue_ids]
        shots: list[StoryboardShot] = []
        for cue_index, cue in enumerate(scene_cues):
            meta = cue_metadata.get(cue["cue_id"], {})
            function = _function(sequence, len(cues), cue["text"])
            visual, framing, shot_type = _visual_type(function, cue["text"], sequence)
            beats.append(StoryBeat(f"beat-{len(beats)+1:03}", section.section_id, cue["text"], (cue["cue_id"],), cue["start_ms"], cue["end_ms"], function, "CURIOSITY" if function == "OPENING_HOOK" else "CLARITY", 0.75 if function in {"OPENING_HOOK", "ESCALATION"} else 0.45, visual))
            split = function == "OPENING_HOOK" or (cue["end_ms"] - cue["start_ms"] >= request.config.preferred_shot_duration_ms * 2)
            cursor = cue["start_ms"]
            for part, duration in enumerate(_allocate_shot_durations(cue["end_ms"] - cue["start_ms"], request.config, split)):
                current_visual, current_framing, current_type = (visual, framing, shot_type) if part == 0 else _visual_type("DEVELOPMENT", cue["text"], sequence + part + 1)
                movement, justification = _movement(function, current_visual, sequence + part)
                location = _location(cue["text"])
                period = _period(cue["text"])
                environment = EnvironmentPlan(location, period, "UNSPECIFIED_REQUIRES_ART_DIRECTION", "contextual foreground", "primary subject", "subtitle-safe lower third clear")
                composition = ShotComposition(current_framing, "CENTER_SAFE_UPPER_TWO_THIRDS", "SUBJECT_THEN_ENVIRONMENT", "FOREGROUND_MIDGROUND_BACKGROUND", "35mm documentary", "EYE_LEVEL", "CONSISTENT_LEFT_TO_RIGHT", True)
                camera = CameraPlan(movement, "SLOW" if movement != "STATIC" else "NONE", justification, "LOCKED_ON_SUBJECT")
                lighting = LightingPlan("NEUTRAL_DOCUMENTARY_EVIDENCE" if current_visual in {"MANUSCRIPT_CLOSE_UP", "ARCHIVAL_DOCUMENT"} else "WARM_HISTORICAL_ATMOSPHERE", "UNSPECIFIED_REQUIRES_ART_DIRECTION", "EARTH_TONES", "MODERATE", "OBSERVATIONAL")
                continuity = VisualContinuityPlan(section.section_id, "SPEAKER_IDENTITY_ONLY" if meta.get("speaker_id") else "NO_NAMED_CHARACTER", "UNSPECIFIED_REQUIRES_ART_DIRECTION", location, lighting.time_of_day, lighting.palette, "NO_UNVERIFIED_PROPS")
                subject = meta.get("speaker_name") or location if location != "UNSPECIFIED_REQUIRES_ART_DIRECTION" else "historical setting"
                action = "introduce the episode promise" if function == "OPENING_HOOK" else "support the narrated evidence"
                asset_type, cost, complexity = _asset_type(current_visual)
                asset = VisualAssetRequirement(f"asset-{sequence+1:03}-{part+1}", asset_type, "REQUIRED" if part == 0 else "RECOMMENDED", current_visual in {"AERIAL_VIEW", "MAP_ANIMATION", "MANUSCRIPT_CLOSE_UP"}, cost, complexity, None, current_visual == "HISTORICAL_RECONSTRUCTION", 0, "Vary crop, camera, or lighting before visible reuse.")
                shot = StoryboardShot(f"shot-{sequence+1:03}-{part+1}", section.section_id, len(shots) + 1, function, ShotTiming(cursor, cursor + duration, duration), (cue["cue_id"],), cue["text"], meta.get("speaker_id"), str(meta.get("role", "PRIMARY_NARRATOR")), current_visual, current_type, composition, camera, str(subject), action, environment, lighting, lighting.palette, "CURIOSITY" if function == "OPENING_HOOK" else "CLARITY", continuity, (asset,), _prompt(str(subject), action, environment, composition, camera, lighting, continuity), "STRONGLY_SUPPORTED" if current_visual in {"MANUSCRIPT_CLOSE_UP", "ARCHIVAL_DOCUMENT"} else "PLAUSIBLE_RECONSTRUCTION", "SYMBOLIC" if current_visual == "ARCHIVAL_DOCUMENT" else "PLAUSIBLE_RECONSTRUCTION", "SUBTITLE_TEXT_ONLY", current_visual not in {"MANUSCRIPT_CLOSE_UP", "ARCHIVAL_DOCUMENT"}, current_visual not in {"MANUSCRIPT_CLOSE_UP", "ARCHIVAL_DOCUMENT"}, "FADE" if sequence == 0 and part == 0 else "CUT", "DISSOLVE" if function in {"ESCALATION", "REVELATION"} else "CUT", justification, "Ambience only when context requires it; duck under narration.", "RECOMMENDED" if current_visual in {"AERIAL_VIEW", "MAP_ANIMATION"} else "OPTIONAL", "NO_LARGE_TEXT_OVER_SUBTITLES", "HIGH", "Narrative function, evidence, and subtitle-safe composition determine this shot.")
                shots.append(shot); assets.append(asdict(asset)); cursor += duration
            sequence += 1
            if meta.get("speaker_id"):
                identity = str(meta["speaker_id"])
                characters.setdefault(identity, CharacterPlan(identity, str(meta.get("speaker_name") or identity), str(meta.get("role", "PRIMARY_NARRATOR")), period, "UNSPECIFIED_REQUIRES_ART_DIRECTION", ("No unsupported facial, wardrobe, age, or historical identity details.",)))
        scenes.append(StoryboardScene(section.section_id, section.title, section.narrative_function, section.start_ms, section.end_ms, section.end_ms-section.start_ms, _location(" ".join(cue["text"] for cue in scene_cues)), _period(" ".join(cue["text"] for cue in scene_cues)), tuple(characters), "HOOK_TO_ORIENTATION" if section.narrative_function == "OPENING_HOOK" else "STEADY_CLARITY", shots[0].visual_type, section.section_id, section.cue_ids, tuple(shots)))
    return sections, tuple(beats), _fill_visual_gaps(tuple(scenes)), tuple(characters.values()), tuple(assets)


def _flatten(scenes: tuple[StoryboardScene, ...]) -> list[StoryboardShot]: return [shot for scene in scenes for shot in scene.shots]


def _fill_visual_gaps(scenes: tuple[StoryboardScene, ...]) -> tuple[StoryboardScene, ...]:
    """Carry a preceding visual through subtitle pauses; no narration cue is altered."""
    rebuilt = [list(scene.shots) for scene in scenes]
    positions = [(scene_index, shot_index) for scene_index, scene in enumerate(rebuilt) for shot_index in range(len(scene))]
    for previous, current in zip(positions, positions[1:]):
        prior = rebuilt[previous[0]][previous[1]]
        following = rebuilt[current[0]][current[1]]
        if following.timing.start_ms > prior.timing.end_ms:
            rebuilt[previous[0]][previous[1]] = replace(prior, timing=ShotTiming(prior.timing.start_ms, following.timing.start_ms, following.timing.start_ms - prior.timing.start_ms), motion_notes=f"{prior.motion_notes} Hold through the intentional subtitle pause.")
    return tuple(replace(scene, shots=tuple(rebuilt[index])) for index, scene in enumerate(scenes))


def _diversity(shots: list[StoryboardShot]) -> dict[str, float]:
    total = max(1, len(shots))
    return {"shot_type_diversity": round(len({shot.shot_type for shot in shots}) / total, 3), "framing_diversity": round(len({shot.composition.framing for shot in shots}) / total, 3), "movement_diversity": round(len({shot.camera.movement for shot in shots}) / total, 3), "asset_diversity": round(len({asset.asset_type for shot in shots for asset in shot.required_assets}) / total, 3), "visual_repetition_score": round(max(0.0, 1 - max((sum(shot.shot_type == current.shot_type for current in shots) for shot in shots), default=0) / total), 3)}


def validate_storyboard(scenes: tuple[StoryboardScene, ...], audio_duration_ms: int, config: StoryboardConfig) -> StoryboardValidationResult:
    shots = _flatten(scenes); errors: list[str] = []; warnings: list[str] = []; cursor = 0
    for shot in shots:
        timing = shot.timing
        if timing.start_ms != cursor: errors.append(f"SHOT_TIMELINE_GAP_OR_OVERLAP:{shot.shot_id}")
        if timing.duration_ms < config.minimum_shot_duration_ms or timing.duration_ms > config.maximum_shot_duration_ms: errors.append(f"SHOT_DURATION_INVALID:{shot.shot_id}")
        if not shot.composition.subtitle_safe: errors.append(f"SUBTITLE_SAFETY_FAILED:{shot.shot_id}")
        if not shot.prompts.core_prompt or not shot.prompts.negative_prompt or "modern objects" not in shot.prompts.negative_prompt: errors.append(f"PROMPT_INVALID:{shot.shot_id}")
        if shot.environment.time_period.startswith("HISTORICAL") and shot.factual_confidence == "DOCUMENTED" and shot.source_support != "VERBATIM_SOURCE_OR_ARCHIVE": errors.append(f"HISTORICAL_CONFIDENCE_INVALID:{shot.shot_id}")
        cursor = timing.end_ms
    drift = audio_duration_ms - cursor
    if drift != 0: errors.append("STORYBOARD_AUDIO_DRIFT")
    metrics = _diversity(shots)
    score_parts = {"narrative_clarity": 10 if scenes else 0, "visual_relevance": 10 if shots else 0, "hook_strength": 10 if shots and shots[0].narrative_function == "OPENING_HOOK" else 0, "pacing": 10 if not errors else 0, "shot_diversity": min(10, round(metrics["shot_type_diversity"] * 10 + metrics["framing_diversity"] * 5)), "continuity": 10 if not errors else 0, "emotional_progression": 8 if any(shot.emotional_tone == "CURIOSITY" for shot in shots) else 4, "production_feasibility": 8 if all(asset.generation_cost_class != "VERY_HIGH" for shot in shots for asset in shot.required_assets) else 4, "historical_consistency": 8 if all(shot.reconstruction_status in {"DOCUMENTED", "PLAUSIBLE_RECONSTRUCTION", "SYMBOLIC"} for shot in shots) else 0, "prompt_quality": 6 if not errors else 0, "subtitle_safety": 5 if not errors else 0, "cost_efficiency": 5 if shots else 0}
    short_sample_deduction = 8 if audio_duration_ms < 10_000 else 0
    score = float(sum(score_parts.values()) - short_sample_deduction)
    grade = "EXCELLENT" if score >= 90 else "STRONG" if score >= 80 else "ACCEPTABLE" if score >= 70 else "FAIL"
    deductions = tuple(f"{key}:{10-value}" for key, value in score_parts.items() if value < 10 and key not in {"emotional_progression", "production_feasibility", "historical_consistency", "prompt_quality", "subtitle_safety", "cost_efficiency"}) + (("short_runtime_sample:8",) if short_sample_deduction else ())
    status = "FAIL" if errors or grade in {"ACCEPTABLE", "FAIL"} else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return StoryboardValidationResult(status, tuple(errors), tuple(warnings), cursor, drift, "PASS" if not errors else "FAIL", "PASS" if not any("HISTORICAL" in error for error in errors) else "FAIL", "PASS" if not any("SUBTITLE" in error for error in errors) else "FAIL", "PASS" if not any("PROMPT" in error for error in errors) else "FAIL", metrics, score, grade, deductions)


def render_timeline_from_storyboard(scenes: tuple[StoryboardScene, ...], audio_path: Path, subtitle_manifest: dict[str, Any]) -> dict[str, Any]:
    shots = _flatten(scenes)
    return {"schema_version": EPISODE_RENDER_MANIFEST_V2, "episode_id": "storyboard-v1-ready", "scenes": [{"scene_id": shot.shot_id, "start_ms": shot.timing.start_ms, "end_ms": shot.timing.end_ms, "duration_ms": shot.timing.duration_ms, "visual_asset_path": f"assets/required/{shot.required_assets[0].asset_id}.png", "motion": "PUSH_IN" if shot.camera.movement != "STATIC" else "STATIC", "transition": "FADE" if shot.transition_out == "DISSOLVE" else "CUT", "claim_ids": ["storyboard-planning-only"], "source_ids": ["subtitle-track"], "visual_policy_refs": ["storyboard-subtitle-safe-policy"]} for shot in shots], "audio_layers": [{"layer_id": "narration-mastered", "role": "NARRATION", "path": str(audio_path), "start_ms": 0, "gain_db": 0}], "subtitles": {"mode": "BURNED_IN", "path": str(subtitle_manifest["exports"]["ass"])}, "output": {"video": "exports/storyboard-ready.mp4", "report": "working/storyboard-ready-report.json"}}


def _markdown(scenes: tuple[StoryboardScene, ...], validation: StoryboardValidationResult) -> str:
    lines = ["# Production Storyboard v1", "", f"Quality: **{validation.quality_grade}** ({validation.quality_score:.1f}/100)", ""]
    for scene in scenes:
        lines.extend([f"## {scene.scene_id}: {scene.narrative_purpose}", f"{scene.start_ms}–{scene.end_ms} ms · {scene.visual_strategy}", "", "| Shot | Timing | Visual | Camera | Asset |", "|---|---:|---|---|---|"])
        for shot in scene.shots:
            lines.append(f"| {shot.shot_id} | {shot.timing.start_ms}–{shot.timing.end_ms} | {shot.visual_type} | {shot.camera.movement} | {shot.required_assets[0].asset_type} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def _manifest(request: StoryboardRequest, subtitle_manifest: dict[str, Any], fingerprint: str, scenes: tuple[StoryboardScene, ...], beats: tuple[StoryBeat, ...], characters: tuple[CharacterPlan, ...], assets: tuple[dict[str, Any], ...], validation: StoryboardValidationResult, paths: dict[str, Path], cache_hit: bool) -> dict[str, Any]:
    locations = sorted({scene.location for scene in scenes if not scene.location.startswith("UNSPECIFIED")})
    counts: dict[str, int] = {}
    costs: dict[str, int] = {}
    for asset in assets: counts[asset["asset_type"]] = counts.get(asset["asset_type"], 0) + 1; costs[asset["generation_cost_class"]] = costs.get(asset["generation_cost_class"], 0) + 1
    return {"schema_version": STORYBOARD_SCHEMA_V1, "status": validation.status, "source_transcript": subtitle_manifest.get("source_transcript"), "source_subtitles": subtitle_manifest.get("exports"), "source_audio": str(request.mastered_audio_path), "input_fingerprint": fingerprint, "config_fingerprint": _fingerprint(asdict(request.config)), "storyboard_fingerprint": _fingerprint([asdict(scene) for scene in scenes]), "deterministic_seed": request.config.deterministic_seed, "narrative_arc": [scene.narrative_purpose for scene in scenes], "scene_count": len(scenes), "beat_count": len(beats), "shot_count": len(_flatten(scenes)), "total_duration_ms": subtitle_manifest["source_audio_duration_ms"], "coverage_duration_ms": validation.timing_coverage_ms, "drift_ms": validation.drift_ms, "character_count": len(characters), "location_count": len(locations), "required_asset_count": len(assets), "asset_type_counts": counts, "cost_class_distribution": costs, "visual_diversity_metrics": validation.diversity_metrics, "continuity_status": validation.continuity_status, "historical_validation": validation.historical_status, "subtitle_safety_status": validation.subtitle_safety_status, "prompt_quality_status": validation.prompt_quality_status, "quality_score": validation.quality_score, "quality_grade": validation.quality_grade, "warnings": list(validation.warnings), "errors": list(validation.errors), "export_paths": {key: str(value) for key, value in paths.items()}, "cache_status": "HIT" if cache_hit else "MISS", "render_readiness": "PASS" if validation.status != "FAIL" else "FAIL"}


def generate_storyboard(request: StoryboardRequest) -> tuple[tuple[StoryboardScene, ...], StoryboardExportResult, StoryboardValidationResult]:
    if not request.mastered_audio_path.is_file(): raise FileNotFoundError("STORYBOARD_MASTERED_AUDIO_NOT_FOUND")
    if not request.subtitle_manifest_path.is_file(): raise FileNotFoundError("STORYBOARD_SUBTITLE_MANIFEST_NOT_FOUND")
    audio = inspect_pcm_wav(request.mastered_audio_path)
    subtitle_manifest = _read_json(request.subtitle_manifest_path)
    if subtitle_manifest.get("status") not in {"PASS", "PASS_WITH_WARNINGS"}: raise ValueError("STORYBOARD_SUBTITLE_VALIDATION_REQUIRED")
    if subtitle_manifest.get("source_audio_duration_ms") != audio["duration_ms"]: raise ValueError("STORYBOARD_MASTERED_AUDIO_DURATION_MISMATCH")
    request.output_directory.mkdir(parents=True, exist_ok=True)
    paths = {"storyboard": request.output_directory / "production-storyboard-v1.json", "markdown": request.output_directory / "production-storyboard-v1.md", "asset_plan": request.output_directory / "production-storyboard-assets-v1.json", "character_bible": request.output_directory / "production-character-bible-v1.json", "location_bible": request.output_directory / "production-location-bible-v1.json", "validation": request.output_directory / "production-storyboard-v1-validation.json"}
    manifest_path = request.manifest_path or request.output_directory / "production-storyboard-v1-manifest.json"
    fingerprint = _fingerprint({"generator": _GENERATOR_REVISION, "audio": file_sha256(request.mastered_audio_path), "subtitle": file_sha256(request.subtitle_manifest_path), "config": asdict(request.config)})
    cache_hit = False
    if manifest_path.is_file() and all(path.is_file() and path.stat().st_size > 0 for path in paths.values()):
        try: cache_hit = _read_json(manifest_path).get("input_fingerprint") == fingerprint
        except (OSError, ValueError, json.JSONDecodeError): cache_hit = False
    sections, beats, scenes, characters, assets = _build_storyboard(subtitle_manifest, request)
    validation = validate_storyboard(scenes, audio["duration_ms"], request.config)
    timeline = render_timeline_from_storyboard(scenes, request.mastered_audio_path, subtitle_manifest)
    validate_episode_render_manifest_v2(timeline)
    if not cache_hit:
        atomic_write_json(paths["storyboard"], {"schema_version": STORYBOARD_SCHEMA_V1, "sections": [asdict(section) for section in sections], "beats": [asdict(beat) for beat in beats], "scenes": [asdict(scene) for scene in scenes], "render_timeline": timeline})
        paths["markdown"].write_text(_markdown(scenes, validation), encoding="utf-8", newline="\n")
        atomic_write_json(paths["asset_plan"], {"schema_version": STORYBOARD_SCHEMA_V1, "assets": list(assets)})
        atomic_write_json(paths["character_bible"], {"schema_version": STORYBOARD_SCHEMA_V1, "characters": [asdict(character) for character in characters]})
        locations = [{"location_id": _fingerprint(scene.location)[:12], "name": scene.location, "period": scene.period, "architecture": "UNSPECIFIED_REQUIRES_ART_DIRECTION", "materials": "UNSPECIFIED_REQUIRES_ART_DIRECTION", "climate": "UNSPECIFIED_REQUIRES_ART_DIRECTION", "light": scene.shots[0].lighting.style, "palette": scene.shots[0].lighting.palette, "crowd_density": "UNSPECIFIED", "props": "NO_UNVERIFIED_PROPS", "signage_policy": "NO_INVENTED_TEXT", "environmental_continuity": scene.continuity_anchor, "prohibited_anachronisms": ["modern buildings", "modern clothing", "modern technology"]} for scene in scenes]
        atomic_write_json(paths["location_bible"], {"schema_version": STORYBOARD_SCHEMA_V1, "locations": locations})
    atomic_write_json(paths["validation"], {"schema_version": STORYBOARD_VALIDATION_SCHEMA_V1, **asdict(validation), "render_timeline_validation": "PASS"})
    manifest = _manifest(request, subtitle_manifest, fingerprint, scenes, beats, characters, assets, validation, {**paths, "manifest": manifest_path}, cache_hit)
    atomic_write_json(manifest_path, manifest)
    return scenes, StoryboardExportResult(validation.status, paths["storyboard"], paths["markdown"], paths["asset_plan"], paths["character_bible"], paths["location_bible"], paths["validation"], manifest_path, cache_hit), validation
