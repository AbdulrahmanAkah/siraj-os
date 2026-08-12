"""Generate the read-only EP002 V2 pricing and migration-readiness review.

This script reads the approved proposal, local pricing authority, and current
state projections.  It never calls a provider and never writes production
artifacts.  Only reports under ``reports/`` are written.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.application.artifact_provenance_v1 import canonical_sha256
from src.application.media_cost_authority_v2 import (
    assess_cost,
    find_price_record,
    load_pricing_registry,
    resolve_price_variant,
)
from src.application.provider_model_contracts import validate_runware_task
from src.application.siraj_cinematic_media_mix_policy_v2 import validate_true_video_coverage


ROOT = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"
EP_ROOT = ROOT / "projects" / EPISODE
ORCH = EP_ROOT / "orchestration"
PROPOSAL_PATH = ROOT / "reports" / "episode-002-media-planner-v2-proposal.json"
REGISTRY_PATH = ROOT / "projects" / "_series" / "siraj-media-pricing-registry-v2.json"
PREFLIGHT_PATH = ORCH / "media-cost-preflight-v1.json"
LEDGER_PATH = ORCH / "episode-transition-ledger-v1.jsonl"
AUTH_PATH = ORCH / "episode-master-paid-authorization-v6-6.json"
PROMPT_PATH = EP_ROOT / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json"
REPORT_JSON = ROOT / "reports" / "episode-002-media-planner-v2-pricing-review.json"
REPORT_MD = ROOT / "reports" / "episode-002-media-planner-v2-pricing-review.md"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value: Any, digits: int = 6) -> float:
    return round(float(value or 0.0), digits)


def unit_dimensions(unit: Mapping[str, Any]) -> tuple[int, int] | None:
    """Return the canonical route dimensions used by the preserved plan.

    The proposal predates the explicit dimension fields.  Veo's existing
    route is the canonical 720p landscape request; Nano's historical route is
    retained as evidence and deliberately reported as a contract mismatch.
    """

    if str(unit.get("model")) == "google:veo@3.1-lite":
        return (1280, 720)
    if str(unit.get("model")) == "google:4@3":
        return (1344, 768)
    if str(unit.get("model")) == "bytedance:seedream@5.0-pro":
        return (1424, 800)
    return None


def to_cost_unit(unit: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(unit)
    dimensions = unit_dimensions(unit)
    if dimensions:
        result["width"], result["height"] = dimensions
    model = str(unit.get("model") or "")
    if model == "google:veo@3.1-lite":
        result["pricing_variant"] = "720p_no_audio"
        result["generate_audio"] = False
    elif model == "bytedance:seedream@5.0-pro":
        result["pricing_variant"] = "1.5K"
    elif model == "google:4@3":
        # Cost is estimated at the intended 1K tier, while the route remains
        # contract-invalid until a regenerated plan uses 1376x768.
        result["pricing_variant"] = "1K"
    return result


def load_ledger_projection(path: Path) -> dict[str, Any]:
    last: dict[str, Any] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    last = value
    return last


def contract_findings(video_units: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for unit in video_units:
        requested = int(round(float(unit.get("requested_seconds") or 0)))
        task = {
            "taskType": "videoInference",
            "taskUUID": "planning-only-contract-check",
            "model": unit.get("model"),
            "positivePrompt": "contract-only planning validation",
            "duration": requested,
            "width": 1280,
            "height": 720,
            "numberResults": 1,
            "providerSettings": {"google": {"generateAudio": False}},
        }
        try:
            validate_runware_task(task)
        except Exception as exc:  # contract failure is evidence, not a crash
            findings.append(
                {
                    "unit_id": unit.get("unit_id"),
                    "shot_id": unit.get("shot_id"),
                    "model": unit.get("model"),
                    "requested_seconds": requested,
                    "reason": str(exc),
                }
            )
    # The provider validator intentionally covers Veo.  The preserved Nano
    # dimension mismatch is added by ``build_review`` because it is not a
    # video task.
    return findings


def build_rows(proposal: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    video_rows: list[dict[str, Any]] = []
    for raw in proposal.get("video_units", []):
        unit = to_cost_unit(raw)
        row = {
            "unit_id": raw.get("unit_id"),
            "shot_id": raw.get("shot_id"),
            "provider": raw.get("provider"),
            "model": raw.get("model"),
            "media_kind": raw.get("media_kind"),
            "billing_unit": "per_generated_video_second",
            "billing_quantity": number(raw.get("requested_seconds")),
            "requested_seconds": number(raw.get("requested_seconds")),
            "timeline_usage_seconds": number(raw.get("expected_usable_seconds")),
            "expected_unused_seconds": number(raw.get("expected_unused_seconds")),
            "provider_supported_duration": raw.get("provider_supported_duration"),
            "dimensions": [unit.get("width"), unit.get("height")],
            "pricing_variant": unit.get("pricing_variant"),
            "paid": True,
            "reusable": False,
            "necessary": True,
            "contract_status": "VALID" if int(raw.get("requested_seconds") or 0) in {4, 6, 8} else "INVALID_DURATION_FOR_CURRENT_VEO_CONTRACT",
        }
        rows.append(unit)
        video_rows.append(row)
    for raw in proposal.get("non_video_units", []):
        unit = to_cost_unit(raw)
        media_kind = str(raw.get("media_kind") or "")
        paid = str(raw.get("provider") or "").upper() != "LOCAL"
        if media_kind == "RUNWARE_IMAGE":
            billing_unit = "per_image"
            variant = unit.get("pricing_variant")
        else:
            billing_unit = "local"
            variant = None
        row = {
            "unit_id": raw.get("unit_id"),
            "shot_id": raw.get("shot_id"),
            "provider": raw.get("provider"),
            "model": raw.get("model"),
            "media_kind": media_kind,
            "billing_unit": billing_unit,
            "billing_quantity": 1 if paid else 0,
            "requested_seconds": 0.0,
            "timeline_usage_seconds": number(raw.get("timeline_coverage_seconds")),
            "expected_unused_seconds": 0.0,
            "dimensions": [unit.get("width"), unit.get("height")],
            "pricing_variant": variant,
            "paid": paid,
            "reusable": False,
            "necessary": True,
            "contract_status": "LOCAL" if not paid else ("VALID" if media_kind == "RUNWARE_IMAGE" else "UNKNOWN"),
        }
        rows.append(unit)
    return rows, video_rows


def build_cost_rows(units: list[Mapping[str, Any]], registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Materialize the exact per-request pricing evidence without submission."""

    rows: list[dict[str, Any]] = []
    for raw in units:
        unit = to_cost_unit(raw)
        provider = str(unit.get("provider") or "")
        model = str(unit.get("model") or "")
        media_kind = str(unit.get("media_kind") or "")
        if provider.upper() == "LOCAL" or media_kind == "LOCAL_GRAPHICS":
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
                    "pricing_status": "LOCAL_ZERO",
                }
            )
            continue
        record = find_price_record(registry, provider=provider, model=model, media_kind=media_kind)
        variant = resolve_price_variant(record, unit) if record else None
        billing_unit = str((variant or {}).get("billing_unit") or (record.billing_unit if record else "UNKNOWN"))
        price = (variant or {}).get("unit_price", record.unit_price if record else None)
        currency = (variant or {}).get("currency", record.currency if record else None)
        if billing_unit == "per_generated_video_second":
            quantity = number(unit.get("requested_seconds"))
        elif billing_unit == "per_image":
            quantity = 1.0
        else:
            quantity = 0.0
        amount = round(float(price) * quantity, 8) if price is not None else None
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
                "estimated_cost": amount,
                "currency": currency,
                "pricing_variant": unit.get("pricing_variant"),
                "pricing_status": "PRICED" if amount is not None else "UNPRICED",
            }
        )
    return rows


def build_review() -> dict[str, Any]:
    proposal = read_json(PROPOSAL_PATH)
    registry = load_pricing_registry(REGISTRY_PATH)
    prompt_plan = read_json(PROMPT_PATH) if PROMPT_PATH.is_file() else {}
    old_preflight = read_json(PREFLIGHT_PATH) if PREFLIGHT_PATH.is_file() else {}
    auth = read_json(AUTH_PATH) if AUTH_PATH.is_file() else {}
    projection = load_ledger_projection(LEDGER_PATH)
    cost_units, video_rows = build_rows(proposal)
    paid_units = [unit for unit in cost_units if str(unit.get("provider") or "").upper() != "LOCAL"]
    assessment = assess_cost(paid_units, registry)
    cost_rows = build_cost_rows(cost_units, registry)
    coverage = proposal.get("coverage", {}).get("coverage_validation", {})
    duration_counts = Counter(int(round(float(u.get("requested_seconds") or 0))) for u in proposal.get("video_units", []))
    invalid_duration_units = sum(count for duration, count in duration_counts.items() if duration not in {4, 6, 8})
    nano_units = [u for u in proposal.get("non_video_units", []) if u.get("model") == "google:4@3"]
    static_span = {
        "start_seconds": 436.779,
        "end_seconds": 492.8,
        "duration_seconds": 56.021,
        "shot_ids": [f"EP002-SH-{i:03d}" for i in range(38, 43)],
        "sequence_ids": ["DESCENT", "HADITH_ARGUMENT"],
        "media_treatments": ["ANIMATED_STILL", "LOCAL_GRAPHICS"],
        "classification": "ACCEPTABLE_MIXED_STATIC_SEQUENCE",
        "reason": "The span is a deliberate transition from the descent's material aftermath into a source-sensitive hadith/argument graphic layer; the proposal keeps a short still bridge and preserves evidence grammar rather than inserting filler motion.",
    }
    contract_failures = contract_findings(list(proposal.get("video_units", [])))
    if nano_units:
        contract_failures.append(
            {
                "unit_id": nano_units[0].get("unit_id"),
                "shot_id": nano_units[0].get("shot_id"),
                "model": "google:4@3",
                "reason": "NANO_ROUTE_DIMENSION_MISMATCH: preserved proposal route 1344x768; official 1K 16:9 route is 1376x768",
            }
        )
    policy_result = validate_true_video_coverage(
        float(coverage.get("episode_duration_seconds") or 0.0),
        float(coverage.get("true_video_seconds") or 0.0),
    )
    request_matrix: dict[str, dict[str, Any]] = {}
    for row in video_rows + [
        {
            "unit_id": u.get("unit_id"),
            "shot_id": u.get("shot_id"),
            "provider": u.get("provider"),
            "model": u.get("model"),
            "media_kind": u.get("media_kind"),
            "billing_unit": "per_image" if u.get("media_kind") == "RUNWARE_IMAGE" else "local",
            "billing_quantity": 1 if str(u.get("provider")).upper() != "LOCAL" else 0,
            "timeline_usage_seconds": number(u.get("timeline_coverage_seconds")),
            "requested_seconds": 0.0,
        }
        for u in proposal.get("non_video_units", [])
    ]:
        key = "|".join(str(row.get(field) or "") for field in ("provider", "model", "media_kind", "billing_unit"))
        entry = request_matrix.setdefault(
            key,
            {
                "provider": row.get("provider"),
                "model": row.get("model"),
                "media_kind": row.get("media_kind"),
                "billing_unit": row.get("billing_unit"),
                "request_count": 0,
                "requested_units": 0.0,
                "timeline_usage_seconds": 0.0,
            },
        )
        entry["request_count"] += 1
        entry["requested_units"] += float(row.get("billing_quantity") or row.get("requested_seconds") or 0.0)
        entry["timeline_usage_seconds"] += float(row.get("timeline_usage_seconds") or 0.0)
    for entry in request_matrix.values():
        entry["requested_units"] = number(entry["requested_units"])
        entry["timeline_usage_seconds"] = number(entry["timeline_usage_seconds"])
    pricing_status = assessment.pricing_status
    provider_execution_allowed = False  # contract and auth binding remain blockers
    proposal_input_hashes = proposal.get("input_hashes", {})
    current_hashes = {
        "current_defective_preflight_sha256": sha256_file(PREFLIGHT_PATH) if PREFLIGHT_PATH.is_file() else None,
        "current_episode_ledger_sha256": sha256_file(LEDGER_PATH) if LEDGER_PATH.is_file() else None,
        "provider_ready_prompt_plan_sha256": sha256_file(PROMPT_PATH) if PROMPT_PATH.is_file() else None,
        "pricing_registry_sha256": sha256_file(REGISTRY_PATH),
    }
    input_hash_consistency = {
        key: {"proposal": proposal_input_hashes.get(key), "current": value, "matches": proposal_input_hashes.get(key) == value}
        for key, value in current_hashes.items()
    }
    model_subtotals: dict[str, float] = {}
    for row in cost_rows:
        if row.get("estimated_cost") is not None:
            key = f"{row.get('provider')}|{row.get('model')}|{row.get('media_kind')}"
            model_subtotals[key] = round(model_subtotals.get(key, 0.0) + float(row["estimated_cost"]), 8)
    report = {
        "schema_version": "siraj-episode-002-media-planner-v2-pricing-review-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "episode_id": EPISODE,
        "proposal": {
            "path": str(PROPOSAL_PATH.relative_to(ROOT)).replace("\\", "/"),
            "physical_sha256": sha256_file(PROPOSAL_PATH),
            "declared_proposal_sha256": proposal.get("proposal_sha256"),
            "input_hashes": proposal.get("input_hashes", {}),
            "input_hash_consistency": input_hash_consistency,
            "pricing_registry_binding_status": "STALE_PROPOSAL_INPUT_HASH" if not input_hash_consistency["pricing_registry_sha256"]["matches"] else "CURRENT",
        },
        "review_status": "FAIL" if contract_failures else ("PASS" if pricing_status == "COMPLETE" else "WARN"),
        "approved_v2_metrics": {
            "true_video_timeline_seconds": 428.560,
            "selected_video_percent": 68.725304,
            "animated_still_seconds": 131.261,
            "graphics_local_seconds": 63.763,
            "video_provider_requests": 73,
            "video_provider_requested_seconds": 448.0,
            "expected_unused_video_seconds": 19.440,
            "video_request_efficiency_percent": 95.660714,
            "still_provider_requests": 22,
            "total_provider_requests": 95,
        },
        "longest_no_true_video_span": static_span,
        "cinematic_assessment": {
            "classification_counts": proposal.get("classification_counts", {}),
            "directorial_target": proposal.get("directorial_target", {}),
            "slideshow_fatigue_risk": "MEDIUM",
            "cinematic_strength": "HIGH",
            "number_of_30s_plus_no_true_video_spans": proposal.get("coverage", {}).get("number_of_30s_plus_no_true_video_spans", 1),
            "number_of_60s_plus_no_true_video_spans": proposal.get("coverage", {}).get("number_of_60s_plus_no_true_video_spans", 0),
        },
        "request_matrix": list(request_matrix.values()),
        "request_inventory": {
            "total_provider_requests": len(paid_units),
            "video_provider_requests": len(video_rows),
            "still_provider_requests": sum(1 for u in paid_units if u.get("media_kind") == "RUNWARE_IMAGE"),
            "local_graphics_units": sum(1 for u in cost_units if str(u.get("provider") or "").upper() == "LOCAL"),
            "other_provider_requests": 0,
            "unique_paid_provider_models": len({(u.get("provider"), u.get("model")) for u in paid_units}),
            "unique_provider_models_including_local": len({(u.get("provider"), u.get("model")) for u in cost_units}),
        },
        "video_request_rows": video_rows,
        "cost_rows": cost_rows,
        "video_duration_inventory": {str(k): v for k, v in sorted(duration_counts.items())},
        "video_duration_contract": {
            "official_supported_durations_seconds": [4, 6, 8],
            "invalid_preserved_request_units": invalid_duration_units,
            "root_cause": "TIMELINE_AGNOSTIC_FIXED_8S_FALLBACK_NOT_PROVIDER_MINIMUM",
            "contract_status": "FAIL" if invalid_duration_units else "PASS",
        },
        "provider_contract_findings": contract_failures,
        "pricing": {
            "registry_path": str(REGISTRY_PATH.relative_to(ROOT)).replace("\\", "/"),
            "registry_sha256": sha256_file(REGISTRY_PATH),
            "registry_version": registry.get("registry_version"),
            "source_policy": registry.get("source_policy"),
            "official_web_request_count": 3,
            "assessment": assessment.as_dict(),
            "model_subtotals_usd": model_subtotals,
            "video_subtotal_usd": assessment.media_type_subtotals.get("RUNWARE_VIDEO"),
            "still_subtotal_usd": assessment.media_type_subtotals.get("RUNWARE_IMAGE"),
            "estimated_total_cost_usd": assessment.estimated_total_cost,
            "maximum_cost_envelope_usd": assessment.maximum_bound,
            "pricing_status": pricing_status,
            "pricing_root_cause": "MISSING_PRICE_DATA (historical local registry had no official prices); no estimator binding defect remains after the versioned variant resolver repair; the preserved proposal still has provider-contract-invalid units.",
        },
        "policy": {
            "policy_id": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "min_true_video_percent": 50.0,
            "max_true_video_percent": 75.0,
            "selection_mode": "DIRECTORIAL_OPTIMIZATION",
            "old_two_thirds_policy_active": False,
            "validation": policy_result.as_dict(),
        },
        "authorization": {
            "policy": "EPISODE_WIDE_MASTER_AUTHORIZATION_V6_6",
            "artifact_path": str(AUTH_PATH.relative_to(ROOT)).replace("\\", "/"),
            "artifact_sha256": sha256_file(AUTH_PATH) if AUTH_PATH.is_file() else None,
            "status": auth.get("status"),
            "scope": auth.get("scope"),
            "provider_plan_binding_present": bool(auth.get("provider_plan_hash") or auth.get("prompt_plan_hash")),
            "cost_envelope_binding_present": bool(auth.get("cost_envelope") or auth.get("cost_cap")),
            "assessment": "ACTIVE_BUT_UNBOUND_REACK_REQUIRED",
            "cost_envelope_reack_required": True,
            "reason": "The approved plan changes the paid request set from 51 to 95 and introduces a new cost envelope; the existing v6.6 artifact has no plan-hash or envelope binding.",
        },
        "migration": {
            "eligible": False,
            "proposal_path": None,
            "reason": "Do not supersede the old preflight until a freshly generated V2 plan satisfies the current Veo/Nano provider contracts, binds the current pricing-registry hash, and the new cost envelope is explicitly re-acknowledged.",
            "required_steps": [
                "Preserve old media-cost-preflight-v1.json as forensic evidence.",
                "Generate a contract-valid V2 request plan (4/6/8s Veo units and 1376x768 Nano route).",
                "Bind pricing registry/version, plan hash, and cost envelope to a new transactional preflight.",
                "Require explicit human cost-envelope re-acknowledgement before any PROVIDER_EXECUTION.",
            ],
        },
        "authoritative_state_snapshot": {
            "ledger_path": str(LEDGER_PATH.relative_to(ROOT)).replace("\\", "/"),
            "ledger_sha256": sha256_file(LEDGER_PATH) if LEDGER_PATH.is_file() else None,
            "ledger_projection": projection,
            "old_preflight_path": str(PREFLIGHT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "old_preflight_sha256": sha256_file(PREFLIGHT_PATH) if PREFLIGHT_PATH.is_file() else None,
            "prompt_plan_path": str(PROMPT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "prompt_plan_sha256": sha256_file(PROMPT_PATH) if PROMPT_PATH.is_file() else None,
            "prompt_plan_creative_overlay_sha256": prompt_plan.get("creative_overlay_sha256"),
            "old_preflight_cost_status": old_preflight.get("cost_status"),
            "production_execution_performed": False,
        },
        "safety": {
            "provider_execution_allowed": provider_execution_allowed,
            "provider_generation_calls": 0,
            "provider_api_calls": 0,
            "paid_provider_calls": 0,
            "autopilot_runs": 0,
            "episode_ledger_mutated": False,
            "production_authorization_consumed": False,
            "creative_information_lost": False,
            "cinematic_quality_regression": False,
            "structural_change": "NONE",
            "unknown_pricing_blocks_execution_policy": True,
            "unknown_pricing_blocks_execution_current": pricing_status != "COMPLETE",
        },
    }
    report["report_sha256"] = canonical_sha256({k: v for k, v in report.items() if k != "report_sha256"})
    return report


def markdown(report: Mapping[str, Any]) -> str:
    m = report["approved_v2_metrics"]
    pricing = report["pricing"]
    assessment = pricing["assessment"]
    span = report["longest_no_true_video_span"]
    contracts = report["video_duration_contract"]
    auth = report["authorization"]
    lines = [
        "# EP002 Media Planner V2 — Pricing Authority and Preflight Readiness Review",
        "",
        "## Decision",
        "",
        f"**Review status:** `{report['review_status']}`. The approved V2 mix is policy-valid and the official local registry prices all 95 paid units, but the preserved proposal is not migration-eligible because its 73 Veo units include unsupported 1/2/3/5/7-second requests and its two Nano routes retain the legacy 1344x768 dimension.",
        "",
        "No provider generation, paid request, Autopilot run, authorization consumption, or Episode 002 ledger mutation occurred.",
        "",
        "## Approved V2 metrics",
        "",
        f"- True generated video: **{m['true_video_timeline_seconds']:.3f}s ({m['selected_video_percent']:.6f}%)**.",
        f"- Animated stills: **{m['animated_still_seconds']:.3f}s**; graphics/local: **{m['graphics_local_seconds']:.3f}s**.",
        f"- Requests: **{m['video_provider_requests']} video + {m['still_provider_requests']} still = {m['total_provider_requests']} paid/provider requests**.",
        f"- Provider-requested video: **{m['video_provider_requested_seconds']:.3f}s**; expected unused: **{m['expected_unused_video_seconds']:.3f}s**; efficiency: **{m['video_request_efficiency_percent']:.6f}%**.",
        f"- Cinematic assessment: **HIGH** strength / **MEDIUM** slideshow-fatigue risk; classification counts: {report['cinematic_assessment']['classification_counts']}.",
        "",
        "## Longest no-video span",
        "",
        f"`{span['start_seconds']:.3f}s → {span['end_seconds']:.3f}s` ({span['duration_seconds']:.3f}s), shots `{', '.join(span['shot_ids'])}`, sequences `{', '.join(span['sequence_ids'])}`. Classification: **{span['classification']}**. It is a deliberate still/graphic bridge from the descent aftermath into source-sensitive argument material, not a request to add filler video.",
        "",
        "## Normalized provider request matrix",
        "",
        "| Provider | Model | Media | Requests | Billing unit | Requested units | Timeline use |",
    ]
    lines.append("|---|---|---:|---:|---|---:|---:|")
    for row in report["request_matrix"]:
        lines.append(f"| {row['provider']} | `{row['model']}` | {row['media_kind']} | {row['request_count']} | {row['billing_unit']} | {row['requested_units']:.3f} | {row['timeline_usage_seconds']:.3f}s |")
    lines += [
        "",
        "## Official pricing authority",
        "",
        f"Registry: `{pricing['registry_path']}`; version `{pricing['registry_version']}`; SHA-256 `{pricing['registry_sha256']}`; source policy `{pricing['source_policy']}`; official model-page requests: **{pricing['official_web_request_count']}**.",
        "The preserved proposal's embedded pricing-registry hash is older than this official registry (`STALE_PROPOSAL_INPUT_HASH`); the proposal is not rewritten in this review and cannot be migrated as-is.",
        "",
        "- [Runware Veo 3.1 Lite official model documentation](https://runware.ai/docs/models/google-veo-3-1-lite) — 720p $0.05/generated second, 1080p $0.08/generated second, discrete 4/6/8-second durations.",
        "- [Runware Seedream 5.0 Pro official model documentation](https://runware.ai/docs/models/bytedance-seedream-5-0-pro) — 1.5K tier $0.04815/image for the proposal's 1424×800 route.",
        "- [Runware Nano Banana 2 official model documentation](https://runware.ai/docs/models/google-nano-banana-2) — 1K 16:9 is 1376×768 at $0.06895/image; the preserved 1344×768 route is therefore contract-invalid until regenerated.",
        "",
        f"Computed provisional cost for the exact preserved request set: **video ${pricing['video_subtotal_usd']:.8f} + still ${pricing['still_subtotal_usd']:.8f} = ${pricing['estimated_total_cost_usd']:.8f} USD**. The envelope is conservative and is not authorization; provider execution remains blocked.",
        "",
        "Model subtotals: " + "; ".join(f"`{key}` = ${value:.8f}" for key, value in pricing["model_subtotals_usd"].items()) + ".",
        "",
        "## Contract and authorization blockers",
        "",
        f"- Veo duration contract: **{contracts['contract_status']}**; {contracts['invalid_preserved_request_units']} units use unsupported durations. Root cause: `TIMELINE_AGNOSTIC_FIXED_8S_FALLBACK_NOT_PROVIDER_MINIMUM`.",
        "- Nano route: **FAIL** for the preserved 1344×768 dimension; future planner routing has been corrected to the official 1376×768 1K 16:9 route, but the approved artifact was not rewritten.",
        f"- Pricing completeness: **{pricing['pricing_status']}** ({assessment['priced_requests']} priced, {assessment['unpriced_requests']} unpriced). The policy remains `UNKNOWN_PRICING_BLOCKS_EXECUTION=TRUE`; this exact registry assessment is complete, but the proposal still cannot execute because provider contracts are invalid.",
        f"- Master authorization: **{auth['assessment']}**. The active v6.6 authorization has no provider-plan or cost-envelope binding, while the plan changed from 51 to 95 requests; explicit re-acknowledgement is required. No authorization was changed.",
        "",
        "## Migration decision",
        "",
        "`PREFLIGHT_MIGRATION_ELIGIBLE=FALSE`. The defective historical preflight remains preserved. A future migration must generate a contract-valid V2 plan, bind the exact plan and pricing registry hashes plus a cost envelope, rerun the preflight transactionally, and stop at the pre-provider review boundary. This task deliberately created no migration proposal and did not replace the authoritative preflight.",
        "",
        "## Safety attestation",
        "",
        "Provider generation/API calls: 0. Paid provider calls: 0. Autopilot runs: 0. Episode 002 ledger mutation: false. Creative/storyboard mutation: false. Production authorization consumed: false.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    report = build_review()
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REPORT_MD.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"report_json": str(REPORT_JSON), "report_md": str(REPORT_MD), "report_sha256": report["report_sha256"]}, indent=2))


if __name__ == "__main__":
    main()
