from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.application.local_video_production.visual_execution_v1 import (
    execute_visual_plan, load_gemini_quota_policy,
    reset_transient_visual_state_for_run, visual_cache_disposition,
)
from src.application.local_video_production.visual_generation_director_v1 import VisualGenerationConfig, build_visual_generation_plan, route_visual_asset
from src.application.local_video_production.visual_provider_v1 import (
    GEMINI_ECONOMY_IMAGE_MODEL, GEMINI_IMAGE_PROVIDER_ID, GEMINI_PREMIUM_IMAGE_MODEL,
    GEMINI_PRIMARY_IMAGE_MODEL, GeminiImageMissingApiKeyError, GeminiImageProvider,
    GeminiImageQuotaError, GeminiImageRateLimitError, GeminiQuotaGuard, GeminiQuotaGuardError,
    GeminiQuotaPolicy, ReferenceImagePackage, VisualAssetRequest, VisualGenerationRequest,
    VisualLiveGuardError, VisualQualityProfile, classify_gemini_image_error,
    image_dimensions, request_fingerprint, validate_generated_image,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + (1600).to_bytes(4, "big") + (900).to_bytes(4, "big") + b"\x08\x02\x00\x00\x00" + b"\x00\x00\x00\x00"


def _asset(asset_id: str = "asset-1") -> VisualAssetRequest:
    return VisualAssetRequest(asset_id, "scene-1", "shot-1", 0, 1000, "GENERATED_IMAGE", "REQUIRED", "Arabic source narrative without external call.", "v1", VisualQualityProfile(requested_resolution="1K"))


def _request(**kwargs: object) -> VisualGenerationRequest:
    values: dict[str, object] = {"asset": _asset(), "provider_id": GEMINI_IMAGE_PROVIDER_ID, "model_id": GEMINI_PRIMARY_IMAGE_MODEL, "live": True, "confirm_quota_use": True}
    values.update(kwargs)
    return VisualGenerationRequest(**values)  # type: ignore[arg-type]


class _Part:
    @staticmethod
    def from_bytes(**kwargs: object) -> dict[str, object]: return kwargs


class _Types:
    Part = _Part
    class GenerateContentConfig:
        def __init__(self, **kwargs: object) -> None: self.kwargs = kwargs
    class HttpOptions:
        def __init__(self, **kwargs: object) -> None: self.kwargs = kwargs
    class ImageConfig:
        def __init__(self, **kwargs: object) -> None: self.kwargs = kwargs


class _Client:
    def __init__(self, response: object | Exception) -> None:
        self.response, self.calls = response, []
        self.models = self
    def generate_content(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception): raise self.response
        return self.response


def _response(data: bytes = PNG, mime_type: str = "image/png") -> object:
    return SimpleNamespace(response_id="safe-id", usage_metadata=SimpleNamespace(prompt_token_count=3, candidates_token_count=4, total_token_count=7), candidates=[SimpleNamespace(finish_reason="STOP", content=SimpleNamespace(parts=[SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime_type))]))])


def _policy(**kwargs: object) -> GeminiQuotaPolicy:
    values: dict[str, object] = {"live_generation_enabled": True}
    values.update(kwargs)
    return GeminiQuotaPolicy(**values)  # type: ignore[arg-type]


def _storyboard_files(tmp_path: Path) -> tuple[Path, Path, Path]:
    storyboard = {"scenes": [{"scene_id": "scene-1", "location": "Baghdad", "shots": [{"scene_id": "scene-1", "shot_id": "shot-1", "narrative_function": "OPENING_HOOK", "transcript_span": "Baghdad.", "subject": "city", "action": "establish", "environment": {}, "composition": {}, "camera": {}, "lighting": {}, "continuity_requirements": {}, "factual_confidence": "PLAUSIBLE_RECONSTRUCTION", "reconstruction_status": "PLAUSIBLE_RECONSTRUCTION", "speculative_visual": True, "timing": {"start_ms": 0, "end_ms": 1000}, "transition_out": "CUT", "required_assets": [{"asset_id": "asset-1", "asset_type": "REUSABLE_ESTABLISHING_SHOT", "priority": "REQUIRED", "complexity": "MEDIUM", "reuse_allowed": True}]}]}]}
    characters, locations = {"characters": []}, {"locations": [{"location_id": "baghdad", "name": "Baghdad"}]}
    paths = (tmp_path / "storyboard.json", tmp_path / "characters.json", tmp_path / "locations.json")
    for path, data in zip(paths, (storyboard, characters, locations)): path.write_text(json.dumps(data), encoding="utf-8")
    return paths


def test_quota_guard_requires_live_confirmation_key_and_limits() -> None:
    guard = GeminiQuotaGuard(_policy(), explicit_live_confirmation=False)
    with pytest.raises(VisualLiveGuardError): guard.authorize(_request(), api_key_present=True)
    guard = GeminiQuotaGuard(_policy(), explicit_live_confirmation=True)
    with pytest.raises(GeminiImageMissingApiKeyError): guard.authorize(_request(), api_key_present=False)
    guard = GeminiQuotaGuard(_policy(), explicit_live_confirmation=True)
    guard.authorize(_request(), api_key_present=True); guard.record_attempt(GEMINI_PRIMARY_IMAGE_MODEL)
    with pytest.raises(GeminiQuotaGuardError): guard.authorize(_request(), api_key_present=True)


def test_only_primary_is_enabled_and_quota_unknown_is_explicit() -> None:
    guard = GeminiQuotaGuard(_policy(), explicit_live_confirmation=True)
    with pytest.raises(GeminiQuotaGuardError): guard.authorize(_request(model_id=GEMINI_PREMIUM_IMAGE_MODEL), api_key_present=True)
    assert guard.quota_status == "MODEL_LIMIT_REACHED" and guard.quota_remaining == "UNKNOWN"


def test_error_mapping_rate_quota_and_no_retry_flags() -> None:
    assert isinstance(classify_gemini_image_error(RuntimeError("429 rate")), GeminiImageRateLimitError)
    assert isinstance(classify_gemini_image_error(RuntimeError("quota exhausted")), GeminiImageQuotaError)
    assert not GeminiImageRateLimitError().retryable and not GeminiImageQuotaError().fallback_eligible


def test_provider_uses_structured_image_config_and_never_calls_without_confirmation() -> None:
    client = _Client(_response())
    provider = GeminiImageProvider(client=client, types_module=_Types(), environment={})
    with pytest.raises(VisualLiveGuardError): provider.generate(_request(confirm_quota_use=False))
    result = provider.generate(_request())
    assert result.mime_type == "image/png" and client.calls[0]["config"].kwargs["response_modalities"] == ["IMAGE"]
    assert client.calls[0]["config"].kwargs["image_config"].kwargs == {"aspect_ratio": "16:9", "image_size": "1K"}


def test_image_validation_and_request_cache_key_are_deterministic(tmp_path: Path) -> None:
    image = tmp_path / "asset.png"; image.write_bytes(PNG)
    assert validate_generated_image(image).status == "PASS"
    first = request_fingerprint(_request(), style_bible_fingerprint="a", character_bible_fingerprint="b", location_bible_fingerprint="c", storyboard_fingerprint="d", config_fingerprint="e")
    changed = request_fingerprint(_request(model_id=GEMINI_ECONOMY_IMAGE_MODEL), style_bible_fingerprint="a", character_bible_fingerprint="b", location_bible_fingerprint="c", storyboard_fingerprint="d", config_fingerprint="e")
    assert first != changed and image_dimensions(PNG, "image/png") == (1600, 900)


def test_policy_loader_rejects_financial_fields_and_accepts_quota_policy(tmp_path: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"schema_version": "1.0", "live_generation_enabled": True, "maximum_requests_per_run": 1, "maximum_assets_per_run": 1, "maximum_retries_per_asset": 0, "maximum_primary_requests_per_run": 1, "maximum_premium_requests_per_run": 0, "maximum_economy_requests_per_run": 0, "maximum_4k_requests_per_run": 0, "stop_on_rate_limit": True, "stop_on_quota_exhaustion": True, "allow_model_escalation": False, "allow_cross_model_fallback": False, "default_model": GEMINI_PRIMARY_IMAGE_MODEL, "default_resolution": "1K", "default_aspect_ratio": "16:9"}), encoding="utf-8")
    assert load_gemini_quota_policy(policy).maximum_requests_per_run == 1
    policy.write_text('{"maximum_total_cost_usd": 1}', encoding="utf-8")
    with pytest.raises(ValueError): load_gemini_quota_policy(policy)


def test_plan_is_offline_and_live_execution_uses_one_fake_primary_request(tmp_path: Path) -> None:
    storyboard, characters, locations = _storyboard_files(tmp_path)
    result = build_visual_generation_plan(storyboard, characters, locations, tmp_path / "working" / "visual-provider-v1", tmp_path / "manifest.json")
    plan = json.loads(result.plan_path.read_text(encoding="utf-8"))
    assert plan["status"] == "DRY_RUN_ONLY" and plan["network_calls"] == 0 and "cost_estimate" not in plan
    provider = GeminiImageProvider(client=_Client(_response()), types_module=_Types(), environment={})
    execution = execute_visual_plan(result.plan_path, tmp_path, provider, quota_policy=_policy(), live=True, confirm_quota_use=True, maximum_assets=1, maximum_requests=1, maximum_retries=0)
    assert execution["status"] == "PASS" and execution["request_count"] == 1 and execution["fallback_used"] is False
    report = json.loads((tmp_path / "working" / "visual-provider-v1" / "production-visual-quota-report-v1.json").read_text(encoding="utf-8"))
    assert report["assets_generated"] == 1 and report["quota_remaining"] == "UNKNOWN"
    master = next(item for item in execution["generated"] if item["asset_id"].startswith("master-location-"))
    assert master["model_id"] == GEMINI_PRIMARY_IMAGE_MODEL


def test_stale_transient_failure_is_reset_and_history_is_preserved(tmp_path: Path) -> None:
    registry = [{"asset_id": "master-location-baghdad", "status": "REJECTED", "errors": ["QUOTA_EXHAUSTED"], "model": GEMINI_PREMIUM_IMAGE_MODEL}]
    requests = {"master-location-baghdad": {"asset_id": "master-location-baghdad"}}
    reset = reset_transient_visual_state_for_run(registry, requests, policy=_policy(), live=True, confirm_quota_use=True, api_key_present=True)
    record = registry[0]
    assert reset == ["master-location-baghdad"]
    assert record["status"] == record["current_status"] == "READY_TO_GENERATE"
    assert record["errors"] == record["current_errors"] == []
    assert record["attempt_history"][0]["errors"] == ["QUOTA_EXHAUSTED"]
    assert record["last_provider_error"] is None
    assert visual_cache_disposition(record, tmp_path) == "INCOMPLETE_ATTEMPT"


def test_stale_rate_limit_is_retryable_but_permanent_rejections_remain_blocked() -> None:
    transient = [{"asset_id": "master-a", "status": "REJECTED", "errors": ["RATE_LIMITED"]}]
    permanent = [{"asset_id": "master-b", "status": "REJECTED", "errors": ["SAFETY_BLOCK"]}, {"asset_id": "master-c", "status": "REJECTED", "errors": ["HUMAN_REJECTION"]}]
    request_map = {"master-a": {}, "master-b": {}, "master-c": {}}
    assert reset_transient_visual_state_for_run(transient + permanent, request_map, policy=_policy(), live=True, confirm_quota_use=True, api_key_present=True) == ["master-a"]
    assert transient[0]["status"] == "READY_TO_GENERATE"
    assert [item["status"] for item in permanent] == ["REJECTED", "REJECTED"]


def test_current_policy_overrides_stale_premium_model_and_keeps_dependents_blocked(tmp_path: Path) -> None:
    storyboard, characters, locations = _storyboard_files(tmp_path)
    plan_result = build_visual_generation_plan(storyboard, characters, locations, tmp_path / "working" / "visual-provider-v1", tmp_path / "manifest.json")
    plan = json.loads(plan_result.plan_path.read_text(encoding="utf-8"))
    master = next(item for item in plan["assets"] if item["asset_id"].startswith("master-location-"))
    master.update({"status": "REJECTED", "errors": ["QUOTA_EXHAUSTED"], "model": GEMINI_PREMIUM_IMAGE_MODEL, "model_role": "PREMIUM_QUALITY"})
    plan_result.plan_path.write_text(json.dumps(plan), encoding="utf-8")
    client = _Client(_response())
    execution = execute_visual_plan(plan_result.plan_path, tmp_path, GeminiImageProvider(client=client, types_module=_Types(), environment={}), quota_policy=_policy(maximum_premium_requests_per_run=0), live=True, confirm_quota_use=True, maximum_assets=1, maximum_requests=1, maximum_retries=0)
    updated = json.loads(plan_result.plan_path.read_text(encoding="utf-8"))
    master = next(item for item in updated["assets"] if item["asset_id"].startswith("master-location-"))
    dependent = next(item for item in updated["assets"] if not item["asset_id"].startswith("master-location-"))
    assert execution["status"] == "PASS" and client.calls[0]["model"] == GEMINI_PRIMARY_IMAGE_MODEL
    assert master["model"] == GEMINI_PRIMARY_IMAGE_MODEL and master["model_role"] == "ACTIVE_PRIMARY"
    assert master["approval_status"] == "HUMAN_REVIEW_REQUIRED"
    assert dependent["status"] == "BLOCKED_BY_DEPENDENCY"


def test_transient_failure_is_not_a_final_cache_hit_and_successful_cache_is_reusable(tmp_path: Path) -> None:
    transient = {"status": "RETRYABLE_PROVIDER_FAILURE", "current_errors": ["QUOTA_EXHAUSTED"]}
    assert visual_cache_disposition(transient, tmp_path) == "TRANSIENT_FAILURE_RETRYABLE"
    image = tmp_path / "generated.png"; image.write_bytes(PNG)
    successful = {"status": "GENERATED", "output_path": "generated.png", "file_hash": validate_generated_image(image).sha256}
    assert visual_cache_disposition(successful, tmp_path) == "SUCCESSFUL_IMMUTABLE_RESULT"


def test_execution_returns_top_level_quota_failure_context(tmp_path: Path) -> None:
    storyboard, characters, locations = _storyboard_files(tmp_path)
    plan_result = build_visual_generation_plan(storyboard, characters, locations, tmp_path / "working" / "visual-provider-v1", tmp_path / "manifest.json")
    provider = GeminiImageProvider(client=_Client(RuntimeError("quota exhausted")), types_module=_Types(), environment={})
    execution = execute_visual_plan(plan_result.plan_path, tmp_path, provider, quota_policy=_policy(), live=True, confirm_quota_use=True, maximum_assets=1, maximum_requests=1, maximum_retries=0)
    assert execution["status"] == "FAIL"
    assert execution["stopped_reason"] == "QUOTA_EXHAUSTED"
    assert execution["provider_error_code"] == execution["provider_error_category"] == "QUOTA_EXHAUSTED"
    assert execution["quota_status"] == "QUOTA_EXHAUSTED"
    assert execution["requests_attempted"] == 1
    assert execution["requests_succeeded"] == 0
    assert execution["requests_failed"] == 1
    assert execution["assets_generated"] == 0


def test_router_keeps_routes_but_runtime_policy_blocks_premium() -> None:
    hero = route_visual_asset({"asset_id": "a", "asset_type": "SHOT", "complexity": "HIGH", "priority": "REQUIRED"}, {"narrative_function": "OPENING_HOOK"}, VisualGenerationConfig())
    assert hero.selected_model == GEMINI_PREMIUM_IMAGE_MODEL


def test_cli_visual_run_flags_and_render_verify_remain_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.application import cli_v2
    monkeypatch.setattr(cli_v2, "verify_local_render", lambda *args, **kwargs: {"status": "VALID"})
    assert cli_v2.command_render_verify("project", "ffprobe", False)["status"] == "SUCCESS"
    args = cli_v2.build_parser().parse_args(["visual", "run", "--project-root", "project", "--quota-policy", "policy.json", "--live", "--confirm-quota-use", "--maximum-assets", "1", "--maximum-requests", "1", "--maximum-retries", "0"])
    assert args.confirm_quota_use and args.maximum_requests == 1


def test_visual_cli_exit_codes_are_truthful() -> None:
    from scripts.fast_track.run_gemini_visual_provider_v1 import execution_message, exit_code_for_execution, failure_reason_for_execution
    assert exit_code_for_execution({"status": "PASS"}) == 0
    assert exit_code_for_execution({"status": "FAIL", "stopped_reason": "QUOTA_EXHAUSTED"}) != 0
    assert exit_code_for_execution({"status": "FAIL", "stopped_reason": "BLOCKED_BY_DEPENDENCY"}) != 0
    assert execution_message({"status": "FAIL", "stopped_reason": "QUOTA_EXHAUSTED"}) == "FAIL: QUOTA_EXHAUSTED"
    assert execution_message({"status": "FAIL", "stopped_reason": "BLOCKED_BY_DEPENDENCY"}) == "FAIL: BLOCKED_BY_DEPENDENCY"
    assert execution_message({"status": "FAIL", "stopped_reason": "RATE_LIMITED"}) == "FAIL: RATE_LIMITED"
    assert execution_message({"status": "FAIL", "stopped_reason": "NO_READY_ASSET"}) == "FAIL: NO_READY_ASSET"
    assert execution_message({"status": "FAIL"}) == "FAIL: PROVIDER_FAILURE"
    assert failure_reason_for_execution({"status": "FAIL", "provider_error_category": "RATE_LIMITED"}) == "RATE_LIMITED"
    assert failure_reason_for_execution({"status": "FAIL", "quota_report_summary": {"stopped_reason": "QUOTA_EXHAUSTED"}}) == "QUOTA_EXHAUSTED"
