"""Bounded live execution for an approved visual generation plan."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .visual_provider_v1 import (
    GEMINI_IMAGE_PROVIDER_ID,
    GeminiQuotaGuard,
    GeminiQuotaPolicy,
    ReferenceImagePackage,
    VisualAssetRequest,
    VisualGenerationRequest,
    VisualProvider,
    VisualProviderError,
    VisualQualityProfile,
    atomic_write_json,
    validate_generated_image,
    write_generated_image,
)


_TRANSIENT_PROVIDER_ERRORS = frozenset({
    "QUOTA_EXHAUSTED",
    "RATE_LIMITED",
    "API_TRANSIENT",
    "PROVIDER_UNAVAILABLE",
    "DAILY_LIMIT_REACHED",
})
_PERMANENT_REJECTION_ERRORS = frozenset({
    "SAFETY_BLOCK",
    "INVALID_PROMPT",
    "INVALID_ASSET",
    "RELIGIOUS_SAFETY_BLOCK",
    "HUMAN_REJECTION",
    "UNSUPPORTED_CONTENT",
})


_POLICY_KEYS = frozenset({
    "schema_version", "live_generation_enabled", "maximum_requests_per_run",
    "maximum_assets_per_run", "maximum_retries_per_asset",
    "maximum_primary_requests_per_run", "maximum_premium_requests_per_run",
    "maximum_economy_requests_per_run", "maximum_4k_requests_per_run",
    "stop_on_rate_limit", "stop_on_quota_exhaustion", "allow_model_escalation",
    "allow_cross_model_fallback", "default_model", "default_resolution",
    "default_aspect_ratio",
})


def load_gemini_quota_policy(path: Path | None) -> GeminiQuotaPolicy:
    if path is None:
        raise ValueError("GEMINI_QUOTA_POLICY_REQUIRED")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict) or set(value) - _POLICY_KEYS:
        raise ValueError("GEMINI_QUOTA_POLICY_INVALID")
    missing = {"schema_version", "live_generation_enabled", "maximum_requests_per_run", "maximum_assets_per_run", "maximum_retries_per_asset", "default_model", "default_resolution", "default_aspect_ratio"} - set(value)
    if missing or value.get("schema_version") != "1.0":
        raise ValueError("GEMINI_QUOTA_POLICY_INVALID")
    numeric = {key: value.get(key, 0) for key in _POLICY_KEYS if key.startswith("maximum_")}
    if any(not isinstance(item, int) or item < 0 for item in numeric.values()):
        raise ValueError("GEMINI_QUOTA_POLICY_LIMIT_INVALID")
    return GeminiQuotaPolicy(**{key: value[key] for key in value})


def _request_from_plan(value: dict[str, Any], *, live: bool, confirm_quota_use: bool, policy: GeminiQuotaPolicy) -> VisualGenerationRequest:
    # A no-escalation quota policy is authoritative for the bounded live run;
    # it never upgrades a ready asset to a premium model or 4K request.
    model = str(value["model"]) if policy.allow_model_escalation else policy.default_model
    resolution = str(value["resolution"]) if policy.allow_model_escalation else policy.default_resolution
    aspect_ratio = str(value["aspect_ratio"]) if policy.allow_model_escalation else policy.default_aspect_ratio
    profile = VisualQualityProfile(
        requested_resolution=resolution, aspect_ratio=aspect_ratio,
        name="MASTER_REFERENCE" if str(value["asset_id"]).startswith("master-") else "STANDARD_FINAL",
        hero=False, human_review_required=True,
    )
    asset = VisualAssetRequest(
        asset_id=str(value["asset_id"]),
        scene_id="MASTER_REFERENCE" if str(value["asset_id"]).startswith("master-") else str(value.get("scene_id", "UNKNOWN")),
        shot_id=str(value["asset_id"]), timeline_start_ms=0, timeline_end_ms=0,
        asset_type="MASTER_REFERENCE" if str(value["asset_id"]).startswith("master-") else "GENERATED_IMAGE",
        priority="REQUIRED", prompt=str(value["prompt"]), prompt_version=str(value["prompt_version"]),
        quality_profile=profile, references=ReferenceImagePackage(),
        dependency_asset_ids=tuple(value.get("dependencies", [])),
    )
    return VisualGenerationRequest(asset, str(value["provider"]), model, live=live, confirm_quota_use=confirm_quota_use)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_status(record: dict[str, Any]) -> str:
    return str(record.get("current_status") or record.get("status") or "PLANNED")


def _current_errors(record: dict[str, Any]) -> list[str]:
    errors = record.get("current_errors", record.get("errors", []))
    return [str(item) for item in errors] if isinstance(errors, list) else []


def _append_attempt_history(record: dict[str, Any], *, status: str, errors: list[str], event: str) -> None:
    history = record.get("attempt_history")
    if not isinstance(history, list):
        history = []
    entry = {
        "event": event,
        "status": status,
        "errors": list(errors),
        "provider_error": record.get("last_provider_error") or (errors[0] if errors else None),
        "model": record.get("last_attempt_model") or record.get("model"),
        "timestamp": record.get("last_attempt_timestamp") or _utc_timestamp(),
    }
    history.append(entry)
    record["attempt_history"] = history
    record["last_attempt"] = entry


def _is_permanent_rejection(record: dict[str, Any]) -> bool:
    status = _current_status(record)
    errors = set(_current_errors(record))
    approval = str(record.get("approval_status", ""))
    return approval in {"HUMAN_REJECTED", "REJECTED"} or status == "REJECTED" and bool(errors & _PERMANENT_REJECTION_ERRORS)


def reset_transient_visual_state_for_run(
    registry: list[dict[str, Any]],
    request_map: dict[str, dict[str, Any]],
    *,
    policy: GeminiQuotaPolicy,
    live: bool,
    confirm_quota_use: bool,
    api_key_present: bool,
) -> list[str]:
    """Make prior transient provider outcomes retryable in a new authorized run.

    A visual record's current state is intentionally separate from its append-only
    attempt history.  Provider availability is run-scoped; policy/safety/human
    rejections remain persistent and are never reset here.
    """
    if not (live and confirm_quota_use and policy.live_generation_enabled and api_key_present):
        return []
    reset: list[str] = []
    for record in registry:
        asset_id = str(record.get("asset_id", ""))
        if asset_id not in request_map or _is_permanent_rejection(record):
            continue
        status = _current_status(record)
        errors = _current_errors(record)
        if status in {"REJECTED", "RETRYABLE_PROVIDER_FAILURE", "PROVIDER_BLOCKED"} and set(errors) & _TRANSIENT_PROVIDER_ERRORS:
            _append_attempt_history(record, status=status, errors=errors, event="PRIOR_TRANSIENT_FAILURE_PRESERVED")
            record.update({
                "status": "READY_TO_GENERATE",
                "current_status": "READY_TO_GENERATE",
                "errors": [],
                "current_errors": [],
                "last_provider_error": None,
                "last_attempt_model": None,
                "last_attempt_timestamp": None,
                "retry_count": 0,
                "cache_status": "TRANSIENT_FAILURE_RETRYABLE",
            })
            reset.append(asset_id)
    return reset


def visual_cache_disposition(record: dict[str, Any], project_root: Path) -> str:
    """Classify cache entries without treating transient provider failures as hits."""
    if _is_permanent_rejection(record):
        return "PERMANENT_REJECTION"
    if set(_current_errors(record)) & _TRANSIENT_PROVIDER_ERRORS:
        return "TRANSIENT_FAILURE_RETRYABLE"
    output_path, expected_hash = record.get("output_path"), record.get("file_hash")
    if isinstance(output_path, str) and isinstance(expected_hash, str):
        candidate = (project_root / output_path).resolve(strict=False)
        try:
            candidate.relative_to(project_root)
        except ValueError:
            return "INCOMPLETE_ATTEMPT"
        from .visual_generation_director_v1 import visual_asset_cache_valid
        if visual_asset_cache_valid(record, project_root):
            return "SUCCESSFUL_IMMUTABLE_RESULT"
    return "INCOMPLETE_ATTEMPT"


def _model_role(model_id: str) -> str:
    if model_id == "gemini-3.1-flash-image":
        return "ACTIVE_PRIMARY"
    if model_id == "gemini-3-pro-image":
        return "PREMIUM_QUALITY"
    return "ECONOMY"


def _apply_current_policy_to_record(record: dict[str, Any], request: VisualGenerationRequest) -> None:
    """Persist the live policy decision rather than stale dry-run routing metadata."""
    record.update({
        "model": request.model_id,
        "selected_model": request.model_id,
        "model_role": _model_role(request.model_id),
        "resolution": request.asset.quality_profile.requested_resolution,
        "aspect_ratio": request.asset.quality_profile.aspect_ratio,
        "policy_model_override": True,
    })


def execute_visual_plan(
    plan_path: Path, project_root: Path, provider: VisualProvider, *, quota_policy: GeminiQuotaPolicy,
    live: bool, confirm_quota_use: bool, maximum_assets: int | None = None,
    maximum_requests: int | None = None, maximum_retries: int | None = None,
) -> dict[str, Any]:
    """Generate only ready assets, with no hidden retry or model fallback."""
    plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
    if plan.get("provider") != GEMINI_IMAGE_PROVIDER_ID or provider.provider_id != GEMINI_IMAGE_PROVIDER_ID:
        raise ValueError("VISUAL_PROVIDER_SELECTION_INVALID")
    policy = replace(
        quota_policy,
        maximum_assets_per_run=maximum_assets if maximum_assets is not None else quota_policy.maximum_assets_per_run,
        maximum_requests_per_run=maximum_requests if maximum_requests is not None else quota_policy.maximum_requests_per_run,
        maximum_retries_per_asset=maximum_retries if maximum_retries is not None else quota_policy.maximum_retries_per_asset,
    )
    guard = GeminiQuotaGuard(policy, explicit_live_confirmation=confirm_quota_use)
    registry = plan.get("assets", [])
    request_map = {str(item["asset_id"]): item for item in plan.get("requests", [])}
    api_key_present = bool(getattr(provider, "api_key_present", lambda: True)())
    reset_transient_visual_state_for_run(
        registry, request_map, policy=policy, live=live,
        confirm_quota_use=confirm_quota_use, api_key_present=api_key_present,
    )
    ready = [item for item in registry if _current_status(item) == "READY_TO_GENERATE" and str(item.get("asset_id")) in request_map]
    ready.sort(key=lambda item: (0 if str(item.get("asset_id", "")).startswith("master-") else 1, str(item.get("asset_id", ""))))
    selected = ready[:policy.maximum_assets_per_run]
    generated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    stopped_reason: str | None = None
    requests_succeeded = 0
    requests_failed = 0
    for record in selected:
        request = _request_from_plan(request_map[str(record["asset_id"])], live=live, confirm_quota_use=confirm_quota_use, policy=policy)
        _apply_current_policy_to_record(record, request)
        try:
            guard.authorize(request, api_key_present=api_key_present)
        except VisualProviderError as error:
            guard.record_error(error); stopped_reason = error.code
            rejected.append({"asset_id": request.asset.asset_id, "error": error.code})
            break
        attempts = 0
        while True:
            guard.record_attempt(request.model_id)
            try:
                response = provider.generate(request)
                output = write_generated_image(response, project_root / "working" / "visual-provider-v1" / "generated" / request.asset.asset_id)
                validation = validate_generated_image(Path(output["path"]), required_aspect_ratio=request.asset.quality_profile.aspect_ratio)
                if validation.status != "PASS":
                    raise VisualProviderError("GENERATED_IMAGE_TECHNICAL_VALIDATION_FAILED")
                record.update({
                    "status": "GENERATED", "current_status": "GENERATED", "current_errors": [], "errors": [],
                    "last_provider_error": None, "last_attempt_model": response.model_id,
                    "last_attempt_timestamp": _utc_timestamp(),
                    "output_path": str(Path(output["path"]).relative_to(project_root)).replace("\\", "/"),
                    "file_hash": output["sha256"], "dimensions": {"width": output["width"], "height": output["height"]},
                    "provider": response.provider_id, "model": response.model_id,
                    "usage_metadata": response.usage_metadata, "provider_request_id": response.provider_request_id,
                    "finish_reason": response.finish_reason, "retry_count": attempts,
                    "approval_status": "HUMAN_REVIEW_REQUIRED", "visual_human_review": "REQUIRED",
                    "visual_automated_content_review": "NOT_RUN_REQUEST_LIMIT_ONE",
                    "technical_validation": {"status": validation.status, "mime_type": validation.mime_type, "width": validation.width, "height": validation.height, "sha256": validation.sha256, "errors": list(validation.errors)},
                    "render_readiness": "READY_PENDING_HUMAN_APPROVAL",
                    "cache_status": "SUCCESSFUL_IMMUTABLE_RESULT",
                })
                _append_attempt_history(record, status="GENERATED", errors=[], event="GENERATION_SUCCEEDED")
                guard.record_success(); requests_succeeded += 1
                generated.append({"asset_id": request.asset.asset_id, "scene_id": request.asset.scene_id, "shot_id": request.asset.shot_id, "model_id": response.model_id, **output})
                break
            except VisualProviderError as error:
                guard.record_error(error); requests_failed += 1
                rate_or_quota = error.code in {"RATE_LIMITED", "QUOTA_EXHAUSTED", "DAILY_LIMIT_REACHED"}
                if error.retryable and not rate_or_quota and attempts < policy.maximum_retries_per_asset:
                    attempts += 1; guard.record_retry(); continue
                is_permanent = error.code in _PERMANENT_REJECTION_ERRORS
                outcome = "REJECTED" if is_permanent else "RETRYABLE_PROVIDER_FAILURE"
                record.update({
                    "status": outcome,
                    "current_status": outcome,
                    "errors": [error.code],
                    "current_errors": [error.code],
                    "last_provider_error": error.code,
                    "last_attempt_model": request.model_id,
                    "last_attempt_timestamp": _utc_timestamp(),
                    "retry_count": attempts,
                    "cache_status": "PERMANENT_REJECTION" if is_permanent else "TRANSIENT_FAILURE_RETRYABLE",
                })
                _append_attempt_history(record, status=outcome, errors=[error.code], event="GENERATION_FAILED")
                rejected.append({"asset_id": request.asset.asset_id, "error": error.code})
                stopped_reason = error.code
                break
        if stopped_reason:
            break
    if not selected:
        stopped_reason = "BLOCKED_BY_DEPENDENCY" if any(_current_status(item) == "BLOCKED_BY_DEPENDENCY" for item in registry) else "NO_READY_ASSET"
    report = guard.report(
        provider=GEMINI_IMAGE_PROVIDER_ID, model=policy.default_model, live_run=live,
        confirmation_received=confirm_quota_use, requests_succeeded=requests_succeeded,
        requests_failed=requests_failed, stopped_reason=stopped_reason,
    )
    report_path = project_root / "working" / "visual-provider-v1" / "production-visual-quota-report-v1.json"
    atomic_write_json(report_path, report)
    plan["assets"] = registry
    status = "PASS" if generated and not rejected else "PARTIAL" if generated else "FAIL"
    plan["live_execution"] = {
        "status": status, "generated": generated, "rejected": rejected,
        "stopped_reason": stopped_reason,
        "provider_error_code": guard.last_provider_error,
        "provider_error_category": guard.last_provider_error,
        "quota_status": guard.quota_status,
        "requests_attempted": guard.requests_used,
        "requests_succeeded": requests_succeeded,
        "requests_failed": requests_failed,
        "assets_generated": guard.assets_generated,
        "request_count": guard.requests_used, "retry_count": guard.retries_used,
        "quota_report": str(report_path.relative_to(project_root)).replace("\\", "/"),
        "quota_report_summary": report,
        "fallback_used": False,
    }
    atomic_write_json(plan_path, plan)
    assets_path = plan_path.parent / "production-visual-assets-v1.json"
    atomic_write_json(assets_path, {"schema_version": "siraj-production-visual-assets-v1", "assets": registry})
    manifest_path = project_root / "manifests" / "production-visual-provider-v1.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        manifest.update({
            "assets": registry,
            "generated_asset_count": len([item for item in registry if item.get("status") == "GENERATED"]),
            "quota_report": str(report_path.relative_to(project_root)).replace("\\", "/"),
            "live_execution": plan["live_execution"],
            "render_readiness": "READY_PENDING_HUMAN_APPROVAL" if generated else manifest.get("render_readiness"),
        })
        atomic_write_json(manifest_path, manifest)
    return plan["live_execution"]
