"""Deterministic Visual Production Director for storyboard-driven image plans.

Planning is entirely local.  It produces no image and never imports a network
SDK; the Gemini adapter is invoked separately only through its live guard.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from .visual_provider_v1 import (
    GEMINI_ECONOMY_IMAGE_MODEL,
    GEMINI_LEGACY_IMAGE_MODEL,
    GEMINI_PREMIUM_IMAGE_MODEL,
    GEMINI_PRIMARY_IMAGE_MODEL,
    GEMINI_IMAGE_PROVIDER_ID,
    ReferenceImagePackage,
    VisualAssetRequest,
    VisualGenerationRequest,
    VisualQualityProfile,
    atomic_write_json,
    file_sha256,
    request_fingerprint,
)


VISUAL_GENERATION_PLAN_SCHEMA_V1 = "siraj-production-visual-generation-plan-v1"
VISUAL_STYLE_BIBLE_SCHEMA_V1 = "siraj-production-visual-style-bible-v1"
VISUAL_ASSET_REGISTRY_SCHEMA_V1 = "siraj-production-visual-assets-v1"
VISUAL_PROVIDER_MANIFEST_SCHEMA_V1 = "siraj-production-visual-provider-v1"
PROMPT_VERSION = "gemini-visual-prompt-v1"


@dataclass(frozen=True)
class VisualGenerationConfig:
    primary_model: str = GEMINI_PRIMARY_IMAGE_MODEL
    premium_model: str = GEMINI_PREMIUM_IMAGE_MODEL
    economy_model: str = GEMINI_ECONOMY_IMAGE_MODEL
    legacy_model: str = GEMINI_LEGACY_IMAGE_MODEL
    default_aspect_ratio: str = "16:9"
    default_final_resolution: str = "2K"
    draft_resolution: str = "1K"
    hero_resolution: str = "4K"
    max_references_per_request: int = 4


@dataclass(frozen=True)
class ModelRoutingDecision:
    asset_id: str
    initial_model: str
    selected_model: str
    model_role: str
    resolution: str
    reasons: tuple[str, ...]
    escalation_allowed: bool
    fallback_model: str | None


@dataclass(frozen=True)
class VisualPlanResult:
    status: str
    plan_path: Path
    style_bible_path: Path
    asset_registry_path: Path
    quality_report_path: Path
    continuity_report_path: Path
    quota_report_path: Path
    manifest_path: Path
    asset_count: int
    cache_status: str


def json_fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"VISUAL_INPUT_NOT_OBJECT:{path.name}")
    return value


def route_visual_asset(asset: dict[str, Any], shot: dict[str, Any], config: VisualGenerationConfig) -> ModelRoutingDecision:
    narrative = str(shot.get("narrative_function", ""))
    asset_type = str(asset.get("asset_type", ""))
    complexity = str(asset.get("complexity", "MEDIUM"))
    priority = str(asset.get("priority", "RECOMMENDED"))
    reasons: list[str] = []
    if narrative in {"OPENING_HOOK", "CLIMAX"} or asset_type in {"CHARACTER_MASTER_REFERENCE", "LOCATION_MASTER_REFERENCE"}:
        reasons.append("HERO_OR_MASTER_REFERENCE")
        return ModelRoutingDecision(str(asset["asset_id"]), config.premium_model, config.premium_model, "PREMIUM_QUALITY", config.hero_resolution, tuple(reasons), True, config.primary_model)
    if asset_type in {"MAP", "INFOGRAPHIC", "SIMPLE_BACKGROUND"} or (complexity == "LOW" and priority != "REQUIRED"):
        reasons.append("LOW_COMPLEXITY_SUPPORT_ASSET")
        return ModelRoutingDecision(str(asset["asset_id"]), config.economy_model, config.economy_model, "ECONOMY", config.draft_resolution, tuple(reasons), False, config.legacy_model)
    reasons.append("STANDARD_CINEMATIC_ASSET")
    if complexity == "HIGH": reasons.append("HIGH_COMPLEXITY")
    return ModelRoutingDecision(str(asset["asset_id"]), config.primary_model, config.primary_model, "ACTIVE_PRIMARY", config.default_final_resolution, tuple(reasons), True, config.legacy_model)


def build_visual_style_bible(storyboard: dict[str, Any]) -> dict[str, Any]:
    locations = sorted({str(scene.get("location", "UNSPECIFIED")) for scene in storyboard.get("scenes", [])})
    return {
        "schema_version": VISUAL_STYLE_BIBLE_SCHEMA_V1,
        "visual_identity": "restrained cinematic historical documentary",
        "realism_level": "PHOTOREALISTIC_RECONSTRUCTION_WITH_HISTORICAL_RESTRAINT",
        "cinematic_language": {"lens": "observational 35mm and 50mm documentary language", "depth_of_field": "motivated, not universal", "camera": "composed and legible"},
        "color_science": {"palette": "earth tones with natural daylight variations", "contrast": "moderate", "skin_tone_policy": "natural and non-stylized"},
        "lighting_philosophy": "period-appropriate motivated light; avoid default orange-and-teal treatment",
        "texture_policy": "material-specific texture; subtle film grain only when justified",
        "historical_reconstruction_policy": "do not assert unverified visual details as fact; mark plausible reconstructions",
        "map_style": "geographically restrained base image; exact Arabic labels belong in render layer",
        "infographic_style": "minimal hierarchy; exact figures belong in render layer",
        "document_style": "period-correct materials; no invented readable paragraphs",
        "title_card_style": "render-layer typography, not image-model text",
        "subtitle_safe_policy": "keep lower 22 percent uncluttered unless the shot explicitly declares another safe region",
        "forbidden_styles": ["watermark", "logo", "accidental readable text", "modern objects", "duplicate people", "warped faces", "extra limbs", "collage unless requested", "unmotivated smoke", "universal shallow depth of field"],
        "forbidden_modern_artifacts": ["modern architecture", "modern clothing", "modern technology", "invented political borders"],
        "locations": locations,
    }


def _english_prompt(shot: dict[str, Any], style_bible: dict[str, Any]) -> str:
    composition = shot.get("composition", {})
    camera = shot.get("camera", {})
    lighting = shot.get("lighting", {})
    environment = shot.get("environment", {})
    exclusions = "; ".join(style_bible["forbidden_styles"] + style_bible["forbidden_modern_artifacts"])
    return "\n".join([
        "Production goal: create one coherent historical documentary frame supporting the narrated shot.",
        f"Arabic source narrative (do not render as on-image text): {shot.get('transcript_span', '')}",
        f"Main subject: {shot.get('subject', 'documentary environment')}. Action: {shot.get('action', 'observe the moment')}.",
        f"Environment: location {environment.get('geographic_location', 'unspecified')}; period {environment.get('time_period', 'unspecified')}; weather {environment.get('weather', 'unspecified')}.",
        f"Composition: {composition.get('framing', 'wide')}; subject placement {composition.get('subject_placement', 'upper two thirds')}; depth {composition.get('depth', 'foreground midground background')}.",
        f"Camera: {camera.get('movement', 'locked')}; angle {composition.get('camera_angle', 'eye level')}; lens feel {composition.get('lens_feel', 'documentary')}.",
        f"Lighting: {lighting.get('style', 'natural')}; palette {lighting.get('palette', 'earth tones')}; contrast {lighting.get('contrast', 'moderate')}.",
        f"Continuity: anchor {shot.get('continuity_requirements', {}).get('continuity_anchor', 'none')}; preserve wardrobe, location, palette, and screen direction when references are supplied.",
        "Subtitle safety: keep the lower third uncluttered; render no subtitles, title, logo, or invented text in the image.",
        f"Historical restraint: factual confidence is {shot.get('factual_confidence', 'UNKNOWN')}; reconstruction is {shot.get('reconstruction_status', 'UNKNOWN')}; do not invent disputed factual details.",
        f"Explicit exclusions: {exclusions}.",
        "Output quality: cinematic realism, clear anatomy, coherent faces, physically plausible materials, single camera viewpoint.",
    ])


def _approval_for(asset: dict[str, Any], shot: dict[str, Any]) -> str:
    if asset.get("asset_type") in {"CHARACTER_MASTER_REFERENCE", "LOCATION_MASTER_REFERENCE", "MAP", "DOCUMENT"}:
        return "HUMAN_REVIEW_REQUIRED"
    if shot.get("narrative_function") in {"OPENING_HOOK", "CLIMAX"} or shot.get("speculative_visual"):
        return "HUMAN_REVIEW_REQUIRED"
    return "AUTO_APPROVED"


def _master_assets(character_bible: dict[str, Any], location_bible: dict[str, Any]) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for character in character_bible.get("characters", []):
        if character.get("role") == "PRIMARY_NARRATOR":
            continue
        planned.append({"asset_id": f"master-character-{character['character_id']}", "asset_type": "CHARACTER_MASTER_REFERENCE", "priority": "REQUIRED", "complexity": "HIGH", "dependency": None, "scene_id": None, "shot_id": None, "approval_status": "HUMAN_REVIEW_REQUIRED", "status": "PLANNED", "role": character.get("role"), "reference_subject": character.get("name")})
    for location in location_bible.get("locations", []):
        planned.append({"asset_id": f"master-location-{location['location_id']}", "asset_type": "LOCATION_MASTER_REFERENCE", "priority": "REQUIRED", "complexity": "HIGH", "dependency": None, "scene_id": None, "shot_id": None, "approval_status": "HUMAN_REVIEW_REQUIRED", "status": "PLANNED", "reference_subject": location.get("name")})
    return planned


def _location_master_id(location_bible: dict[str, Any], name: str) -> str | None:
    for location in location_bible.get("locations", []):
        if location.get("name") == name:
            return f"master-location-{location['location_id']}"
    return None


def _character_master_id(character_bible: dict[str, Any], character_id: str | None) -> str | None:
    for character in character_bible.get("characters", []):
        if character.get("character_id") == character_id:
            return f"master-character-{character_id}"
    return None


def build_visual_generation_plan(storyboard_path: Path, character_bible_path: Path, location_bible_path: Path, output_directory: Path, manifest_path: Path, *, config: VisualGenerationConfig | None = None, replace: bool = False) -> VisualPlanResult:
    config = config or VisualGenerationConfig()
    storyboard, character_bible, location_bible = _read_object(storyboard_path), _read_object(character_bible_path), _read_object(location_bible_path)
    if not replace and manifest_path.exists():
        existing = _read_object(manifest_path)
        if existing.get("input_fingerprint") == json_fingerprint({"storyboard": storyboard, "characters": character_bible, "locations": location_bible, "config": asdict(config)}):
            return VisualPlanResult("PASS", output_directory / "production-visual-generation-plan-v1.json", output_directory / "production-visual-style-bible-v1.json", output_directory / "production-visual-assets-v1.json", output_directory / "production-visual-quality-report-v1.json", output_directory / "production-visual-continuity-report-v1.json", output_directory / "production-visual-quota-report-v1.json", manifest_path, len(existing.get("assets", [])), "HIT")
    output_directory.mkdir(parents=True, exist_ok=True)
    style_bible = build_visual_style_bible(storyboard)
    style_fingerprint, character_fingerprint, location_fingerprint, storyboard_fingerprint, config_fingerprint = (json_fingerprint(style_bible), json_fingerprint(character_bible), json_fingerprint(location_bible), json_fingerprint(storyboard), json_fingerprint(asdict(config)))
    registry = _master_assets(character_bible, location_bible)
    requests: list[VisualGenerationRequest] = []
    route_records: list[dict[str, Any]] = []
    for master in registry:
        subject = str(master.get("reference_subject", "historical reference"))
        synthetic_shot = {"narrative_function": "OPENING_HOOK", "transcript_span": "", "subject": subject, "action": "establish a locked visual reference", "environment": {"geographic_location": subject if master["asset_type"] == "LOCATION_MASTER_REFERENCE" else "historical documentary setting", "time_period": "UNSPECIFIED_REQUIRES_ART_DIRECTION", "weather": "UNSPECIFIED"}, "composition": {"framing": "wide establishing" if master["asset_type"] == "LOCATION_MASTER_REFERENCE" else "neutral three-quarter portrait", "subject_placement": "upper two thirds", "depth": "foreground midground background", "camera_angle": "eye level", "lens_feel": "50mm documentary"}, "camera": {"movement": "locked"}, "lighting": {"style": "natural motivated", "palette": "earth tones", "contrast": "moderate"}, "continuity_requirements": {"continuity_anchor": master["asset_id"]}, "factual_confidence": "PLAUSIBLE_RECONSTRUCTION", "reconstruction_status": "PLAUSIBLE_RECONSTRUCTION"}
        route = route_visual_asset(master, synthetic_shot, config)
        profile = VisualQualityProfile(name="MASTER_REFERENCE", requested_resolution=route.resolution, aspect_ratio=config.default_aspect_ratio, hero=True, human_review_required=True)
        request = VisualGenerationRequest(VisualAssetRequest(asset_id=master["asset_id"], scene_id="MASTER_REFERENCE", shot_id=master["asset_id"], timeline_start_ms=0, timeline_end_ms=0, asset_type=master["asset_type"], priority="REQUIRED", prompt=_english_prompt(synthetic_shot, style_bible), prompt_version=PROMPT_VERSION, quality_profile=profile, factual_confidence="PLAUSIBLE_RECONSTRUCTION", reconstruction_status="PLAUSIBLE_RECONSTRUCTION"), GEMINI_IMAGE_PROVIDER_ID, route.selected_model)
        fingerprint = request_fingerprint(request, style_bible_fingerprint=style_fingerprint, character_bible_fingerprint=character_fingerprint, location_bible_fingerprint=location_fingerprint, storyboard_fingerprint=storyboard_fingerprint, config_fingerprint=config_fingerprint)
        master.update({"status": "READY_TO_GENERATE", "provider": request.provider_id, "model": request.model_id, "model_role": route.model_role, "prompt_hash": sha256(request.asset.prompt.encode("utf-8")).hexdigest(), "cache_key": fingerprint, "dependencies": [], "timeline": None, "warnings": ["MASTER_REFERENCE_REQUIRES_HUMAN_APPROVAL_BEFORE_DEPENDENT_SHOTS"]})
        route_records.append({**asdict(route), "asset_id": request.asset.asset_id, "cache_key": fingerprint})
        requests.append(request)
    for scene in storyboard.get("scenes", []):
        for shot in scene.get("shots", []):
            for required in shot.get("required_assets", []):
                asset = dict(required)
                asset["scene_id"], asset["shot_id"] = shot["scene_id"], shot["shot_id"]
                route = route_visual_asset(asset, shot, config)
                dependencies = tuple(item for item in (_location_master_id(location_bible, str(scene.get("location", ""))), _character_master_id(character_bible, shot.get("speaker_id"))) if item)
                profile = VisualQualityProfile(name="HERO_FINAL" if route.model_role == "PREMIUM_QUALITY" else "STANDARD_FINAL", requested_resolution=route.resolution, aspect_ratio=config.default_aspect_ratio, hero=route.model_role == "PREMIUM_QUALITY", human_review_required=_approval_for(asset, shot) == "HUMAN_REVIEW_REQUIRED")
                request = VisualGenerationRequest(VisualAssetRequest(asset_id=str(asset["asset_id"]), scene_id=shot["scene_id"], shot_id=shot["shot_id"], timeline_start_ms=int(shot["timing"]["start_ms"]), timeline_end_ms=int(shot["timing"]["end_ms"]), asset_type=str(asset["asset_type"]), priority=str(asset.get("priority", "RECOMMENDED")), prompt=_english_prompt(shot, style_bible), prompt_version=PROMPT_VERSION, quality_profile=profile, references=ReferenceImagePackage(), negative_constraints=tuple(style_bible["forbidden_styles"]), dependency_asset_ids=dependencies, factual_confidence=str(shot.get("factual_confidence", "UNKNOWN")), reconstruction_status=str(shot.get("reconstruction_status", "UNKNOWN")), subtitle_safe_region="LOWER_THIRD_CLEAR", parent_asset_id=None), GEMINI_IMAGE_PROVIDER_ID, route.selected_model)
                fingerprint = request_fingerprint(request, style_bible_fingerprint=style_fingerprint, character_bible_fingerprint=character_fingerprint, location_bible_fingerprint=location_fingerprint, storyboard_fingerprint=storyboard_fingerprint, config_fingerprint=config_fingerprint)
                blocked = bool(dependencies)
                registry.append({"asset_id": request.asset.asset_id, "type": request.asset.asset_type, "role": shot.get("narrative_function"), "scene_id": request.asset.scene_id, "shot_id": request.asset.shot_id, "status": "BLOCKED_BY_DEPENDENCY" if blocked else "READY_TO_GENERATE", "provider": request.provider_id, "model": request.model_id, "model_role": route.model_role, "references": [], "version": 1, "parent": None, "prompt_hash": sha256(request.asset.prompt.encode("utf-8")).hexdigest(), "file_hash": None, "dimensions": None, "score": None, "approval_status": _approval_for(asset, shot), "reuse_permissions": bool(asset.get("reuse_allowed")), "dependencies": list(dependencies), "timeline": {"start_ms": request.asset.timeline_start_ms, "end_ms": request.asset.timeline_end_ms, "crop_mode": "COVER_16_9", "motion_plan": shot.get("camera", {}).get("movement"), "transition": shot.get("transition_out"), "subtitle_safe_region": request.asset.subtitle_safe_region, "overlay_safe_region": "LOWER_THIRD_CLEAR"}, "factual_confidence": request.asset.factual_confidence, "reconstruction_status": request.asset.reconstruction_status, "cache_key": fingerprint, "warnings": ["PLANNED_ONLY_NO_IMAGE_GENERATED", "DEPENDENT_SHOT_REQUIRES_APPROVED_MASTER_REFERENCES"] if blocked else ["PLANNED_ONLY_NO_IMAGE_GENERATED"]})
                route_records.append({**asdict(route), "asset_id": request.asset.asset_id, "cache_key": fingerprint})
                requests.append(request)
    plan = {"schema_version": VISUAL_GENERATION_PLAN_SCHEMA_V1, "status": "DRY_RUN_ONLY", "provider": GEMINI_IMAGE_PROVIDER_ID, "local_providers": {"comfyui": "DISABLED:LOCAL_HARDWARE_QUALITY_INSUFFICIENT", "sdxl": "DISABLED:LOCAL_HARDWARE_QUALITY_INSUFFICIENT", "flux": "DISABLED:LOCAL_HARDWARE_QUALITY_INSUFFICIENT", "imagen": "DISABLED:DEPRECATED_PROVIDER"}, "style_bible_fingerprint": style_fingerprint, "model_routing": route_records, "assets": registry, "requests": [{"asset_id": item.asset.asset_id, "provider": item.provider_id, "model": item.model_id, "prompt": item.asset.prompt, "prompt_version": item.asset.prompt_version, "references": [], "dependencies": list(item.asset.dependency_asset_ids), "resolution": item.asset.quality_profile.requested_resolution, "aspect_ratio": item.asset.quality_profile.aspect_ratio, "live": False} for item in requests], "network_calls": 0, "generated_images": 0, "provider_nondeterminism": "LIVE_IMAGE_MODELS_ARE_NOT_BYTE_DETERMINISTIC; cache prevents duplicate approved generation."}
    quality = {"schema_version": "siraj-production-visual-quality-report-v1", "status": "PLAN_VALIDATED", "image_validation": "NOT_RUN_DRY_RUN", "visual_critic": "NOT_RUN", "required_categories": ["prompt_adherence", "cinematic_composition", "character_consistency", "location_consistency", "historical_accuracy", "anatomy_and_faces", "lighting_and_color", "emotional_impact", "subtitle_safety", "technical_quality", "render_usability"], "approval_policy": {"hero": "HUMAN_REVIEW_REQUIRED", "master_references": "HUMAN_REVIEW_REQUIRED", "speculative_reconstruction": "HUMAN_REVIEW_REQUIRED"}}
    continuity = {"schema_version": "siraj-production-visual-continuity-report-v1", "status": "PLAN_VALIDATED", "character_pipeline": "MASTER_REFERENCE_REQUIRED_BEFORE_DEPENDENT_SHOTS", "location_pipeline": "MASTER_REFERENCE_REQUIRED_BEFORE_DEPENDENT_SHOTS", "blocked_dependent_assets": [item["asset_id"] for item in registry if item["status"] == "BLOCKED_BY_DEPENDENCY"], "reference_limits": {"maximum_per_request": config.max_references_per_request, "selection": "priority_then_approved_only"}}
    quota_report = {"schema_version": "siraj-production-visual-quota-report-v1", "status": "DRY_RUN_ONLY", "provider": GEMINI_IMAGE_PROVIDER_ID, "quota_status": "UNKNOWN", "quota_remaining": "UNKNOWN", "requests_attempted": 0, "requests_succeeded": 0, "requests_failed": 0, "assets_generated": 0, "retries_used": 0, "guard_requirements": ["GEMINI_API_KEY", "--live", "--confirm-quota-use", "valid quota policy"], "timestamps": {}}
    input_fingerprint = json_fingerprint({"storyboard": storyboard, "characters": character_bible, "locations": location_bible, "config": asdict(config)})
    manifest = {"schema_version": VISUAL_PROVIDER_MANIFEST_SCHEMA_V1, "status": "DRY_RUN_ONLY", "active_provider": GEMINI_IMAGE_PROVIDER_ID, "active_models": {"primary": config.primary_model, "premium": config.premium_model, "economy": config.economy_model, "legacy_fast": config.legacy_model}, "api_key_present": bool(os.environ.get("GEMINI_API_KEY", "").strip()), "input_fingerprint": input_fingerprint, "assets": registry, "asset_count": len(registry), "generated_asset_count": 0, "quality": quality["status"], "continuity": continuity["status"], "quota_report": "production-visual-quota-report-v1.json", "historical_validation": "PASS_METADATA_ONLY", "render_readiness": "READY_FOR_APPROVED_ASSETS_ONLY", "cache_status": "MISS", "warnings": ["DRY_RUN_CREATED_NO_EXTERNAL_REQUEST", "NO_ASSET_IS_APPROVED_OR_GENERATED"], "errors": []}
    outputs = {"production-visual-generation-plan-v1.json": plan, "production-visual-style-bible-v1.json": style_bible, "production-visual-assets-v1.json": {"schema_version": VISUAL_ASSET_REGISTRY_SCHEMA_V1, "assets": registry}, "production-visual-quality-report-v1.json": quality, "production-visual-continuity-report-v1.json": continuity, "production-visual-quota-report-v1.json": quota_report}
    for name, value in outputs.items(): atomic_write_json(output_directory / name, value)
    atomic_write_json(manifest_path, manifest)
    return VisualPlanResult("PASS", output_directory / "production-visual-generation-plan-v1.json", output_directory / "production-visual-style-bible-v1.json", output_directory / "production-visual-assets-v1.json", output_directory / "production-visual-quality-report-v1.json", output_directory / "production-visual-continuity-report-v1.json", output_directory / "production-visual-quota-report-v1.json", manifest_path, len(registry), "MISS")


def visual_asset_cache_valid(record: dict[str, Any], project_root: Path) -> bool:
    path = record.get("output_path")
    expected = record.get("file_hash")
    if not isinstance(path, str) or not isinstance(expected, str): return False
    candidate = (project_root / path).resolve(strict=False)
    try: candidate.relative_to(project_root)
    except ValueError: return False
    return candidate.is_file() and file_sha256(candidate) == expected


_ALLOWED_TRANSITIONS = {
    "PLANNED": {"BLOCKED_BY_DEPENDENCY", "READY_TO_GENERATE", "COST_BLOCKED", "PROVIDER_BLOCKED"},
    "BLOCKED_BY_DEPENDENCY": {"READY_TO_GENERATE", "REJECTED"},
    "READY_TO_GENERATE": {"GENERATING", "COST_BLOCKED", "PROVIDER_BLOCKED"},
    "GENERATING": {"GENERATED", "NEEDS_CORRECTION", "REJECTED"},
    "GENERATED": {"VALIDATING", "NEEDS_CORRECTION"},
    "VALIDATING": {"APPROVED", "NEEDS_CORRECTION", "REJECTED"},
    "NEEDS_CORRECTION": {"GENERATING", "REJECTED"},
    "APPROVED": set(), "REJECTED": set(), "COST_BLOCKED": {"READY_TO_GENERATE"}, "PROVIDER_BLOCKED": {"READY_TO_GENERATE"},
}


def validate_asset_state_transition(current: str, target: str) -> None:
    if target not in _ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"VISUAL_ASSET_STATE_TRANSITION_INVALID:{current}:{target}")


def build_render_timeline_from_approved_assets(registry: dict[str, Any], project_root: Path) -> list[dict[str, Any]]:
    """Produce the narrow visual timeline contract consumed by the render layer."""
    timeline: list[dict[str, Any]] = []
    for asset in sorted(registry.get("assets", []), key=lambda item: (item.get("timeline", {}).get("start_ms", -1), item.get("asset_id", ""))):
        if asset.get("status") != "APPROVED":
            continue
        output = asset.get("output_path")
        if not isinstance(output, str):
            raise ValueError("APPROVED_VISUAL_ASSET_OUTPUT_PATH_REQUIRED")
        candidate = (project_root / output).resolve(strict=False)
        try: candidate.relative_to(project_root)
        except ValueError as error: raise ValueError("VISUAL_ASSET_OUTSIDE_PROJECT") from error
        if not candidate.is_file() or not visual_asset_cache_valid(asset, project_root):
            raise ValueError("APPROVED_VISUAL_ASSET_INVALID")
        timing = asset.get("timeline", {})
        timeline.append({"scene_id": asset.get("scene_id"), "shot_id": asset.get("shot_id"), "visual_asset_path": output, "start_ms": timing.get("start_ms"), "end_ms": timing.get("end_ms"), "crop_mode": timing.get("crop_mode"), "motion": timing.get("motion_plan"), "transition": timing.get("transition"), "subtitle_safe_region": timing.get("subtitle_safe_region"), "overlay_safe_region": timing.get("overlay_safe_region")})
    return timeline
