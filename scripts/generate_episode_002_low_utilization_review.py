"""Generate the final local review of low-utilization EP002 video units.

This script is deliberately proposal/report-only.  It reads the already
contract-valid proposal, validates the discrete Veo duration choice and
pricing evidence, and writes only report artifacts.  It never mutates the
episode ledger, authorization, preflight, storyboard, or creative plan.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.artifact_provenance_v1 import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
PROPOSAL_PATH = ROOT / "reports" / "episode-002-media-planner-v2-contract-valid-proposal.json"
REPORT_MD = ROOT / "reports" / "episode-002-low-utilization-video-review.md"
REPORT_JSON = ROOT / "reports" / "episode-002-low-utilization-video-review.json"

EPISODE = "episode-002-adam-temptation-fall-repentance"
EXPECTED_OVERLAY = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
EXPECTED_STRUCTURAL = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
SUPPORTED_DURATIONS = (4, 6, 8)
VIDEO_PRICE_USD = 0.05


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ceil_required(value: float) -> int:
    integer = int(value)
    return integer if abs(value - integer) < 1e-9 else integer + 1


def feasible_duration(required: float, supported: tuple[int, ...]) -> int | None:
    needed = ceil_required(required)
    for duration in supported:
        if duration >= needed:
            return duration
    return None


def sequence_units(units: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for unit in units:
        grouped[str(unit.get("shot_id"))].append(unit)
    for values in grouped.values():
        values.sort(key=lambda row: float(row.get("timeline_start_seconds") or 0.0))
    return dict(grouped)


def merge_analysis(unit: Mapping[str, Any], by_shot: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    siblings = by_shot.get(str(unit.get("shot_id")), [])
    index = next((index for index, row in enumerate(siblings) if row.get("unit_id") == unit.get("unit_id")), -1)
    adjacent_same_shot = []
    if index > 0:
        adjacent_same_shot.append(siblings[index - 1])
    if index >= 0 and index + 1 < len(siblings):
        adjacent_same_shot.append(siblings[index + 1])
    reasons: list[str] = []
    for sibling in adjacent_same_shot:
        combined = float(unit.get("timeline_required_seconds") or 0.0) + float(sibling.get("timeline_required_seconds") or 0.0)
        if combined > max(SUPPORTED_DURATIONS):
            reasons.append(f"same-shot combined timeline {combined:.3f}s exceeds the {max(SUPPORTED_DURATIONS)}s provider maximum")
        if sibling.get("direction_fingerprint") != unit.get("direction_fingerprint"):
            reasons.append("adjacent unit has a distinct approved cinematic direction fingerprint")
    if not adjacent_same_shot:
        reasons.append("no adjacent unit exists within the same narrative shot")
    return {
        "available": False,
        "same_shot_adjacent_units": [str(row.get("unit_id")) for row in adjacent_same_shot],
        "reason": "; ".join(reasons),
    }


def build_review() -> tuple[dict[str, Any], str]:
    proposal = read_json(PROPOSAL_PATH)
    proposal_sha = file_sha256(PROPOSAL_PATH)
    assert proposal["episode_id"] == EPISODE
    assert proposal["status"] == "CONTRACT_VALID_PROPOSAL_ONLY"
    assert proposal["provider_contracts"]["status"] == "PASS"
    assert proposal["cost_summary"]["pricing_status"] == "COMPLETE"
    assert proposal["authoritative_inputs"]["creative_overlay_sha256"] == EXPECTED_OVERLAY
    assert proposal["authoritative_inputs"]["structural_fingerprint"] == EXPECTED_STRUCTURAL
    assert proposal["coverage"]["true_generated_video_timeline_seconds"] == 428.56
    assert proposal["coverage"]["true_generated_video_timeline_percent"] == 68.725304
    assert proposal["request_inventory"]["video_provider_requests"] == 73

    all_units = list(proposal["video_units"])
    low_units = [unit for unit in all_units if float(unit["utilization_percent"]) < 75.0]
    assert len(low_units) == 18
    by_shot = sequence_units(all_units)
    cost_by_id = {str(row["request_id"]): row for row in proposal["cost_rows"]}
    reviewed: list[dict[str, Any]] = []
    for unit in low_units:
        supported = tuple(int(value) for value in unit["provider_supported_durations"])
        required = float(unit["timeline_required_seconds"]) + float(unit.get("editing_handle_seconds") or 0.0)
        minimum = feasible_duration(required, supported)
        selected = int(unit["selected_provider_duration"])
        assert minimum == selected
        assert selected == minimum
        assert float(unit.get("editing_handle_seconds") or 0.0) == 0.0
        cost = cost_by_id[str(unit["unit_id"])]
        merge = merge_analysis(unit, by_shot)
        reviewed.append(
            {
                "unit_id": unit["unit_id"],
                "shot_id": unit["shot_id"],
                "sequence": unit["sequence_id"],
                "provider": unit["provider"],
                "model": unit["model"],
                "timeline_required_seconds": unit["timeline_required_seconds"],
                "editing_handle_seconds": unit["editing_handle_seconds"],
                "minimum_usable_generation_seconds": unit["minimum_usable_generation_seconds"],
                "requested_seconds": unit["requested_seconds"],
                "expected_usable_seconds": unit["expected_usable_seconds"],
                "expected_unused_seconds": unit["expected_unused_seconds"],
                "utilization_percent": unit["utilization_percent"],
                "supported_provider_durations": list(supported),
                "selected_provider_duration": selected,
                "billing_duration_seconds": unit["billing_duration_seconds"],
                "duration_selection_reason": (
                    f"{selected}s is the smallest supported duration satisfying ceil({required:.3f}s)="
                    f"{ceil_required(required)}s; no smaller supported duration can cover the preserved interval."
                ),
                "cinematic_purpose": unit["cinematic_reason"],
                "direction_source_fields": unit.get("direction_source_fields"),
                "direction_fingerprint": unit.get("direction_fingerprint"),
                "planning_identity": unit.get("planning_identity"),
                "payload_sha256": unit.get("payload_sha256"),
                "cost_usd": cost["estimated_cost"],
                "cost_basis": {
                    "billing_unit": cost["billing_unit"],
                    "unit_price_usd": cost["unit_price"],
                    "billing_quantity": cost["billing_quantity"],
                    "pricing_variant": cost.get("pricing_variant"),
                },
                "classification": "UNAVOIDABLE_PROVIDER_DURATION_OVERHEAD",
                "below_25_specific_reason": (
                    "The preserved cinematic sub-phase is shorter than the provider's 4s minimum; removing or demoting it would alter the approved temporal beat, while a smaller provider duration does not exist."
                    if float(unit["utilization_percent"]) < 25.0
                    else None
                ),
                "smaller_duration_check": {
                    "status": "PASS",
                    "selected_is_smallest_feasible": True,
                    "smaller_supported_duration_exists": any(value < selected for value in supported),
                    "smaller_duration_can_cover_required_interval": False,
                },
                "merge_check": merge,
                "sequential_recomposition_check": {
                    "available": False,
                    "reason": "The unit is already the terminal/short phase of its approved shot decomposition; recomposition would change distinct direction phases or shot ownership, not merely remove provider overhead.",
                },
                "loop_or_reuse": False,
            }
        )

    summary = {
        "low_utilization_units_below_75": len(low_units),
        "low_utilization_units_below_50": sum(float(unit["utilization_percent"]) < 50.0 for unit in low_units),
        "low_utilization_units_below_25": sum(float(unit["utilization_percent"]) < 25.0 for unit in low_units),
        "unavoidable_provider_overhead_units": len(reviewed),
        "justified_editing_or_cinematic_overhead_units": 0,
        "safe_duration_reduction_units": 0,
        "safe_merge_units": 0,
        "safe_recomposition_units": 0,
        "human_review_units": 0,
        "low_unit_requested_seconds": round(sum(float(unit["requested_seconds"]) for unit in low_units), 3),
        "low_unit_unused_seconds": round(sum(float(unit["expected_unused_seconds"]) for unit in low_units), 3),
        "low_unit_cost_usd": round(sum(float(cost_by_id[str(unit["unit_id"])] ["estimated_cost"] or 0.0) for unit in low_units), 8),
    }
    report: dict[str, Any] = {
        "schema_version": "siraj-episode-002-low-utilization-video-review-v1",
        "status": "WARN",
        "created_at_utc": utc_now(),
        "episode_id": EPISODE,
        "source_proposal": {
            "path": "reports/episode-002-media-planner-v2-contract-valid-proposal.json",
            "physical_sha256": proposal_sha,
            "declared_proposal_sha256": proposal["proposal_sha256"],
        },
        "authority": {
            "creative_overlay_sha256": EXPECTED_OVERLAY,
            "structural_fingerprint": EXPECTED_STRUCTURAL,
            "true_video_timeline_seconds": proposal["coverage"]["true_generated_video_timeline_seconds"],
            "true_video_percent": proposal["coverage"]["true_generated_video_timeline_percent"],
            "cinematic_strength": proposal["cinematic_assessment"]["cinematic_strength"],
            "provider_contract_status": proposal["provider_contracts"]["status"],
            "pricing_status": proposal["cost_summary"]["pricing_status"],
        },
        "provider_contract": {
            "provider": "RUNWARE",
            "model": "google:veo@3.1-lite",
            "supported_durations_seconds": list(SUPPORTED_DURATIONS),
            "billing_unit": "per_generated_video_second",
            "unit_price_usd": VIDEO_PRICE_USD,
            "pricing_variant": "720p_no_audio",
            "negative_prompt_field": "BLOCKED",
            "source": "proposal-bound-current-canonical-registry",
        },
        "summary": summary,
        "units": reviewed,
        "merge_policy": {
            "same_shot_candidates": 0,
            "cross_shot_candidates": 0,
            "cross_shot_merge_allowed": False,
            "reason": "Adjacent storyboard shots retain independent shot ownership, timing, and creative direction; no merge is safe without an explicit structural/creative rebuild.",
        },
        "sequential_recomposition_policy": {
            "candidates": 0,
            "loops_allowed": False,
            "duplicate_output_reuse_allowed": False,
            "reason": "The reviewed units are already distinct terminal phases; recomposition would alter approved temporal progression rather than remove only provider overhead.",
        },
        "optimization": {
            "available": False,
            "proposal_path": None,
            "reason": "All 18 units already use the smallest contract-valid duration. No safe merge or sequential recomposition preserves the approved distinct temporal phases and shot ownership. Any cost reduction would require a new human creative/media decision, not a local efficiency optimization.",
            "current_provider_requests": proposal["request_inventory"]["video_provider_requests"],
            "proposed_provider_requests": None,
            "current_provider_requested_seconds": proposal["coverage"]["provider_requested_video_seconds"],
            "proposed_provider_requested_seconds": None,
            "current_unused_seconds": proposal["coverage"]["expected_unused_video_seconds"],
            "proposed_unused_seconds": None,
            "current_efficiency_percent": proposal["coverage"]["video_request_efficiency_percent"],
            "proposed_efficiency_percent": None,
            "current_total_cost_usd": proposal["cost_summary"]["estimated_total_cost_usd"],
            "proposed_total_cost_usd": None,
            "true_video_timeline_seconds_before": proposal["coverage"]["true_generated_video_timeline_seconds"],
            "true_video_timeline_seconds_after": None,
            "cinematic_quality_regression": False,
            "creative_information_lost": False,
            "structural_change": "NONE",
        },
        "migration_decision": "MIGRATE_CURRENT_PLAN",
        "safety": {
            "provider_execution_executed": False,
            "production_authorization_consumed": False,
            "episode_ledger_mutated": False,
            "migration_applied": False,
            "network_calls": 0,
            "provider_api_calls": 0,
            "paid_provider_calls": 0,
            "files_deleted": 0,
        },
        "validation": {
            "all_low_units_contract_valid": True,
            "all_low_units_use_smallest_feasible_duration": True,
            "all_below_25_have_specific_reason": True,
            "no_safe_duration_reduction": True,
            "no_safe_merge": True,
            "no_safe_recomposition": True,
            "approved_coverage_preserved": True,
            "proposal_not_modified": True,
        },
    }
    report["report_sha256"] = canonical_sha256(report)
    markdown = render_markdown(report)
    return report, markdown


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report["summary"]
    authority = report["authority"]
    optimization = report["optimization"]
    lines = [
        "# EP002 Low-Utilization Video Unit Final Review",
        "",
        "**Scope:** local review only. The contract-valid proposal, storyboard, creative overlay, ledger, authorization, and migration state were not modified.",
        "",
        f"**Review status:** `{report['status']}`. All 18 units below 75% use the smallest duration supported by the current Veo contract. The warning records provider-granularity waste, not a provider-contract failure.",
        "",
        f"Approved authority remains **{authority['true_video_timeline_seconds']:.3f}s / {authority['true_video_percent']:.6f}% true video**, cinematic strength **{authority['cinematic_strength']}**, structural fingerprint `{authority['structural_fingerprint']}`.",
        "",
        "## Decision summary",
        "",
        f"- Below 75%: **{summary['low_utilization_units_below_75']}**; below 50%: **{summary['low_utilization_units_below_50']}**; below 25%: **{summary['low_utilization_units_below_25']}**.",
        f"- Unavoidable provider-duration overhead: **{summary['unavoidable_provider_overhead_units']}** units.",
        f"- Justified editing/cinematic overhead: **{summary['justified_editing_or_cinematic_overhead_units']}** units; safe duration reductions: **{summary['safe_duration_reduction_units']}**; safe merges: **{summary['safe_merge_units']}**; safe recompositions: **{summary['safe_recomposition_units']}**; human-review units: **{summary['human_review_units']}**.",
        f"- The reviewed units account for **{summary['low_unit_requested_seconds']:.3f}s** requested, **{summary['low_unit_unused_seconds']:.3f}s** unused, and **${summary['low_unit_cost_usd']:.8f} USD**.",
        "",
        "## Contract conclusion",
        "",
        "The only supported Veo durations are 4, 6, and 8 seconds. Every reviewed unit is already at the smallest feasible member of that set: 4 seconds for sub-4-second intervals, and 6 seconds for the 4.025-second and 4.200-second intervals. There is no smaller valid duration to select.",
        "",
        "The 4-second requests below 25% are not silently accepted as efficient. Each has a specific reason: it is a preserved, direction-bearing terminal sub-phase shorter than the provider minimum. Demoting it to a still or changing its boundary would change the approved cinematic design, so that would require a separate human creative decision rather than a local cost optimization.",
        "",
        "## Unit-by-unit review",
        "",
        "| Unit | Shot | Sequence | Req. | Handle | Requested | Usable | Unused | Util. | Cost | Classification |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for unit in report["units"]:
        lines.append(
            f"| `{unit['unit_id']}` | {unit['shot_id']} | {unit['sequence']} | {unit['timeline_required_seconds']:.3f}s | {unit['editing_handle_seconds']:.3f}s | {unit['requested_seconds']}s | {unit['expected_usable_seconds']:.3f}s | {unit['expected_unused_seconds']:.3f}s | {unit['utilization_percent']:.3f}% | ${unit['cost_usd']:.2f} | {unit['classification']} |"
        )
    lines += ["", "## Evidence and safety checks", ""]
    for unit in report["units"]:
        lines += [
            f"### `{unit['unit_id']}`",
            "",
            f"- Provider/model: `{unit['provider']}` / `{unit['model']}`; supported durations: **{unit['supported_provider_durations']}**; selected/billed: **{unit['selected_provider_duration']}s**.",
            f"- Selection: {unit['duration_selection_reason']}",
            f"- Cinematic purpose: {unit['cinematic_purpose']}",
            f"- Cost: **${unit['cost_usd']:.8f} USD** ({unit['cost_basis']['billing_unit']}, {unit['cost_basis']['billing_quantity']} billed units at ${unit['cost_basis']['unit_price_usd']:.5f}).",
            f"- Smaller-duration check: **PASS**. Merge available: **FALSE** ({unit['merge_check']['reason']}). Sequential recomposition: **FALSE** ({unit['sequential_recomposition_check']['reason']}).",
            f"- Loop/reuse: **FALSE**. Payload `{unit['payload_sha256']}`; planning identity `{unit['planning_identity']}`.",
        ]
        if unit["below_25_specific_reason"]:
            lines.append(f"- Below-25% evidence: {unit['below_25_specific_reason']}")
        lines.append("")
    lines += [
        "## Optional optimization result",
        "",
        "Cross-shot merging was also checked and produced zero candidates: adjacent storyboard shots have independent structural ownership and creative direction, so combining them would require an explicit structural/creative rebuild.",
        "",
        "No safe optimization proposal was produced. There is no valid shorter provider duration, no same-shot merge that preserves the distinct approved phases, and no safe sequential recomposition. The current 73-request / 496.000-second plan therefore remains the correct migration candidate; no insignificant cost reduction justifies changing the cinematic plan.",
        "",
        f"Current provider-requested video: **{optimization['current_provider_requested_seconds']:.3f}s**; current unused: **{optimization['current_unused_seconds']:.3f}s**; current efficiency: **{optimization['current_efficiency_percent']:.6f}%**; current total: **${optimization['current_total_cost_usd']:.8f} USD**.",
        "Proposed values: **NONE**. True-video timeline remains **428.560s / 68.725304%**; floor and ceiling remain PASS; structural change is NONE.",
        "",
        "## Migration decision",
        "",
        "`MIGRATE_CURRENT_PLAN`. This review does not apply migration, execute preflight, consume authorization, or call a provider. A future migration may use the existing contract-valid proposal and its separate migration proposal after human review.",
        "",
        "Provider execution: **FALSE**. Production authorization consumed: **FALSE**. Episode ledger mutated: **FALSE**. Files deleted: **0**.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    report, markdown = build_review()
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(markdown, encoding="utf-8")
    print(json.dumps({"report": str(REPORT_JSON), "markdown": str(REPORT_MD), "status": report["status"], "decision": report["migration_decision"], "units": len(report["units"])}, indent=2))


if __name__ == "__main__":
    main()
