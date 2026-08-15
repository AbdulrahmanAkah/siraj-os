"""Offline PR01 production-readiness binding and fail-closed gates.

This module has no provider transport, no paid transport, and no network
capability.  It compiles and validates future approval material, then keeps
the real production/paid authorization false until a later episode-specific
Desktop release gate is satisfied.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Iterable, Mapping, Sequence
import uuid

from src.application.pr01_face_detection_v1 import EXPECTED_MODEL_SHA256


PR01_ID = "SIRAJ_PR01_PRODUCTION_READINESS_BINDING_V1"
CONSTITUTION_ID = "SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION"
CONSTITUTION_VERSION = "1.2.0"
CONSTITUTION_BUNDLE_SHA256 = "b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5"
CONSTITUTION_BUNDLE_RELATIVE = Path(
    "config/constitution/siraj-unified-production-constitution/1.2.0/bundle_manifest.json"
)
PREVIOUS_CONSTITUTION_VERSION = "1.1.0"
PREVIOUS_CONSTITUTION_BUNDLE_SHA256 = "c82097a3de2dfa9c4b7a4b6d2c7c1b1f7fab909d25575724167e8ea7f4e3c7b8"
EXPECTED_RULE_COUNT = 51
EXACT_PROVIDER = "RUNWARE"
EXACT_MODEL_ID = "google:veo@3.1-lite"
BRAND_ASSETS_DIRECTORY = Path(r"C:\Users\abdul\OneDrive\Desktop\سراج\intro outro")
BRAND_INTRO_SHA256 = "3de59689f16329fd7f701d010526a9280843917625d02dcac9aa5569250b37f4"
BRAND_OUTRO_SHA256 = "09c01a3e144b9c1fbfe3ddad5d08f2fb4759ef054d6b071ce17e255f7c614004"
UNKNOWN_ATTEMPT_ID = "1e6d0013-d37f-5df7-ab53-444c4f17c14c"
UNKNOWN_REQUEST_ID = "EP002-SH-001-V01"
UNKNOWN_TASK_UUID = "planning-only-23fd9f353315ea244f26e1940c4fe737"
UNKNOWN_STATUS = "SUBMISSION_STATUS_UNKNOWN"
UNKNOWN_BLOCK_CODE = "TASKUUID_NOT_RECOVERABLE_UNKNOWN_REMAINS_BLOCK"
INVALIDATING_EVENTS = (
    "constitution_bundle_changed",
    "technical_delivery_profile_changed",
    "provider_binding_changed",
    "provider_model_id_changed",
    "prompt_changed",
    "payload_changed",
    "reference_image_changed",
    "canonical_still_changed",
    "pricing_snapshot_changed",
    "cost_cap_changed",
    "batch_membership_changed",
    "request_count_changed",
    "compatibility_transform_changed",
    "audio_measurement_changed",
    "face_detector_model_changed",
    "face_detector_threshold_changed",
    "face_calibration_corpus_changed",
    "brand_asset_hash_changed",
    "human_approval_revoked",
)
ALLOWED_PROVIDER_PAYLOAD_FIELDS = frozenset(
    {
        "taskType",
        "taskUUID",
        "model",
        "positivePrompt",
        "duration",
        "width",
        "height",
        "numberResults",
        "seed",
        "inputs",
        "providerSettings",
    }
)


class PR01Error(RuntimeError):
    """Fail-closed PR01 validation error."""


class BindingMismatchError(PR01Error):
    """A hashed approval input changed."""


class PaidStartDenied(PR01Error):
    """The paid boundary was not entered from an approved Desktop action."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PR01Error(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def document_body(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    for key in (
        "binding_sha256",
        "snapshot_sha256",
        "profile_sha256",
        "document_sha256",
        "manifest_sha256",
    ):
        result.pop(key, None)
    return result


def document_hash(value: Mapping[str, Any]) -> str:
    return canonical_sha256(document_body(value))


def config_path(repo_root: Path, relative: str) -> Path:
    return Path(repo_root).resolve() / Path(relative)


def load_profile(repo_root: Path) -> dict[str, Any]:
    return read_json(config_path(repo_root, "config/technical_delivery/siraj_technical_delivery_profile_v1.json"))


def load_provider_binding(repo_root: Path) -> dict[str, Any]:
    return read_json(config_path(repo_root, "config/pr01/provider_binding/google_veo_3_1_lite_runware_v1.json"))


def load_pricing_snapshot(repo_root: Path) -> dict[str, Any]:
    return read_json(config_path(repo_root, "config/pr01/provider_binding/provider_pricing_snapshot_v1.json"))


def rebind_pr01_constitution_binding(
    repo_root: Path,
    *,
    previous_constitution_version: str = PREVIOUS_CONSTITUTION_VERSION,
    previous_constitution_bundle_sha256: str = PREVIOUS_CONSTITUTION_BUNDLE_SHA256,
) -> dict[str, Any]:
    """Validate the offline PR01 invalidation/rebind after a policy amendment.

    This is a read-only state transition description. It never rebuilds M01/M02/M03,
    starts production, invokes a provider, or authorizes a paid operation.
    """

    manifest_path = config_path(repo_root, str(CONSTITUTION_BUNDLE_RELATIVE))
    if not manifest_path.is_file():
        return {
            "status": "BLOCKED",
            "reason": "CONSTITUTION_MANIFEST_MISSING",
            "production_authorized": False,
            "paid_execution_authorized": False,
        }
    manifest = read_json(manifest_path)
    current = {
        "constitution_id": manifest.get("constitution_id"),
        "constitution_version": manifest.get("version"),
        "constitution_bundle_sha256": sha256_file(manifest_path),
    }
    previous = {
        "constitution_id": CONSTITUTION_ID,
        "constitution_version": previous_constitution_version,
        "constitution_bundle_sha256": previous_constitution_bundle_sha256,
    }
    profile = load_profile(repo_root)
    binding = profile.get("constitution_binding")
    rebind = profile.get("constitution_rebind")
    profile_matches = isinstance(binding, Mapping) and all(
        binding.get(key) == value
        for key, value in current.items()
    ) and binding.get("rule_count") == EXPECTED_RULE_COUNT
    revalidation_recorded = isinstance(rebind, Mapping) and (
        rebind.get("status") == "REBOUND_AFTER_CONSTITUTION_POLICY_AMENDMENT"
        and rebind.get("invalidation_event") == "constitution_bundle_changed"
        and rebind.get("m01_m02_m03_input_hashes_unchanged") is True
        and rebind.get("compatibility_revalidated") is True
    )
    changed = previous != current
    status = "PASS" if changed and profile_matches and revalidation_recorded else "BLOCKED"
    return {
        "status": status,
        "invalidation_event": "constitution_bundle_changed" if changed else "NO_MATERIAL_CONSTITUTION_CHANGE",
        "previous_binding": previous,
        "current_binding": current,
        "prior_approvals": "INVALIDATED",
        "m01_m02_m03_rebuild_required": False if revalidation_recorded else True,
        "m01_m02_m03_compatibility_revalidated": revalidation_recorded,
        "historical_unknown": historical_unknown_state(),
        "production_authorized": False,
        "paid_execution_authorized": False,
        "provider_calls": 0,
        "paid_calls": 0,
        "network_production_calls": 0,
        "retry_or_resubmission": 0,
    }


def validate_profile(profile: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    constitution = profile.get("constitution_binding")
    if not isinstance(constitution, Mapping):
        issues.append("CONSTITUTION_BINDING_MISSING")
    else:
        if constitution.get("constitution_id") != CONSTITUTION_ID:
            issues.append("CONSTITUTION_ID_MISMATCH")
        if constitution.get("constitution_version") != CONSTITUTION_VERSION:
            issues.append("CONSTITUTION_VERSION_MISMATCH")
        if constitution.get("constitution_bundle_sha256") != CONSTITUTION_BUNDLE_SHA256:
            issues.append("CONSTITUTION_BUNDLE_HASH_MISMATCH")
        if constitution.get("rule_count") != EXPECTED_RULE_COUNT:
            issues.append("CONSTITUTION_RULE_COUNT_MISMATCH")
    rebind = profile.get("constitution_rebind")
    if not isinstance(rebind, Mapping) or rebind.get("status") != "REBOUND_AFTER_CONSTITUTION_POLICY_AMENDMENT":
        issues.append("CONSTITUTION_REBIND_MISSING")
    elif rebind.get("invalidation_event") != "constitution_bundle_changed":
        issues.append("CONSTITUTION_REBIND_EVENT_MISMATCH")
    elif rebind.get("m01_m02_m03_input_hashes_unchanged") is not True or rebind.get("compatibility_revalidated") is not True:
        issues.append("PR01_COMPATIBILITY_REVALIDATION_MISSING")
    audio = profile.get("audio_delivery")
    if not isinstance(audio, Mapping):
        return ["AUDIO_PROFILE_MISSING"]
    expected = {
        "target_integrated_loudness_lufs": -16.0,
        "pass_loudness_min_lufs": -17.0,
        "pass_loudness_max_lufs": -15.0,
        "target_true_peak_dbtp": -1.5,
        "true_peak_ceiling_dbtp": -1.0,
        "sample_rate_hz": 48000,
        "channel_policy": "STEREO",
        "measurement_standard": "EBU R128",
    }
    for key, value in expected.items():
        if audio.get(key) != value:
            issues.append(f"PROFILE_VALUE_MISMATCH:{key}")
    if audio.get("measurement_required_on_actual_bytes") is not True:
        issues.append("ACTUAL_AUDIO_MEASUREMENT_REQUIRED")
    if audio.get("unknown_measurement_is_blocking") is not True:
        issues.append("UNKNOWN_AUDIO_MEASUREMENT_NOT_BLOCKING")
    normalization = audio.get("normalization_policy")
    if not isinstance(normalization, Mapping) or normalization.get("duration_must_be_preserved") is not True:
        issues.append("DURATION_PRESERVATION_NOT_BOUND")
    face = profile.get("face_policy")
    if not isinstance(face, Mapping) or face.get("all_human_faces_visible") is not False:
        issues.append("GLOBAL_FACE_BAN_NOT_BOUND")
    publication = profile.get("publication_policy")
    if not isinstance(publication, Mapping) or publication.get("human_final_certification_required") is not True:
        issues.append("HUMAN_FINAL_CERTIFICATION_NOT_BOUND")
    return issues


def measure_audio_file(audio_path: Path, *, ffmpeg_path: Path | None = None, ffprobe_path: Path | None = None) -> dict[str, Any]:
    """Measure actual local bytes; unavailable statistics are never PASS."""

    audio_path = Path(audio_path).resolve()
    if not audio_path.is_file():
        return {"status": "UNKNOWN", "reason": "AUDIO_BYTES_MISSING"}
    ffmpeg = ffmpeg_path
    if ffmpeg is None:
        try:
            import imageio_ffmpeg  # type: ignore

            ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
        except Exception:
            ffmpeg = Path(shutil.which("ffmpeg") or "")
    if not ffmpeg or not Path(ffmpeg).is_file():
        return {"status": "UNKNOWN", "reason": "FFMPEG_MISSING"}
    process = subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostats",
            "-i",
            str(audio_path),
            "-af",
            "loudnorm=I=-16:TP=-1.0:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    matches = re.findall(r"\{\s*\"input_i\".*?\}", process.stderr, flags=re.DOTALL)
    if process.returncode != 0 or not matches:
        return {"status": "UNKNOWN", "reason": "LOUDNESS_STATISTICS_UNAVAILABLE", "returncode": process.returncode}
    try:
        stats = json.loads(matches[-1])
        integrated = float(stats["input_i"])
        true_peak = float(stats["input_tp"])
        lra = float(stats.get("input_lra", "nan"))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {"status": "UNKNOWN", "reason": "LOUDNESS_STATISTICS_INVALID"}
    duration = None
    if ffprobe_path is None:
        discovered = shutil.which("ffprobe")
        ffprobe_path = Path(discovered) if discovered else None
    if ffprobe_path and Path(ffprobe_path).is_file():
        probe = subprocess.run(
            [str(ffprobe_path), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        try:
            duration = float(probe.stdout.strip())
        except ValueError:
            duration = None
    if duration is None and audio_path.suffix.casefold() == ".wav":
        try:
            import wave

            with wave.open(str(audio_path), "rb") as wav:
                duration = wav.getnframes() / float(wav.getframerate())
        except (OSError, wave.Error, ZeroDivisionError):
            duration = None
    return {
        "status": "MEASURED",
        "audio_sha256": sha256_file(audio_path),
        "integrated_lufs": integrated,
        "true_peak_dbtp": true_peak,
        "lra": lra,
        "duration_seconds": duration,
        "tool": "FFmpeg loudnorm first-pass",
        "measurement_standard": "EBU R128",
    }


def classify_audio_measurement(measurement: Mapping[str, Any], profile: Mapping[str, Any]) -> dict[str, Any]:
    audio = profile["audio_delivery"]
    if measurement.get("status") != "MEASURED":
        return {"status": "BLOCKED", "reason": "AUDIO_MEASUREMENT_UNKNOWN"}
    integrated = measurement.get("integrated_lufs")
    true_peak = measurement.get("true_peak_dbtp")
    duration = measurement.get("duration_seconds")
    if not isinstance(integrated, (int, float)) or not isinstance(true_peak, (int, float)):
        return {"status": "BLOCKED", "reason": "AUDIO_MEASUREMENT_FIELDS_MISSING"}
    if not (audio["pass_loudness_min_lufs"] <= integrated <= audio["pass_loudness_max_lufs"]):
        return {"status": "FAIL", "reason": "INTEGRATED_LOUDNESS_OUTSIDE_WINDOW", "measurement": dict(measurement)}
    if true_peak > audio["true_peak_ceiling_dbtp"]:
        return {"status": "FAIL", "reason": "TRUE_PEAK_ABOVE_CEILING", "measurement": dict(measurement)}
    return {
        "status": "PASS",
        "duration_seconds": duration,
        "duration_authority": audio["normalization_policy"]["duration_authority"],
        "duration_preserved": True,
        "measurement": dict(measurement),
    }


def duration_preservation_check(before_seconds: float, after_seconds: float, profile: Mapping[str, Any]) -> bool:
    tolerance = float(profile["audio_delivery"]["normalization_policy"]["duration_tolerance_seconds"])
    return abs(float(before_seconds) - float(after_seconds)) <= tolerance


def _face_semantic_failures(text: str) -> tuple[str, ...]:
    try:
        from src.application.unified_constitution_enforcement_v1 import analyze_face_semantics

        return tuple(analyze_face_semantics(text))
    except Exception:
        lowered = text.casefold()
        if any(token in lowered for token in ("visible face", "visible mouth", "visible eyes", "portrait")):
            return ("FAIL_GLOBAL_FACE_POLICY",)
        return ()


def build_exact_provider_payload(
    *,
    prompt: str,
    duration_seconds: int,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    task_uuid: str,
    seed: int | None = None,
    frame_images: Sequence[Mapping[str, Any]] | None = None,
    person_generation: str = "dont_allow",
) -> dict[str, Any]:
    if not prompt.strip():
        raise BindingMismatchError("PROMPT_REQUIRED")
    if _face_semantic_failures(prompt):
        raise BindingMismatchError("FAIL_GLOBAL_FACE_POLICY")
    try:
        parsed_uuid = uuid.UUID(task_uuid)
    except (ValueError, AttributeError) as exc:
        raise BindingMismatchError("TASK_UUID_UUID4_REQUIRED") from exc
    if parsed_uuid.version != 4:
        raise BindingMismatchError("TASK_UUID_UUID4_REQUIRED")
    if duration_seconds not in (4, 6, 8):
        raise BindingMismatchError("VEO31_DURATION_UNSUPPORTED")
    dimensions = {
        "16:9": {
            "720p": (1280, 720),
            "1080p": (1920, 1080),
        },
        "9:16": {
            "720p": (720, 1280),
            "1080p": (1080, 1920),
        },
    }
    try:
        width, height = dimensions[aspect_ratio][resolution]
    except KeyError as exc:
        raise BindingMismatchError("VEO31_ASPECT_OR_RESOLUTION_UNSUPPORTED") from exc
    if seed is not None and not 0 <= int(seed) <= 4_294_967_295:
        raise BindingMismatchError("VEO31_SEED_OUT_OF_RANGE")
    if frame_images is not None and not 1 <= len(frame_images) <= 2:
        raise BindingMismatchError("VEO31_FRAME_IMAGES_COUNT_INVALID")
    payload: dict[str, Any] = {
        "taskType": "videoInference",
        "taskUUID": str(parsed_uuid),
        "model": EXACT_MODEL_ID,
        "positivePrompt": prompt,
        "duration": duration_seconds,
        "width": width,
        "height": height,
        "numberResults": 1,
        "providerSettings": {
            "google": {
                "generateAudio": False,
                "personGeneration": person_generation,
            }
        },
    }
    if seed is not None:
        payload["seed"] = int(seed)
    if frame_images is not None:
        payload["inputs"] = {"frameImages": [dict(row) for row in frame_images]}
    return payload


def validate_exact_provider_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    extras = sorted(set(payload) - ALLOWED_PROVIDER_PAYLOAD_FIELDS)
    if extras:
        raise BindingMismatchError("UNBOUND_PROVIDER_PAYLOAD_FIELDS:" + ",".join(extras))
    if payload.get("taskType") != "videoInference":
        raise BindingMismatchError("TASK_TYPE_MISMATCH")
    if payload.get("model") != EXACT_MODEL_ID:
        raise BindingMismatchError("EXACT_MODEL_ID_REQUIRED")
    if "negativePrompt" in payload:
        raise BindingMismatchError("NEGATIVE_PROMPT_UNSUPPORTED")
    if not isinstance(payload.get("positivePrompt"), str) or not payload["positivePrompt"].strip():
        raise BindingMismatchError("POSITIVE_PROMPT_REQUIRED")
    try:
        parsed_uuid = uuid.UUID(str(payload.get("taskUUID")))
    except (ValueError, AttributeError) as exc:
        raise BindingMismatchError("TASK_UUID_UUID4_REQUIRED") from exc
    if parsed_uuid.version != 4:
        raise BindingMismatchError("TASK_UUID_UUID4_REQUIRED")
    if payload.get("duration") not in (4, 6, 8):
        raise BindingMismatchError("VEO31_DURATION_UNSUPPORTED")
    if payload.get("numberResults") != 1:
        raise BindingMismatchError("VEO31_ONE_RESULT_REQUIRED")
    inputs = payload.get("inputs")
    if inputs is not None:
        if not isinstance(inputs, Mapping) or set(inputs) != {"frameImages"}:
            raise BindingMismatchError("VEO31_FRAME_IMAGES_INPUTS_INVALID")
        frame_images = inputs.get("frameImages")
        if not isinstance(frame_images, list) or not 1 <= len(frame_images) <= 2:
            raise BindingMismatchError("VEO31_FRAME_IMAGES_COUNT_INVALID")
    return dict(payload)


@dataclass(frozen=True, slots=True)
class CostLine:
    unit_id: str
    duration_seconds: int
    resolution: str
    price_per_second: Decimal
    cost: Decimal

    def as_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "duration_seconds": self.duration_seconds,
            "resolution": self.resolution,
            "price_per_second": format(self.price_per_second, "f"),
            "cost": format(self.cost, "f"),
        }


def cost_preflight(
    rows: Iterable[Mapping[str, Any]],
    pricing_snapshot: Mapping[str, Any],
    *,
    max_cost_usd: str | Decimal,
) -> dict[str, Any]:
    if pricing_snapshot.get("provider") != EXACT_PROVIDER or pricing_snapshot.get("exact_model_id") != EXACT_MODEL_ID:
        raise BindingMismatchError("PRICING_SNAPSHOT_BINDING_MISMATCH")
    prices = pricing_snapshot.get("prices_per_second")
    if not isinstance(prices, Mapping):
        raise BindingMismatchError("PRICING_SNAPSHOT_MISSING")
    try:
        cap = Decimal(str(max_cost_usd))
    except InvalidOperation as exc:
        raise BindingMismatchError("COST_CAP_INVALID") from exc
    lines: list[CostLine] = []
    for row in rows:
        resolution = str(row.get("resolution") or "")
        if resolution not in prices:
            raise BindingMismatchError("PRICING_RESOLUTION_MISSING")
        try:
            seconds = int(row["duration_seconds"])
            price = Decimal(str(prices[resolution]))
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise BindingMismatchError("PRICING_ROW_INVALID") from exc
        if seconds not in (4, 6, 8) or seconds <= 0:
            raise BindingMismatchError("DURATION_INVALID")
        lines.append(CostLine(str(row.get("unit_id") or ""), seconds, resolution, price, price * seconds))
    total = sum((line.cost for line in lines), Decimal("0"))
    if total > cap:
        raise BindingMismatchError("COST_CAP_EXCEEDED")
    return {
        "status": "PASS",
        "provider": EXACT_PROVIDER,
        "model": EXACT_MODEL_ID,
        "currency": pricing_snapshot.get("currency"),
        "pricing_snapshot_hash": document_hash(pricing_snapshot),
        "maximum_cost_usd": format(cap, "f"),
        "estimated_cost_usd": format(total, "f"),
        "lines": [line.as_dict() for line in lines],
        "decimal_arithmetic": True,
    }


@dataclass(frozen=True, slots=True)
class PaidStartCard:
    episode_id: str
    provider: str
    exact_model_id: str
    request_count: int
    provider_seconds: int
    estimated_cost_usd: str
    maximum_cost_usd: str
    currency: str
    batch_type: str
    prompt_hashes: tuple[str, ...]
    payload_hashes: tuple[str, ...]
    pricing_snapshot_hash: str
    provider_binding_hash: str
    technical_profile_hash: str
    compatibility_transform_hash: str
    source: str = "DESKTOP"

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "provider": self.provider,
            "exact_model_id": self.exact_model_id,
            "request_count": self.request_count,
            "provider_seconds": self.provider_seconds,
            "estimated_cost_usd": self.estimated_cost_usd,
            "maximum_cost_usd": self.maximum_cost_usd,
            "currency": self.currency,
            "batch_type": self.batch_type,
            "prompt_hashes": list(self.prompt_hashes),
            "payload_hashes": list(self.payload_hashes),
            "pricing_snapshot_hash": self.pricing_snapshot_hash,
            "provider_binding_hash": self.provider_binding_hash,
            "technical_profile_hash": self.technical_profile_hash,
            "compatibility_transform_hash": self.compatibility_transform_hash,
            "source": self.source,
        }


def approval_hash(card: PaidStartCard) -> str:
    return canonical_sha256(card.as_dict())


def evaluate_paid_start(
    card: PaidStartCard,
    *,
    origin: str,
    explicit_click: bool,
    human_approval: bool,
    click_nonce: str,
    current_card: PaidStartCard | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if origin != "DESKTOP":
        reasons.append("PAID_START_DESKTOP_ONLY")
    if explicit_click is not True:
        reasons.append("EXPLICIT_DESKTOP_CLICK_REQUIRED")
    if human_approval is not True:
        reasons.append("HUMAN_PAID_AUTHORIZATION_REQUIRED")
    if not click_nonce.strip():
        reasons.append("CLICK_NONCE_REQUIRED")
    if current_card is not None and approval_hash(card) != approval_hash(current_card):
        reasons.append("APPROVAL_STALE_INPUT_CHANGED")
    if reasons:
        return {"status": "BLOCKED", "reasons": reasons, "production_authorized": False}
    return {
        "status": "DESKTOP_CLICK_GATE_PASS_FOR_EPISODE_SPECIFIC_PREFLIGHT",
        "production_authorized": False,
        "approval_hash": approval_hash(card),
    }


def enforce_pr01_desktop_paid_gate(*, request: Any, unit: Mapping[str, Any]) -> dict[str, Any]:
    """Guard the real gateway before transport.

    The existing master authorization remains the carrier so old request
    constructors remain source-compatible. A future Desktop release must
    add the nested PR01 card and approval hash; terminal, CLI, recovery,
    compiler, QA, and test paths cannot manufacture this object.
    """

    authorization = getattr(request, "master_authorization_reference", None)
    if not isinstance(authorization, Mapping):
        raise PaidStartDenied("PR01_DESKTOP_APPROVAL_REQUIRED")
    approval = authorization.get("pr01_paid_start_authorization")
    if not isinstance(approval, Mapping):
        raise PaidStartDenied("PR01_DESKTOP_APPROVAL_REQUIRED")
    if approval.get("source") != "DESKTOP":
        raise PaidStartDenied("PR01_PAID_START_DESKTOP_ONLY")
    if approval.get("explicit_click") is not True or approval.get("human_approval") is not True:
        raise PaidStartDenied("PR01_EXPLICIT_HUMAN_DESKTOP_CLICK_REQUIRED")
    if approval.get("production_authorized") is True:
        raise PaidStartDenied("PR01_PRODUCTION_AUTHORIZATION_MUST_REMAIN_FALSE")
    if str(getattr(request, "provider", "")) != EXACT_PROVIDER or str(getattr(request, "model", "")) != EXACT_MODEL_ID:
        raise PaidStartDenied("PR01_EXACT_PROVIDER_MODEL_REQUIRED")
    try:
        validate_exact_provider_payload(request.payload)
    except PR01Error as exc:
        raise PaidStartDenied(str(exc)) from exc
    expected_payload_hash = canonical_sha256(dict(request.payload))
    if approval.get("payload_sha256") != expected_payload_hash:
        raise PaidStartDenied("PR01_PAYLOAD_HASH_MISMATCH")
    if str(approval.get("click_nonce") or "").strip() == "":
        raise PaidStartDenied("PR01_CLICK_NONCE_REQUIRED")
    return {
        "status": "PR01_DESKTOP_GATE_PASS_EPISODE_PREFLIGHT_ONLY",
        "production_authorized": False,
        "paid_execution_authorized": False,
        "payload_sha256": expected_payload_hash,
        "unit_id": str(unit.get("unit_id") or ""),
    }


@dataclass(slots=True)
class FakeStrictGateway:
    """Offline simulation only; never imports or invokes a transport."""

    invocations: int = 0
    used_nonces: set[str] | None = None

    def __post_init__(self) -> None:
        if self.used_nonces is None:
            self.used_nonces = set()

    def execute(
        self,
        payload: Mapping[str, Any],
        *,
        origin: str,
        explicit_click: bool,
        nonce: str,
        provider_outcome: str = "SUCCESS",
        historical_unknown: bool = False,
    ) -> dict[str, Any]:
        if origin != "DESKTOP" or not explicit_click:
            return {"status": "BLOCKED", "reason": "PAID_START_DESKTOP_ONLY", "network_call": False, "paid_call": False}
        if historical_unknown:
            return {"status": "UNKNOWN_REMAINS_BLOCK", "reason": UNKNOWN_BLOCK_CODE, "retry": False, "resubmit": False, "network_call": False, "paid_call": False}
        assert self.used_nonces is not None
        if nonce in self.used_nonces:
            return {"status": "DUPLICATE_CLICK_BLOCKED", "reason": "SINGLE_USE_CLICK_NONCE", "network_call": False, "paid_call": False}
        self.used_nonces.add(nonce)
        validate_exact_provider_payload(payload)
        self.invocations += 1
        if provider_outcome == "FAILURE":
            return {"status": "TERMINAL_PROVIDER_FAILURE", "retry": False, "resubmit": False, "network_call": False, "paid_call": False}
        return {"status": "SIMULATED_DESKTOP_START_ACCEPTED", "network_call": False, "paid_call": False, "payload_sha256": canonical_sha256(payload)}


def historical_unknown_state() -> dict[str, Any]:
    return {
        "attempt_id": UNKNOWN_ATTEMPT_ID,
        "request_id": UNKNOWN_REQUEST_ID,
        "task_uuid": UNKNOWN_TASK_UUID,
        "submission_status": UNKNOWN_STATUS,
        "status": "UNKNOWN_REMAINS_BLOCK",
        "retry_allowed": False,
        "resubmission_allowed": False,
        "recovery_allowed": False,
        "reason": UNKNOWN_BLOCK_CODE,
    }


def run_offline_gate_simulation(payload: Mapping[str, Any]) -> dict[str, Any]:
    gateway = FakeStrictGateway()
    terminal = gateway.execute(payload, origin="TERMINAL", explicit_click=True, nonce="terminal")
    cli = gateway.execute(payload, origin="CLI", explicit_click=True, nonce="cli")
    accepted = gateway.execute(payload, origin="DESKTOP", explicit_click=True, nonce="desktop-1")
    duplicate = gateway.execute(payload, origin="DESKTOP", explicit_click=True, nonce="desktop-1")
    failure = gateway.execute(payload, origin="DESKTOP", explicit_click=True, nonce="desktop-failure", provider_outcome="FAILURE")
    unknown = gateway.execute(payload, origin="DESKTOP", explicit_click=True, nonce="desktop-unknown", historical_unknown=True)
    return {
        "mode": "OFFLINE_FAKE_ONLY",
        "terminal": terminal,
        "cli": cli,
        "desktop_click": accepted,
        "double_click": duplicate,
        "provider_failure": failure,
        "historical_unknown": unknown,
        "fake_invocations": gateway.invocations,
        "network_production_calls": 0,
        "paid_calls": 0,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "montage": False,
    }


def constitution_and_brand_self_test(repo_root: Path, *, check_external_brand_assets: bool = True) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    issues: list[str] = []
    manifest_path = repo_root / CONSTITUTION_BUNDLE_RELATIVE
    if not manifest_path.is_file():
        issues.append("CONSTITUTION_MANIFEST_MISSING")
        return {"status": "BLOCKED", "issues": issues}
    manifest = read_json(manifest_path)
    if manifest.get("constitution_id") != CONSTITUTION_ID or manifest.get("version") != CONSTITUTION_VERSION:
        issues.append("CONSTITUTION_ID_VERSION_MISMATCH")
    if sha256_file(manifest_path) != CONSTITUTION_BUNDLE_SHA256:
        issues.append("CONSTITUTION_BUNDLE_HASH_MISMATCH")
    for entry in manifest.get("files", []):
        path = manifest_path.parent / str(entry.get("path") or "")
        if not path.is_file() or sha256_file(path) != entry.get("sha256"):
            issues.append(f"CONSTITUTION_FILE_HASH_MISMATCH:{entry.get('path')}")
    if manifest.get("phase_status", {}).get("provider_calls") != 0:
        issues.append("CONSTITUTION_PROVIDER_CALL_COUNT_NONZERO")
    if manifest.get("phase_status", {}).get("paid_calls") != 0:
        issues.append("CONSTITUTION_PAID_CALL_COUNT_NONZERO")
    rebind = rebind_pr01_constitution_binding(repo_root)
    if rebind.get("status") != "PASS":
        issues.append("PR01_CONSTITUTION_REBIND_BLOCKED")
    if check_external_brand_assets:
        brand = manifest.get("brand_assets", {})
        if not BRAND_ASSETS_DIRECTORY.is_dir():
            issues.append("BRAND_DIRECTORY_UNAVAILABLE")
        else:
            intro = BRAND_ASSETS_DIRECTORY / str(brand.get("intro_filename") or "")
            outro = BRAND_ASSETS_DIRECTORY / str(brand.get("outro_filename") or "")
            if not intro.is_file() or sha256_file(intro) != BRAND_INTRO_SHA256:
                issues.append("INTRO_BRAND_HASH_MISMATCH")
            if not outro.is_file() or sha256_file(outro) != BRAND_OUTRO_SHA256:
                issues.append("OUTRO_BRAND_HASH_MISMATCH")
    return {
        "status": "PASS" if not issues else "BLOCKED",
        "issues": issues,
        "constitution_modified": bool(issues and any("CONSTITUTION_FILE_HASH" in issue for issue in issues)),
        "brand_directory": str(BRAND_ASSETS_DIRECTORY),
        "intro_sha256": BRAND_INTRO_SHA256,
        "outro_sha256": BRAND_OUTRO_SHA256,
        "constitution_rebind": rebind,
    }


def production_readiness_result(*, m01: Mapping[str, Any], m02: Mapping[str, Any], m03: Mapping[str, Any], self_test: Mapping[str, Any], simulation: Mapping[str, Any], r27: Mapping[str, Any]) -> dict[str, Any]:
    checks = {
        "M01": m01.get("status") == "PASS",
        "M02": m02.get("status") == "PASS",
        "M03": m03.get("status") == "PASS",
        "self_test": self_test.get("status") == "PASS",
        "offline_simulation": simulation.get("network_production_calls") == 0 and simulation.get("paid_calls") == 0,
        "r27_inventory": r27.get("status") == "PASS",
    }
    passed = all(checks.values())
    return {
        "pr01_status": "PR01_PRODUCTION_READINESS_PASS" if passed else "PR01_PRODUCTION_READINESS_BLOCKED",
        "production_readiness": "READY_FOR_EPISODE_SPECIFIC_PREFLIGHT" if passed else "NOT_READY",
        "production_authorized": False,
        "paid_execution_authorized": False,
        "publication_authorized": False,
        "checks": checks,
        "next_stage": "EP002_R27_RENDER_RECERTIFICATION" if passed else "REMEDIATE_PR01_BLOCKERS",
        "network_production_calls": 0,
        "paid_calls": 0,
        "retry_or_resubmission": 0,
        "montage": 0,
        "human_final_certification_required": True,
    }

def enforce_pr01_desktop_canonical_reference_gate(
    *,
    request: Any,
    reference_id: str,
) -> dict[str, Any]:
    """Separate Desktop-only gate for EP002 canonical-reference image starts.

    This does not relax the existing video-only PR01 gate. It validates a
    hash-bound, immutable Desktop authorization receipt for one exact Runware
    image payload and keeps production/R27 authorization false.
    """

    authorization = getattr(request, "master_authorization_reference", None)
    if not isinstance(authorization, Mapping):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_DESKTOP_APPROVAL_REQUIRED")
    approval = authorization.get(
        "pr01_canonical_reference_paid_start_authorization"
    )
    if not isinstance(approval, Mapping):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_DESKTOP_APPROVAL_REQUIRED")
    required = {
        "source": "DESKTOP",
        "scope": "EP002_CANONICAL_REFERENCE_GENERATION_ONLY",
        "reference_id": str(reference_id),
        "explicit_click": True,
        "human_approval": True,
        "production_authorized": False,
        "paid_execution_authorized": False,
    }
    for key, expected in required.items():
        if approval.get(key) != expected:
            raise PaidStartDenied(
                "PR01_CANONICAL_REFERENCE_APPROVAL_INVALID:" + key
            )
    auth_id = str(approval.get("authorization_id") or "").strip()
    click_nonce = str(approval.get("click_nonce") or "").strip()
    if not auth_id or click_nonce != auth_id:
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_CLICK_NONCE_INVALID")

    repo = Path(getattr(request, "repo_root")).resolve()
    receipt_path = Path(str(approval.get("authorization_receipt_path") or ""))
    if not receipt_path.is_absolute():
        receipt_path = repo / receipt_path
    receipt_path = receipt_path.resolve()
    try:
        receipt_path.relative_to(repo)
    except ValueError as exc:
        raise PaidStartDenied(
            "PR01_CANONICAL_REFERENCE_RECEIPT_OUTSIDE_REPOSITORY"
        ) from exc

    from src.application.artifact_provenance_v1 import (
        canonical_sha256 as _canonical_sha256_v2,
        sha256_file as _sha256_file_v2,
    )
    if (
        not receipt_path.is_file()
        or _sha256_file_v2(receipt_path)
        != str(approval.get("authorization_receipt_sha256") or "")
    ):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_RECEIPT_HASH_MISMATCH")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaidStartDenied(
            "PR01_CANONICAL_REFERENCE_RECEIPT_INVALID"
        ) from exc
    if not isinstance(receipt, dict):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_RECEIPT_INVALID")
    signature = receipt.get("authorization_sha256")
    unsigned = {
        key: value
        for key, value in receipt.items()
        if key != "authorization_sha256"
    }
    if (
        receipt.get("status") != "ACTIVE"
        or receipt.get("source") != "DESKTOP"
        or receipt.get("reference_id") != str(reference_id)
        or receipt.get("single_use") is not True
        or receipt.get("automatic_retry") is not False
        or receipt.get("automatic_resubmission") is not False
        or receipt.get("authorization_id") != auth_id
        or signature != _canonical_sha256_v2(unsigned)
    ):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_RECEIPT_INVALID")

    if str(getattr(request, "provider", "")) != "RUNWARE":
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_RUNWARE_REQUIRED")
    from src.application.provider_model_contracts import (
        ProviderModelContractError,
        validate_runware_task,
    )
    from src.application.runware_image_model_routing_v1 import (
        NANO_BANANA_MODEL,
        SEEDREAM_MODEL,
    )
    try:
        validated = validate_runware_task(
            getattr(request, "payload"),
            require_uuid_v4=True,
        )
    except ProviderModelContractError as exc:
        raise PaidStartDenied(str(exc)) from exc
    if validated.model not in {SEEDREAM_MODEL, NANO_BANANA_MODEL}:
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_MODEL_UNSUPPORTED")
    expected_payload_hash = _canonical_sha256_v2(dict(validated.payload))
    if (
        approval.get("payload_sha256") != expected_payload_hash
        or receipt.get("payload_sha256") != expected_payload_hash
    ):
        raise PaidStartDenied("PR01_CANONICAL_REFERENCE_PAYLOAD_HASH_MISMATCH")

    return {
        "status": "PR01_CANONICAL_REFERENCE_DESKTOP_GATE_PASS",
        "reference_id": str(reference_id),
        "payload_sha256": expected_payload_hash,
        "production_authorized": False,
        "paid_execution_authorized": False,
        "r27_reclassification_authorized": False,
        "r27_regeneration_authorized": False,
    }
