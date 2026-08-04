from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

RUNWARE_API_URL = "https://api.runware.ai/v1"
PACKAGE_REL = Path(
    "projects/episode-001-adam/cinematic/shot-packages/"
    "adam-dc2-s02-sh03/veo-shot-pack-001-v1.json"
)
AUTHORIZATION_REL = Path(
    "projects/episode-001-adam/contracts/"
    "runware-beat-01-execution-authorization-v1.json"
)
OUTPUT_DIR_REL = Path(
    "projects/episode-001-adam/cinematic/shot-packages/"
    "adam-dc2-s02-sh03/outputs"
)
LOCK_NAME = "runware-beat-01-execution-lock-v1.json"
RECEIPT_NAME = "runware-beat-01-execution-receipt-v1.json"
REVIEW_NAME = "runware-beat-01-human-review-v1.json"

EXPECTED_EPISODE_ID = "episode-001-adam"
EXPECTED_SHOT_ID = "ADAM-DC2-S02-SH03"
EXPECTED_BEAT_ID = "ADAM-DC2-S02-SH03-B01"
EXPECTED_PACKAGE_ID = "adam_veo_shot_pack_001_v1_afe8d586bc5cf23c"
EXPECTED_PACKAGE_SHA256 = (
    "3a8e48d5400ee786b4521495ddc4dd3317dd593ce68aa6ce151ab68fe886cb41"
)
EXPECTED_MODEL = "google:veo@3.1-lite"
EXPECTED_SEED = 3256281284
EXPECTED_DURATION = 8
EXPECTED_WIDTH = 1280
EXPECTED_HEIGHT = 720
EXPECTED_MAX_COST_USD = 0.40

ProgressCallback = Callable[[str, int | None], None]


class ProductionGateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    repo_root: Path
    package_path: Path
    authorization_path: Path
    output_dir: Path
    lock_path: Path
    receipt_path: Path
    review_path: Path
    episode_id: str
    shot_id: str
    beat_id: str
    package_id: str
    package_sha256: str
    model: str
    positive_prompt: str
    width: int
    height: int
    duration: int
    seed: int
    number_results: int
    output_format: str
    generate_audio: bool
    person_generation: str
    max_cost_usd: float


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    task_uuid: str
    video_uuid: str
    video_url: str
    output_path: Path
    output_sha256: str
    returned_seed: int | None
    actual_cost_usd: float | None
    receipt_path: Path
    status: str


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionGateError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise ProductionGateError(f"JSON_OBJECT_REQUIRED:{path}")
    return payload


def canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionGateError(f"OBJECT_REQUIRED:{label}")
    return value


def load_execution_spec(repo_root: Path) -> ExecutionSpec:
    repo = repo_root.resolve()
    package_path = repo / PACKAGE_REL
    authorization_path = repo / AUTHORIZATION_REL
    package = _read_json(package_path)
    authorization = _read_json(authorization_path)

    package_hash = canonical_sha256(package)
    if package_hash != EXPECTED_PACKAGE_SHA256:
        raise ProductionGateError(
            "SHOT_PACKAGE_CANONICAL_HASH_MISMATCH:"
            f"{package_hash}"
        )
    if authorization.get("shot_package_sha256") != package_hash:
        raise ProductionGateError("AUTHORIZATION_PACKAGE_HASH_MISMATCH")
    if authorization.get("human_approval") is not True:
        raise ProductionGateError("HUMAN_AUTHORIZATION_MISSING")
    if authorization.get("status") != (
        "AUTHORIZED_EXACTLY_ONE_DESKTOP_SUBMISSION"
    ):
        raise ProductionGateError("AUTHORIZATION_STATUS_INVALID")
    if authorization.get("execution_surface") != "SIRAJ_DESKTOP_UI_ONLY":
        raise ProductionGateError("DESKTOP_EXECUTION_SURFACE_REQUIRED")

    attempt_policy = _mapping(
        authorization.get("attempt_policy"),
        "attempt_policy",
    )
    if attempt_policy.get("maximum_submission_attempts") != 1:
        raise ProductionGateError("EXACTLY_ONE_SUBMISSION_REQUIRED")
    if attempt_policy.get("automatic_retry") != "BLOCKED":
        raise ProductionGateError("AUTOMATIC_RETRY_MUST_REMAIN_BLOCKED")
    if attempt_policy.get("full_episode_bulk_generation") != "BLOCKED":
        raise ProductionGateError("BULK_GENERATION_MUST_REMAIN_BLOCKED")
    if attempt_policy.get("beat_02_execution") != (
        "BLOCKED_UNTIL_BEAT_01_HUMAN_REVIEW"
    ):
        raise ProductionGateError("BEAT_02_MUST_REMAIN_BLOCKED")

    if package.get("episode_id") != EXPECTED_EPISODE_ID:
        raise ProductionGateError("EPISODE_ID_CHANGED")
    if package.get("shot_id") != EXPECTED_SHOT_ID:
        raise ProductionGateError("SHOT_ID_CHANGED")
    if package.get("shot_package_id") != EXPECTED_PACKAGE_ID:
        raise ProductionGateError("SHOT_PACKAGE_ID_CHANGED")

    beats = package.get("generation_beats")
    if not isinstance(beats, list):
        raise ProductionGateError("GENERATION_BEATS_MISSING")
    beat = next(
        (
            item
            for item in beats
            if isinstance(item, Mapping)
            and item.get("beat_id") == EXPECTED_BEAT_ID
        ),
        None,
    )
    if beat is None:
        raise ProductionGateError("AUTHORIZED_BEAT_MISSING")
    if beat.get("execution_status") != "NOT_AUTHORISED":
        raise ProductionGateError("IMMUTABLE_PACKAGE_EXECUTION_STATE_CHANGED")

    settings = _mapping(beat.get("settings"), "settings")
    provider_settings = _mapping(
        settings.get("provider_settings"),
        "provider_settings",
    )
    google = _mapping(provider_settings.get("google"), "provider_settings.google")

    expected = {
        "task_type": "videoInference",
        "model": EXPECTED_MODEL,
        "width": EXPECTED_WIDTH,
        "height": EXPECTED_HEIGHT,
        "duration": EXPECTED_DURATION,
        "seed": EXPECTED_SEED,
        "number_results": 1,
        "output_format": "MP4",
    }
    for key, value in expected.items():
        if settings.get(key) != value:
            raise ProductionGateError(f"SETTING_CHANGED:{key}")

    if google.get("generateAudio") is not False:
        raise ProductionGateError("AUDIO_MUST_REMAIN_DISABLED")
    if google.get("personGeneration") != "dont_allow":
        raise ProductionGateError("PERSON_GENERATION_MUST_REMAIN_DISABLED")

    prompt = beat.get("positive_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ProductionGateError("POSITIVE_PROMPT_MISSING")

    cap = float(authorization.get("maximum_authorised_cost_usd", -1))
    if abs(cap - EXPECTED_MAX_COST_USD) > 1e-9:
        raise ProductionGateError("AUTHORISED_COST_CAP_CHANGED")

    output_dir = repo / OUTPUT_DIR_REL
    return ExecutionSpec(
        repo_root=repo,
        package_path=package_path,
        authorization_path=authorization_path,
        output_dir=output_dir,
        lock_path=output_dir / LOCK_NAME,
        receipt_path=output_dir / RECEIPT_NAME,
        review_path=output_dir / REVIEW_NAME,
        episode_id=EXPECTED_EPISODE_ID,
        shot_id=EXPECTED_SHOT_ID,
        beat_id=EXPECTED_BEAT_ID,
        package_id=EXPECTED_PACKAGE_ID,
        package_sha256=package_hash,
        model=EXPECTED_MODEL,
        positive_prompt=prompt.strip(),
        width=EXPECTED_WIDTH,
        height=EXPECTED_HEIGHT,
        duration=EXPECTED_DURATION,
        seed=EXPECTED_SEED,
        number_results=1,
        output_format="MP4",
        generate_audio=False,
        person_generation="dont_allow",
        max_cost_usd=cap,
    )


def build_video_inference_payload(
    spec: ExecutionSpec,
    task_uuid: str,
) -> list[dict[str, Any]]:
    try:
        parsed = uuid.UUID(task_uuid)
    except ValueError as exc:
        raise ProductionGateError("TASK_UUID_V4_REQUIRED") from exc
    if parsed.version != 4:
        raise ProductionGateError("TASK_UUID_V4_REQUIRED")
    return [
        {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": spec.model,
            "positivePrompt": spec.positive_prompt,
            "width": spec.width,
            "height": spec.height,
            "duration": spec.duration,
            "seed": spec.seed,
            "numberResults": spec.number_results,
            "outputType": "URL",
            "outputFormat": spec.output_format,
            "includeCost": True,
            "deliveryMethod": "async",
            "providerSettings": {
                "google": {
                    "generateAudio": spec.generate_audio,
                    "personGeneration": spec.person_generation,
                }
            },
        }
    ]


def _create_submission_lock(
    spec: ExecutionSpec,
    task_uuid: str,
    request_payload: list[dict[str, Any]],
) -> dict[str, Any]:
    spec.output_dir.mkdir(parents=True, exist_ok=True)
    lock = {
        "schema_version": "siraj-runware-beat-execution-lock-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "task_uuid": task_uuid,
        "status": "SUBMISSION_LOCKED_BEFORE_NETWORK",
        "created_at_utc": _now_utc(),
        "maximum_submission_attempts": 1,
        "automatic_retry": "BLOCKED",
        "request_payload_sha256": canonical_sha256({"tasks": request_payload}),
        "api_key_persisted": False,
    }
    raw = (
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            spec.lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ProductionGateError(
            "SUBMISSION_ALREADY_LOCKED_USE_RECOVERY"
        ) from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)
    return lock


def _update_lock(spec: ExecutionSpec, **updates: Any) -> dict[str, Any]:
    lock = _read_json(spec.lock_path)
    lock.update(updates)
    lock["updated_at_utc"] = _now_utc()
    lock["api_key_persisted"] = False
    _atomic_write_json(spec.lock_path, lock)
    return lock


def read_execution_state(spec: ExecutionSpec) -> dict[str, Any]:
    state: dict[str, Any] = {
        "lock_exists": spec.lock_path.is_file(),
        "receipt_exists": spec.receipt_path.is_file(),
        "review_exists": spec.review_path.is_file(),
        "lock": None,
        "receipt": None,
        "review": None,
    }
    if state["lock_exists"]:
        state["lock"] = _read_json(spec.lock_path)
    if state["receipt_exists"]:
        state["receipt"] = _read_json(spec.receipt_path)
    if state["review_exists"]:
        state["review"] = _read_json(spec.review_path)
    return state


def _post_json(
    api_key: str,
    tasks: list[dict[str, Any]],
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    key = api_key.strip()
    if not key:
        raise ProductionGateError("RUNWARE_API_KEY_REQUIRED")
    body = json.dumps(tasks, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        RUNWARE_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "SIRAJ-Desktop-Production-Console/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_body = response.read()
    except urllib.error.HTTPError as exc:
        message = exc.read(2048).decode("utf-8", errors="replace")
        raise ProductionGateError(
            f"RUNWARE_HTTP_ERROR:{exc.code}:{message}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ProductionGateError(
            f"RUNWARE_NETWORK_ERROR:{exc.reason}"
        ) from exc
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionGateError("RUNWARE_RESPONSE_NOT_JSON") from exc
    if not isinstance(payload, dict):
        raise ProductionGateError("RUNWARE_RESPONSE_OBJECT_REQUIRED")
    return payload


def _response_error(payload: Mapping[str, Any]) -> str | None:
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if not isinstance(first, Mapping):
        return "RUNWARE_UNKNOWN_ERROR"
    return (
        f"{first.get('code', 'RUNWARE_ERROR')}:"
        f"{first.get('message', 'Unknown Runware error')}"
    )


def _matching_data(
    payload: Mapping[str, Any],
    task_uuid: str,
) -> Mapping[str, Any] | None:
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    matches = [
        item
        for item in data
        if isinstance(item, Mapping)
        and item.get("taskUUID") == task_uuid
    ]
    if not matches:
        return None
    for item in reversed(matches):
        if item.get("status") == "success" or item.get("videoURL"):
            return item
    return matches[-1]


def _download_video(
    url: str,
    destination: Path,
    *,
    timeout: float = 180.0,
) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SIRAJ-Desktop-Production-Console/1.0"},
    )
    digest = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if size <= 0:
        partial.unlink(missing_ok=True)
        raise ProductionGateError("DOWNLOADED_VIDEO_IS_EMPTY")
    os.replace(partial, destination)
    return digest.hexdigest(), size


def _write_failure_receipt(
    spec: ExecutionSpec,
    task_uuid: str,
    status: str,
    error: str,
    request_payload: list[dict[str, Any]],
) -> None:
    receipt = {
        "schema_version": "siraj-runware-beat-execution-receipt-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "task_uuid": task_uuid,
        "status": status,
        "error": error,
        "request_payload": request_payload,
        "request_payload_sha256": canonical_sha256({"tasks": request_payload}),
        "shot_package_id": spec.package_id,
        "shot_package_sha256": spec.package_sha256,
        "maximum_authorised_cost_usd": spec.max_cost_usd,
        "automatic_retry": "BLOCKED",
        "api_key_persisted": False,
        "recorded_at_utc": _now_utc(),
    }
    _atomic_write_json(spec.receipt_path, receipt)


def _finalize_success(
    spec: ExecutionSpec,
    task_uuid: str,
    item: Mapping[str, Any],
    request_payload: list[dict[str, Any]],
    progress: ProgressCallback,
) -> ExecutionResult:
    video_url = str(item.get("videoURL", "")).strip()
    video_uuid = str(item.get("videoUUID", "")).strip()
    if not video_url or not video_uuid:
        raise ProductionGateError("SUCCESS_RESPONSE_MISSING_VIDEO")
    progress("تنزيل ملف الفيديو…", 96)
    output_path = (
        spec.output_dir
        / f"{spec.beat_id}_{task_uuid}.mp4"
    )
    output_hash, output_size = _download_video(video_url, output_path)
    returned_seed_raw = item.get("seed")
    returned_seed = (
        int(returned_seed_raw)
        if isinstance(returned_seed_raw, (int, float))
        else None
    )
    cost_raw = item.get("cost")
    actual_cost = (
        float(cost_raw)
        if isinstance(cost_raw, (int, float))
        else None
    )
    status = "SUCCESS"
    if actual_cost is not None and actual_cost > spec.max_cost_usd + 1e-9:
        status = "SUCCESS_COST_CAP_BREACH_RECORDED"

    receipt = {
        "schema_version": "siraj-runware-beat-execution-receipt-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "task_uuid": task_uuid,
        "video_uuid": video_uuid,
        "video_url": video_url,
        "status": status,
        "request_payload": request_payload,
        "request_payload_sha256": canonical_sha256({"tasks": request_payload}),
        "shot_package_id": spec.package_id,
        "shot_package_sha256": spec.package_sha256,
        "output_filename": output_path.name,
        "output_path_relative": str(output_path.relative_to(spec.repo_root)),
        "output_sha256": output_hash,
        "output_size_bytes": output_size,
        "returned_seed": returned_seed,
        "actual_cost_usd": actual_cost,
        "maximum_authorised_cost_usd": spec.max_cost_usd,
        "automatic_retry": "BLOCKED",
        "beat_02_execution": "BLOCKED_UNTIL_BEAT_01_HUMAN_REVIEW",
        "api_key_persisted": False,
        "completed_at_utc": _now_utc(),
    }
    _atomic_write_json(spec.receipt_path, receipt)
    _update_lock(
        spec,
        status=status,
        video_uuid=video_uuid,
        output_filename=output_path.name,
        output_sha256=output_hash,
        actual_cost_usd=actual_cost,
    )
    progress("اكتمل التنزيل وتسجيل البصمة والإيصال.", 100)
    return ExecutionResult(
        task_uuid=task_uuid,
        video_uuid=video_uuid,
        video_url=video_url,
        output_path=output_path,
        output_sha256=output_hash,
        returned_seed=returned_seed,
        actual_cost_usd=actual_cost,
        receipt_path=spec.receipt_path,
        status=status,
    )


def _poll_task(
    spec: ExecutionSpec,
    api_key: str,
    task_uuid: str,
    request_payload: list[dict[str, Any]],
    *,
    progress: ProgressCallback,
    max_wait_seconds: float,
) -> ExecutionResult:
    deadline = time.monotonic() + max_wait_seconds
    delay = 8.0
    while time.monotonic() < deadline:
        progress("المهمة قيد المعالجة لدى Runware…", None)
        time.sleep(delay)
        payload = _post_json(
            api_key,
            [{"taskType": "getResponse", "taskUUID": task_uuid}],
        )
        error = _response_error(payload)
        if error:
            _update_lock(spec, status="RUNWARE_ERROR", error=error)
            _write_failure_receipt(
                spec,
                task_uuid,
                "RUNWARE_ERROR_NO_RETRY",
                error,
                request_payload,
            )
            raise ProductionGateError(error)
        item = _matching_data(payload, task_uuid)
        if item is None:
            delay = min(20.0, delay * 1.4)
            continue
        status = str(item.get("status", "")).lower()
        if status == "error":
            error = str(item.get("message", "RUNWARE_TASK_ERROR"))
            _update_lock(spec, status="RUNWARE_ERROR", error=error)
            _write_failure_receipt(
                spec,
                task_uuid,
                "RUNWARE_ERROR_NO_RETRY",
                error,
                request_payload,
            )
            raise ProductionGateError(error)
        if status == "success" or item.get("videoURL"):
            return _finalize_success(
                spec,
                task_uuid,
                item,
                request_payload,
                progress,
            )
        progress_raw = item.get("progress")
        progress_value = (
            max(1, min(94, int(progress_raw)))
            if isinstance(progress_raw, (int, float))
            else None
        )
        if progress_value is not None:
            progress(f"التوليد: {progress_value}٪", progress_value)
        delay = min(20.0, delay * 1.35)

    _update_lock(
        spec,
        status="POLLING_TIMEOUT_RECOVERABLE",
        error="Polling timed out; do not resubmit. Use recovery.",
    )
    raise ProductionGateError(
        "POLLING_TIMEOUT_USE_RECOVERY_DO_NOT_RESUBMIT"
    )


def execute_once(
    repo_root: Path,
    api_key: str,
    *,
    progress: ProgressCallback | None = None,
    max_wait_seconds: float = 1800.0,
) -> ExecutionResult:
    callback = progress or (lambda message, value: None)
    spec = load_execution_spec(repo_root)
    state = read_execution_state(spec)
    if state["receipt_exists"]:
        receipt = state["receipt"] or {}
        if str(receipt.get("status", "")).startswith("SUCCESS"):
            raise ProductionGateError("BEAT_ALREADY_GENERATED")
    if state["lock_exists"]:
        raise ProductionGateError("SUBMISSION_ALREADY_LOCKED_USE_RECOVERY")

    task_uuid = str(uuid.uuid4())
    request_payload = build_video_inference_payload(spec, task_uuid)
    _create_submission_lock(spec, task_uuid, request_payload)
    callback("تم قفل المحاولة الوحيدة قبل الاتصال بالشبكة.", 1)
    try:
        response = _post_json(api_key, request_payload)
    except Exception as exc:
        _update_lock(
            spec,
            status="SUBMISSION_AMBIGUOUS_NO_RESUBMISSION",
            error=str(exc),
        )
        _write_failure_receipt(
            spec,
            task_uuid,
            "SUBMISSION_AMBIGUOUS_NO_RETRY",
            str(exc),
            request_payload,
        )
        raise

    error = _response_error(response)
    if error:
        _update_lock(spec, status="RUNWARE_REJECTED", error=error)
        _write_failure_receipt(
            spec,
            task_uuid,
            "RUNWARE_REJECTED_NO_RETRY",
            error,
            request_payload,
        )
        raise ProductionGateError(error)

    _update_lock(
        spec,
        status="SUBMITTED_POLLING",
        submission_response=response,
    )
    callback("تم إرسال محاولة Beat 01 الوحيدة. بدأت المتابعة.", 3)
    immediate = _matching_data(response, task_uuid)
    if immediate is not None and (
        immediate.get("status") == "success"
        or immediate.get("videoURL")
    ):
        return _finalize_success(
            spec,
            task_uuid,
            immediate,
            request_payload,
            callback,
        )
    return _poll_task(
        spec,
        api_key,
        task_uuid,
        request_payload,
        progress=callback,
        max_wait_seconds=max_wait_seconds,
    )


def recover_existing(
    repo_root: Path,
    api_key: str,
    *,
    progress: ProgressCallback | None = None,
    max_wait_seconds: float = 1800.0,
) -> ExecutionResult:
    callback = progress or (lambda message, value: None)
    spec = load_execution_spec(repo_root)
    state = read_execution_state(spec)
    lock = state.get("lock")
    if not isinstance(lock, Mapping):
        raise ProductionGateError("NO_EXISTING_SUBMISSION_TO_RECOVER")
    task_uuid = str(lock.get("task_uuid", "")).strip()
    if not task_uuid:
        raise ProductionGateError("LOCK_TASK_UUID_MISSING")
    if state["receipt_exists"]:
        receipt = state["receipt"] or {}
        if str(receipt.get("status", "")).startswith("SUCCESS"):
            output_relative = receipt.get("output_path_relative")
            if isinstance(output_relative, str):
                output_path = spec.repo_root / output_relative
                if output_path.is_file():
                    return ExecutionResult(
                        task_uuid=task_uuid,
                        video_uuid=str(receipt.get("video_uuid", "")),
                        video_url=str(receipt.get("video_url", "")),
                        output_path=output_path,
                        output_sha256=str(receipt.get("output_sha256", "")),
                        returned_seed=receipt.get("returned_seed"),
                        actual_cost_usd=receipt.get("actual_cost_usd"),
                        receipt_path=spec.receipt_path,
                        status=str(receipt.get("status")),
                    )
    payload = build_video_inference_payload(spec, task_uuid)
    callback("استعادة المهمة نفسها دون إنشاء محاولة جديدة…", 2)
    return _poll_task(
        spec,
        api_key,
        task_uuid,
        payload,
        progress=callback,
        max_wait_seconds=max_wait_seconds,
    )


_SCORE_LIMITS = {
    "material_transformation": 25,
    "water_clay_physics": 25,
    "camera_composition": 15,
    "temporal_stability": 15,
    "visual_safety": 20,
}


def save_human_review(
    repo_root: Path,
    category_scores: Mapping[str, int],
    blocking_failures: str,
    notes: Mapping[str, str],
) -> dict[str, Any]:
    spec = load_execution_spec(repo_root)
    receipt = _read_json(spec.receipt_path)
    if not str(receipt.get("status", "")).startswith("SUCCESS"):
        raise ProductionGateError("SUCCESSFUL_EXECUTION_RECEIPT_REQUIRED")
    relative = receipt.get("output_path_relative")
    if not isinstance(relative, str):
        raise ProductionGateError("OUTPUT_PATH_MISSING_FROM_RECEIPT")
    output_path = spec.repo_root / relative
    if not output_path.is_file():
        raise ProductionGateError("GENERATED_VIDEO_FILE_MISSING")
    actual_hash = file_sha256(output_path)
    if actual_hash != receipt.get("output_sha256"):
        raise ProductionGateError("GENERATED_VIDEO_HASH_MISMATCH")

    clean_scores: dict[str, int] = {}
    for key, maximum in _SCORE_LIMITS.items():
        value = int(category_scores.get(key, -1))
        if not 0 <= value <= maximum:
            raise ProductionGateError(f"REVIEW_SCORE_OUT_OF_RANGE:{key}")
        clean_scores[key] = value
    total = sum(clean_scores.values())
    blocking = blocking_failures.strip()
    decision = "PASS" if total >= 80 and not blocking else "FAIL"
    review = {
        "schema_version": "siraj-runware-beat-01-human-review-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "task_uuid": receipt.get("task_uuid"),
        "video_uuid": receipt.get("video_uuid"),
        "output_filename": receipt.get("output_filename"),
        "output_sha256": actual_hash,
        "actual_cost_usd": receipt.get("actual_cost_usd"),
        "returned_seed": receipt.get("returned_seed"),
        "category_scores": clean_scores,
        "score_total": total,
        "pass_threshold": 80,
        "blocking_failures": blocking,
        "notes": {
            str(key): str(value).strip()
            for key, value in notes.items()
        },
        "human_decision": decision,
        "reviewed_at_utc": _now_utc(),
        "beat_02_execution": "BLOCKED",
        "next_stage": (
            "AUTHOR_BEAT_02_FROM_ACCEPTED_BEAT_01_OUTPUT"
            if decision == "PASS"
            else "REVISE_OR_SIMPLIFY_BEAT_01_WITH_NEW_AUTHORIZATION_REQUIRED"
        ),
    }
    _atomic_write_json(spec.review_path, review)
    _update_lock(
        spec,
        status=f"HUMAN_REVIEW_{decision}",
        human_review_score=total,
        human_review_path=str(spec.review_path.relative_to(spec.repo_root)),
    )
    return review
