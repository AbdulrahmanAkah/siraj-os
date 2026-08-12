"""Generate the local Episode 002 Media Planner V2 proposal.

This script only writes reports/proposal artifacts.  It never writes the
authoritative preflight, ledger, storyboard, creative overlay or
authorization and never imports a provider transport.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file
from src.application.media_cost_authority_v2 import assess_cost, load_pricing_registry
from src.application.siraj_media_planner_v2 import build_media_planner_v2_proposal


REPO = Path(__file__).resolve().parents[1]
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
PLAN_REL = Path("projects") / EPISODE_ID / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
REGISTRY_REL = Path("projects/_series/siraj-media-pricing-registry-v2.json")
CURRENT_PREFLIGHT_REL = Path("projects") / EPISODE_ID / "orchestration" / "media-cost-preflight-v1.json"
LEDGER_REL = Path("projects") / EPISODE_ID / "orchestration" / "episode-transition-ledger-v1.jsonl"
PROPOSAL_REL = Path("reports/episode-002-media-planner-v2-proposal.json")
REVIEW_REL = Path("reports/episode-002-media-planner-v2-review.md")
STRUCTURAL_FINGERPRINT = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
OVERLAY_SHA256 = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
EPISODE_DURATION = 623.584


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _money(value: Any) -> str:
    return "UNKNOWN" if value is None else str(value)


def main() -> None:
    plan_path = REPO / PLAN_REL
    registry_path = REPO / REGISTRY_REL
    plan = _read(plan_path)
    items = plan.get("items")
    if not isinstance(items, list):
        raise RuntimeError("PROMPT_PLAN_ITEMS_REQUIRED")
    if plan.get("creative_overlay_sha256") != OVERLAY_SHA256:
        raise RuntimeError("PROMOTED_OVERLAY_HASH_MISMATCH")
    registry = load_pricing_registry(registry_path)
    # First build with a temporary empty cost view; units are needed as the
    # input to the cost authority and the authority must not alter planning.
    proposal = build_media_planner_v2_proposal(
        items,
        episode_id=EPISODE_ID,
        episode_duration_seconds=EPISODE_DURATION,
        structural_fingerprint=STRUCTURAL_FINGERPRINT,
        creative_overlay_sha256=OVERLAY_SHA256,
        pricing_assessment={},
    )
    pricing = assess_cost(
        [*proposal["video_units"], *proposal["non_video_units"]],
        registry,
    )
    proposal["pricing"] = pricing.as_dict()
    proposal["pricing"]["registry_path"] = str(REGISTRY_REL).replace("\\", "/")
    proposal["pricing"]["registry_file_sha256"] = sha256_file(registry_path)
    proposal["pricing"]["provider_execution_allowed"] = False if pricing.unpriced_requests else pricing.provider_execution_allowed
    breakdown: dict[str, dict[str, Any]] = {}
    for unit in [*proposal["video_units"], *proposal["non_video_units"]]:
        key = f"{unit.get('provider')}/{unit.get('model')}"
        row = breakdown.setdefault(
            key,
            {
                "provider": unit.get("provider"),
                "model": unit.get("model"),
                "media_kind": unit.get("media_kind"),
                "request_count": 0,
                "requested_seconds": 0.0,
                "timeline_seconds": 0.0,
            },
        )
        row["request_count"] += 1
        row["requested_seconds"] += float(unit.get("requested_seconds") or unit.get("provider_requested_seconds") or 0.0)
        row["timeline_seconds"] += float(unit.get("timeline_coverage_seconds") or unit.get("expected_usable_seconds") or 0.0)
    for row in breakdown.values():
        row["requested_seconds"] = round(row["requested_seconds"], 3)
        row["timeline_seconds"] = round(row["timeline_seconds"], 3)
    proposal["provider_model_breakdown"] = sorted(breakdown.values(), key=lambda row: f"{row['provider']}/{row['model']}")
    proposal["comparisons"] = {
        "old_plan": {
            "true_generated_video_seconds": 21.669,
            "true_generated_video_percent": 3.474913,
            "provider_requested_video_seconds": 112.0,
            "provider_video_requests": 14,
            "provider_requests": 51,
            "still_provider_requests": 37,
            "graphics_local_units": 4,
            "pricing_status": "UNKNOWN",
            "priced_requests": 0,
            "unpriced_requests": 51,
            "unused_provider_video_seconds": 90.331,
            "video_request_efficiency_percent": 19.347321,
            "slide_show_fatigue_risk": "HIGH",
            "status": "FORENSIC_INVALID_UNDER_NEW_POLICY",
        },
        "previous_optimization": {
            "true_generated_video_seconds": 70.519,
            "true_generated_video_percent": 11.308661,
            "status": "FORENSIC_INVALID_UNDER_NEW_POLICY",
        },
        "v2": {
            "true_generated_video_seconds": proposal["coverage"]["true_generated_video_timeline_seconds"],
            "true_generated_video_percent": proposal["coverage"]["true_generated_video_timeline_percent"],
            "status": "RANGE_VALID_PROPOSAL_ONLY",
        },
    }
    classification_counts: dict[str, int] = {}
    for row in proposal["shot_treatments"]:
        classification_counts[row["classification"]] = classification_counts.get(row["classification"], 0) + 1
    proposal["classification_counts"] = classification_counts
    durations = {
        row["shot_id"]: float(row["end_seconds"]) - float(row["start_seconds"])
        for row in proposal["shots"]
    }
    category_seconds = {
        category: round(
            sum(durations[row["shot_id"]] for row in proposal["shot_treatments"] if row["classification"] == category),
            3,
        )
        for category in (
            "VIDEO_REQUIRED_FOR_INTENT",
            "VIDEO_STRONGLY_PREFERRED",
            "VIDEO_BENEFICIAL",
        )
    }
    minimum_formula_seconds = category_seconds["VIDEO_REQUIRED_FOR_INTENT"] + 0.5 * (
        category_seconds["VIDEO_STRONGLY_PREFERRED"] + category_seconds["VIDEO_BENEFICIAL"]
    )
    maximum_useful_candidate = sum(category_seconds.values())
    proposal["cinematic_range"] = {
        "minimum_cinematically_justified_video_seconds": round(
            max(EPISODE_DURATION * 0.50, minimum_formula_seconds), 3
        ),
        "minimum_justification_formula": "all VIDEO_REQUIRED_FOR_INTENT plus half of VIDEO_STRONGLY_PREFERRED and VIDEO_BENEFICIAL, clamped to the hard 50% floor",
        "preferred_cinematic_video_seconds": proposal["coverage"]["true_generated_video_timeline_seconds"],
        "maximum_useful_video_seconds": round(
            min(EPISODE_DURATION * 0.75, maximum_useful_candidate), 3
        ),
        "maximum_useful_is_policy_ceiling_not_target": True,
        "category_seconds": category_seconds,
    }
    proposal["input_hashes"] = {
        "provider_ready_prompt_plan_sha256": sha256_file(plan_path),
        "pricing_registry_sha256": sha256_file(registry_path),
        "current_defective_preflight_sha256": sha256_file(REPO / CURRENT_PREFLIGHT_REL),
        "current_episode_ledger_sha256": sha256_file(REPO / LEDGER_REL),
        "creative_overlay_sha256": OVERLAY_SHA256,
        "authoritative_structural_fingerprint": STRUCTURAL_FINGERPRINT,
    }
    proposal["policy_decision"] = {
        "unknown_pricing_blocks_execution": pricing.unpriced_requests > 0,
        "provider_execution_executed": False,
        "production_authorization_consumed": False,
        "episode_ledger_mutated": False,
        "authoritative_preflight_replaced": False,
        "next_required_human_action": "REVIEW_50_TO_75_PERCENT_DIRECTORIALLY_OPTIMIZED_EP002_MEDIA_PLAN_AND_COST_BEFORE_REPLACING_DEFECTIVE_PREFLIGHT",
    }
    proposal.pop("proposal_sha256", None)
    proposal["proposal_sha256"] = canonical_sha256(proposal)
    proposal_path = REPO / PROPOSAL_REL
    proposal_path.parent.mkdir(parents=True, exist_ok=True)
    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    coverage = proposal["coverage"]
    inventory = proposal["request_inventory"]
    directorial = proposal["directorial_target"]
    lines = [
        "# SIRAJ MEDIA PLANNER V2 — EP002 proposal-only review",
        "",
        "> Local deterministic proposal. No preflight, ledger, storyboard, creative overlay, authorization, or provider state was modified.",
        "",
        "## Decision",
        "",
        f"- Planner status: **PASS (proposal-only)**",
        f"- True generated-video coverage: **{coverage['true_generated_video_timeline_seconds']:.3f}s / {coverage['true_generated_video_timeline_percent']:.6f}%**",
        f"- Hard policy range: **50.0%–75.0% — {coverage['coverage_validation']['status']}**",
        f"- Directorially preferred target: **{directorial['directorially_preferred_video_percent']:.6f}%**",
        f"- Cinematically justified range: **{proposal['cinematic_range']['minimum_cinematically_justified_video_seconds']:.3f}s minimum / {proposal['cinematic_range']['preferred_cinematic_video_seconds']:.3f}s preferred / {proposal['cinematic_range']['maximum_useful_video_seconds']:.3f}s maximum useful**",
        f"- Pricing: **{pricing.pricing_status}** ({pricing.priced_requests} priced / {pricing.unpriced_requests} unpriced)",
        "- Provider execution: **BLOCKED — UNKNOWN_PRICING_BLOCKS_EXECUTION**",
        "",
        "## Why this percentage",
        "",
        f"- Why not 50%: {directorial['why_not_50']}",
        f"- Why not 75%: {directorial['why_not_75']}",
        f"- Why selected: {directorial['why_selected']}",
        "",
        "## Coverage and efficiency",
        "",
        f"- Episode duration: {EPISODE_DURATION:.3f}s",
        f"- True generated video: {coverage['true_generated_video_timeline_seconds']:.3f}s",
        f"- Animated stills: {coverage['animated_still_seconds']:.3f}s",
        f"- Graphics/local: {coverage['graphics_local_seconds']:.3f}s",
        f"- Provider-requested video: {coverage['provider_requested_video_seconds']:.3f}s",
        f"- Expected unused provider duration: {coverage['expected_unused_video_seconds']:.3f}s",
        f"- Provider-unit efficiency: {coverage['video_request_efficiency_percent']:.6f}%",
        f"- Longest no-true-video span: {coverage['longest_no_true_video_span_seconds']:.3f}s",
        f"- 30s+ no-video spans: {coverage['number_of_30s_plus_no_true_video_spans']}",
        f"- 60s+ no-video spans: {coverage['number_of_60s_plus_no_true_video_spans']}",
        "",
        "## Request inventory and cost authority",
        "",
        f"- Video provider requests: {inventory['video_provider_requests']}",
        f"- Still provider requests: {inventory['still_provider_requests']}",
        f"- Graphics/local units: {inventory['graphics_local_units']}",
        f"- Total provider requests: {inventory['total_provider_requests']}",
        f"- Pricing registry: `{REGISTRY_REL.as_posix()}`",
        f"- Estimated total cost: **{_money(pricing.estimated_total_cost)}**",
        f"- Currency: **{_money(pricing.currency)}**",
        "",
        "The registry contains explicit UNPRICED records for the current Runware models because no authoritative local price was available. No price was invented and no network lookup was performed.",
        "",
        "### Provider/model breakdown",
        "",
        "| Provider | Model | Kind | Requests | Requested seconds | Timeline seconds |",
        "|---|---|---|---:|---:|---:|",
    ]
    for row in proposal["provider_model_breakdown"]:
        lines.append(
            f"| {row['provider']} | {row['model']} | {row['media_kind']} | {row['request_count']} | {row['requested_seconds']:.3f} | {row['timeline_seconds']:.3f} |"
        )
    lines.extend([
        "",
        "## Sequence motion coverage",
        "",
        "| Sequence | Duration | True video | Video % | Still | Graphics/local | Classification |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in proposal["sequences"]:
        lines.append(
            f"| {row['sequence_id']} | {row['sequence_duration_seconds']:.3f} | {row['true_video_seconds']:.3f} | {row['true_video_percent']:.3f}% | {row['animated_still_seconds']:.3f} | {row['graphics_local_seconds']:.3f} | {row['motion_role']} |"
        )
    lines.extend([
        "",
        "## Per-shot treatment",
        "",
        "| Shot | Class | Selected treatment | Duration | True video | Non-video | Reason |",
        "|---|---|---|---:|---:|---:|---|",
    ])
    for row in proposal["shots"]:
        reason = row["classification_reason"].replace("|", "/")
        lines.append(
            f"| {row['shot_id']} | {row['classification']} | {row['selected_media_treatment']} | {row['end_seconds'] - row['start_seconds']:.3f} | {row['true_video_seconds']:.3f} | {row['non_video_seconds']:.3f} | {reason} |"
        )
    lines.extend([
        "",
        "## Video units",
        "",
        "Each unit is a distinct proposal-only planning unit. Provider payloads are validated locally against the Veo 3.1 contract and contain no `negativePrompt`; no task is submitted.",
        "",
        "| Unit | Shot | Timeline | Usable | Requested | Unused | Model |",
        "|---|---|---:|---:|---:|---:|---|",
    ])
    for unit in proposal["video_units"]:
        lines.append(
            f"| {unit['unit_id']} | {unit['shot_id']} | {unit['timeline_start_seconds']:.3f}–{unit['timeline_end_seconds']:.3f} | {unit['expected_usable_seconds']:.3f} | {unit['requested_seconds']} | {unit['expected_unused_seconds']:.3f} | {unit['model']} |"
        )
    lines.extend([
        "",
        "## Safety and comparison",
        "",
        "- Old 21.669s / 3.474913% and previous 70.519s / 11.308661% plans remain forensic evidence only; both fail the new hard floor.",
        "- No loops, duplicate clip reuse, structural timing changes, or provider submissions are allowed by this proposal.",
        "- `VEO31_NEGATIVE_PROMPT_FIELD=BLOCKED`: no unsupported field is emitted in the local task validation.",
        "- `CREATIVE_INFORMATION_LOST=FALSE`, `CINEMATIC_QUALITY_REGRESSION=FALSE`, `STRUCTURAL_CHANGE=NONE`.",
        "- Episode 002 current stage remains `PROVIDER_EXECUTION`; authoritative preflight and ledger remain untouched.",
        "",
        "## Required human action",
        "",
        "Review this 50–75% directorially optimized plan and establish authoritative local pricing before any replacement preflight or provider execution.",
        "",
    ])
    (REPO / REVIEW_REL).write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "proposal": str(PROPOSAL_REL),
        "review": str(REVIEW_REL),
        "true_video_seconds": coverage["true_generated_video_timeline_seconds"],
        "true_video_percent": coverage["true_generated_video_timeline_percent"],
        "video_units": inventory["video_provider_requests"],
        "provider_requests": inventory["total_provider_requests"],
        "pricing_status": pricing.pricing_status,
        "priced": pricing.priced_requests,
        "unpriced": pricing.unpriced_requests,
    }, indent=2))


if __name__ == "__main__":
    main()
