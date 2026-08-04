from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

EPISODE_ID = "episode-001-adam"
SHOT_ID = "ADAM-DC2-S02-SH03"
PACKAGE_ID = "adam_veo_shot_pack_001_v1_afe8d586bc5cf23c"
BINDING_ID = "adam_veo_shot_pack_001_binding_v1_fd0f2e91dfe37fc4"
PACKAGE_SHA256 = "3a8e48d5400ee786b4521495ddc4dd3317dd593ce68aa6ce151ab68fe886cb41"
MANIFEST_ID = "adam_veo_production_manifest_v1_83ce0eb05bd48993"
MANIFEST_BINDING_ID = "adam_veo_production_manifest_binding_v1_4571b4aa53e79b4a"
POLICY_ID = "adam_visual_safety_policy_v2_2a7c860f00834840"
STORYBOARD_FINGERPRINT = "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
MODEL = "google:veo@3.1-lite"
BEAT_01_ID = "ADAM-DC2-S02-SH03-B01"
BEAT_02_ID = "ADAM-DC2-S02-SH03-B02"
EXPECTED_SEED = 3256281284
REQUIRED_PROMPT_FRAGMENTS = (
    "One continuous photorealistic cinematic macro shot",
    "thin stream of clear rainwater",
    "bind into dense layered clay",
    "one small natural eddy that settles",
    "no person",
    "no human figure",
    "no body shape",
    "no supernatural being",
    "no magical energy",
    "no text",
    "no logo",
    "no watermark",
    "never forms a humanoid shape",
)


class VeoShotPackageError(ValueError):
    pass


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VeoShotPackageError(f"{label} must be an object.")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VeoShotPackageError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VeoShotPackageError(f"{path} must contain a JSON object.")
    return value


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_package(
    package: Mapping[str, Any],
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> None:
    if package.get("shot_package_id") != PACKAGE_ID:
        raise VeoShotPackageError("Shot package id changed.")
    if package.get("episode_id") != EPISODE_ID:
        raise VeoShotPackageError("Episode id changed.")
    if package.get("shot_id") != SHOT_ID:
        raise VeoShotPackageError("Shot id changed.")
    if package.get("status") != "READY_FOR_HUMAN_SHOT_PACKAGE_REVIEW":
        raise VeoShotPackageError("Package must remain in human review.")
    if package.get("next_stage_if_human_approved") != (
        "MANUAL_RUNWARE_EXECUTION_OF_BEAT_01"
    ):
        raise VeoShotPackageError("Approved next stage changed.")

    bindings = _mapping(package.get("bindings"), "package bindings")
    if bindings.get("veo_production_manifest_id") != MANIFEST_ID:
        raise VeoShotPackageError("Package binds another manifest.")
    if bindings.get("visual_safety_policy_id") != POLICY_ID:
        raise VeoShotPackageError("Package binds another visual policy.")
    if bindings.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise VeoShotPackageError("Storyboard fingerprint changed.")

    if manifest.get("manifest_id") != MANIFEST_ID:
        raise VeoShotPackageError("Repository manifest id changed.")
    if policy.get("policy_id") != POLICY_ID:
        raise VeoShotPackageError("Repository policy id changed.")

    shots = manifest.get("shots")
    if not isinstance(shots, list):
        raise VeoShotPackageError("Manifest shots missing.")
    shot = next(
        (
            item for item in shots
            if isinstance(item, Mapping) and item.get("shot_id") == SHOT_ID
        ),
        None,
    )
    if shot is None:
        raise VeoShotPackageError("Target shot missing from manifest.")
    if shot.get("primary_production_mode") != "TEXT_TO_VIDEO":
        raise VeoShotPackageError("Target shot is no longer text-to-video.")
    if shot.get("source_image_requirement") != "NOT_REQUIRED":
        raise VeoShotPackageError("Target shot unexpectedly requires a source image.")
    if shot.get("recommended_veo_generation_units_seconds") != [8, 8]:
        raise VeoShotPackageError("Target shot generation units changed.")
    if shot.get("editorial_duration_seconds") != 16:
        raise VeoShotPackageError("Target shot editorial duration changed.")

    execution = _mapping(package.get("execution_authorization"), "execution")
    if execution.get("automatic_provider_execution") != "BLOCKED":
        raise VeoShotPackageError("Automatic execution opened.")
    if execution.get("manual_user_execution") != (
        "BLOCKED_UNTIL_HUMAN_SHOT_PACKAGE_APPROVAL"
    ):
        raise VeoShotPackageError("Manual execution opened before approval.")
    if execution.get("second_generation_beat") != (
        "DEFERRED_UNTIL_BEAT_01_HUMAN_REVIEW"
    ):
        raise VeoShotPackageError("Beat 02 was opened too early.")

    beats = package.get("generation_beats")
    if not isinstance(beats, list) or len(beats) != 2:
        raise VeoShotPackageError("Exactly two generation beats are required.")
    beat_01 = _mapping(beats[0], "beat 01")
    beat_02 = _mapping(beats[1], "beat 02")
    if beat_01.get("beat_id") != BEAT_01_ID:
        raise VeoShotPackageError("Beat 01 id changed.")
    if beat_01.get("execution_status") != "NOT_AUTHORISED":
        raise VeoShotPackageError("Beat 01 execution opened before approval.")
    if beat_01.get("source_image") != "NONE_TEXT_TO_VIDEO":
        raise VeoShotPackageError("Beat 01 source mode changed.")
    if beat_01.get("duration_seconds") != 8:
        raise VeoShotPackageError("Beat 01 duration changed.")

    settings = _mapping(beat_01.get("settings"), "beat 01 settings")
    if settings.get("task_type") != "videoInference":
        raise VeoShotPackageError("Task type changed.")
    if settings.get("model") != MODEL:
        raise VeoShotPackageError("Model changed.")
    if settings.get("width") != 1280 or settings.get("height") != 720:
        raise VeoShotPackageError("720p landscape dimensions changed.")
    if settings.get("resolution_parameter") != (
        "OMIT_FOR_TEXT_TO_VIDEO_WITH_WIDTH_HEIGHT"
    ):
        raise VeoShotPackageError("Resolution dependency rule changed.")
    if settings.get("duration") != 8:
        raise VeoShotPackageError("Settings duration changed.")
    if settings.get("seed") != EXPECTED_SEED:
        raise VeoShotPackageError("Deterministic seed changed.")
    if settings.get("number_results") != 1:
        raise VeoShotPackageError("Result count must remain one.")

    provider = _mapping(
        _mapping(settings.get("provider_settings"), "provider settings").get("google"),
        "google settings",
    )
    if provider.get("generateAudio") is not False:
        raise VeoShotPackageError("Audio generation must remain off.")
    if provider.get("personGeneration") != "dont_allow":
        raise VeoShotPackageError("People must remain disabled for this shot.")

    prompt = beat_01.get("positive_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise VeoShotPackageError("Positive prompt missing.")
    for fragment in REQUIRED_PROMPT_FRAGMENTS:
        if fragment not in prompt:
            raise VeoShotPackageError(
                f"Required prompt fragment missing: {fragment}"
            )
    negative = _mapping(beat_01.get("negative_prompt"), "negative prompt policy")
    if negative.get("field_usage") != (
        "NOT_USED_MODEL_SCHEMA_DOES_NOT_LIST_NEGATIVE_PROMPT"
    ):
        raise VeoShotPackageError("Unsupported negative-prompt field was enabled.")

    if beat_02.get("beat_id") != BEAT_02_ID:
        raise VeoShotPackageError("Beat 02 id changed.")
    if beat_02.get("status") != "DEFERRED":
        raise VeoShotPackageError("Beat 02 must remain deferred.")
    if beat_02.get("execution_status") != "BLOCKED":
        raise VeoShotPackageError("Beat 02 execution must remain blocked.")
    if beat_02.get("prompt") != "NOT_YET_AUTHORED":
        raise VeoShotPackageError("Beat 02 prompt was authored prematurely.")

    gate = _mapping(package.get("acceptance_gate"), "acceptance gate")
    scoring = _mapping(gate.get("scoring"), "acceptance scoring")
    if scoring.get("pass_threshold") != 80:
        raise VeoShotPackageError("Acceptance threshold changed.")
    if scoring.get("blocking_failure_overrides_score") is not True:
        raise VeoShotPackageError("Blocking failures must override score.")
    if sum(
        int(scoring[key])
        for key in (
            "material_transformation_and_narrative_function",
            "water_and_clay_physical_coherence",
            "camera_control_and_composition",
            "temporal_texture_and_geometry_stability",
            "visual_safety_and_absence_of_forbidden_forms",
        )
    ) != 100:
        raise VeoShotPackageError("Acceptance score weights must total 100.")

    receipt = _mapping(
        package.get("provider_execution_receipt"),
        "provider execution receipt",
    )
    if receipt.get("status") != "NOT_GENERATED":
        raise VeoShotPackageError("Package unexpectedly contains generated output.")


def validate_binding(
    binding: Mapping[str, Any],
    package: Mapping[str, Any],
    manifest_binding: Mapping[str, Any],
) -> None:
    if binding.get("binding_id") != BINDING_ID:
        raise VeoShotPackageError("Binding id changed.")
    if binding.get("shot_package_id") != package.get("shot_package_id"):
        raise VeoShotPackageError("Binding points to another package.")
    if binding.get("shot_package_sha256") != PACKAGE_SHA256:
        raise VeoShotPackageError("Recorded package hash changed.")
    if canonical_sha256(package) != PACKAGE_SHA256:
        raise VeoShotPackageError("Shot package canonical hash mismatch.")
    if binding.get("veo_production_manifest_binding_id") != MANIFEST_BINDING_ID:
        raise VeoShotPackageError("Binding points to another manifest binding.")
    if manifest_binding.get("binding_id") != MANIFEST_BINDING_ID:
        raise VeoShotPackageError("Repository manifest binding changed.")
    if binding.get("human_shot_package_approval") is not False:
        raise VeoShotPackageError("Human approval was forged.")
    if binding.get("manual_provider_execution") != (
        "BLOCKED_UNTIL_HUMAN_SHOT_PACKAGE_APPROVAL"
    ):
        raise VeoShotPackageError("Binding opened manual execution.")
    if binding.get("automatic_paid_execution") != "BLOCKED":
        raise VeoShotPackageError("Binding opened automatic paid execution.")
    if binding.get("next_stage") != (
        "HUMAN_REVIEW_ADAM_VEO_SHOT_PACK_001_V1"
    ):
        raise VeoShotPackageError("Binding next stage changed.")


def validate_repository(repo_root: Path) -> dict[str, Any]:
    episode = repo_root / "projects" / "episode-001-adam"
    package = read_json(
        episode
        / "cinematic"
        / "shot-packages"
        / "adam-dc2-s02-sh03"
        / "veo-shot-pack-001-v1.json"
    )
    binding = read_json(
        episode
        / "contracts"
        / "veo-shot-pack-001-binding-v1.json"
    )
    manifest = read_json(
        episode / "cinematic" / "veo-production-manifest-v1.json"
    )
    manifest_binding = read_json(
        episode / "contracts" / "veo-production-manifest-binding-v1.json"
    )
    policy = read_json(
        episode / "cinematic" / "visual-safety-policy-v2.json"
    )
    validate_package(package, manifest, policy)
    validate_binding(binding, package, manifest_binding)
    return {
        "status": "PASS_ADAM_VEO_SHOT_PACK_001_V1",
        "shot_package_id": package["shot_package_id"],
        "binding_id": binding["binding_id"],
        "shot_id": SHOT_ID,
        "beat_01_status": package["generation_beats"][0]["execution_status"],
        "beat_02_status": package["generation_beats"][1]["status"],
        "next_stage": binding["next_stage"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()
    result = validate_repository(args.repo_root.resolve())
    for key, value in result.items():
        print(f"{key.upper()}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
