"""Provider-neutral, quota-guarded Gemini image generation contracts.

Planning and tests are fully offline.  A real image request needs an explicit
live acknowledgement and a bounded :class:`GeminiQuotaGuard` supplied by the
execution layer.  Runtime assets are written only to a project workspace.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from hashlib import sha256
import base64
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any


VISUAL_PROVIDER_SCHEMA_V1 = "siraj-visual-provider-v1"
GEMINI_IMAGE_PROVIDER_ID = "GEMINI_IMAGE"
GEMINI_PRIMARY_IMAGE_MODEL = "gemini-3.1-flash-image"
GEMINI_PREMIUM_IMAGE_MODEL = "gemini-3-pro-image"
GEMINI_ECONOMY_IMAGE_MODEL = "gemini-3.1-flash-lite-image"
GEMINI_LEGACY_IMAGE_MODEL = "gemini-2.5-flash-image"
SUPPORTED_GEMINI_IMAGE_MODELS = frozenset({
    GEMINI_PRIMARY_IMAGE_MODEL, GEMINI_PREMIUM_IMAGE_MODEL,
    GEMINI_ECONOMY_IMAGE_MODEL, GEMINI_LEGACY_IMAGE_MODEL,
})
SUPPORTED_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/webp"})
QUOTA_STATUSES = frozenset({
    "AVAILABLE", "UNKNOWN", "RATE_LIMITED", "QUOTA_EXHAUSTED",
    "DAILY_LIMIT_REACHED", "RUN_LIMIT_REACHED", "MODEL_LIMIT_REACHED",
    "LIVE_CONFIRMATION_REQUIRED", "API_KEY_MISSING",
})


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(text)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def redacted_text(value: object) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ")[-700:]
    return re.sub(r"AIza[0-9A-Za-z_-]{12,}", "[REDACTED_API_KEY]", text)


class VisualProviderError(RuntimeError):
    code = "VISUAL_PROVIDER_FAILURE"
    retryable = False
    fallback_eligible = False

    def __init__(self, detail: str = "") -> None:
        super().__init__(self.code if not detail else f"{self.code}:{redacted_text(detail)}")


class GeminiImageMissingApiKeyError(VisualProviderError):
    code = "API_KEY_MISSING"


class GeminiImageAuthenticationError(VisualProviderError):
    code = "API_KEY_INVALID"


class GeminiImagePermissionError(VisualProviderError):
    code = "PERMISSION_DENIED"


class GeminiImageModelUnavailableError(VisualProviderError):
    code = "MODEL_UNAVAILABLE"
    fallback_eligible = True


class GeminiImageInvalidRequestError(VisualProviderError):
    code = "INVALID_REQUEST"


class GeminiImageQuotaError(VisualProviderError):
    code = "QUOTA_EXHAUSTED"


class GeminiImageDailyLimitError(VisualProviderError):
    code = "DAILY_LIMIT_REACHED"


class GeminiImageRateLimitError(VisualProviderError):
    code = "RATE_LIMITED"


class GeminiImageTimeoutError(VisualProviderError):
    code = "TIMEOUT"
    retryable = True
    fallback_eligible = True


class GeminiImageServiceUnavailableError(VisualProviderError):
    code = "API_TRANSIENT"
    retryable = True
    fallback_eligible = True


class GeminiImageSafetyBlockedError(VisualProviderError):
    code = "SAFETY_BLOCK"


class GeminiImageInvalidResponseError(VisualProviderError):
    code = "INVALID_RESPONSE"


class VisualLiveGuardError(VisualProviderError):
    code = "LIVE_CONFIRMATION_REQUIRED"


class GeminiQuotaGuardError(VisualProviderError):
    code = "QUOTA_GUARD_BLOCKED"


def classify_gemini_image_error(error: Exception) -> VisualProviderError:
    text = f"{type(error).__name__}:{error}".lower()
    detail = redacted_text(error)
    if "daily" in text and ("limit" in text or "quota" in text):
        return GeminiImageDailyLimitError(detail)
    if "quota" in text or "resourceexhausted" in text:
        return GeminiImageQuotaError(detail)
    if "rate" in text or "429" in text:
        return GeminiImageRateLimitError(detail)
    if "api key" in text or "unauthenticated" in text or "401" in text:
        return GeminiImageAuthenticationError(detail)
    if "permission" in text or "forbidden" in text or "403" in text:
        return GeminiImagePermissionError(detail)
    if "safety" in text or "blocked" in text:
        return GeminiImageSafetyBlockedError(detail)
    if "model" in text and ("not found" in text or "unavailable" in text):
        return GeminiImageModelUnavailableError(detail)
    if "timeout" in text or "deadline" in text:
        return GeminiImageTimeoutError(detail)
    if "unavailable" in text or "503" in text or "500" in text:
        return GeminiImageServiceUnavailableError(detail)
    if "invalid" in text or "400" in text:
        return GeminiImageInvalidRequestError(detail)
    return VisualProviderError(detail)


@dataclass(frozen=True)
class GeminiQuotaPolicy:
    schema_version: str = "1.0"
    live_generation_enabled: bool = False
    maximum_requests_per_run: int = 1
    maximum_assets_per_run: int = 1
    maximum_retries_per_asset: int = 0
    maximum_primary_requests_per_run: int = 1
    maximum_premium_requests_per_run: int = 0
    maximum_economy_requests_per_run: int = 0
    maximum_4k_requests_per_run: int = 0
    stop_on_rate_limit: bool = True
    stop_on_quota_exhaustion: bool = True
    allow_model_escalation: bool = False
    allow_cross_model_fallback: bool = False
    default_model: str = GEMINI_PRIMARY_IMAGE_MODEL
    default_resolution: str = "1K"
    default_aspect_ratio: str = "16:9"


@dataclass
class GeminiQuotaGuard:
    policy: GeminiQuotaPolicy
    explicit_live_confirmation: bool = False
    requests_used: int = 0
    assets_generated: int = 0
    retries_used: int = 0
    model_request_counts: dict[str, int] = field(default_factory=dict)
    quota_status: str = "UNKNOWN"
    quota_remaining: str = "UNKNOWN"
    last_provider_error: str | None = None

    def _limit_for_model(self, model_id: str) -> int:
        if model_id == GEMINI_PRIMARY_IMAGE_MODEL:
            return self.policy.maximum_primary_requests_per_run
        if model_id == GEMINI_PREMIUM_IMAGE_MODEL:
            return self.policy.maximum_premium_requests_per_run
        return self.policy.maximum_economy_requests_per_run

    def authorize(self, request: "VisualGenerationRequest", *, api_key_present: bool) -> None:
        if not request.live or not self.explicit_live_confirmation or not self.policy.live_generation_enabled:
            self.quota_status = "LIVE_CONFIRMATION_REQUIRED"
            raise VisualLiveGuardError("EXPLICIT_LIVE_AND_CONFIRM_QUOTA_USE_REQUIRED")
        if not api_key_present:
            self.quota_status = "API_KEY_MISSING"
            raise GeminiImageMissingApiKeyError()
        if self.assets_generated >= self.policy.maximum_assets_per_run:
            self.quota_status = "RUN_LIMIT_REACHED"
            raise GeminiQuotaGuardError("MAXIMUM_ASSETS_PER_RUN")
        if self.requests_used >= self.policy.maximum_requests_per_run:
            self.quota_status = "RUN_LIMIT_REACHED"
            raise GeminiQuotaGuardError("MAXIMUM_REQUESTS_PER_RUN")
        if self.model_request_counts.get(request.model_id, 0) >= self._limit_for_model(request.model_id):
            self.quota_status = "MODEL_LIMIT_REACHED"
            raise GeminiQuotaGuardError("MAXIMUM_MODEL_REQUESTS_PER_RUN")
        if request.asset.quality_profile.requested_resolution == "4K" and self.model_request_counts.get(request.model_id, 0) >= self.policy.maximum_4k_requests_per_run:
            self.quota_status = "MODEL_LIMIT_REACHED"
            raise GeminiQuotaGuardError("MAXIMUM_4K_REQUESTS_PER_RUN")
        self.quota_status = "AVAILABLE"

    def record_attempt(self, model_id: str) -> None:
        self.requests_used += 1
        self.model_request_counts[model_id] = self.model_request_counts.get(model_id, 0) + 1

    def record_success(self) -> None:
        self.assets_generated += 1
        self.quota_status = "AVAILABLE"

    def record_retry(self) -> None:
        self.retries_used += 1

    def record_error(self, error: VisualProviderError) -> None:
        self.last_provider_error = error.code
        if error.code in QUOTA_STATUSES:
            self.quota_status = error.code
        elif error.code == "RATE_LIMITED":
            self.quota_status = "RATE_LIMITED"
        elif error.code == "QUOTA_EXHAUSTED":
            self.quota_status = "QUOTA_EXHAUSTED"
        elif error.code == "DAILY_LIMIT_REACHED":
            self.quota_status = "DAILY_LIMIT_REACHED"

    def report(self, *, provider: str, model: str, live_run: bool, confirmation_received: bool, requests_succeeded: int, requests_failed: int, stopped_reason: str | None) -> dict[str, Any]:
        return {
            "schema_version": "siraj-production-visual-quota-report-v1",
            "provider": provider, "model": model, "live_run": live_run,
            "confirmation_received": confirmation_received,
            "request_limit": self.policy.maximum_requests_per_run,
            "asset_limit": self.policy.maximum_assets_per_run,
            "retry_limit": self.policy.maximum_retries_per_asset,
            "requests_attempted": self.requests_used,
            "requests_succeeded": requests_succeeded,
            "requests_failed": requests_failed,
            "assets_generated": self.assets_generated,
            "retries_used": self.retries_used,
            "rate_limit_status": self.quota_status == "RATE_LIMITED",
            "quota_status": self.quota_status,
            "quota_remaining": self.quota_remaining,
            "provider_error_code": self.last_provider_error,
            "provider_error_category": self.last_provider_error,
            "stopped_reason": stopped_reason,
            "timestamps": {},
        }


@dataclass(frozen=True)
class ReferenceImage:
    reference_id: str
    kind: str
    path: Path
    sha256: str
    priority: int
    approved: bool = False


@dataclass(frozen=True)
class ReferenceImagePackage:
    references: tuple[ReferenceImage, ...] = ()
    excluded_references: tuple[dict[str, str], ...] = ()


@dataclass(frozen=True)
class VisualQualityProfile:
    name: str = "STANDARD_FINAL"
    requested_resolution: str = "2K"
    aspect_ratio: str = "16:9"
    hero: bool = False
    human_review_required: bool = False


@dataclass(frozen=True)
class VisualAssetRequest:
    asset_id: str
    scene_id: str
    shot_id: str
    timeline_start_ms: int
    timeline_end_ms: int
    asset_type: str
    priority: str
    prompt: str
    prompt_version: str
    quality_profile: VisualQualityProfile
    references: ReferenceImagePackage = field(default_factory=ReferenceImagePackage)
    negative_constraints: tuple[str, ...] = ()
    dependency_asset_ids: tuple[str, ...] = ()
    factual_confidence: str = "UNKNOWN"
    reconstruction_status: str = "UNKNOWN"
    subtitle_safe_region: str = "LOWER_THIRD_CLEAR"
    parent_asset_id: str | None = None


@dataclass(frozen=True)
class VisualGenerationRequest:
    asset: VisualAssetRequest
    provider_id: str
    model_id: str
    live: bool = False
    confirm_quota_use: bool = False
    timeout_seconds: float = 120.0


@dataclass(frozen=True)
class VisualGenerationResponse:
    provider_id: str
    model_id: str
    mime_type: str
    image_bytes: bytes
    usage_metadata: dict[str, Any]
    provider_request_id: str | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class ImageValidationResult:
    status: str
    mime_type: str | None
    width: int | None
    height: int | None
    sha256: str | None
    errors: tuple[str, ...]


@dataclass(frozen=True)
class VisualQualityScore:
    overall_score: float
    grade: str
    category_scores: dict[str, float]
    deductions: dict[str, float]


class VisualCritic(ABC):
    """Offline contract only; no automated visual judgement is claimed."""
    @abstractmethod
    def critique(self, image_path: Path, prompt: str, context: dict[str, Any]) -> dict[str, Any]: ...


class VisualProvider(ABC):
    provider_id: str
    @abstractmethod
    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResponse: ...


class GeminiImageProvider(VisualProvider):
    """The only runtime image provider; official Gemini SDK code remains here."""
    provider_id = GEMINI_IMAGE_PROVIDER_ID

    def __init__(self, *, client: Any | None = None, types_module: Any | None = None, environment: dict[str, str] | None = None) -> None:
        self._client, self._types = client, types_module
        self._environment = environment if environment is not None else os.environ

    def api_key_present(self) -> bool:
        # An injected client is an offline-test transport; it never needs an
        # environment credential and must not cause local tests to touch one.
        return self._client is not None and self._types is not None or bool(self._environment.get("GEMINI_API_KEY", "").strip())

    def _client_and_types(self) -> tuple[Any, Any]:
        if self._client is not None and self._types is not None:
            return self._client, self._types
        key = self._environment.get("GEMINI_API_KEY", "").strip()
        if not key: raise GeminiImageMissingApiKeyError()
        try:
            from google import genai
            from google.genai import types
        except ImportError as error:
            raise VisualProviderError("GOOGLE_GENAI_SDK_NOT_INSTALLED") from error
        self._client, self._types = genai.Client(api_key=key), types
        return self._client, self._types

    @staticmethod
    def _part_from_reference(types_module: Any, reference: ReferenceImage) -> Any:
        data, mime_type = reference.path.read_bytes(), image_mime_type(reference.path)
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES: raise GeminiImageInvalidRequestError("REFERENCE_MIME_UNSUPPORTED")
        factory = getattr(getattr(types_module, "Part", None), "from_bytes", None)
        return factory(data=data, mime_type=mime_type) if callable(factory) else {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(data).decode("ascii")}}

    def generate(self, request: VisualGenerationRequest) -> VisualGenerationResponse:
        if request.provider_id != self.provider_id: raise GeminiImageInvalidRequestError("PROVIDER_MISMATCH")
        if request.model_id not in SUPPORTED_GEMINI_IMAGE_MODELS: raise GeminiImageModelUnavailableError("UNSUPPORTED_GEMINI_IMAGE_MODEL")
        if not request.live or not request.confirm_quota_use: raise VisualLiveGuardError("EXPLICIT_LIVE_AND_CONFIRM_QUOTA_USE_REQUIRED")
        client, types_module = self._client_and_types()
        contents: list[Any] = [request.asset.prompt]
        for reference in request.asset.references.references:
            if not reference.approved: raise GeminiImageInvalidRequestError("REFERENCE_NOT_APPROVED")
            contents.append(self._part_from_reference(types_module, reference))
        try:
            values: dict[str, Any] = {"response_modalities": ["IMAGE"]}
            if hasattr(types_module, "ImageConfig"):
                values["image_config"] = types_module.ImageConfig(aspect_ratio=request.asset.quality_profile.aspect_ratio, image_size=request.asset.quality_profile.requested_resolution)
            if hasattr(types_module, "HttpOptions"):
                values["http_options"] = types_module.HttpOptions(timeout=int(request.timeout_seconds * 1000))
            response = client.models.generate_content(model=request.model_id, contents=contents, config=types_module.GenerateContentConfig(**values))
            image, mime_type = extract_gemini_image(response)
        except VisualProviderError: raise
        except Exception as error: raise classify_gemini_image_error(error) from error
        if not image: raise GeminiImageInvalidResponseError("EMPTY_IMAGE_RESPONSE")
        return VisualGenerationResponse(self.provider_id, request.model_id, mime_type, image, usage_metadata_from_response(response), getattr(response, "response_id", None), first_finish_reason(response))


def first_finish_reason(response: Any) -> str | None:
    candidates = getattr(response, "candidates", None) or []
    return str(getattr(candidates[0], "finish_reason", "")) or None if candidates else None


def usage_metadata_from_response(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None: return {}
    names = ("prompt_token_count", "candidates_token_count", "total_token_count", "cached_content_token_count")
    return {name: value for name in names if (value := getattr(usage, name, None)) is not None}


def extract_gemini_image(response: Any) -> tuple[bytes, str]:
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data, mime_type = (getattr(inline, "data", None), getattr(inline, "mime_type", None)) if inline else (None, None)
            if data:
                normalized = str(mime_type or "image/png").lower()
                if normalized not in SUPPORTED_IMAGE_MIME_TYPES: raise GeminiImageInvalidResponseError("UNSUPPORTED_IMAGE_MIME")
                return bytes(data), normalized
    raise GeminiImageInvalidResponseError("IMAGE_PART_MISSING")


def image_mime_type(path: Path) -> str:
    head = path.read_bytes()[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"): return "image/png"
    if head.startswith(b"\xff\xd8\xff"): return "image/jpeg"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP": return "image/webp"
    return "application/octet-stream"


def image_dimensions(data: bytes, mime_type: str) -> tuple[int, int]:
    if mime_type == "image/png" and data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if mime_type == "image/jpeg":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF: index += 1; continue
            marker = data[index + 1]; index += 2
            if marker in {0xD8, 0xD9}: continue
            size = int.from_bytes(data[index:index + 2], "big")
            if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
                return int.from_bytes(data[index + 5:index + 7], "big"), int.from_bytes(data[index + 3:index + 5], "big")
            index += max(size, 2)
    raise GeminiImageInvalidResponseError("IMAGE_DIMENSIONS_UNREADABLE")


def write_generated_image(response: VisualGenerationResponse, output_path: Path) -> dict[str, Any]:
    width, height = image_dimensions(response.image_bytes, response.mime_type)
    suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[response.mime_type]
    final_path = output_path.with_suffix(suffix); final_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=final_path.parent, suffix=suffix, delete=False) as handle:
        temporary = Path(handle.name); handle.write(response.image_bytes)
    try:
        if not temporary.is_file() or temporary.stat().st_size < 16: raise GeminiImageInvalidResponseError("IMAGE_FILE_EMPTY")
        temporary.replace(final_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(final_path), "mime_type": response.mime_type, "width": width, "height": height, "sha256": file_sha256(final_path)}


def validate_generated_image(path: Path, *, required_aspect_ratio: str = "16:9", aspect_tolerance: float = 0.08) -> ImageValidationResult:
    if not path.is_file() or path.stat().st_size < 16: return ImageValidationResult("FAIL", None, None, None, None, ("IMAGE_FILE_MISSING_OR_EMPTY",))
    mime_type = image_mime_type(path)
    if mime_type not in SUPPORTED_IMAGE_MIME_TYPES: return ImageValidationResult("FAIL", mime_type, None, None, None, ("IMAGE_MIME_UNSUPPORTED",))
    try: width, height = image_dimensions(path.read_bytes(), mime_type)
    except GeminiImageInvalidResponseError as error: return ImageValidationResult("FAIL", mime_type, None, None, None, (error.code,))
    try: numerator, denominator = (int(value) for value in required_aspect_ratio.split(":"))
    except ValueError: return ImageValidationResult("FAIL", mime_type, width, height, None, ("ASPECT_RATIO_INVALID",))
    expected = numerator / denominator
    errors = () if abs((width / height) - expected) <= aspect_tolerance else ("IMAGE_ASPECT_RATIO_MISMATCH",)
    return ImageValidationResult("PASS" if not errors else "FAIL", mime_type, width, height, file_sha256(path), errors)


def request_fingerprint(request: VisualGenerationRequest, *, style_bible_fingerprint: str, character_bible_fingerprint: str, location_bible_fingerprint: str, storyboard_fingerprint: str, config_fingerprint: str) -> str:
    payload = {"provider": request.provider_id, "model": request.model_id, "prompt_version": request.asset.prompt_version, "prompt": request.asset.prompt, "references": [reference.sha256 for reference in request.asset.references.references], "aspect_ratio": request.asset.quality_profile.aspect_ratio, "resolution": request.asset.quality_profile.requested_resolution, "quality_profile": asdict(request.asset.quality_profile), "style_bible": style_bible_fingerprint, "character_bible": character_bible_fingerprint, "location_bible": location_bible_fingerprint, "storyboard": storyboard_fingerprint, "parent": request.asset.parent_asset_id, "config": config_fingerprint}
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def quality_grade(score: float) -> str:
    if score >= 95: return "MASTERPIECE"
    if score >= 90: return "EXCELLENT"
    if score >= 85: return "STRONG"
    if score >= 75: return "ACCEPTABLE"
    return "FAIL"


def score_visual_quality(categories: dict[str, float]) -> dict[str, Any]:
    weights = {"prompt_adherence": 15, "cinematic_composition": 12, "character_consistency": 15, "location_consistency": 8, "historical_accuracy": 10, "anatomy_and_faces": 10, "lighting_and_color": 8, "emotional_impact": 8, "subtitle_safety": 4, "technical_quality": 5, "render_usability": 5}
    missing = sorted(set(weights) - set(categories))
    if missing: raise ValueError(f"VISUAL_QUALITY_CATEGORIES_MISSING:{','.join(missing)}")
    deductions = {key: round(weights[key] - max(0.0, min(float(categories[key]), float(weights[key]))), 3) for key in weights}
    return {"overall_score": round(sum(float(categories[key]) for key in weights), 3), "grade": quality_grade(sum(float(categories[key]) for key in weights)), "category_scores": {key: float(categories[key]) for key in weights}, "deductions": deductions}
