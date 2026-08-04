from __future__ import annotations

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

from src.application.episode_production_control_v1 import (
    assert_budget_allows_new_paid_request,
)
from src.application.runware_execution_v1 import (
    RUNWARE_API_URL,
    ProductionGateError,
    _download_video,
    _matching_data,
    _post_json,
    _response_error,
    canonical_sha256,
    file_sha256,
    load_execution_spec,
)

AUTOMATIC_STATE_NAME = "automatic-video-generation-state-v1.json"
AUTOMATIC_AUTHORIZATION_REL = Path(
    "projects/episode-001-adam/contracts/"
    "automatic-video-user-authorization-v1.json"
)
AUTOMATIC_REVIEW_NAME = "automatic-video-final-score-v1.json"
PASS_THRESHOLD = 80
MAX_ATTEMPTS = 3
MAX_COST_PER_ATTEMPT_USD = 0.40

ProgressCallback = Callable[[str, int | None], None]


@dataclass(frozen=True, slots=True)
class AttemptPlan:
    attempt_number: int
    prompt_variant: str
    positive_prompt: str
    seed: int


@dataclass(frozen=True, slots=True)
class AutomaticVideoSpec:
    repo_root: Path
    output_root: Path
    state_path: Path
    review_path: Path
    episode_id: str
    shot_id: str
    beat_id: str
    model: str
    width: int
    height: int
    duration: int
    plans: tuple[AttemptPlan, ...]


@dataclass(frozen=True, slots=True)
class AutomaticVideoResult:
    attempt_number: int
    task_uuid: str
    video_uuid: str
    output_path: Path
    output_sha256: str
    returned_seed: int | None
    actual_cost_usd: float | None
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


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def decision_for_score(score: int) -> str:
    value = int(score)
    if not 0 <= value <= 100:
        raise ProductionGateError("FINAL_SCORE_MUST_BE_0_TO_100")
    return "PASS" if value >= PASS_THRESHOLD else "FAIL"


def _revised_prompt(original: str) -> str:
    return (
        "One uninterrupted photorealistic cinematic macro shot with absolutely "
        "no cut, dissolve, morph, transition, time jump, or replacement of the "
        "scene. Keep the same small ordinary stone, the same earthen fissure, "
        "the same camera axis, and the same continuous spatial geometry visible "
        "throughout the full eight seconds. A thin stream of clear rainwater "
        "enters dry cracked soil at ground level. During the first two seconds, "
        "show individual grains visibly darkening and absorbing water in place. "
        "From seconds two through six, show those exact grains gradually "
        "loosening, swelling, sliding only a few millimeters, and physically "
        "binding into dense layered wet clay while the original fissure and "
        "stone remain continuously identifiable. The clay layers must form "
        "progressively inside the same composition, never appearing as a second "
        "image or a new scene. During the final two seconds, the same current "
        "curls once around the same stone into one small natural eddy, then "
        "slows and settles while the camera remains on the same continuous "
        "macro view. Use restrained earth colors, soft overcast daylight, "
        "realistic capillary absorption, surface tension, sediment movement, "
        "and physically plausible water and clay behavior. Camera: one very "
        "slow perfectly stabilized forward macro glide, no shake, no zoom, no "
        "speed ramp. No person, human form, face, limbs, creature, animal, "
        "supernatural being, magical energy, luminous symbols, writing, text, "
        "logo, or watermark. The clay never forms a humanoid shape. No large "
        "whirlpool. No cross-fade, ghosting, double exposure, or scene change. "
        "The final frame must be the physically evolved state of the exact "
        "opening frame."
    )


def _fallback_prompt(original: str) -> str:
    return (
        "A single continuous eight-second photorealistic macro documentary shot "
        "of rainwater soaking one fixed patch of cracked earth around one small "
        "stone. Do not attempt a dramatic transformation or a new final "
        "composition. Preserve the same camera, stone, cracks, and framing from "
        "start to finish. Show only subtle real-time physical changes: soil "
        "grains darken, water enters the cracks, fine sediment softens into wet "
        "clay along the existing channel, and one tiny eddy around the stone "
        "calms before the final frame. No cut, transition, dissolve, morph, "
        "cross-fade, double exposure, ghosting, time jump, or scene replacement. "
        "One stable slow macro glide, grounded natural physics, muted brown and "
        "charcoal tones, shallow depth of field. No person, human figure, body "
        "shape, face, limbs, creature, animal, supernatural being, magical "
        "energy, symbols, writing, text, logo, or watermark. The clay never "
        "forms a humanoid shape."
    )


def load_automatic_video_spec(repo_root: Path) -> AutomaticVideoSpec:
    legacy = load_execution_spec(repo_root)
    authorization = _read_json(
        legacy.repo_root / AUTOMATIC_AUTHORIZATION_REL
    )
    if authorization.get("status") != "AUTHORIZED":
        raise ProductionGateError("AUTOMATIC_VIDEO_AUTHORIZATION_MISSING")
    if authorization.get("execution_surface") != "SIRAJ_DESKTOP_UI_ONLY":
        raise ProductionGateError("DESKTOP_EXECUTION_SURFACE_REQUIRED")
    generation = authorization.get("generation_policy")
    review = authorization.get("review_policy")
    if not isinstance(generation, Mapping) or not isinstance(review, Mapping):
        raise ProductionGateError("AUTOMATIC_VIDEO_POLICY_MISSING")
    if generation.get("maximum_attempts") != MAX_ATTEMPTS:
        raise ProductionGateError("MAXIMUM_ATTEMPTS_CHANGED")
    if float(
        generation.get("maximum_cost_per_attempt_usd", -1)
    ) != MAX_COST_PER_ATTEMPT_USD:
        raise ProductionGateError("MAXIMUM_COST_PER_ATTEMPT_CHANGED")
    if generation.get("background_paid_retry_without_click") != "BLOCKED":
        raise ProductionGateError("BACKGROUND_PAID_RETRY_MUST_REMAIN_BLOCKED")
    if review.get("required_input") != "ONE_INTEGER_ONLY_0_TO_100":
        raise ProductionGateError("SCORE_ONLY_REVIEW_CONTRACT_CHANGED")
    if review.get("pass_threshold") != PASS_THRESHOLD:
        raise ProductionGateError("PASS_THRESHOLD_CHANGED")
    plans = (
        AttemptPlan(
            attempt_number=1,
            prompt_variant="ORIGINAL_SHOT_PACKAGE",
            positive_prompt=legacy.positive_prompt,
            seed=legacy.seed,
        ),
        AttemptPlan(
            attempt_number=2,
            prompt_variant="CONTINUITY_AND_PHYSICS_REPAIR",
            positive_prompt=_revised_prompt(legacy.positive_prompt),
            seed=(legacy.seed + 1) % (2**32),
        ),
        AttemptPlan(
            attempt_number=3,
            prompt_variant="SIMPLIFIED_CONTINUOUS_FALLBACK",
            positive_prompt=_fallback_prompt(legacy.positive_prompt),
            seed=(legacy.seed + 2) % (2**32),
        ),
    )
    output_root = legacy.output_dir
    return AutomaticVideoSpec(
        repo_root=legacy.repo_root,
        output_root=output_root,
        state_path=output_root / AUTOMATIC_STATE_NAME,
        review_path=output_root / AUTOMATIC_REVIEW_NAME,
        episode_id=legacy.episode_id,
        shot_id=legacy.shot_id,
        beat_id=legacy.beat_id,
        model=legacy.model,
        width=legacy.width,
        height=legacy.height,
        duration=legacy.duration,
        plans=plans,
    )


def _base_state(spec: AutomaticVideoSpec) -> dict[str, Any]:
    return {
        "schema_version": "siraj-automatic-video-generation-state-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "status": "READY_TO_GENERATE",
        "current_attempt": 1,
        "maximum_attempts": MAX_ATTEMPTS,
        "pass_threshold": PASS_THRESHOLD,
        "maximum_cost_per_attempt_usd": MAX_COST_PER_ATTEMPT_USD,
        "attempts": [],
        "accepted_output_path_relative": None,
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
    }


def _legacy_receipt_path(spec: AutomaticVideoSpec) -> Path:
    return spec.output_root / "runware-beat-01-execution-receipt-v1.json"


def _legacy_review_path(spec: AutomaticVideoSpec) -> Path:
    return spec.output_root / "runware-beat-01-human-review-v1.json"


def _import_legacy_attempt(
    spec: AutomaticVideoSpec,
    state: dict[str, Any],
) -> dict[str, Any]:
    receipt_path = _legacy_receipt_path(spec)
    if not receipt_path.is_file():
        return state
    receipt = _read_json(receipt_path)
    if not str(receipt.get("status", "")).startswith("SUCCESS"):
        return state
    relative = receipt.get("output_path_relative")
    if not isinstance(relative, str):
        return state
    output_path = spec.repo_root / relative
    if not output_path.is_file():
        return state
    actual_hash = file_sha256(output_path)
    if actual_hash != receipt.get("output_sha256"):
        raise ProductionGateError("LEGACY_OUTPUT_HASH_MISMATCH")

    attempt = {
        "attempt_number": 1,
        "prompt_variant": "ORIGINAL_SHOT_PACKAGE",
        "status": "GENERATED_AWAITING_SCORE",
        "task_uuid": receipt.get("task_uuid"),
        "video_uuid": receipt.get("video_uuid"),
        "output_path_relative": relative,
        "output_filename": output_path.name,
        "output_sha256": actual_hash,
        "returned_seed": receipt.get("returned_seed"),
        "actual_cost_usd": receipt.get("actual_cost_usd"),
        "legacy_receipt_imported": True,
        "generated_at_utc": receipt.get("completed_at_utc"),
        "score": None,
        "decision": None,
    }
    state["attempts"] = [attempt]
    state["current_attempt"] = 1
    state["status"] = "AWAITING_SCORE"

    legacy_review_path = _legacy_review_path(spec)
    if legacy_review_path.is_file():
        review = _read_json(legacy_review_path)
        total = review.get("score_total")
        if isinstance(total, int) and 0 <= total <= 100:
            attempt["score"] = total
            attempt["decision"] = decision_for_score(total)
            if attempt["decision"] == "PASS":
                state["status"] = "ACCEPTED"
                state["accepted_output_path_relative"] = relative
            else:
                state["status"] = "READY_TO_GENERATE"
                state["current_attempt"] = 2
    state["updated_at_utc"] = _now_utc()
    return state


def _reconcile_state(
    spec: AutomaticVideoSpec,
    state: dict[str, Any],
) -> dict[str, Any]:
    status = str(state.get("status", ""))
    attempt_number = int(state.get("current_attempt", 1))
    if 1 <= attempt_number <= MAX_ATTEMPTS:
        receipt_path = _receipt_path(spec, attempt_number)
        entry = _attempt_record(state, attempt_number)
        if receipt_path.is_file():
            receipt = _read_json(receipt_path)
            relative = receipt.get("output_path_relative")
            if (
                str(receipt.get("status", "")).startswith("SUCCESS")
                and isinstance(relative, str)
                and (spec.repo_root / relative).is_file()
            ):
                if entry is None:
                    entry = _ensure_attempt_entry(
                        state,
                        _plan(spec, attempt_number),
                    )
                entry.update(
                    {
                        "status": "GENERATED_AWAITING_SCORE",
                        "task_uuid": receipt.get("task_uuid"),
                        "video_uuid": receipt.get("video_uuid"),
                        "output_path_relative": relative,
                        "output_filename": receipt.get("output_filename"),
                        "output_sha256": receipt.get("output_sha256"),
                        "returned_seed": receipt.get("returned_seed"),
                        "actual_cost_usd": receipt.get("actual_cost_usd"),
                    }
                )
                if entry.get("score") is None:
                    state["status"] = "AWAITING_SCORE"
        elif status == "GENERATING" and _lock_path(
            spec,
            attempt_number,
        ).is_file():
            state["status"] = "RECOVERY_REQUIRED"
    return state


def load_state(spec: AutomaticVideoSpec) -> dict[str, Any]:
    spec.output_root.mkdir(parents=True, exist_ok=True)
    if spec.state_path.is_file():
        state = _read_json(spec.state_path)
    else:
        state = _import_legacy_attempt(spec, _base_state(spec))
    state = _reconcile_state(spec, state)
    _atomic_write_json(spec.state_path, state)
    return state


def _attempt_record(
    state: Mapping[str, Any],
    attempt_number: int,
) -> dict[str, Any] | None:
    attempts = state.get("attempts")
    if not isinstance(attempts, list):
        return None
    for item in attempts:
        if (
            isinstance(item, dict)
            and item.get("attempt_number") == attempt_number
        ):
            return item
    return None


def _plan(spec: AutomaticVideoSpec, number: int) -> AttemptPlan:
    for plan in spec.plans:
        if plan.attempt_number == number:
            return plan
    raise ProductionGateError("ATTEMPT_PLAN_NOT_AVAILABLE")


def _attempt_directory(spec: AutomaticVideoSpec, number: int) -> Path:
    return spec.output_root / f"attempt-{number:02d}"


def _lock_path(spec: AutomaticVideoSpec, number: int) -> Path:
    return _attempt_directory(spec, number) / "submission-lock-v1.json"


def _receipt_path(spec: AutomaticVideoSpec, number: int) -> Path:
    return _attempt_directory(spec, number) / "execution-receipt-v1.json"


def build_attempt_payload(
    spec: AutomaticVideoSpec,
    plan: AttemptPlan,
    task_uuid: str,
) -> list[dict[str, Any]]:
    parsed = uuid.UUID(task_uuid)
    if parsed.version != 4:
        raise ProductionGateError("TASK_UUID_V4_REQUIRED")
    return [
        {
            "taskType": "videoInference",
            "taskUUID": task_uuid,
            "model": spec.model,
            "positivePrompt": plan.positive_prompt,
            "width": spec.width,
            "height": spec.height,
            "duration": spec.duration,
            "seed": plan.seed,
            "numberResults": 1,
            "outputType": "URL",
            "outputFormat": "MP4",
            "includeCost": True,
            "deliveryMethod": "async",
            "providerSettings": {
                "google": {
                    "generateAudio": False,
                    "personGeneration": "dont_allow",
                }
            },
        }
    ]


def _write_lock(
    spec: AutomaticVideoSpec,
    plan: AttemptPlan,
    task_uuid: str,
    payload: list[dict[str, Any]],
) -> None:
    path = _lock_path(spec, plan.attempt_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "siraj-automatic-video-submission-lock-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "attempt_number": plan.attempt_number,
        "task_uuid": task_uuid,
        "prompt_variant": plan.prompt_variant,
        "status": "SUBMISSION_LOCKED_BEFORE_NETWORK",
        "request_payload_sha256": canonical_sha256({"tasks": payload}),
        "automatic_resubmission": "BLOCKED",
        "api_key_persisted_in_project": False,
        "created_at_utc": _now_utc(),
    }
    raw = (
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise ProductionGateError(
            "ATTEMPT_ALREADY_LOCKED_RECOVERY_REQUIRED"
        ) from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


def _update_lock(
    spec: AutomaticVideoSpec,
    attempt_number: int,
    **updates: Any,
) -> None:
    path = _lock_path(spec, attempt_number)
    record = _read_json(path)
    record.update(updates)
    record["updated_at_utc"] = _now_utc()
    record["api_key_persisted_in_project"] = False
    _atomic_write_json(path, record)


def _persist_state(spec: AutomaticVideoSpec, state: dict[str, Any]) -> None:
    state["updated_at_utc"] = _now_utc()
    _atomic_write_json(spec.state_path, state)


def _ensure_attempt_entry(
    state: dict[str, Any],
    plan: AttemptPlan,
) -> dict[str, Any]:
    existing = _attempt_record(state, plan.attempt_number)
    if existing is not None:
        return existing
    entry = {
        "attempt_number": plan.attempt_number,
        "prompt_variant": plan.prompt_variant,
        "status": "READY_TO_GENERATE",
        "task_uuid": None,
        "video_uuid": None,
        "output_path_relative": None,
        "output_filename": None,
        "output_sha256": None,
        "returned_seed": None,
        "actual_cost_usd": None,
        "score": None,
        "decision": None,
    }
    attempts = state.setdefault("attempts", [])
    if not isinstance(attempts, list):
        raise ProductionGateError("STATE_ATTEMPTS_INVALID")
    attempts.append(entry)
    return entry


def current_output_path(repo_root: Path) -> Path | None:
    spec = load_automatic_video_spec(repo_root)
    state = load_state(spec)
    number = int(state.get("current_attempt", 1))
    entry = _attempt_record(state, number)
    if entry is None and state.get("status") == "ACCEPTED":
        relative = state.get("accepted_output_path_relative")
    else:
        relative = entry.get("output_path_relative") if entry else None
    if not isinstance(relative, str):
        return None
    path = spec.repo_root / relative
    return path if path.is_file() else None


def _finalize_success(
    spec: AutomaticVideoSpec,
    state: dict[str, Any],
    plan: AttemptPlan,
    task_uuid: str,
    item: Mapping[str, Any],
    payload: list[dict[str, Any]],
    progress: ProgressCallback,
) -> AutomaticVideoResult:
    video_url = str(item.get("videoURL", "")).strip()
    video_uuid = str(item.get("videoUUID", "")).strip()
    if not video_url or not video_uuid:
        raise ProductionGateError("SUCCESS_RESPONSE_MISSING_VIDEO")

    progress("تنزيل الفيديو الناتج…", 96)
    output_dir = _attempt_directory(spec, plan.attempt_number)
    output_path = (
        output_dir
        / f"{spec.beat_id}_attempt-{plan.attempt_number:02d}_{task_uuid}.mp4"
    )
    output_hash, output_size = _download_video(video_url, output_path)
    returned_seed = (
        int(item["seed"])
        if isinstance(item.get("seed"), (int, float))
        else None
    )
    actual_cost = (
        float(item["cost"])
        if isinstance(item.get("cost"), (int, float))
        else None
    )
    status = "SUCCESS"
    if (
        actual_cost is not None
        and actual_cost > MAX_COST_PER_ATTEMPT_USD + 1e-9
    ):
        status = "SUCCESS_COST_CAP_BREACH_RECORDED"

    receipt = {
        "schema_version": "siraj-automatic-video-execution-receipt-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "attempt_number": plan.attempt_number,
        "prompt_variant": plan.prompt_variant,
        "task_uuid": task_uuid,
        "video_uuid": video_uuid,
        "video_url": video_url,
        "status": status,
        "request_payload": payload,
        "request_payload_sha256": canonical_sha256({"tasks": payload}),
        "output_path_relative": str(output_path.relative_to(spec.repo_root)),
        "output_filename": output_path.name,
        "output_sha256": output_hash,
        "output_size_bytes": output_size,
        "returned_seed": returned_seed,
        "actual_cost_usd": actual_cost,
        "maximum_cost_per_attempt_usd": MAX_COST_PER_ATTEMPT_USD,
        "api_key_persisted_in_project": False,
        "completed_at_utc": _now_utc(),
    }
    _atomic_write_json(
        _receipt_path(spec, plan.attempt_number),
        receipt,
    )
    _update_lock(
        spec,
        plan.attempt_number,
        status=status,
        video_uuid=video_uuid,
        output_filename=output_path.name,
        output_sha256=output_hash,
        actual_cost_usd=actual_cost,
    )

    entry = _ensure_attempt_entry(state, plan)
    entry.update(
        {
            "status": "GENERATED_AWAITING_SCORE",
            "task_uuid": task_uuid,
            "video_uuid": video_uuid,
            "output_path_relative": str(output_path.relative_to(spec.repo_root)),
            "output_filename": output_path.name,
            "output_sha256": output_hash,
            "returned_seed": returned_seed,
            "actual_cost_usd": actual_cost,
            "generated_at_utc": _now_utc(),
        }
    )
    state["status"] = "AWAITING_SCORE"
    state["current_attempt"] = plan.attempt_number
    _persist_state(spec, state)
    progress("اكتمل التوليد والتنزيل. أدخل تقييمًا من 0 إلى 100.", 100)
    return AutomaticVideoResult(
        attempt_number=plan.attempt_number,
        task_uuid=task_uuid,
        video_uuid=video_uuid,
        output_path=output_path,
        output_sha256=output_hash,
        returned_seed=returned_seed,
        actual_cost_usd=actual_cost,
        status=status,
    )


def _poll(
    spec: AutomaticVideoSpec,
    state: dict[str, Any],
    plan: AttemptPlan,
    api_key: str,
    task_uuid: str,
    payload: list[dict[str, Any]],
    progress: ProgressCallback,
    max_wait_seconds: float,
) -> AutomaticVideoResult:
    deadline = time.monotonic() + max_wait_seconds
    delay = 8.0
    while time.monotonic() < deadline:
        progress("Runware يعالج الفيديو…", None)
        time.sleep(delay)
        response = _post_json(
            api_key,
            [{"taskType": "getResponse", "taskUUID": task_uuid}],
        )
        error = _response_error(response)
        if error:
            _update_lock(
                spec,
                plan.attempt_number,
                status="RUNWARE_ERROR",
                error=error,
            )
            raise ProductionGateError(error)
        item = _matching_data(response, task_uuid)
        if item is None:
            delay = min(20.0, delay * 1.35)
            continue
        status = str(item.get("status", "")).lower()
        if status == "error":
            error = str(item.get("message", "RUNWARE_TASK_ERROR"))
            _update_lock(
                spec,
                plan.attempt_number,
                status="RUNWARE_ERROR",
                error=error,
            )
            raise ProductionGateError(error)
        if status == "success" or item.get("videoURL"):
            return _finalize_success(
                spec,
                state,
                plan,
                task_uuid,
                item,
                payload,
                progress,
            )
        value = item.get("progress")
        if isinstance(value, (int, float)):
            progress(f"التوليد: {int(value)}٪", max(1, min(94, int(value))))
        delay = min(20.0, delay * 1.35)
    _update_lock(
        spec,
        plan.attempt_number,
        status="POLLING_TIMEOUT_RECOVERABLE",
    )
    raise ProductionGateError("POLLING_TIMEOUT_PRESS_CREATE_VIDEO_TO_RECOVER")


def generate_or_resume(
    repo_root: Path,
    api_key: str,
    *,
    progress: ProgressCallback | None = None,
    max_wait_seconds: float = 1800.0,
) -> AutomaticVideoResult:
    callback = progress or (lambda message, value: None)
    key = api_key.strip()
    if not key:
        raise ProductionGateError("RUNWARE_API_KEY_REQUIRED")

    spec = load_automatic_video_spec(repo_root)
    state = load_state(spec)
    status = str(state.get("status", ""))
    if status == "ACCEPTED":
        raise ProductionGateError("CURRENT_VIDEO_ALREADY_ACCEPTED")
    if status == "AWAITING_SCORE":
        raise ProductionGateError("FINAL_SCORE_REQUIRED_BEFORE_NEXT_ATTEMPT")
    if status == "REQUIRES_PROMPT_REDESIGN":
        raise ProductionGateError("MAXIMUM_ATTEMPTS_REACHED")

    attempt_number = int(state.get("current_attempt", 1))
    if not 1 <= attempt_number <= MAX_ATTEMPTS:
        raise ProductionGateError("CURRENT_ATTEMPT_OUT_OF_RANGE")
    plan = _plan(spec, attempt_number)
    entry = _ensure_attempt_entry(state, plan)
    lock_path = _lock_path(spec, attempt_number)

    if lock_path.is_file():
        lock = _read_json(lock_path)
        task_uuid = str(lock.get("task_uuid", "")).strip()
        if not task_uuid:
            raise ProductionGateError("LOCK_TASK_UUID_MISSING")
        payload = build_attempt_payload(spec, plan, task_uuid)
        callback("استعادة المهمة القائمة دون إنشاء طلب جديد…", 2)
        return _poll(
            spec,
            state,
            plan,
            key,
            task_uuid,
            payload,
            callback,
            max_wait_seconds,
        )

    assert_budget_allows_new_paid_request(
        spec.repo_root,
        MAX_COST_PER_ATTEMPT_USD,
    )
    task_uuid = str(uuid.uuid4())
    payload = build_attempt_payload(spec, plan, task_uuid)
    _write_lock(spec, plan, task_uuid, payload)
    entry.update(
        {
            "status": "SUBMISSION_LOCKED",
            "task_uuid": task_uuid,
        }
    )
    state["status"] = "GENERATING"
    _persist_state(spec, state)
    callback(
        f"إرسال المحاولة {attempt_number} تلقائيًا…",
        1,
    )
    try:
        response = _post_json(key, payload)
    except Exception as exc:
        _update_lock(
            spec,
            attempt_number,
            status="SUBMISSION_AMBIGUOUS_RECOVERY_ONLY",
            error=str(exc),
        )
        state["status"] = "RECOVERY_REQUIRED"
        _persist_state(spec, state)
        raise

    error = _response_error(response)
    if error:
        _update_lock(
            spec,
            attempt_number,
            status="RUNWARE_REJECTED",
            error=error,
        )
        state["status"] = "RECOVERY_REQUIRED"
        _persist_state(spec, state)
        raise ProductionGateError(error)

    _update_lock(
        spec,
        attempt_number,
        status="SUBMITTED_POLLING",
        submission_response=response,
    )
    immediate = _matching_data(response, task_uuid)
    if immediate is not None and (
        immediate.get("status") == "success"
        or immediate.get("videoURL")
    ):
        return _finalize_success(
            spec,
            state,
            plan,
            task_uuid,
            immediate,
            payload,
            callback,
        )
    return _poll(
        spec,
        state,
        plan,
        key,
        task_uuid,
        payload,
        callback,
        max_wait_seconds,
    )


def save_final_score(repo_root: Path, score: int) -> dict[str, Any]:
    spec = load_automatic_video_spec(repo_root)
    state = load_state(spec)
    if state.get("status") != "AWAITING_SCORE":
        raise ProductionGateError("NO_GENERATED_VIDEO_AWAITING_SCORE")

    value = int(score)
    decision = decision_for_score(value)
    attempt_number = int(state.get("current_attempt", 1))
    entry = _attempt_record(state, attempt_number)
    if entry is None:
        raise ProductionGateError("CURRENT_ATTEMPT_RECORD_MISSING")
    relative = entry.get("output_path_relative")
    expected_hash = entry.get("output_sha256")
    if not isinstance(relative, str) or not isinstance(expected_hash, str):
        raise ProductionGateError("CURRENT_OUTPUT_RECORD_INCOMPLETE")
    output_path = spec.repo_root / relative
    if not output_path.is_file():
        raise ProductionGateError("GENERATED_VIDEO_FILE_MISSING")
    actual_hash = file_sha256(output_path)
    if actual_hash != expected_hash:
        raise ProductionGateError("GENERATED_VIDEO_HASH_MISMATCH")

    entry["score"] = value
    entry["decision"] = decision
    entry["reviewed_at_utc"] = _now_utc()
    entry["status"] = "ACCEPTED" if decision == "PASS" else "REJECTED"

    if decision == "PASS":
        state["status"] = "ACCEPTED"
        state["accepted_output_path_relative"] = relative
        next_stage = "EPISODE_QUEUE_SELECT_NEXT_VIDEO_SHOT"
    elif attempt_number < MAX_ATTEMPTS:
        state["current_attempt"] = attempt_number + 1
        state["status"] = "READY_TO_GENERATE"
        next_stage = f"GENERATE_ATTEMPT_{attempt_number + 1:02d}"
    else:
        state["status"] = "REQUIRES_PROMPT_REDESIGN"
        next_stage = "MANUAL_PROMPT_REDESIGN_REQUIRED"

    review = {
        "schema_version": "siraj-automatic-video-final-score-v1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "attempt_number": attempt_number,
        "output_path_relative": relative,
        "output_sha256": actual_hash,
        "final_score_0_to_100": value,
        "pass_threshold": PASS_THRESHOLD,
        "decision": decision,
        "next_stage": next_stage,
        "review_input_contract": "ONE_INTEGER_ONLY_0_TO_100",
        "reviewed_at_utc": _now_utc(),
    }
    reviews = state.setdefault("reviews", [])
    if not isinstance(reviews, list):
        raise ProductionGateError("STATE_REVIEWS_INVALID")
    reviews.append(review)
    _persist_state(spec, state)
    _atomic_write_json(spec.review_path, review)
    return review
