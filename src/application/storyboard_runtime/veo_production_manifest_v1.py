from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

EPISODE_ID = "episode-001-adam"
POLICY_ID = "adam_visual_safety_policy_v2_2a7c860f00834840"
EVIDENCE_ID = "adam_visual_safety_human_direction_v2_e5875735fb8ada90"
BINDING_ID = "adam_visual_safety_policy_binding_v2_d70eccdd4ffca1b6"
MANIFEST_ID = "adam_veo_production_manifest_v1_83ce0eb05bd48993"
MANIFEST_BINDING_ID = "adam_veo_production_manifest_binding_v1_4571b4aa53e79b4a"
MODEL = "google:veo@3.1-lite"
STORYBOARD_FINGERPRINT = "867b88ade164ebe444aeaaeeb9f60accef122f59cf8b45b020223f3ca8788bf8"
SCRIPT_FINGERPRINT = "ff540783ec519581bd902caf81145c3f77819a7351f2bd5d07e9f84705a4fb27"
ALLOWED_DURATIONS = {4, 6, 8}
EXPECTED_COUNTS = {
    "IMAGE_TO_VIDEO": 29,
    "TEXT_TO_VIDEO": 10,
    "COMPOSITING": 25,
    "GRAPHICS": 6,
}
REQUIRED_POLICY_RULES = {
    "NO_TABARRUJ_FOR_WOMEN",
    "WOMEN_HAIR_MUST_REMAIN_COVERED",
    "WOMEN_LIMITED_EXPOSURE_NECESSITY_ONLY",
    "NO_COMPLETE_IDENTIFIABLE_FACE_FOR_ANY_CHARACTER",
    "ADAM_DEPICTION_CONSTRAINTS",
    "NO_ANGEL_DEPICTION",
    "NO_ALLAH_OR_UNSEEN_ESSENCE_DEPICTION",
    "NO_IBLIS_BODY_OR_FACE_DEPICTION",
    "PARADISE_NO_DECAY_BARRENNESS_OR_DEPLETION",
    "TREE_SPECIES_NOT_ASSERTED",
    "SOURCE_IMAGE_CONTROLS_VIDEO",
    "PRELIMINARY_REFERENCE_NOT_FINAL_IDENTITY",
}


class VeoProductionManifestError(ValueError):
    pass


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise VeoProductionManifestError(f"{label} must be an object.")
    return value


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VeoProductionManifestError(f"Cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise VeoProductionManifestError(f"{path} must contain a JSON object.")
    return value


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_policy(policy: Mapping[str, Any]) -> None:
    if policy.get("episode_id") != EPISODE_ID:
        raise VeoProductionManifestError("Policy episode changed.")
    if policy.get("policy_id") != POLICY_ID:
        raise VeoProductionManifestError("Policy id changed.")
    if policy.get("status") != "HUMAN_DIRECTIVES_ACTIVE":
        raise VeoProductionManifestError("Policy is not active.")
    if policy.get("master_visual_approval") is not False:
        raise VeoProductionManifestError("Master visual approval must remain false.")
    rules = policy.get("rules")
    if not isinstance(rules, list):
        raise VeoProductionManifestError("Policy rules must be a list.")
    by_id = {
        item.get("rule_id"): item
        for item in rules
        if isinstance(item, Mapping) and isinstance(item.get("rule_id"), str)
    }
    if set(by_id) != REQUIRED_POLICY_RULES:
        raise VeoProductionManifestError("Policy rule set changed.")

    modesty = _mapping(by_id["NO_TABARRUJ_FOR_WOMEN"], "modesty rule")
    if modesty.get("severity") != "BLOCKING":
        raise VeoProductionManifestError("No-tabarruj rule must be blocking.")

    hair = _mapping(by_id["WOMEN_HAIR_MUST_REMAIN_COVERED"], "hair rule")
    if hair.get("severity") != "BLOCKING":
        raise VeoProductionManifestError("Hair rule must be blocking.")

    exposure = _mapping(
        by_id["WOMEN_LIMITED_EXPOSURE_NECESSITY_ONLY"],
        "women exposure rule",
    )
    allowed = exposure.get("allowed_only_when_necessary")
    if not isinstance(allowed, list):
        raise VeoProductionManifestError("Women exposure allowance missing.")
    required_allowances = {"الكفان", "القدمان", "جزء محدود غير مكتمل من ملامح الوجه"}
    if set(allowed) != required_allowances:
        raise VeoProductionManifestError("Women exposure allowances changed.")
    forbidden = exposure.get("forbidden")
    if not isinstance(forbidden, list) or "الشعر" not in forbidden:
        raise VeoProductionManifestError("Hair must remain forbidden.")
    if "الوجه كاملًا بملامحه الواضحة" not in forbidden:
        raise VeoProductionManifestError("Complete female face must remain forbidden.")

    face = _mapping(
        by_id["NO_COMPLETE_IDENTIFIABLE_FACE_FOR_ANY_CHARACTER"],
        "face rule",
    )
    if face.get("severity") != "BLOCKING":
        raise VeoProductionManifestError("Complete-face prohibition must be blocking.")
    if "وجه أمامي كامل" not in (face.get("rejection") or []):
        raise VeoProductionManifestError("Full frontal face rejection missing.")


def validate_evidence(evidence: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    if evidence.get("evidence_id") != EVIDENCE_ID:
        raise VeoProductionManifestError("Evidence id changed.")
    if evidence.get("resulting_policy_id") != policy.get("policy_id"):
        raise VeoProductionManifestError("Evidence binds another policy.")
    phrase = evidence.get("exact_human_direction_ar")
    phrase_hash = evidence.get("exact_human_direction_sha256")
    if not isinstance(phrase, str) or not isinstance(phrase_hash, str):
        raise VeoProductionManifestError("Exact human direction missing.")
    if hashlib.sha256(phrase.encode("utf-8")).hexdigest() != phrase_hash:
        raise VeoProductionManifestError("Human direction hash mismatch.")


def validate_binding(
    binding: Mapping[str, Any],
    policy: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    if binding.get("binding_id") != BINDING_ID:
        raise VeoProductionManifestError("Binding id changed.")
    if binding.get("policy_id") != policy.get("policy_id"):
        raise VeoProductionManifestError("Binding points to another policy.")
    if binding.get("human_direction_evidence_id") != evidence.get("evidence_id"):
        raise VeoProductionManifestError("Binding points to another evidence record.")
    if binding.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise VeoProductionManifestError("Storyboard fingerprint changed.")
    if binding.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise VeoProductionManifestError("Script fingerprint changed.")
    if binding.get("automatic_paid_execution") != "BLOCKED":
        raise VeoProductionManifestError("Automatic paid execution must remain blocked.")
    if binding.get("full_episode_generation") != "NOT_YET_AUTHORISED":
        raise VeoProductionManifestError("Full episode generation opened unexpectedly.")


def validate_manifest(
    manifest: Mapping[str, Any],
    policy: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    if manifest.get("manifest_id") != MANIFEST_ID:
        raise VeoProductionManifestError("Manifest id changed.")
    if manifest.get("episode_id") != EPISODE_ID:
        raise VeoProductionManifestError("Manifest episode changed.")
    if manifest.get("storyboard_fingerprint") != STORYBOARD_FINGERPRINT:
        raise VeoProductionManifestError("Manifest storyboard fingerprint changed.")
    if manifest.get("script_fingerprint") != SCRIPT_FINGERPRINT:
        raise VeoProductionManifestError("Manifest script fingerprint changed.")
    if manifest.get("visual_safety_policy_id") != policy.get("policy_id"):
        raise VeoProductionManifestError("Manifest binds another policy.")
    if manifest.get("visual_safety_policy_binding_id") != binding.get("binding_id"):
        raise VeoProductionManifestError("Manifest binds another policy binding.")

    model = _mapping(manifest.get("primary_video_model"), "primary video model")
    if model.get("model") != MODEL:
        raise VeoProductionManifestError("Primary Veo model changed.")
    if model.get("provider") != "RUNWARE":
        raise VeoProductionManifestError("Provider changed.")
    if model.get("generate_audio") is not False:
        raise VeoProductionManifestError("Audio generation must remain off.")
    if model.get("number_results_per_attempt") != 1:
        raise VeoProductionManifestError("Result count must remain one.")

    execution = _mapping(manifest.get("execution_policy"), "execution policy")
    if execution.get("automatic_paid_execution") != "BLOCKED":
        raise VeoProductionManifestError("Automatic paid execution opened.")
    if execution.get("full_episode_bulk_generation") != "BLOCKED_UNTIL_BATCH_GATE":
        raise VeoProductionManifestError("Bulk generation opened.")

    shots = manifest.get("shots")
    if not isinstance(shots, list) or len(shots) != 70:
        raise VeoProductionManifestError("Manifest must contain seventy shots.")
    ids = [shot.get("shot_id") for shot in shots if isinstance(shot, Mapping)]
    if len(ids) != 70 or len(set(ids)) != 70:
        raise VeoProductionManifestError("Shot ids must be seventy unique values.")

    if sum(int(shot.get("editorial_duration_seconds", 0)) for shot in shots) != 1320:
        raise VeoProductionManifestError("Editorial duration must remain 1320 seconds.")

    counts: dict[str, int] = {}
    for raw in shots:
        shot = _mapping(raw, "shot")
        mode = shot.get("primary_production_mode")
        counts[str(mode)] = counts.get(str(mode), 0) + 1
        if shot.get("visual_safety_policy_id") != POLICY_ID:
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} does not bind policy v2."
            )
        if shot.get("face_policy") != "NO_COMPLETE_IDENTIFIABLE_FACE_FOR_ANY_CHARACTER":
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} lost the face policy."
            )
        if shot.get("provider_execution") != (
            "MANUAL_USER_OPERATED_ONLY_AFTER_SHOT_PACKAGE_REVIEW"
        ):
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} opened unreviewed execution."
            )
        units = shot.get("recommended_veo_generation_units_seconds")
        if not isinstance(units, list):
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} has invalid generation units."
            )
        if any(unit not in ALLOWED_DURATIONS for unit in units):
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} uses an unsupported Veo duration."
            )
        if mode == "GRAPHICS" and units:
            raise VeoProductionManifestError(
                f"{shot.get('shot_id')} graphics shot must not invoke Veo."
            )
        if mode == "IMAGE_TO_VIDEO":
            if shot.get("source_image_requirement") != "REQUIRED":
                raise VeoProductionManifestError(
                    f"{shot.get('shot_id')} image-to-video source is not required."
                )
            generated = sum(int(unit) for unit in units)
            held = int(shot.get("editorial_hold_seconds", 0))
            if generated + held != int(shot.get("editorial_duration_seconds", 0)):
                raise VeoProductionManifestError(
                    f"{shot.get('shot_id')} generation plan does not fill duration."
                )
        if mode == "TEXT_TO_VIDEO":
            if shot.get("source_image_requirement") != "NOT_REQUIRED":
                raise VeoProductionManifestError(
                    f"{shot.get('shot_id')} text-to-video source rule changed."
                )
            generated = sum(int(unit) for unit in units)
            held = int(shot.get("editorial_hold_seconds", 0))
            if generated + held != int(shot.get("editorial_duration_seconds", 0)):
                raise VeoProductionManifestError(
                    f"{shot.get('shot_id')} generation plan does not fill duration."
                )

    if counts != EXPECTED_COUNTS:
        raise VeoProductionManifestError(
            f"Production-mode counts changed: {counts!r}"
        )
    if manifest.get("classification_counts") != EXPECTED_COUNTS:
        raise VeoProductionManifestError("Recorded classification counts changed.")
    if manifest.get("next_stage") != "VEO_SHOT_PACKAGE_AUTHORING_V1":
        raise VeoProductionManifestError("Next stage changed.")



def validate_manifest_binding(
    manifest_binding: Mapping[str, Any],
    manifest: Mapping[str, Any],
    policy_binding: Mapping[str, Any],
) -> None:
    if manifest_binding.get("binding_id") != MANIFEST_BINDING_ID:
        raise VeoProductionManifestError("Manifest binding id changed.")
    if manifest_binding.get("manifest_id") != manifest.get("manifest_id"):
        raise VeoProductionManifestError("Manifest binding points to another manifest.")
    if manifest_binding.get("visual_safety_policy_binding_id") != policy_binding.get(
        "binding_id"
    ):
        raise VeoProductionManifestError(
            "Manifest binding points to another visual safety binding."
        )
    if manifest_binding.get("primary_video_model") != MODEL:
        raise VeoProductionManifestError("Manifest binding model changed.")
    if manifest_binding.get("shot_count") != 70:
        raise VeoProductionManifestError("Manifest binding shot count changed.")
    if manifest_binding.get("automatic_paid_execution") != "BLOCKED":
        raise VeoProductionManifestError(
            "Manifest binding opened automatic paid execution."
        )
    if manifest_binding.get("full_episode_bulk_generation") != (
        "BLOCKED_UNTIL_BATCH_GATE"
    ):
        raise VeoProductionManifestError(
            "Manifest binding opened full-episode bulk generation."
        )
    if manifest_binding.get("next_stage") != "VEO_SHOT_PACKAGE_AUTHORING_V1":
        raise VeoProductionManifestError("Manifest binding next stage changed.")


def validate_repository(repo_root: Path) -> dict[str, Any]:
    episode = repo_root / "projects" / "episode-001-adam"
    policy = read_json(episode / "cinematic" / "visual-safety-policy-v2.json")
    evidence = read_json(episode / "evidence" / "visual-safety-human-direction-v2.json")
    binding = read_json(episode / "contracts" / "visual-safety-policy-binding-v2.json")
    manifest = read_json(episode / "cinematic" / "veo-production-manifest-v1.json")
    manifest_binding = read_json(
        episode / "contracts" / "veo-production-manifest-binding-v1.json"
    )
    validate_policy(policy)
    validate_evidence(evidence, policy)
    validate_binding(binding, policy, evidence)
    validate_manifest(manifest, policy, binding)
    validate_manifest_binding(manifest_binding, manifest, binding)
    return {
        "status": "PASS_ADAM_VEO_PRODUCTION_MANIFEST_V1",
        "policy_id": policy["policy_id"],
        "evidence_id": evidence["evidence_id"],
        "binding_id": binding["binding_id"],
        "manifest_id": manifest["manifest_id"],
        "manifest_binding_id": manifest_binding["binding_id"],
        "primary_video_model": manifest["primary_video_model"]["model"],
        "shot_count": manifest["shot_count"],
        "editorial_duration_seconds": manifest["editorial_duration_seconds"],
        "classification_counts": manifest["classification_counts"],
        "next_stage": manifest["next_stage"],
        "automatic_paid_execution": manifest["execution_policy"][
            "automatic_paid_execution"
        ],
        "full_episode_bulk_generation": manifest["execution_policy"][
            "full_episode_bulk_generation"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_repository(args.repo_root.resolve())
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
    print("STATUS=" + result["status"])
    print("POLICY_ID=" + result["policy_id"])
    print("EVIDENCE_ID=" + result["evidence_id"])
    print("BINDING_ID=" + result["binding_id"])
    print("MANIFEST_ID=" + result["manifest_id"])
    print("MANIFEST_BINDING_ID=" + result["manifest_binding_id"])
    print("PRIMARY_VIDEO_MODEL=" + result["primary_video_model"])
    print("SHOT_COUNT=" + str(result["shot_count"]))
    print("EDITORIAL_DURATION_SECONDS=" + str(result["editorial_duration_seconds"]))
    print("NEXT_STAGE=" + result["next_stage"])
    print("AUTOMATIC_PAID_EXECUTION=" + result["automatic_paid_execution"])
    print("FULL_EPISODE_BULK_GENERATION=" + result["full_episode_bulk_generation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
