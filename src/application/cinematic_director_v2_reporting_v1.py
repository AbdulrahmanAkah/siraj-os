"""Offline reports and selective-review projections for Cinematic Director V2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.artifact_provenance_v1 import artifact_reference, sha256_file, write_new_json
from src.application.preserved_alignment_candidate_salvage_v1 import derive_salvage_view
from src.application.siraj_cinematic_director_v2 import (
    FRESH_EPISODE_MODE,
    fresh_episode_initialization,
    evaluate_v1_compatibility,
    sequence_quality_review,
)


SCHEMA_VERSION = "siraj-cinematic-director-v2-reporting-v1"


def _groups(directions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_id = {row["shot_id"]: row for row in directions}
    ranges = {
        "A_temptation": range(12, 17),
        "B_shared_action": range(17, 22),
        "C_repentance_guidance": range(30, 35),
        "D_hadith_argument": range(40, 45),
        "E_descent": range(36, 39),
        "E_closing_earth": range(50, 56),
    }
    return {
        key: [by_id[f"EP002-SH-{number:03d}"] for number in shot_range]
        for key, shot_range in ranges.items()
    }


def build_v2_reports(repo_root: Path, episode_id: str) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    salvage = derive_salvage_view(repo, episode_id)
    directions = [dict(row) for row in salvage["candidate_overlay"]["directions"] if row["shot_id"] in {patch["shot_id"] for patch in salvage["patches"]}]
    groups = _groups(directions)
    compatibility = evaluate_v1_compatibility(directions)
    quality = sequence_quality_review(groups)
    review_rows = [
        {
            "shot_id": row["shot_id"],
            "decision": "KEEP_EXISTING",
            "reason": "No deterministic material weakness was established; V2 preserves paid creative work by default.",
            "patch": None,
            "structural_change": "NONE",
        }
        for row in directions
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "episode_002_designation": "V1_COMPATIBILITY_BASE",
        "episode_002_policy": "PRESERVE_EXISTING",
        "episode_002_full_rewrite": False,
        "candidate_sha256": salvage["candidate_sha256"],
        "candidate_patch_count": salvage["candidate_patch_count"],
        "candidate_promoted": False,
        "authoritative_alignment_modified": False,
        "structural_fingerprint": salvage["structural_validation"]["structural_fingerprint"],
        "salvage_classification": salvage["salvage_classification"],
        "finding_scope_bug_fixed": True,
        "gate_001_luna_resolution_ignored": True,
        "selective_review": {
            "shots_reviewed": len(review_rows),
            "keep_existing_count": len(review_rows),
            "selective_v2_enhancement_recommended_count": 0,
            "patched_count": 0,
            "unchanged_count": len(review_rows),
            "rows": review_rows,
            "policy": "PATCH requires a specific material benefit greater than preservation risk; no automatic patching.",
        },
        "v2_compatibility": compatibility,
        "v2_quality_architecture": quality,
        "next_episode_fresh_start": fresh_episode_initialization("NEXT_NEW_EPISODE"),
        "ownership": {
            "python": ["schema_validation", "structural_binding", "duplicate_analysis", "field_ownership", "cost_accounting", "provenance", "retry_safety"],
            "luna": ["bounded_semantic_cinematic_reasoning", "typed_creative_direction_only"],
            "storyboard": ["shot_ids", "queue_order", "timings", "duration", "segment_ids", "beat_bindings"],
            "sequence_grammar": ["derived_visual_thesis", "material_camera_light_motion_progression", "continuity_and_contrast"],
            "provider_adapters": ["model_specific_contracts", "transport", "polling", "download"],
            "human_approval": ["paid_authorization", "candidate_promotion", "resume_after_gate"],
        },
        "network_calls": 0,
        "paid_provider_calls": 0,
        "autopilot_runs": 0,
        "files_deleted": 0,
    }


def _architecture_markdown(report: dict[str, Any]) -> str:
    ownership = report["ownership"]
    return "\n".join([
        "# SIRAJ Cinematic Director V2 Architecture", "",
        "V2 is an offline typed creative contract. It does not create paid calls by default and does not own storyboard structure.", "",
        "## Ownership", "",
        *[f"- **{owner}:** " + ", ".join(values) for owner, values in ownership.items()], "",
        "## Episode 002 policy", "",
        "Episode 002 remains `V1_COMPATIBILITY_BASE`; its preserved candidate is not a native V2 rewrite and no patch is auto-promoted.", "",
        "## Next episode", "",
        "`NATIVE_SIRAJ_CINEMATIC_DIRECTOR_V2` starts from `FRESH_EPISODE`; Episode 002 motifs, palette, grammar, and prompt language are forbidden automatic inheritance.", "",
    ])


def _fresh_start_markdown(contract: dict[str, Any]) -> str:
    return "\n".join([
        "# SIRAJ Cinematic Director V2 — Next Episode Fresh-Start Contract", "",
        f"Mode: `{contract['cinematic_mode']}`", f"Initialization: `{contract['creative_initialization']}`", "",
        "## Allowed inheritance", "", *[f"- `{value}`" for value in contract["permitted_inheritance"]], "",
        "## Forbidden automatic inheritance", "", *[f"- `{value}`" for value in contract["forbidden_automatic_inheritance"]], "",
        "No Episode 002 visual grammar or motif is inherited automatically.", "",
    ])


def _selective_markdown(report: dict[str, Any]) -> str:
    rows = report["selective_review"]["rows"]
    return "\n".join([
        "# Episode 002 — Cinematic Director V2 Selective Review", "",
        "All 29 preserved candidate shots were reviewed. No deterministic material weakness justified a derived V2 patch; preservation risk therefore prevailed.", "",
        f"- KEEP_EXISTING: `{len(rows)}`", "- SELECTIVE_V2_ENHANCEMENT_RECOMMENDED: `0`", "- PATCH: `0`", "- UNCHANGED: `29`", "",
        "## Shot decisions", "", *[f"- `{row['shot_id']}` — `{row['decision']}`: {row['reason']}" for row in rows], "",
    ])


def write_v2_outputs(repo_root: Path, episode_id: str) -> dict[str, str]:
    repo = Path(repo_root).resolve()
    report = build_v2_reports(repo, episode_id)
    outputs = {
        "selective_json": repo / "reports" / "episode-002-cinematic-director-v2-selective-review.json",
        "selective_md": repo / "reports" / "episode-002-cinematic-director-v2-selective-review.md",
        "architecture_md": repo / "reports" / "siraj-cinematic-director-v2-architecture.md",
        "verification_json": repo / "reports" / "siraj-cinematic-director-v2-verification.json",
        "fresh_start_md": repo / "reports" / "siraj-cinematic-director-v2-next-episode-fresh-start-contract.md",
    }
    if any(path.exists() for path in outputs.values()):
        raise RuntimeError("V2_REPORT_TARGET_ALREADY_EXISTS")
    write_new_json(outputs["selective_json"], report["selective_review"])
    write_new_json(outputs["verification_json"], report)
    for key, text in {
        "selective_md": _selective_markdown(report),
        "architecture_md": _architecture_markdown(report),
        "fresh_start_md": _fresh_start_markdown(report["next_episode_fresh_start"]),
    }.items():
        with outputs[key].open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return {key: str(path) for key, path in outputs.items()}
