"""Governed VEO-video boundary.  It has no default live client."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Protocol
from pathlib import Path

ALLOWED_MODELS = frozenset({"VEO_3_1_LITE_1080P", "VEO_3_1_FAST_1080P"})


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VideoProviderPolicy:
    schema_version: str = "siraj-video-provider-policy-v1"
    provider: str = "GEMINI_VEO"
    maximum_final_generated_video_seconds: int = 300
    maximum_generated_seconds_without_additional_approval: int = 450
    absolute_generated_seconds_cap: int = 600
    allowed_models: tuple[str, ...] = ("VEO_3_1_LITE_1080P", "VEO_3_1_FAST_1080P")
    external_confirmation_required: bool = True
    disclosure_permission_required: bool = True
    request_limit: int = 0


class VideoClient(Protocol):
    def generate(self, request: dict[str, Any]) -> dict[str, Any]: ...


def validate_video_output(path: Path, *, expected_sha256: str) -> list[str]:
    """Technical contract only; content and historical safety remain human review."""
    if not path.is_file() or path.stat().st_size <= 0:
        return ["VIDEO_OUTPUT_MISSING_OR_EMPTY"]
    actual = sha256(path.read_bytes()).hexdigest()
    return [] if actual == expected_sha256 else ["VIDEO_OUTPUT_SHA256_MISMATCH"]


def validate_video_allocation(allocation: dict[str, Any], policy: VideoProviderPolicy) -> list[str]:
    errors: list[str] = []
    requests = allocation.get("requests")
    if not isinstance(requests, list):
        return ["VIDEO_ALLOCATION_REQUESTS_INVALID"]
    final_seconds = 0
    generated_seconds = 0
    for request in requests:
        if not isinstance(request, dict): errors.append("VIDEO_REQUEST_INVALID"); continue
        model = request.get("preferred_model")
        seconds = request.get("requested_duration_seconds")
        if model not in policy.allowed_models or model not in ALLOWED_MODELS: errors.append("VIDEO_MODEL_NOT_ALLOWED")
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0: errors.append("VIDEO_DURATION_INVALID"); continue
        if request.get("video_required") not in {"REQUIRED", "PREFERRED", "OPTIONAL", "NOT_NEEDED"}: errors.append("VIDEO_REQUIREMENT_INVALID")
        if not isinstance(request.get("video_justification"), str) or not request["video_justification"].strip(): errors.append("VIDEO_JUSTIFICATION_REQUIRED")
        if model == "VEO_3_1_FAST_1080P" and (not isinstance(request.get("video_justification"), str) or not request["video_justification"].strip()): errors.append("VIDEO_FAST_JUSTIFICATION_REQUIRED")
        final_seconds += seconds if request.get("video_required") == "REQUIRED" else 0
        generated_seconds += seconds
    if final_seconds > policy.maximum_final_generated_video_seconds: errors.append("POLICY_VALIDATION_ERROR:MAXIMUM_FINAL_GENERATED_VIDEO_SECONDS")
    if generated_seconds > policy.absolute_generated_seconds_cap: errors.append("POLICY_VALIDATION_ERROR:ABSOLUTE_GENERATED_SECONDS_CAP")
    if generated_seconds > policy.maximum_generated_seconds_without_additional_approval and not allocation.get("additional_approval"):
        errors.append("VIDEO_ADDITIONAL_APPROVAL_REQUIRED")
    return sorted(set(errors))


class VideoProviderV1:
    """Validates allocations and only calls an injected client after every live guard."""
    def __init__(self, policy: VideoProviderPolicy, client: VideoClient | None = None) -> None:
        self.policy, self.client = policy, client

    def execute(self, allocation: dict[str, Any], *, allow_external: bool, confirm_live: bool, credential_present: bool, disclosure_permitted: bool) -> dict[str, Any]:
        errors = validate_video_allocation(allocation, self.policy)
        if errors: return {"status": "PERMANENT_FAILURE", "errors": errors, "external_calls": 0}
        if not (allow_external and confirm_live and credential_present and disclosure_permitted and self.policy.request_limit > 0):
            return {"status": "BLOCKED_BY_EXTERNAL_PROVIDER", "blocker": "EXTERNAL_CONFIRMATION_REQUIRED", "retryable": True, "external_calls": 0}
        if self.client is None:
            return {"status": "NOT_IMPLEMENTED", "blocker": "VIDEO_CLIENT_DISCONNECTED", "external_calls": 0}
        outputs = []
        for request in allocation["requests"]:
            if request["video_required"] == "NOT_NEEDED": continue
            response = self.client.generate(request)
            if not response.get("path") or not response.get("sha256"):
                return {"status": "RETRYABLE_FAILURE", "blocker": "INVALID_RESPONSE", "external_calls": len(outputs) + 1, "outputs": outputs}
            outputs.append({"request_id": request["request_id"], "status": "HUMAN_REVIEW_REQUIRED", "model": request["preferred_model"], "duration_seconds": request["requested_duration_seconds"], "path": response["path"], "sha256": response["sha256"], "request_fingerprint": fingerprint(request)})
        return {"status": "COMPLETED", "outputs": outputs, "external_calls": len(outputs), "approval_status": "HUMAN_REVIEW_REQUIRED"}
