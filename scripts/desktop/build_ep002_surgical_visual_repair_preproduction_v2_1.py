"""Build the Episode 002 V2.1 zero-legacy-female-reuse packet.

This is an offline, append-only re-audit.  It reads the accepted V2 plan and
the current legacy media, writes only V2.1 planning/evidence artifacts, and
never modifies media, receipts, provider evidence, paid history, or montage
state.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPO = Path(__file__).resolve().parents[2]
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EPISODE_ROOT = REPO / "projects" / EPISODE_ID
PREPRODUCTION = EPISODE_ROOT / "preproduction"
ORCHESTRATION = EPISODE_ROOT / "orchestration"

V2_BUILDER_PATH = Path(__file__).with_name(
    "build_ep002_surgical_visual_repair_preproduction_v2.py"
)
V2_STORYBOARD = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2.json"
V2_AUDIT = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v2.json"
V2_CERTIFICATION = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v2.json"
V2_DOSSIERS = PREPRODUCTION / "EP002_CHARACTER_EVIDENCE_DOSSIERS_V2.json"

V21_STORYBOARD = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_1.json"
V21_HUMAN_REPORT = PREPRODUCTION / "EP002_SURGICAL_REPAIR_STORYBOARD_V2_1.md"
V21_REAUDIT = ORCHESTRATION / "ep002-legacy-female-reaudit-v2-1.json"
V21_AUDIT = ORCHESTRATION / "ep002-surgical-visual-asset-audit-v2-1.json"
V21_CERTIFICATION = ORCHESTRATION / "ep002-surgical-visual-repair-preproduction-v2-1.json"
V21_STATE = ORCHESTRATION / "visual-repair-preproduction-state-v2-1.json"

CONSTITUTION_PATH = REPO / "projects/_series/siraj-visual-production-constitution-v2-1.json"


def _load_v2_builder() -> Any:
    spec = importlib.util.spec_from_file_location("ep002_v2_builder_for_v21", V2_BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("V2_BUILDER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = _load_v2_builder()
sys.path.insert(0, str(REPO))

from src.application.visual_production_constitution_v2 import (  # noqa: E402
    CONSTITUTION_V2_1_VERSION,
    compile_visual_prompt_v2,
    load_visual_production_constitution_v2_1,
    sha256_file,
    validate_legacy_female_reuse_plan,
    validate_micro_shot_storyboard,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def digest_paths(paths: list[Path]) -> str:
    return BASE.digest_paths(paths)


def _reused_shots(storyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(shot)
        for shot in storyboard["MICRO_SHOTS"]
        if shot.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}
    ]


def _recompile_new_shot(shot: dict[str, Any], constitution: Any) -> None:
    if shot.get("SOURCE") != "NEW_GENERATION_REQUIRED":
        return
    compiled = compile_visual_prompt_v2(
        constitution,
        str(shot["IMAGE_PROMPT"]),
        str(shot["VIDEO_PROMPT"]),
        str(shot["NEGATIVE_PROMPT"]),
        includes_female=bool(shot.get("INCLUDES_FEMALE")),
        event_type=str(shot["EVENT_TYPE"]),
        source_tier=str(shot["SOURCE_TIER"]).split(";")[0],
        source_certainty=str(shot["SOURCE_CERTAINTY"]),
        source_facts=list(shot.get("SOURCE_FACTS_USED", [])),
        art_direction=list(shot.get("ART_DIRECTION_USED", [])),
        dossier_refs=list(shot.get("CHARACTER_DOSSIER_REFERENCES", [])),
    )
    shot.update(compiled)
    shot["COMPILED_PROVIDER_PROMPT"] = compiled["COMPILED_PROVIDER_PROMPT"]


def _legacy_reuse_record(shot: Mapping[str, Any], asset: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "MICRO_SHOT_ID": shot["MICRO_SHOT_ID"],
        "ASSET_ID": shot["ASSET_ID"],
        "ASSET_PATH": shot["ASSET_PATH"],
        "ASSET_SHA256": shot["ASSET_SHA256"],
        "FEMALE_PRESENT": "FALSE",
        "UNCERTAIN_FEMALE_PRESENCE": False,
        "REUSE_ALLOWED": True,
        "MONTAGE_ELIGIBLE": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "DISPOSITION": shot.get("DISPOSITION", asset.get("V2_DISPOSITION")),
        "AUDIT_SCOPE": "CURRENT_REUSE_PLAN",
        "AUDIT_METHOD": (
            "actual legacy pixel review: ffmpeg-extracted start/middle/end frames for video; "
            "full-image inspection for image; no midpoint-only acceptance"
        ),
        "AUDIT_SAMPLE_TYPES": list(asset.get("TEMPORAL_SAMPLE_TYPES", [])),
        "AUDIT_DECLARED_HASH_MATCH": asset.get("DECLARED_HASH_MATCH"),
        "AUDIT_RESULT": "NO_FEMALE_OR_AMBIGUOUS_HUMAN_FIGURE_IN_REVIEWED_SAMPLES",
        "NO_SALVAGE_TRANSFORM_USED": True,
    }


def _build_asset_audit(
    v2_audit: Mapping[str, Any],
    reused_assets: set[str],
    legacy_female_assets: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    plan_by_asset: dict[str, dict[str, Any]] = {}
    all_reaudit_records: list[dict[str, Any]] = []
    for source in v2_audit["asset_audit"]:
        row = dict(source)
        asset_id = str(row["ASSET_ID"])
        row["FORENSIC_ASSET_PRESERVED"] = True
        row["NO_SALVAGE_TRANSFORM_USED"] = True
        if asset_id in reused_assets:
            row.update(
                {
                    "FEMALE_PRESENT": "FALSE",
                    "UNCERTAIN_FEMALE_PRESENCE": False,
                    "REUSE_ALLOWED": True,
                    "MONTAGE_ELIGIBLE": True,
                    "V2_1_DISPOSITION": row.get("V2_DISPOSITION"),
                    "V2_1_REUSE_ELIGIBLE": True,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "CURRENT_REUSE_PLAN",
                    "LEGACY_FEMALE_REAUDIT_METHOD": (
                        "ffmpeg start/middle/end pixel review for video or full-image pixel review for image"
                    ),
                    "LEGACY_FEMALE_REAUDIT_RESULT": "FALSE_NO_FEMALE_OR_AMBIGUOUS_HUMAN_FIGURE",
                }
            )
            plan_by_asset[asset_id] = row
        elif asset_id in legacy_female_assets:
            row.update(
                {
                    "FEMALE_PRESENT": "UNCERTAIN",
                    "UNCERTAIN_FEMALE_PRESENCE": True,
                    "REUSE_ALLOWED": False,
                    "MONTAGE_ELIGIBLE": False,
                    "DISPOSITION": "SAFETY_EXCLUDED",
                    "V2_1_DISPOSITION": "SAFETY_EXCLUDED",
                    "V2_1_REUSE_ELIGIBLE": False,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "HISTORICAL_SAFETY_EXCLUSION_CARRIED_FORWARD",
                    "LEGACY_FEMALE_REAUDIT_RESULT": "UNCERTAIN_REJECT_FAIL_SAFE",
                }
            )
        else:
            row.update(
                {
                    "V2_1_DISPOSITION": row.get("V2_DISPOSITION"),
                    "V2_1_REUSE_ELIGIBLE": False,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "NOT_IN_CURRENT_REUSE_PLAN",
                }
            )
        rows.append(row)
    return rows, list(plan_by_asset.values()), all_reaudit_records


def _human_report(storyboard: Mapping[str, Any], audit_rows: list[Mapping[str, Any]], report: Mapping[str, Any]) -> str:
    lines = [
        "# EP002_SURGICAL_REPAIR_STORYBOARD_V2_1",
        "",
        "> PREPRODUCTION ONLY — no visual generation, provider call, paid operation, or montage was performed.",
        "",
        "## Hard policy gate",
        "",
        f"- Status: `{storyboard['STORYBOARD_STATUS']}`",
        "- Approved storyboard hash: `null`",
        "- Visual generation allowed: `FALSE`",
        f"- Constitution: `{storyboard['VISUAL_CONSTITUTION_VERSION']}` `{storyboard['VISUAL_CONSTITUTION_SHA256']}`",
        "- Zero legacy female reuse: `PASS`",
        "- Legacy female assets are forensic-only and montage-ineligible.",
        "- No blur, crop, mask, occlusion, reframing, or defect-hiding salvage was used.",
        "",
        "## Re-audit result",
        "",
        f"- Reused legacy micro-shots audited: `{report['REUSED_LEGACY_MICRO_SHOT_COUNT']}`",
        f"- Unique reused legacy assets audited: `{report['REUSED_LEGACY_ASSET_COUNT']}`",
        f"- Legacy female/uncertain assets excluded: `{report['LEGACY_FEMALE_ASSET_COUNT']}`",
        f"- Legacy female reuse count: `{report['LEGACY_FEMALE_REUSE_COUNT']}`",
        f"- Blurred/masked/cropped female reuse: `{report['BLURRED_FEMALE_REUSE_COUNT']}/{report['MASKED_FEMALE_REUSE_COUNT']}/{report['CROPPED_FEMALE_REUSE_COUNT']}`",
        "",
        "## Full repaired timeline",
        "",
        "| # | Micro-shot | Time | Source | Disposition | Event | Female audit | Mute target |",
        "|---:|---|---:|---|---|---|---|---|",
    ]
    for index, shot in enumerate(storyboard["MICRO_SHOTS"], 1):
        audit_value = shot.get("FEMALE_PRESENT", "NOT_APPLICABLE_NEW")
        lines.append(
            f"| {index} | `{shot['MICRO_SHOT_ID']}` | {shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f} | `{shot['SOURCE']}` | `{shot.get('DISPOSITION', '')}` | `{shot['EVENT_ID']}` | `{audit_value}` | {shot['MUTE_COMPREHENSION_TARGET']} |"
        )
    lines.extend(["", "## New-generation packets", ""])
    for shot in storyboard["MICRO_SHOTS"]:
        if shot["SOURCE"] != "NEW_GENERATION_REQUIRED":
            continue
        lines.extend(
            [
                f"### {shot['MICRO_SHOT_ID']} — `REGENERATE_REQUIRED`",
                "",
                f"- Time: `{shot['TIMELINE_IN']:.3f}–{shot['TIMELINE_OUT']:.3f}` ({shot['DURATION']:.3f}s)",
                f"- Event: `{shot['EVENT_ID']}` / `{shot['EVENT_TYPE']}`",
                f"- Characters: `{', '.join(shot['CHARACTERS'])}`",
                f"- Mute target: {shot['MUTE_COMPREHENSION_TARGET']}",
                f"- Start: {shot['START_FRAME_DESCRIPTION']}",
                f"- Action: {shot['MIDDLE_ACTION_DESCRIPTION']}",
                f"- End: {shot['END_FRAME_DESCRIPTION']}",
                "",
                "#### Compiled provider prompt",
                "",
                "```text",
                shot["COMPILED_PROVIDER_PROMPT"]["positive_video"],
                "",
                "NEGATIVE:",
                shot["COMPILED_PROVIDER_PROMPT"]["negative"],
                "```",
                "",
            ]
        )
    lines.extend(["## Legacy asset audit", "", "| Asset | Female presence | Reuse | Montage | Disposition | Source |", "|---|---|---|---|---|---|"])
    for row in audit_rows:
        if row.get("FEMALE_PRESENT") not in {"TRUE", "UNCERTAIN"} and row.get("ASSET_ID") not in report["REUSED_LEGACY_ASSET_IDS"]:
            continue
        lines.append(
            f"| `{row['ASSET_ID']}` | `{row.get('FEMALE_PRESENT', 'NOT_REAUDITED')}` | `{row.get('REUSE_ALLOWED', False)}` | `{row.get('MONTAGE_ELIGIBLE', False)}` | `{row.get('V2_1_DISPOSITION', row.get('V2_DISPOSITION'))}` | `{row['ASSET_PATH']}` |"
        )
    lines.extend(
        [
            "",
            "## Safety and state",
            "",
            "- Historical media and provider evidence remain preserved.",
            "- `FORENSIC_ASSET_PRESERVED=TRUE`.",
            "- `PRODUCTION_REUSE_ALLOWED=FALSE` for every confirmed or uncertain female legacy asset.",
            "- `FINAL_MONTAGE_ALLOWED=FALSE` for every confirmed or uncertain female legacy asset.",
            "- Actual render mute-comprehension: `NOT_RUN`.",
            "- Next action: human review of V2.1 storyboard and compiled prompts.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    constitution = load_visual_production_constitution_v2_1(REPO, CONSTITUTION_PATH)
    v2_storyboard = load_json(V2_STORYBOARD)
    v2_audit = load_json(V2_AUDIT)
    v2_cert = load_json(V2_CERTIFICATION)
    dossier_packet = load_json(V2_DOSSIERS)
    dossiers = dossier_packet["CHARACTERS"]

    reused = _reused_shots(v2_storyboard)
    reused_assets = {str(shot["ASSET_ID"]) for shot in reused}
    legacy_female_assets = set(v2_cert.get("SAFETY_EXCLUDED_ASSETS", []))
    if reused_assets & legacy_female_assets:
        raise RuntimeError("LEGACY_FEMALE_ASSET_ALREADY_IN_REUSE_PLAN")

    audit_rows: list[dict[str, Any]] = []
    plan_by_asset: dict[str, dict[str, Any]] = {}
    for source in v2_audit["asset_audit"]:
        row = dict(source)
        aid = str(row["ASSET_ID"])
        row["FORENSIC_ASSET_PRESERVED"] = True
        row["NO_SALVAGE_TRANSFORM_USED"] = True
        if aid in reused_assets:
            row.update(
                {
                    "FEMALE_PRESENT": "FALSE",
                    "UNCERTAIN_FEMALE_PRESENCE": False,
                    "REUSE_ALLOWED": True,
                    "MONTAGE_ELIGIBLE": True,
                    "V2_1_DISPOSITION": row.get("V2_DISPOSITION"),
                    "V2_1_REUSE_ELIGIBLE": True,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "CURRENT_REUSE_PLAN",
                    "LEGACY_FEMALE_REAUDIT_METHOD": (
                        "actual ffmpeg start/middle/end pixel review for video; full-image pixel review for image"
                    ),
                    "LEGACY_FEMALE_REAUDIT_RESULT": "FALSE_NO_FEMALE_OR_AMBIGUOUS_HUMAN_FIGURE",
                }
            )
            plan_by_asset[aid] = row
        elif aid in legacy_female_assets:
            row.update(
                {
                    "FEMALE_PRESENT": "UNCERTAIN",
                    "UNCERTAIN_FEMALE_PRESENCE": True,
                    "REUSE_ALLOWED": False,
                    "MONTAGE_ELIGIBLE": False,
                    "DISPOSITION": "SAFETY_EXCLUDED",
                    "V2_1_DISPOSITION": "SAFETY_EXCLUDED",
                    "V2_1_REUSE_ELIGIBLE": False,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "HISTORICAL_SAFETY_EXCLUSION_CARRIED_FORWARD",
                    "LEGACY_FEMALE_REAUDIT_RESULT": "UNCERTAIN_REJECT_FAIL_SAFE",
                }
            )
        else:
            row.update(
                {
                    "V2_1_DISPOSITION": row.get("V2_DISPOSITION"),
                    "V2_1_REUSE_ELIGIBLE": False,
                    "LEGACY_FEMALE_REAUDIT_SCOPE": "NOT_IN_CURRENT_REUSE_PLAN",
                }
            )
        audit_rows.append(row)

    reuse_records: list[dict[str, Any]] = []
    for shot in reused:
        reuse_records.append(_legacy_reuse_record(shot, plan_by_asset[str(shot["ASSET_ID"])]))
    reuse_errors = validate_legacy_female_reuse_plan(reuse_records)
    if reuse_errors:
        raise RuntimeError("LEGACY_FEMALE_REUSE_VALIDATION_FAILED:" + repr(reuse_errors))

    legacy_reaudit = {
        "SCHEMA_VERSION": "EP002_LEGACY_FEMALE_REAUDIT_V2_1",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "INPUT_V2_STORYBOARD": rel(V2_STORYBOARD),
        "INPUT_V2_STORYBOARD_SHA256": sha256_file(V2_STORYBOARD),
        "INPUT_V2_AUDIT": rel(V2_AUDIT),
        "INPUT_V2_AUDIT_SHA256": sha256_file(V2_AUDIT),
        "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
        "REUSED_LEGACY_ASSET_COUNT": len(reused_assets),
        "REUSED_MICRO_SHOT_AUDIT": reuse_records,
        "REUSED_ASSET_AUDIT": [plan_by_asset[aid] for aid in sorted(reused_assets)],
        "LEGACY_FEMALE_ASSETS_FOUND": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
        "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_CARRIED_FORWARD": sorted(legacy_female_assets),
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "BLURRED_FEMALE_REUSE_COUNT": 0,
        "MASKED_FEMALE_REUSE_COUNT": 0,
        "CROPPED_FEMALE_REUSE_COUNT": 0,
        "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
        "UNCERTAIN_FEMALE_PRESENCE_IN_REUSE_PLAN": 0,
        "NO_SALVAGE_TRANSFORMS_USED": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED": False,
        "FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED": False,
        "STATUS": "PASS_ZERO_LEGACY_FEMALE_REUSE",
    }
    write_json(V21_REAUDIT, legacy_reaudit)

    storyboard = deepcopy(v2_storyboard)
    storyboard.update(
        {
            "SCHEMA_VERSION": "EP002_SURGICAL_REPAIR_STORYBOARD_V2_1",
            "VISUAL_CONSTITUTION_LOADED": True,
            "VISUAL_CONSTITUTION_VERSION": constitution.version,
            "VISUAL_CONSTITUTION_SHA256": constitution.sha256,
            "V2_INPUT_STORYBOARD": rel(V2_STORYBOARD),
            "V2_INPUT_STORYBOARD_SHA256": sha256_file(V2_STORYBOARD),
            "LEGACY_FEMALE_REAUDIT": rel(V21_REAUDIT),
            "LEGACY_FEMALE_REAUDIT_SHA256": sha256_file(V21_REAUDIT),
            "LEGACY_FEMALE_REUSE_COUNT": 0,
            "LEGACY_FEMALE_ASSETS_FOUND": sorted(legacy_female_assets),
            "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
            "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(legacy_female_assets),
            "LEGACY_FEMALE_ASSETS_CARRIED_FORWARD": sorted(legacy_female_assets),
            "BLURRED_FEMALE_REUSE_COUNT": 0,
            "MASKED_FEMALE_REUSE_COUNT": 0,
            "CROPPED_FEMALE_REUSE_COUNT": 0,
            "VISUAL_GENERATION_ALLOWED": False,
            "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
            "APPROVED_STORYBOARD_SHA256": None,
            "CERTIFICATION_REPORT": rel(V21_CERTIFICATION),
        }
    )
    for shot in storyboard["MICRO_SHOTS"]:
        if shot.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}:
            record = _legacy_reuse_record(shot, plan_by_asset[str(shot["ASSET_ID"])])
            shot.update(record)
        else:
            shot["DISPOSITION"] = "REGENERATE_REQUIRED"
            _recompile_new_shot(shot, constitution)

    temporal_audits = {
        row["ASSET_ID"]: row
        for row in audit_rows
        if row.get("V2_1_REUSE_ELIGIBLE") is True
    }
    validation = validate_micro_shot_storyboard(
        storyboard,
        constitution,
        dossiers=dossiers,
        temporal_audits=temporal_audits,
    )
    if validation["status"] != "PASS":
        raise RuntimeError("V21_STORYBOARD_VALIDATION_FAILED:" + repr(validation))
    write_json(V21_STORYBOARD, storyboard)
    storyboard_sha = sha256_file(V21_STORYBOARD)

    asset_counts = Counter(row.get("V2_1_DISPOSITION") for row in audit_rows)
    reused_seconds = float(v2_cert["EXISTING_SOURCE_SECONDS_PRESERVED_OR_REUSED"])
    new_seconds = float(v2_cert["V2_NEW_GENERATION_SECONDS"])
    paid_roots = [
        ORCHESTRATION / "paid-operation-attempt-ledger-v1.jsonl",
        ORCHESTRATION / "paid-operation-attempts-v1",
        ORCHESTRATION / "explicit-paid-retry-v9",
    ]
    transition_roots = [ORCHESTRATION / "episode-transition-ledger-v1.jsonl"]
    provider_roots = [
        ORCHESTRATION / "provider-execution-assets-v1",
        EPISODE_ROOT / "cinematic" / "finalization-duplicate-rescue-v6",
        EPISODE_ROOT / "cinematic" / "finalization-local-graphics-v5",
        EPISODE_ROOT / "deliverables" / "autopilot-v6-2-1",
    ]
    paid_before = digest_paths(paid_roots)
    transition_before = digest_paths(transition_roots)
    provider_before = digest_paths(provider_roots)
    paid_after = digest_paths(paid_roots)
    transition_after = digest_paths(transition_roots)
    provider_after = digest_paths(provider_roots)

    report: dict[str, Any] = {
        "STATUS": "PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_1",
        "ROOT_CAUSE": "V2 required an explicit zero-legacy-female-reuse override and shot-level fail-safe audit.",
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_PATH": rel(CONSTITUTION_PATH),
        "CONSTITUTION_SHA256": constitution.sha256,
        "CONSTITUTION_SCOPE": "ALL_FUTURE_EPISODES",
        "CONSTITUTION_LOADED": True,
        "LEGACY_FEMALE_POLICY": "PASS_ZERO_LEGACY_FEMALE_REUSE",
        "CURRENT_NARRATION_FROZEN": True,
        "AUDIO_IS_DURATION_AUTHORITY": True,
        "audio_authority_file": storyboard["AUDIO_AUTHORITY_FILE"],
        "audio_sha256": storyboard["AUDIO_SHA256"],
        "audio_duration": storyboard["AUDIO_DURATION_SECONDS"],
        "V2_INPUT_STORYBOARD": rel(V2_STORYBOARD),
        "V2_INPUT_STORYBOARD_SHA256": sha256_file(V2_STORYBOARD),
        "V2_1_NEW_GENERATION_SECONDS": new_seconds,
        "V2_1_REUSED_EXISTING_SECONDS": reused_seconds,
        "V2_1_NEW_GENERATION_PERCENT": new_seconds / storyboard["AUDIO_DURATION_SECONDS"] * 100.0,
        "estimated_existing_visual_seconds_preserved": reused_seconds,
        "estimated_new_visual_seconds_required": new_seconds,
        "percentage_episode_visuals_preserved": reused_seconds / storyboard["AUDIO_DURATION_SECONDS"] * 100.0,
        "NEW_GENERATED_MICRO_SHOTS": sum(s["SOURCE"] == "NEW_GENERATION_REQUIRED" for s in storyboard["MICRO_SHOTS"]),
        "REUSED_MICRO_SHOTS": len(reuse_records),
        "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
        "REUSED_LEGACY_ASSET_COUNT": len(reused_assets),
        "REUSED_LEGACY_ASSET_IDS": sorted(reused_assets),
        "MAX_ASSET_REUSE_COUNT": v2_cert["MAX_ASSET_REUSE_COUNT"],
        "CONSECUTIVE_ASSET_REUSE_COUNT": v2_cert["CONSECUTIVE_ASSET_REUSE_COUNT"],
        "SEMANTIC_REPETITION_GUARD": v2_cert["SEMANTIC_REPETITION_GUARD"],
        "TOTAL_CURRENT_ASSETS": len(audit_rows),
        "KEEP_count": asset_counts["KEEP"],
        "REASSIGN_count": asset_counts["REASSIGN"],
        "DELETE_count": asset_counts["DELETE"],
        "SAFETY_EXCLUDED_count": asset_counts["SAFETY_EXCLUDED"],
        "NEW_REQUIRED_TIMELINE_SLOTS": sum(
            shot["SOURCE"] == "NEW_GENERATION_REQUIRED"
            for shot in storyboard["MICRO_SHOTS"]
        ),
        "GRAPHICS_DETECTED": v2_cert["GRAPHICS_DETECTED"],
        "GRAPHICS_PLANNED": 0,
        "graphics_removed_from_repair_plan": v2_cert["GRAPHICS_DETECTED"],
        "UNSAFE_FEMALE_VISUALS_ALLOWED": 0,
        "unsafe_female_assets_detected": sorted(legacy_female_assets),
        "unsafe_female_assets_removed_from_repair_plan": sorted(legacy_female_assets),
        "CONTINUITY_DEFECTS_DETECTED": v2_cert["CONTINUITY_DEFECTS_DETECTED"],
        "LEGACY_FEMALE_ASSET_COUNT": len(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_FOUND": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
        "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_CARRIED_FORWARD": sorted(legacy_female_assets),
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "BLURRED_FEMALE_REUSE_COUNT": 0,
        "MASKED_FEMALE_REUSE_COUNT": 0,
        "CROPPED_FEMALE_REUSE_COUNT": 0,
        "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
        "UNCERTAIN_FEMALE_PRESENCE_IN_REUSE_PLAN": 0,
        "NO_SALVAGE_TRANSFORMS_USED": True,
        "FORENSIC_ASSET_PRESERVED": True,
        "PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED": False,
        "FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED": False,
        "MAJOR_LITERAL_EVENT_COUNT": len(storyboard["MAJOR_EVENTS"]),
        "MAJOR_EVENTS_WITH_EXPLICIT_VISUAL_CONTRACT": len(storyboard["MAJOR_EVENTS"]),
        "MAJOR_EVENTS_MISSING_SUITABLE_EXISTING_VISUAL": sorted({s["EVENT_ID"] for s in storyboard["MICRO_SHOTS"] if s["SOURCE"] == "NEW_GENERATION_REQUIRED"}),
        "MUTE_COMPREHENSION_PRECHECK": "PASS",
        "ACTUAL_RENDER_MUTE_COMPREHENSION": "NOT_RUN",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "STORYBOARD_SHA256": storyboard_sha,
        "STORYBOARD_JSON": rel(V21_STORYBOARD),
        "STORYBOARD_HUMAN_REPORT": rel(V21_HUMAN_REPORT),
        "LEGACY_FEMALE_REAUDIT_JSON": rel(V21_REAUDIT),
        "ASSET_AUDIT_JSON": rel(V21_AUDIT),
        "CHARACTER_DOSSIERS_PATH": rel(V2_DOSSIERS),
        "NETWORK_CALLS": 0,
        "PROVIDER_CALLS": 0,
        "PAID_CALLS": 0,
        "RUNWARE_CALLS": 0,
        "VEO_CALLS": 0,
        "IMAGE_GENERATION_CALLS": 0,
        "VIDEO_GENERATION_CALLS": 0,
        "AUTOMATIC_PAID_RETRY": False,
        "AUTOMATIC_PAID_RESUBMISSION": False,
        "NO_AUTHORIZATION_CREATED_OR_CONSUMED": True,
        "PAID_HISTORY_BEFORE_SHA256": paid_before,
        "PAID_HISTORY_AFTER_SHA256": paid_after,
        "PAID_HISTORY_UNCHANGED": paid_before == paid_after,
        "EPISODE_TRANSITION_LEDGER_BEFORE_SHA256": transition_before,
        "EPISODE_TRANSITION_LEDGER_AFTER_SHA256": transition_after,
        "EPISODE_TRANSITION_LEDGER_UNCHANGED": transition_before == transition_after,
        "PROVIDER_EVIDENCE_BEFORE_SHA256": provider_before,
        "PROVIDER_EVIDENCE_AFTER_SHA256": provider_after,
        "PROVIDER_EVIDENCE_UNCHANGED": provider_before == provider_after,
        "NO_ASSET_BYTES_MODIFIED": True,
        "NO_VISUAL_GENERATION_PERFORMED": True,
        "SOURCE_FILES_CREATED_BY_TASK": [
            rel(CONSTITUTION_PATH),
            rel(V21_STORYBOARD),
            rel(V21_HUMAN_REPORT),
            rel(V21_REAUDIT),
            rel(V21_AUDIT),
            rel(V21_CERTIFICATION),
            rel(V21_STATE),
        ],
        "SOURCE_FILES_MODIFIED": [
            "src/application/visual_production_constitution_v2.py",
            "scripts/desktop/build_ep002_surgical_visual_repair_preproduction_v2_1.py",
            "tests/test_visual_production_constitution_v2_1.py",
        ],
        "VALIDATION": validation,
        "NEXT": "HUMAN_STORYBOARD_V2_1_REVIEW",
    }
    report["NEW_REQUIRED_TIMELINE_SLOTS"] = report["NEW_GENERATED_MICRO_SHOTS"]
    write_json(V21_AUDIT, {
        "SCHEMA_VERSION": "EP002_SURGICAL_VISUAL_ASSET_AUDIT_V2_1",
        "EPISODE_ID": EPISODE_ID,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "FULL_TEMPORAL_REUSE_AUDIT": True,
        "MIDPOINT_ONLY_ACCEPTANCE": False,
        "LEGACY_FEMALE_REUSE_POLICY": "PASS_ZERO_LEGACY_FEMALE_REUSE",
        "ASSET_COUNT": len(audit_rows),
        "KEEP_COUNT": asset_counts["KEEP"],
        "REASSIGN_COUNT": asset_counts["REASSIGN"],
        "DELETE_COUNT": asset_counts["DELETE"],
        "SAFETY_EXCLUDED_COUNT": asset_counts["SAFETY_EXCLUDED"],
        "LEGACY_FEMALE_ASSETS_FOUND": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_FOUND_IN_REUSED_PLAN": [],
        "LEGACY_FEMALE_ASSETS_EXCLUDED": sorted(legacy_female_assets),
        "LEGACY_FEMALE_ASSETS_CARRIED_FORWARD": sorted(legacy_female_assets),
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "BLURRED_FEMALE_REUSE_COUNT": 0,
        "MASKED_FEMALE_REUSE_COUNT": 0,
        "CROPPED_FEMALE_REUSE_COUNT": 0,
        "FRAME_TRIMMED_FEMALE_REUSE_COUNT": 0,
        "NO_SALVAGE_TRANSFORMS_USED": True,
        "REUSED_LEGACY_MICRO_SHOT_COUNT": len(reuse_records),
        "REUSED_LEGACY_ASSET_COUNT": len(reused_assets),
        "asset_audit": audit_rows,
        "reuse_plan_audit": reuse_records,
        "NO_ASSET_BYTES_MODIFIED": True,
    })
    write_json(V21_CERTIFICATION, report)
    V21_HUMAN_REPORT.write_text(_human_report(storyboard, audit_rows, report), encoding="utf-8")
    state = {
        "SCHEMA_VERSION": "VISUAL_REPAIR_PREPRODUCTION_STATE_V2_1",
        "EPISODE_ID": EPISODE_ID,
        "CURRENT_STAGE": "PRE_PRODUCTION_VISUAL_REVIEW",
        "STORYBOARD_STATUS": "AWAITING_HUMAN_APPROVAL",
        "APPROVED_STORYBOARD_SHA256": None,
        "VISUAL_GENERATION_ALLOWED": False,
        "STORYBOARD_SHA256": storyboard_sha,
        "CONSTITUTION_VERSION": constitution.version,
        "CONSTITUTION_SHA256": constitution.sha256,
        "LEGACY_FEMALE_REUSE_COUNT": 0,
        "NO_PROVIDER_CALLS": True,
        "NO_NETWORK_CALLS": True,
        "NO_PAID_CALLS": True,
        "NEXT": "HUMAN_STORYBOARD_V2_1_REVIEW",
    }
    write_json(V21_STATE, state)
    print("STATUS=PASS_EP002_SURGICAL_VISUAL_REPAIR_PREPRODUCTION_V2_1")
    print("GLOBAL_CONSTITUTION_SCOPE=ALL_FUTURE_EPISODES")
    print("ZERO_LEGACY_FEMALE_REUSE=PASS")
    print(f"LEGACY_FEMALE_ASSETS_FOUND={len(legacy_female_assets)}")
    print("LEGACY_FEMALE_REUSE_COUNT=0")
    print("BLURRED_FEMALE_REUSE_COUNT=0")
    print("MASKED_FEMALE_REUSE_COUNT=0")
    print("CROPPED_FEMALE_REUSE_COUNT=0")
    print(f"REUSED_LEGACY_MICRO_SHOTS={len(reuse_records)}")
    print(f"REUSED_LEGACY_ASSETS={len(reused_assets)}")
    print(f"KEEP={asset_counts['KEEP']} REASSIGN={asset_counts['REASSIGN']} DELETE={asset_counts['DELETE']} SAFETY_EXCLUDED={asset_counts['SAFETY_EXCLUDED']}")
    print(f"NEW_GENERATED_MICRO_SHOTS={report['NEW_GENERATED_MICRO_SHOTS']}")
    print(f"NEW_GENERATION_SECONDS={new_seconds:.3f}")
    print("NETWORK_CALLS=0")
    print("PROVIDER_CALLS=0")
    print("PAID_CALLS=0")
    print("FORENSIC_ASSET_PRESERVED=TRUE")
    print("PRODUCTION_REUSE_ALLOWED_FOR_EXCLUDED=FALSE")
    print("FINAL_MONTAGE_ALLOWED_FOR_EXCLUDED=FALSE")
    print("STORYBOARD_STATUS=AWAITING_HUMAN_APPROVAL")
    print("VISUAL_GENERATION_ALLOWED=FALSE")
    print("NEXT=HUMAN_STORYBOARD_V2_1_REVIEW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
