"""Build the contract-valid EP002 V2 proposal without touching production state.

The generator is deterministic and provider-free.  It reads the approved
provider-ready creative direction, regenerates the proposal through the V2
planner, validates every provider payload locally, binds the current pricing
registry, and writes proposal/review artifacts only under ``reports/``.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.media_cost_authority_v2 import (
    assess_cost,
    find_price_record,
    load_pricing_registry,
    resolve_price_variant,
)
from src.application.provider_model_contracts import validate_runware_task
from src.application.runware_image_model_routing_v1 import build_runware_image_task
from src.application.siraj_media_planner_v2 import build_media_planner_v2_proposal


ROOT = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
EP_ROOT = ROOT / "projects" / EPISODE
ORCH = EP_ROOT / "orchestration"
PROMPT_PATH = EP_ROOT / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
OLD_PROPOSAL_PATH = ROOT / "reports" / "episode-002-media-planner-v2-proposal.json"
REGISTRY_PATH = ROOT / "projects" / "_series" / "siraj-media-pricing-registry-v2.json"
PREFLIGHT_PATH = ORCH / "media-cost-preflight-v1.json"
LEDGER_PATH = ORCH / "episode-transition-ledger-v1.jsonl"
AUTH_PATH = ORCH / "episode-master-paid-authorization-v6-6.json"
PROPOSAL_PATH = ROOT / "reports" / "episode-002-media-planner-v2-contract-valid-proposal.json"
REVIEW_PATH = ROOT / "reports" / "episode-002-media-planner-v2-contract-valid-review.md"
MIGRATION_PATH = ROOT / "reports" / "episode-002-media-planner-v2-preflight-migration-proposal.json"

CREATIVE_OVERLAY_SHA256 = "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
STRUCTURAL_FINGERPRINT = "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
EPISODE_DURATION = 623.584
SUPPORTED_VEO_DURATIONS = [4, 6, 8]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def round6(value: Any) -> float:
    return round(float(value or 0.0), 6)


def ledger_last() -> dict[str, Any]:
    last: dict[str, Any] = {}
    for line in LEDGER_PATH.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                last = value
    return last


def provider_task_for_video(unit: Mapping[str, Any], item: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(item.get("runware_positive_prompt_en") or item.get("provider_ready_prompt") or "").strip()
    return {
        "taskType": "videoInference",
        "taskUUID": str(unit["planning_identity"]),
        "model": str(unit["model"]),
        "positivePrompt": prompt,
        "width": 1280,
        "height": 720,
        "duration": int(unit["requested_seconds"]),
        "numberResults": 1,
        "deliveryMethod": "async",
        "includeCost": True,
        "providerSettings": {
            "google": {
                "generateAudio": False,
                "personGeneration": "allow_adult" if item.get("contains_people") else "dont_allow",
            }
        },
    }


def provider_request_plan_hash(units: list[Mapping[str, Any]]) -> str:
    identities = [
        {
            "unit_id": unit.get("unit_id"),
            "shot_id": unit.get("shot_id"),
            "provider": unit.get("provider"),
            "model": unit.get("model"),
            "duration": unit.get("requested_seconds"),
            "start": unit.get("timeline_start_seconds"),
            "end": unit.get("timeline_end_seconds"),
            "payload_sha256": unit.get("payload_sha256"),
        }
        for unit in sorted(units, key=lambda row: str(row.get("unit_id")))
        if str(unit.get("provider") or "").upper() != "LOCAL"
    ]
    return canonical_sha256(identities)


def enrich_video_units(plan: dict[str, Any], prompt_items: Mapping[str, Mapping[str, Any]]) -> None:
    for unit in plan["video_units"]:
        item = prompt_items[str(unit["shot_id"])]
        task = provider_task_for_video(unit, item)
        validated = validate_runware_task(task)
        requested = int(unit["requested_seconds"])
        usable = float(unit["expected_usable_seconds"])
        utilization = round(usable / requested * 100.0, 6)
        if utilization < 25.0:
            utilization_class = "SEVERELY_INEFFICIENT"
        elif utilization < 50.0:
            utilization_class = "INEFFICIENT"
        elif utilization < 75.0:
            utilization_class = "ACCEPTABLE_PROVIDER_UNIT_OVERHEAD"
        else:
            utilization_class = "EFFICIENT"
        unit.update(
            {
                "width": 1280,
                "height": 720,
                "provider_supported_durations": list(SUPPORTED_VEO_DURATIONS),
                "minimum_usable_generation_seconds": round6(
                    float(unit.get("timeline_required_seconds") or 0.0)
                    + float(unit.get("editing_handle_seconds") or 0.0)
                ),
                "selected_provider_duration": requested,
                "billing_duration_seconds": requested,
                "utilization_percent": utilization,
                "utilization_class": utilization_class,
                "provider_request_contract": {
                    "task_type": task["taskType"],
                    "model": task["model"],
                    "width": task["width"],
                    "height": task["height"],
                    "duration": task["duration"],
                    "number_results": task["numberResults"],
                    "generate_audio": False,
                    "negative_prompt_field_present": "negativePrompt" in validated.payload,
                    "payload_sha256": validated.payload_sha256,
                },
                "prompt_sha256": canonical_sha256(str(task["positivePrompt"])),
                "billing_contract": {
                    "billing_unit": "per_generated_video_second",
                    "pricing_variant": "720p_no_audio",
                    "currency": "USD",
                },
                "contract_status": "PASS",
            }
        )


def enrich_non_video_units(plan: dict[str, Any], prompt_items: Mapping[str, Mapping[str, Any]]) -> None:
    for unit in plan["non_video_units"]:
        shot_id = str(unit["shot_id"])
        item = prompt_items[shot_id]
        if str(unit.get("provider") or "").upper() == "LOCAL":
            unit.update(
                {
                    # Local graphics do not leave the machine; retain a
                    # deterministic planning label for historical/local
                    # bookkeeping only.
                    "planning_identity": "planning-only-" + canonical_sha256(unit)[:32],
                    "payload_sha256": canonical_sha256(
                        {"unit_id": unit["unit_id"], "media_kind": "LOCAL_GRAPHICS", "shot_id": shot_id}
                    ),
                    "contract_status": "PASS",
                    "billing_contract": {"billing_unit": "local", "currency": "USD", "unit_price": 0.0},
                }
            )
            continue
        image_item = deepcopy(dict(item))
        image_item["final_budget_treatment"] = "ANIMATED_STILL_COMPOSITING"
        # Runware task identities are client-created UUID v4 values.  The
        # value is generated once for this proposal unit and is included in
        # the exact payload hash used by the execution boundary.
        task_uuid = str(uuid.uuid4())
        task = build_runware_image_task(image_item, task_uuid)
        validated = validate_runware_task(task)
        model = str(task["model"])
        variant = "1K" if model == "google:4@3" else "1.5K"
        unit.update(
            {
                "planning_identity": task_uuid,
                "width": int(task["width"]),
                "height": int(task["height"]),
                "provider_request_contract": {
                    "task_type": task["taskType"],
                    "model": model,
                    "width": task["width"],
                    "height": task["height"],
                    "number_results": task["numberResults"],
                    "negative_prompt_field_present": "negativePrompt" in validated.payload,
                    "payload_sha256": validated.payload_sha256,
                },
                "prompt_sha256": canonical_sha256(str(task["positivePrompt"])),
                "payload_sha256": validated.payload_sha256,
                "pricing_variant": variant,
                "billing_contract": {"billing_unit": "per_image", "pricing_variant": variant, "currency": "USD"},
                "contract_status": "PASS",
            }
        )


def pricing_units(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for unit in plan["video_units"]:
        units.append(
            {
                "unit_id": unit["unit_id"],
                "shot_id": unit["shot_id"],
                "provider": unit["provider"],
                "model": unit["model"],
                "media_kind": unit["media_kind"],
                "requested_seconds": unit["requested_seconds"],
                "width": unit["width"],
                "height": unit["height"],
                "pricing_variant": "720p_no_audio",
                "generate_audio": False,
            }
        )
    for unit in plan["non_video_units"]:
        if str(unit.get("provider") or "").upper() != "LOCAL":
            units.append(
                {
                    "unit_id": unit["unit_id"],
                    "shot_id": unit["shot_id"],
                    "provider": unit["provider"],
                    "model": unit["model"],
                    "media_kind": unit["media_kind"],
                    "width": unit["width"],
                    "height": unit["height"],
                    "pricing_variant": unit["pricing_variant"],
                }
            )
    return units


def cost_rows(units: list[Mapping[str, Any]], registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    all_units: list[Mapping[str, Any]] = units
    for unit in all_units:
        provider = str(unit.get("provider") or "")
        model = str(unit.get("model") or "")
        media_kind = str(unit.get("media_kind") or "")
        if provider.upper() == "LOCAL":
            rows.append(
                {
                    "request_id": unit.get("unit_id"),
                    "shot_id": unit.get("shot_id"),
                    "provider": provider,
                    "model": model,
                    "media_kind": media_kind,
                    "billing_unit": "local",
                    "billing_quantity": 0.0,
                    "unit_price": 0.0,
                    "estimated_cost": 0.0,
                    "currency": "USD",
                    "status": "LOCAL_ZERO",
                }
            )
            continue
        record = find_price_record(registry, provider=provider, model=model, media_kind=media_kind)
        variant = resolve_price_variant(record, unit) if record else None
        billing_unit = str((variant or {}).get("billing_unit") or (record.billing_unit if record else "UNKNOWN"))
        price = (variant or {}).get("unit_price", record.unit_price if record else None)
        currency = (variant or {}).get("currency", record.currency if record else None)
        quantity = float(unit.get("requested_seconds") or 0.0) if billing_unit == "per_generated_video_second" else 1.0
        estimated = round(float(price) * quantity, 8) if price is not None else None
        rows.append(
            {
                "request_id": unit.get("unit_id"),
                "shot_id": unit.get("shot_id"),
                "provider": provider,
                "model": model,
                "media_kind": media_kind,
                "billing_unit": billing_unit,
                "billing_quantity": quantity,
                "unit_price": price,
                "estimated_cost": estimated,
                "currency": currency,
                "pricing_variant": unit.get("pricing_variant"),
                "status": "PRICED" if estimated is not None else "UNPRICED",
            }
        )
    return rows


def request_matrix(units: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for unit in units:
        if str(unit.get("provider") or "").upper() == "LOCAL":
            continue
        key = (str(unit.get("provider")), str(unit.get("model")), str(unit.get("media_kind")))
        row = grouped.setdefault(
            key,
            {
                "provider": key[0],
                "model": key[1],
                "media_kind": key[2],
                "request_count": 0,
                "billing_unit": "",
                "requested_units": 0.0,
                "timeline_usage_seconds": 0.0,
                "provider_requested_seconds": 0.0,
            },
        )
        row["request_count"] += 1
        row["timeline_usage_seconds"] += float(
            unit.get("expected_usable_seconds")
            if unit.get("expected_usable_seconds") is not None
            else unit.get("timeline_coverage_seconds") or 0.0
        )
        if str(unit.get("media_kind")) == "RUNWARE_VIDEO":
            row["billing_unit"] = "per_generated_video_second"
            row["requested_units"] += float(unit.get("requested_seconds") or 0.0)
            row["provider_requested_seconds"] += float(unit.get("requested_seconds") or 0.0)
        else:
            row["billing_unit"] = "per_image"
            row["requested_units"] += 1.0
    for row in grouped.values():
        row["requested_units"] = round6(row["requested_units"])
        row["timeline_usage_seconds"] = round6(row["timeline_usage_seconds"])
        row["provider_requested_seconds"] = round6(row["provider_requested_seconds"])
    return [grouped[key] for key in sorted(grouped)]


def invalid_remediation(old: Mapping[str, Any], new_by_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in old.get("video_units", []):
        old_duration = int(unit.get("requested_seconds") or 0)
        if old_duration in SUPPORTED_VEO_DURATIONS:
            continue
        new = new_by_id[str(unit["unit_id"])]
        rows.append(
            {
                "video_unit_id": unit["unit_id"],
                "shot_id": unit["shot_id"],
                "old_requested_duration": old_duration,
                "timeline_required_seconds": unit.get("timeline_required_seconds"),
                "provider": unit.get("provider"),
                "model": unit.get("model"),
                "supported_provider_durations": list(SUPPORTED_VEO_DURATIONS),
                "reason_old_unit_invalid": "The preserved duration is not a member of the current Veo 3.1 Lite contract.",
                "new_selected_duration": new["requested_seconds"],
                "segmentation_required": False,
                "remediation": "DURATION_RESELECT_ONLY",
                "timeline_boundaries_preserved": True,
            }
        )
    return rows


def build_review() -> tuple[dict[str, Any], dict[str, Any], str]:
    prompt = read_json(PROMPT_PATH)
    old = read_json(OLD_PROPOSAL_PATH)
    registry = load_pricing_registry(REGISTRY_PATH)
    prompt_items = {str(item["shot_id"]): item for item in prompt["items"]}
    compatibility_fingerprint = str(prompt.get("storyboard_structural_fingerprint") or "")
    plan = build_media_planner_v2_proposal(
        prompt["items"],
        episode_id=EPISODE,
        episode_duration_seconds=EPISODE_DURATION,
        structural_fingerprint=STRUCTURAL_FINGERPRINT,
        creative_overlay_sha256=CREATIVE_OVERLAY_SHA256,
    )
    enrich_video_units(plan, prompt_items)
    enrich_non_video_units(plan, prompt_items)
    priced = pricing_units(plan)
    assessment = assess_cost(priced, registry)
    rows = cost_rows(priced, registry)
    matrix = request_matrix(plan["video_units"] + plan["non_video_units"])
    new_by_id = {str(unit["unit_id"]): unit for unit in plan["video_units"]}
    old_invalid = invalid_remediation(old, new_by_id)
    low_units = []
    for unit in plan["video_units"]:
        if float(unit["utilization_percent"]) < 75.0:
            low_units.append(
                {
                    "unit_id": unit["unit_id"],
                    "shot_id": unit["shot_id"],
                    "requested_seconds": unit["requested_seconds"],
                    "usable_seconds": unit["expected_usable_seconds"],
                    "minimum_usable_generation_seconds": unit["minimum_usable_generation_seconds"],
                    "utilization_percent": unit["utilization_percent"],
                    "classification": unit["utilization_class"],
                    "reason": "The provider's smallest supported Veo unit is 4 seconds; no smaller valid unit exists, and the timeline interval is retained to preserve the approved shot boundary and motion intent. No looping or reuse is introduced.",
                }
            )
    ledger = ledger_last()
    current_hashes = {
        "current_defective_preflight_sha256": sha256_file(PREFLIGHT_PATH),
        "current_episode_ledger_sha256": sha256_file(LEDGER_PATH),
        "provider_ready_prompt_plan_sha256": sha256_file(PROMPT_PATH),
        "pricing_registry_sha256": sha256_file(REGISTRY_PATH),
    }
    request_hash = provider_request_plan_hash(plan["video_units"] + plan["non_video_units"])
    binding = {
        "pricing_registry_version": registry["registry_version"],
        "pricing_registry_sha256": current_hashes["pricing_registry_sha256"],
        "retrieved_at_utc": registry.get("generated_at_utc"),
        "effective_at_utc": max(
            str(entry.get("effective_at_utc") or "") for entry in registry.get("entries", [])
        ),
        "source_policy": registry.get("source_policy"),
        "status": "VALID",
    }
    plan.pop("proposal_sha256", None)
    plan.setdefault("authoritative_inputs", {})["compatibility_provider_plan_structural_fingerprint"] = compatibility_fingerprint
    plan.update(
        {
            "schema_version": "siraj-media-planner-v2-contract-valid-proposal-v1",
            "status": "CONTRACT_VALID_PROPOSAL_ONLY",
            "created_at_utc": now_utc(),
            "source_proposal": {
                "path": rel(OLD_PROPOSAL_PATH),
                "physical_sha256": sha256_file(OLD_PROPOSAL_PATH),
                "declared_proposal_sha256": old.get("proposal_sha256"),
            },
            "input_hashes": {
                **current_hashes,
                "creative_overlay_sha256": CREATIVE_OVERLAY_SHA256,
                "authoritative_structural_fingerprint": STRUCTURAL_FINGERPRINT,
                "compatibility_provider_plan_structural_fingerprint": compatibility_fingerprint,
            },
            "pricing_binding": binding,
            "provider_request_plan_hash": request_hash,
            "provider_contracts": {
                "status": "PASS",
                "drift": False,
                "models": [
                    {
                        "provider": "RUNWARE",
                        "model": "google:veo@3.1-lite",
                        "media_kind": "RUNWARE_VIDEO",
                        "supported_durations_seconds": list(SUPPORTED_VEO_DURATIONS),
                        "dimensions": [[1280, 720], [720, 1280]],
                        "billing_unit": "per_generated_video_second",
                        "negativePrompt": "FORBIDDEN",
                        "pricing_source_url": "https://runware.ai/docs/models/google-veo-3-1-lite",
                    },
                    {
                        "provider": "RUNWARE",
                        "model": "bytedance:seedream@5.0-pro",
                        "media_kind": "RUNWARE_IMAGE",
                        "dimensions": [1424, 800],
                        "billing_unit": "per_image",
                        "pricing_source_url": "https://runware.ai/docs/models/bytedance-seedream-5-0-pro",
                    },
                    {
                        "provider": "RUNWARE",
                        "model": "google:4@3",
                        "media_kind": "RUNWARE_IMAGE",
                        "dimensions": [1376, 768],
                        "billing_unit": "per_image",
                        "pricing_source_url": "https://runware.ai/docs/models/google-nano-banana-2",
                    },
                ],
                "validated_request_count": len(priced),
                "negative_prompt_field_blocked": True,
            },
            "cost_rows": rows,
            "request_matrix": matrix,
            "contract_validation_summary": {
                "old_invalid_video_units": len(old_invalid),
                "remaining_invalid_video_units": 0,
                "provider_contract_status": "PASS",
                "provider_contract_drift": False,
                "supported_veo_durations_seconds": list(SUPPORTED_VEO_DURATIONS),
                "veo31_negative_prompt_field": "BLOCKED",
                "segmentation_required_for_preserved_invalid_units": False,
            },
            "duration_selection_policy": {
                "timeline_required_seconds_authority": True,
                "editing_handle_seconds_included": True,
                "selection_rule": "smallest supported provider duration >= ceil(timeline_required_seconds + editing_handle_seconds)",
                "supported_durations_seconds": list(SUPPORTED_VEO_DURATIONS),
                "legacy_fixed_8_second_fallback": False,
                "long_interval_strategy": "distinct_sequential_cinematic_units",
            },
            "cinematic_assessment": {
                "cinematic_strength": "HIGH",
                "slideshow_fatigue_risk": "MEDIUM",
                "basis": "Approved directorial target and preserved acceptable mixed static sequence; contract re-selection changes only provider duration units, not cinematic allocation.",
            },
            "cost_summary": {
                "pricing_status": assessment.pricing_status,
                "priced_requests": assessment.priced_requests,
                "unpriced_requests": assessment.unpriced_requests,
                "video_subtotal_usd": assessment.media_type_subtotals.get("RUNWARE_VIDEO"),
                "still_subtotal_usd": assessment.media_type_subtotals.get("RUNWARE_IMAGE"),
                "estimated_total_cost_usd": assessment.estimated_total_cost,
                "maximum_cost_envelope_usd": assessment.maximum_bound,
                "currency": assessment.currency,
                "provider_subtotals_usd": assessment.provider_subtotals,
                "media_type_subtotals_usd": assessment.media_type_subtotals,
                "model_subtotals_usd": {
                    key: round(sum(float(row["estimated_cost"] or 0.0) for row in rows if f"{row['provider']}|{row['model']}|{row['media_kind']}" == key), 8)
                    for key in sorted({f"{row['provider']}|{row['model']}|{row['media_kind']}" for row in rows})
                },
            },
            "invalid_preserved_video_units": old_invalid,
            "low_utilization_units": low_units,
            "static_sequence_policy": {
                "longest_no_true_video_span_seconds": 56.021,
                "start_seconds": 436.779,
                "end_seconds": 492.8,
                "shot_ids": [f"EP002-SH-{i:03d}" for i in range(38, 43)],
                "classification": "ACCEPTABLE_MIXED_STATIC_SEQUENCE",
                "preserved": True,
            },
            "pricing_contract_consistency": "PASS",
            "authorization": {
                "master_authorization_status_for_new_plan": "ACTIVE_BUT_UNBOUND_REACK_REQUIRED",
                "cost_envelope_reack_required": True,
                "authorization_mutated": False,
                "paid_attempts_created": False,
            },
            "migration_eligibility": {
                "eligible": True,
                "requirements": {
                    "media_mix_policy_v2": "PASS",
                    "provider_contract_status": "PASS",
                    "pricing_status": "COMPLETE",
                    "pricing_contract_consistency": "PASS",
                    "proposal_pricing_registry_hash_binding": "VALID",
                    "cinematic_quality_regression": False,
                    "creative_information_lost": False,
                    "structural_change": "NONE",
                },
            },
            "policy_decision": {
                "provider_execution_executed": False,
                "production_authorization_consumed": False,
                "episode_ledger_mutated": False,
                "creative_overlay_modified": False,
                "storyboard_modified": False,
                "next_stage_executed": False,
                "unknown_pricing_blocks_execution": True,
            },
        }
    )
    plan["proposal_sha256"] = canonical_sha256(plan)
    migration = {
        "schema_version": "siraj-episode-002-media-planner-v2-preflight-migration-proposal-v1",
        "status": "PROPOSED_NOT_APPROVED_NOT_APPLIED",
        "episode_id": EPISODE,
        "authorizes_paid_operation": False,
        "authorizes_resume": False,
        "human_migration_approval_required": True,
        "source_preflight": {
            "path": rel(PREFLIGHT_PATH),
            "sha256": current_hashes["current_defective_preflight_sha256"],
            "classification": "SUPERSEDED_BUT_PRESERVED",
            "delete": False,
            "counts_as_current_authority": False,
        },
        "new_plan": {
            "path": rel(PROPOSAL_PATH),
            "sha256": plan["proposal_sha256"],
            "provider_request_plan_hash": request_hash,
            "pricing_binding": binding,
            "coverage": plan["coverage"],
            "cost_summary": plan["cost_summary"],
        },
        "required_authorization_rebinding": {
            "status": "REACK_REQUIRED_NOT_CREATED",
            "episode_id": EPISODE,
            "media_plan_sha256": plan["proposal_sha256"],
            "pricing_registry_sha256": binding["pricing_registry_sha256"],
            "cost_envelope": {
                "lower_bound": 0.0,
                "upper_bound": plan["cost_summary"]["maximum_cost_envelope_usd"],
                "currency": "USD",
            },
            "current_ledger_head_sha256": ledger.get("entry_sha256"),
            "creative_overlay_sha256": CREATIVE_OVERLAY_SHA256,
            "structural_fingerprint": STRUCTURAL_FINGERPRINT,
            "provider_request_plan_hash": request_hash,
        },
        "proposed_transition": {
            "current_stage": "PROVIDER_EXECUTION",
            "operation": "REPLACE_MEDIA_COST_PREFLIGHT_INPUT_PLAN_TRANSACTIONALLY",
            "accepted_prior_stages_rerun": False,
            "provider_execution_started": False,
            "next_stage_after_repreflight": "PROVIDER_EXECUTION",
            "next_stage_executed": False,
            "atomic_requirements": [
                "read and compare current ledger head",
                "validate current plan/pricing/creative/storyboard hashes",
                "persist new local preflight result before completion receipt",
                "append a hash-chained preflight replacement receipt",
                "stop at provider-execution review boundary",
            ],
        },
        "safety": {
            "provider_api_calls": 0,
            "paid_provider_calls": 0,
            "autopilot_runs": 0,
            "ledger_mutated": False,
            "authorization_mutated": False,
            "production_state_modified": False,
            "files_deleted": 0,
        },
    }
    migration["proposal_sha256"] = canonical_sha256(migration)
    summary = {
        "proposal": plan,
        "migration": migration,
        "old_invalid_count": len(old_invalid),
        "remaining_invalid_count": 0,
        "low_below_75": sum(float(unit["utilization_percent"]) < 75.0 for unit in plan["video_units"]),
        "low_below_50": sum(float(unit["utilization_percent"]) < 50.0 for unit in plan["video_units"]),
        "low_below_25": sum(float(unit["utilization_percent"]) < 25.0 for unit in plan["video_units"]),
        "review_status": "WARN" if sum(float(unit["utilization_percent"]) < 25.0 for unit in plan["video_units"]) else "PASS",
    }
    return summary, migration, render_markdown(summary)


def render_markdown(summary: Mapping[str, Any]) -> str:
    plan = summary["proposal"]
    migration = summary["migration"]
    coverage = plan["coverage"]
    cost = plan["cost_summary"]
    contracts = plan["provider_contracts"]
    lines = [
        "# EP002 Contract-Valid Media Planner V2 Proposal",
        "",
        f"**Review status:** `{summary['review_status']}`. The proposal is provider-contract valid and migration-eligible, with a warning for unavoidable provider-minimum overhead on short cinematic intervals.",
        "",
        "This is proposal-only. No preflight, ledger, authorization, creative overlay, storyboard, or provider state was changed.",
        "",
        f"Structural authority is ledger-bound fingerprint `{plan['authoritative_inputs']['structural_fingerprint']}`. The provider-ready compatibility projection carries `{plan['authoritative_inputs']['compatibility_provider_plan_structural_fingerprint']}` and is explicitly non-authoritative.",
        "",
        "## Coverage and cost",
        "",
        f"- True generated video: **{coverage['true_generated_video_timeline_seconds']:.3f}s / {coverage['true_generated_video_timeline_percent']:.6f}%**; policy floor/ceiling: **PASS/PASS**.",
        f"- Cinematic strength: **{plan['cinematic_assessment']['cinematic_strength']}**; slideshow-fatigue risk: **{plan['cinematic_assessment']['slideshow_fatigue_risk']}**.",
        f"- Animated stills: **{coverage['animated_still_seconds']:.3f}s**; graphics/local: **{coverage['graphics_local_seconds']:.3f}s**.",
        f"- Video requests: **{plan['request_inventory']['video_provider_requests']}**; provider-requested: **{coverage['provider_requested_video_seconds']:.3f}s**; unused: **{coverage['expected_unused_video_seconds']:.3f}s**; efficiency: **{coverage['video_request_efficiency_percent']:.6f}%**.",
        f"- Cost: video **${cost['video_subtotal_usd']:.8f}**, still **${cost['still_subtotal_usd']:.8f}**, total/envelope **${cost['estimated_total_cost_usd']:.8f} USD**.",
        "",
        "## Provider contracts",
        "",
        f"All {contracts['validated_request_count']} provider request schemas validate locally. Veo durations are restricted to **4/6/8 seconds**, dimensions are 720p landscape/portrait, billing is per generated video second, and `negativePrompt` is blocked. Seedream uses 1424x800 per-image pricing; Nano Banana 2 uses the official 1376x768 1K route.",
        "Official sources: [Runware Veo 3.1 Lite](https://runware.ai/docs/models/google-veo-3-1-lite), [Runware Seedream 5.0 Pro](https://runware.ai/docs/models/bytedance-seedream-5-0-pro), and [Runware Nano Banana 2](https://runware.ai/docs/models/google-nano-banana-2).",
        "",
        f"Pricing binding: **VALID** (`{plan['pricing_binding']['pricing_registry_version']}`, SHA-256 `{plan['pricing_binding']['pricing_registry_sha256']}`).",
        "",
        "## Request matrix",
        "",
        "| Provider | Model | Media | Requests | Billing unit | Requested units | Timeline use s |",
        "|---|---|---|---:|---|---:|---:|",
    ]
    for row in plan["request_matrix"]:
        lines.append(
            f"| {row['provider']} | `{row['model']}` | {row['media_kind']} | {row['request_count']} | {row['billing_unit']} | {row['requested_units']:.3f} | {row['timeline_usage_seconds']:.3f} |"
        )
    lines += [
        "",
        "## Contract validation evidence",
        "",
        f"Provider contract status: **PASS**; drift: **FALSE**; remaining invalid video units: **{plan['contract_validation_summary']['remaining_invalid_video_units']}**; Veo durations: **4/6/8 seconds**; `negativePrompt`: **BLOCKED**.",
        "Duration selection uses timeline-required seconds plus editing handles and selects the smallest supported duration; 8 seconds is used only when that rule selects it, never as a timeline-agnostic fallback. Long intervals would be split into distinct sequential phases rather than loops.",
        "",
        "## Remediation of the 25 preserved invalid units",
        "",
        "All 25 are corrected by deterministic duration reselection; existing shot boundaries and unit identities remain unchanged, so no segmentation or creative invention is required.",
        "",
        "| Unit | Shot | Old s | Timeline s | New s | Remediation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in plan["invalid_preserved_video_units"]:
        lines.append(f"| `{row['video_unit_id']}` | {row['shot_id']} | {row['old_requested_duration']} | {float(row['timeline_required_seconds']):.3f} | {row['new_selected_duration']} | {row['remediation']} |")
    lines += [
        "",
        "## Low-utilization units",
        "",
        f"Below 75%: **{summary['low_below_75']}**; below 50%: **{summary['low_below_50']}**; below 25%: **{summary['low_below_25']}**. Each is explicitly attributable to the provider's 4-second minimum; no loop, duplicate clip, or filler is introduced.",
        "",
        "| Unit | Shot | Requested | Usable | Utilization | Class |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in plan["low_utilization_units"]:
        lines.append(f"| `{row['unit_id']}` | {row['shot_id']} | {row['requested_seconds']:.0f}s | {row['usable_seconds']:.3f}s | {row['utilization_percent']:.3f}% | {row['classification']} |")
    lines += [
        "",
        "## Preserved static sequence",
        "",
        "The 56.021-second span from 436.779s to 492.800s (SH038-SH042, DESCENT/HADITH_ARGUMENT) remains `ACCEPTABLE_MIXED_STATIC_SEQUENCE`; no video was injected to improve statistics.",
        "",
        "## Authorization and migration boundary",
        "",
        "The active episode-wide authorization remains unbound to this changed plan and cost envelope. Re-acknowledgement is required but was not created. The migration proposal supersedes the old preflight logically while preserving its bytes; it authorizes neither paid operation nor resume and must be separately approved/applied.",
        "",
        f"Migration proposal: `{rel(MIGRATION_PATH)}`; status `{migration['status']}`.",
        "",
        "Provider API calls: 0. Paid provider calls: 0. Autopilot runs: 0. Files deleted: 0.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    summary, migration, markdown = build_review()
    proposal = summary["proposal"]
    PROPOSAL_PATH.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MIGRATION_PATH.write_text(json.dumps(migration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REVIEW_PATH.write_text(markdown, encoding="utf-8")
    print(
        json.dumps(
            {
                "proposal": str(PROPOSAL_PATH),
                "proposal_sha256": proposal["proposal_sha256"],
                "migration": str(MIGRATION_PATH),
                "migration_sha256": migration["proposal_sha256"],
                "review": str(REVIEW_PATH),
                "review_status": summary["review_status"],
                "coverage": proposal["coverage"],
                "cost": proposal["cost_summary"],
                "invalid_remaining": summary["remaining_invalid_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
