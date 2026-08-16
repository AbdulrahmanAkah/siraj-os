from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import json
import mimetypes
from pathlib import Path
import time
from typing import Any, Mapping, Sequence
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    atomic_write_json,
    canonical_sha256,
    read_jsonl,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    execute_bytes as execute_paid_bytes,
    execute_json as execute_paid_json,
    http_download_transport,
    http_json_transport,
    record_provider_operation_id,
)
from src.application.pr01_production_readiness_v1 import (
    enforce_pr01_desktop_canonical_reference_gate,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_runware_task,
)
from src.application.runware_image_model_routing_v1 import (
    NEGATIVE_PROMPT_UNSUPPORTED_MODELS,
    route_image_shot,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_reference,
)

SCHEMA_VERSION = "siraj-desktop-canonical-reference-generation-v2"
EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "CANONICAL_REFERENCE_GENERATION"
RUNWARE_URL = "https://api.runware.ai/v1"

REFERENCE_ORDER = (
    "ADAM_GARDEN",
    "ADAM_EARTH",
    "ADAM_DEBATE",
    "HAWWA_GARDEN",
    "HAWWA_EARTH",
    "MUSA_DEBATE",
)
REFERENCE_DEPENDENCIES = {
    "ADAM_EARTH": ("ADAM_GARDEN",),
    "ADAM_DEBATE": ("ADAM_GARDEN",),
    "HAWWA_EARTH": ("HAWWA_GARDEN",),
}
DEFAULT_NEGATIVE = (
    "visible face, partial facial features, eyes, nose, mouth, facial reflection, "
    "modern clothing, logos, zippers, technical fabrics, glamour styling, nudity, "
    "body exposure, fantasy spectacle, aggressive pointing, hostile posture, "
    "anachronistic objects"
)


class CanonicalReferenceGenerationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalReferenceStatus:
    reference_id: str
    filename: str
    status: str
    sha256: str | None
    accepted: bool
    human_review: str
    candidate_path: str | None
    candidate_sha256: str | None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CanonicalReferenceGenerationError(
            "JSON_READ_FAILED:" + str(path)
        ) from exc
    if not isinstance(value, dict):
        raise CanonicalReferenceGenerationError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _repo_relative(repo_root: Path, path: Path) -> str:
    return str(Path(path).resolve().relative_to(Path(repo_root).resolve())).replace("\\", "/")


def _resolve_repo_path(repo_root: Path, value: str) -> Path:
    repo = Path(repo_root).resolve()
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    path = path.resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise CanonicalReferenceGenerationError(
            "PATH_OUTSIDE_REPOSITORY:" + str(path)
        ) from exc
    return path


def _orchestration_root(repo_root: Path) -> Path:
    return Path(repo_root).resolve() / "projects" / EPISODE_ID / "orchestration"


def _reference_root(repo_root: Path) -> Path:
    return _orchestration_root(repo_root) / "canonical-reference-v1"


def _preparation_path(repo_root: Path) -> Path:
    return (
        Path(repo_root).resolve()
        / "reports"
        / "pr01-production-readiness"
        / "EP002_R27_CANONICAL_REFERENCE_PREPARATION_RESULT_V1.json"
    )


def preparation_result(repo_root: Path) -> dict[str, Any]:
    value = _read_json(_preparation_path(repo_root))
    if value.get("status") != "PASS_CANONICAL_REFERENCE_PREPARATION":
        raise CanonicalReferenceGenerationError("REFERENCE_PREPARATION_NOT_PASS")
    if value.get("current_r27_counts") != {
        "KEEP": 0,
        "REGENERATE": 0,
        "BLOCK": 27,
    }:
        raise CanonicalReferenceGenerationError("R27_STATE_CHANGED_BEFORE_REFERENCE_GATE")
    if value.get("reclassification_performed") is not False:
        raise CanonicalReferenceGenerationError("R27_RECLASSIFICATION_ALREADY_PERFORMED")
    if value.get("regeneration_authorized") is not False:
        raise CanonicalReferenceGenerationError("R27_REGENERATION_ALREADY_AUTHORIZED")
    return value


def briefs_path(repo_root: Path) -> Path:
    prep = preparation_result(repo_root)
    return _resolve_repo_path(repo_root, str(prep["reference_briefs_path"]))


def checklist_path(repo_root: Path) -> Path:
    prep = preparation_result(repo_root)
    return _resolve_repo_path(repo_root, str(prep["acceptance_checklist_path"]))


def intake_path(repo_root: Path) -> Path:
    prep = preparation_result(repo_root)
    return _resolve_repo_path(repo_root, str(prep["asset_intake_path"]))


def asset_directory(repo_root: Path) -> Path:
    prep = preparation_result(repo_root)
    return _resolve_repo_path(repo_root, str(prep["reference_asset_directory"]))


def candidate_directory(repo_root: Path) -> Path:
    return _reference_root(repo_root) / "candidates"


def plan_directory(repo_root: Path) -> Path:
    return _reference_root(repo_root) / "plans"


def authorization_directory(repo_root: Path) -> Path:
    return _reference_root(repo_root) / "authorizations"


def authorization_consumption_ledger(repo_root: Path) -> Path:
    return _reference_root(repo_root) / "authorization-consumption-v1.jsonl"


def review_directory(repo_root: Path) -> Path:
    return _reference_root(repo_root) / "review"


def load_briefs(repo_root: Path) -> dict[str, Any]:
    value = _read_json(briefs_path(repo_root))
    refs = value.get("references")
    if not isinstance(refs, list):
        raise CanonicalReferenceGenerationError("REFERENCE_BRIEFS_INVALID")
    if int(value.get("reference_count") or 0) != 6:
        raise CanonicalReferenceGenerationError("REFERENCE_COUNT_INVALID")
    return value


def load_checklist(repo_root: Path) -> dict[str, Any]:
    value = _read_json(checklist_path(repo_root))
    if value.get("human_review_required") is not True:
        raise CanonicalReferenceGenerationError("HUMAN_REVIEW_GATE_REQUIRED")
    if value.get("automatic_pass_allowed") is not False:
        raise CanonicalReferenceGenerationError("AUTOMATIC_REFERENCE_PASS_FORBIDDEN")
    return value


def load_intake(repo_root: Path) -> dict[str, Any]:
    value = _read_json(intake_path(repo_root))
    required = value.get("required_assets")
    if not isinstance(required, list):
        raise CanonicalReferenceGenerationError("REFERENCE_INTAKE_INVALID")
    return value


def _reference_entry(briefs: Mapping[str, Any], reference_id: str) -> dict[str, Any]:
    for item in briefs.get("references", []):
        if isinstance(item, Mapping) and item.get("reference_id") == reference_id:
            return dict(item)
    raise CanonicalReferenceGenerationError("UNKNOWN_REFERENCE_ID:" + reference_id)


def _intake_entry(intake: dict[str, Any], reference_id: str) -> dict[str, Any]:
    for item in intake.get("required_assets", []):
        if isinstance(item, dict) and item.get("reference_id") == reference_id:
            return item
    raise CanonicalReferenceGenerationError("INTAKE_REFERENCE_MISSING:" + reference_id)


def required_checks(repo_root: Path, reference_id: str) -> tuple[str, ...]:
    checklist = load_checklist(repo_root)
    common = checklist.get("common_checks")
    specific = checklist.get("state_specific_checks")
    if not isinstance(common, list) or not isinstance(specific, Mapping):
        raise CanonicalReferenceGenerationError("REFERENCE_CHECKLIST_INVALID")
    state = specific.get(reference_id)
    if not isinstance(state, list):
        raise CanonicalReferenceGenerationError(
            "REFERENCE_STATE_CHECKLIST_MISSING:" + reference_id
        )
    return tuple(str(x) for x in [*common, *state])


def list_statuses(repo_root: Path) -> list[CanonicalReferenceStatus]:
    intake = load_intake(repo_root)
    rows: list[CanonicalReferenceStatus] = []
    for ref_id in REFERENCE_ORDER:
        item = _intake_entry(intake, ref_id)
        rows.append(
            CanonicalReferenceStatus(
                reference_id=ref_id,
                filename=str(item.get("filename") or f"{ref_id}.png"),
                status=str(item.get("status") or "UNKNOWN"),
                sha256=item.get("sha256") if isinstance(item.get("sha256"), str) else None,
                accepted=bool(item.get("accepted")),
                human_review=str(item.get("human_review") or "NOT_STARTED"),
                candidate_path=(
                    str(item.get("candidate_path"))
                    if str(item.get("candidate_path") or "").strip()
                    else None
                ),
                candidate_sha256=(
                    str(item.get("candidate_sha256"))
                    if str(item.get("candidate_sha256") or "").strip()
                    else None
                ),
            )
        )
    return rows


def compose_reference_prompt(
    *,
    global_style_and_policy: Mapping[str, Any],
    brief: Mapping[str, Any],
    has_reference_input: bool,
) -> str:
    details = brief.get("brief")
    if not isinstance(details, Mapping):
        raise CanonicalReferenceGenerationError("REFERENCE_BRIEF_DETAILS_REQUIRED")
    sections: list[str] = [
        str(global_style_and_policy.get("visual_style") or "").strip(),
        "No visible human face under any circumstance.",
        "Do not invent or expose facial anatomy.",
        str(global_style_and_policy.get("historical_uncertainty_policy") or "").strip(),
    ]
    if has_reference_input:
        sections.append(
            "Preserve the same body identity, silhouette, body proportions and "
            "non-facial continuity from the supplied canonical reference image."
        )
    for key in ("purpose", "character", "narrative_state"):
        value = str(details.get(key) or "").strip()
        if value:
            sections.append(f"{key.replace('_', ' ').title()}: {value}")
    for label, key in (
        ("Composition", "composition"),
        ("Identity lock", "identity_lock"),
        ("Wardrobe", "wardrobe"),
        ("Hard forbidden", "hard_forbidden"),
    ):
        value = details.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            cleaned = [str(x).strip() for x in value if str(x).strip()]
            if cleaned:
                sections.append(f"{label}: " + "; ".join(cleaned))
    return " ".join(". ".join(part for part in sections if part).split())


def _data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def _accepted_dependency_inputs(
    repo_root: Path,
    reference_id: str,
) -> tuple[list[str], dict[str, str]]:
    intake = load_intake(repo_root)
    refs: list[str] = []
    hashes: dict[str, str] = {}
    for dependency in REFERENCE_DEPENDENCIES.get(reference_id, ()):
        entry = _intake_entry(intake, dependency)
        if entry.get("accepted") is not True:
            raise CanonicalReferenceGenerationError(
                "DEPENDENCY_REFERENCE_NOT_ACCEPTED:" + dependency
            )
        final_path = asset_directory(repo_root) / str(
            entry.get("filename") or f"{dependency}.png"
        )
        if not final_path.is_file():
            raise CanonicalReferenceGenerationError(
                "DEPENDENCY_REFERENCE_ASSET_MISSING:" + dependency
            )
        current_hash = sha256_file(final_path)
        if current_hash != entry.get("sha256"):
            raise CanonicalReferenceGenerationError(
                "DEPENDENCY_REFERENCE_HASH_MISMATCH:" + dependency
            )
        refs.append(_data_uri(final_path))
        hashes[dependency] = current_hash
    return refs, hashes


def _pricing(repo_root: Path, model: str, reference_count: int) -> dict[str, Any]:
    registry = (
        Path(repo_root).resolve()
        / "projects"
        / "_series"
        / "siraj-media-pricing-registry-v2.json"
    )
    value = _read_json(registry)
    entry = next(
        (
            row
            for row in value.get("entries", [])
            if isinstance(row, Mapping)
            and row.get("provider") == "RUNWARE"
            and row.get("model") == model
            and row.get("media_kind") == "RUNWARE_IMAGE"
            and row.get("status") == "PRICED"
        ),
        None,
    )
    if not isinstance(entry, Mapping):
        raise CanonicalReferenceGenerationError("REFERENCE_MODEL_PRICING_UNKNOWN:" + model)
    unit = float(entry.get("unit_price"))
    extra = entry.get("input_image_pricing")
    extra = extra if isinstance(extra, Mapping) else {}
    per_reference = float(extra.get("additional_input_image_price") or 0.0)
    upper = unit + (reference_count * per_reference)
    return {
        "currency": str(entry.get("currency") or "USD"),
        "base_image_cost": unit,
        "reference_input_count": reference_count,
        "reference_input_unit_cost_upper": per_reference,
        "estimated_upper_bound": upper,
        "registry_version": value.get("registry_version"),
        "registry_sha256": sha256_file(registry),
    }


def prepare_reference_task(
    *,
    repo_root: Path,
    reference_id: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    if reference_id not in REFERENCE_ORDER:
        raise CanonicalReferenceGenerationError("UNKNOWN_REFERENCE_ID:" + reference_id)
    intake = load_intake(repo_root)
    current = _intake_entry(intake, reference_id)
    if current.get("accepted") is True:
        raise CanonicalReferenceGenerationError(
            "REFERENCE_ALREADY_ACCEPTED_CHANGE_CONTROL_REQUIRED:" + reference_id
        )
    briefs = load_briefs(repo_root)
    global_policy = briefs.get("global_style_and_policy")
    if not isinstance(global_policy, Mapping):
        raise CanonicalReferenceGenerationError("GLOBAL_POLICY_REQUIRED")
    ref = _reference_entry(briefs, reference_id)
    reference_images, dependency_hashes = _accepted_dependency_inputs(
        repo_root,
        reference_id,
    )
    prompt = compose_reference_prompt(
        global_style_and_policy=global_policy,
        brief=ref,
        has_reference_input=bool(reference_images),
    )
    shot: dict[str, Any] = {
        "label_ar": reference_id,
        "visual_brief_ar": prompt,
        "runware_positive_prompt_en": prompt,
        "runware_negative_prompt_en": DEFAULT_NEGATIVE,
        "final_budget_treatment": "ANIMATED_STILL_COMPOSITING",
        "image_model_role": (
            "REFERENCE_EDIT" if reference_images else "CHARACTER_CONSISTENCY"
        ),
        "character_identity_id": reference_id.split("_", 1)[0],
        "reference_images": reference_images,
    }
    route = route_image_shot(shot)
    task: dict[str, Any] = {
        "taskType": "imageInference",
        "taskUUID": str(uuid.uuid4()),
        "model": route.model,
        "positivePrompt": prompt,
        "width": route.width,
        "height": route.height,
        "numberResults": 1,
        "outputFormat": "PNG",
        "outputType": "URL",
        "includeCost": True,
    }
    if DEFAULT_NEGATIVE and route.model not in NEGATIVE_PROMPT_UNSUPPORTED_MODELS:
        task["negativePrompt"] = DEFAULT_NEGATIVE
    if reference_images:
        task["inputs"] = {"referenceImages": list(reference_images)}
    validated = validate_runware_task(task, require_uuid_v4=True)
    pricing = _pricing(repo_root, route.model, len(reference_images))
    return {
        "schema_version": SCHEMA_VERSION,
        "reference_id": reference_id,
        "route": {
            "role": route.role,
            "model": route.model,
            "provider": route.provider,
            "width": route.width,
            "height": route.height,
            "reason": route.reason,
        },
        "payload": dict(validated.payload),
        "payload_sha256": canonical_sha256(dict(validated.payload)),
        "dependency_hashes": dependency_hashes,
        "prompt": prompt,
        "pricing": pricing,
    }


def _validate_live_desktop_window(desktop_window: Any) -> None:
    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        raise CanonicalReferenceGenerationError("PYSIDE6_DESKTOP_REQUIRED") from exc
    app = QApplication.instance()
    if app is None:
        raise CanonicalReferenceGenerationError("LIVE_QT_DESKTOP_REQUIRED")
    if desktop_window is None or desktop_window.__class__.__name__ != "SirajDesktopWindow":
        raise CanonicalReferenceGenerationError("SIRAJ_DESKTOP_WINDOW_REQUIRED")
    if not bool(desktop_window.isVisible()):
        raise CanonicalReferenceGenerationError("VISIBLE_SIRAJ_DESKTOP_WINDOW_REQUIRED")
    if QThread.currentThread() is not app.thread():
        raise CanonicalReferenceGenerationError("DESKTOP_GUI_THREAD_REQUIRED")


def issue_desktop_reference_authorization(
    repo_root: Path,
    reference_id: str,
    prepared: Mapping[str, Any],
    *,
    desktop_window: Any,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    _validate_live_desktop_window(desktop_window)
    if prepared.get("reference_id") != reference_id:
        raise CanonicalReferenceGenerationError("PREPARED_REFERENCE_ID_MISMATCH")
    payload = prepared.get("payload")
    if not isinstance(payload, Mapping):
        raise CanonicalReferenceGenerationError("PREPARED_PROVIDER_PAYLOAD_REQUIRED")
    validated = validate_runware_task(payload, require_uuid_v4=True)
    payload = dict(validated.payload)
    payload_hash = canonical_sha256(payload)
    if payload_hash != prepared.get("payload_sha256"):
        raise CanonicalReferenceGenerationError("PREPARED_PAYLOAD_HASH_MISMATCH")
    plan_id = str(uuid.uuid4())
    plan = {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "reference_id": reference_id,
        "payload": payload,
        "payload_sha256": payload_hash,
        "dependency_hashes": dict(prepared.get("dependency_hashes") or {}),
        "pricing": dict(prepared.get("pricing") or {}),
        "created_at_utc": utc_now(),
    }
    plan_path = plan_directory(repo_root) / f"{plan_id}.json"
    write_new_json(plan_path, plan)
    auth_id = str(uuid.uuid4())
    auth = {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": auth_id,
        "status": "ACTIVE",
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "scope": "EP002_CANONICAL_REFERENCE_GENERATION_ONLY",
        "reference_id": reference_id,
        "source": "DESKTOP",
        "explicit_click": True,
        "human_approval": True,
        "single_use": True,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorizes_r27_reclassification": False,
        "authorizes_r27_regeneration": False,
        "plan_path": _repo_relative(repo_root, plan_path),
        "plan_sha256": sha256_file(plan_path),
        "payload_sha256": payload_hash,
        "maximum_cost_usd": float(
            (prepared.get("pricing") or {}).get("estimated_upper_bound") or 0.0
        ),
        "authorized_at_utc": utc_now(),
    }
    auth["authorization_sha256"] = canonical_sha256(auth)
    auth_path = authorization_directory(repo_root) / f"{auth_id}.json"
    write_new_json(auth_path, auth)
    return {
        "authorization": auth,
        "authorization_path": str(auth_path),
        "authorization_file_sha256": sha256_file(auth_path),
    }


def _consumption_for(repo_root: Path, authorization_id: str) -> dict[str, Any] | None:
    rows = read_jsonl(authorization_consumption_ledger(repo_root))
    matches = [row for row in rows if row.get("authorization_id") == authorization_id]
    return matches[-1] if matches else None


def _load_authorized_plan(
    repo_root: Path,
    authorization_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_root = Path(repo_root).resolve()
    authorization_path = _resolve_repo_path(repo_root, str(authorization_path))
    auth = _read_json(authorization_path)
    if auth.get("schema_version") != SCHEMA_VERSION:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_SCHEMA_INVALID")
    if auth.get("status") != "ACTIVE":
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_NOT_ACTIVE")
    if auth.get("source") != "DESKTOP":
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_DESKTOP_ONLY")
    if auth.get("explicit_click") is not True or auth.get("human_approval") is not True:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_EXPLICIT_CLICK_REQUIRED")
    if auth.get("single_use") is not True:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_SINGLE_USE_REQUIRED")
    if auth.get("automatic_retry") is not False or auth.get("automatic_resubmission") is not False:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_AUTOMATION_FORBIDDEN")
    signature = auth.get("authorization_sha256")
    unsigned = {k: v for k, v in auth.items() if k != "authorization_sha256"}
    if signature != canonical_sha256(unsigned):
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_SIGNATURE_INVALID")
    auth_id = str(auth.get("authorization_id") or "")
    if not auth_id or _consumption_for(repo_root, auth_id) is not None:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_ALREADY_CONSUMED")
    plan_path = _resolve_repo_path(repo_root, str(auth.get("plan_path") or ""))
    if not plan_path.is_file() or sha256_file(plan_path) != auth.get("plan_sha256"):
        raise CanonicalReferenceGenerationError("REFERENCE_PLAN_HASH_MISMATCH")
    plan = _read_json(plan_path)
    payload = plan.get("payload")
    if not isinstance(payload, Mapping):
        raise CanonicalReferenceGenerationError("REFERENCE_PLAN_PAYLOAD_REQUIRED")
    validated = validate_runware_task(payload, require_uuid_v4=True)
    if canonical_sha256(dict(validated.payload)) != auth.get("payload_sha256"):
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_PAYLOAD_HASH_MISMATCH")
    if plan.get("reference_id") != auth.get("reference_id"):
        raise CanonicalReferenceGenerationError("REFERENCE_PLAN_ID_MISMATCH")
    return auth, plan


def _consume_authorization(
    repo_root: Path,
    auth: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    auth_id = str(auth.get("authorization_id") or "")
    if _consumption_for(repo_root, auth_id) is not None:
        raise CanonicalReferenceGenerationError("REFERENCE_AUTH_ALREADY_CONSUMED")
    row = {
        "schema_version": SCHEMA_VERSION,
        "authorization_id": auth_id,
        "reference_id": auth.get("reference_id"),
        "plan_sha256": auth.get("plan_sha256"),
        "payload_sha256": auth.get("payload_sha256"),
        "task_uuid": (plan.get("payload") or {}).get("taskUUID"),
        "status": "CONSUMED_BEFORE_PROVIDER_BOUNDARY",
        "automatic_retry": False,
        "automatic_resubmission": False,
        "consumed_at_utc": utc_now(),
    }
    row["consumption_sha256"] = canonical_sha256(row)
    append_jsonl(authorization_consumption_ledger(repo_root), row)
    return row


def _provider_api_key() -> str:
    import os
    for name in ("RUNWARE_API_KEY", "SIRAJ_RUNWARE_API_KEY"):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    raise CanonicalReferenceGenerationError("RUNWARE_API_KEY_REQUIRED")


def _matching_item(payload: Mapping[str, Any], task_uuid: str) -> Mapping[str, Any] | None:
    data = payload.get("data")
    if not isinstance(data, list):
        return None
    for row in data:
        if isinstance(row, Mapping) and str(row.get("taskUUID") or "") == task_uuid:
            return row
    return None


def _master_with_reference_approval(
    repo_root: Path,
    auth: Mapping[str, Any],
    authorization_path: Path,
) -> dict[str, Any]:
    master = dict(master_authorization_reference(repo_root, EPISODE_ID))
    master["pr01_canonical_reference_paid_start_authorization"] = {
        "source": "DESKTOP",
        "scope": "EP002_CANONICAL_REFERENCE_GENERATION_ONLY",
        "reference_id": auth.get("reference_id"),
        "payload_sha256": auth.get("payload_sha256"),
        "explicit_click": True,
        "human_approval": True,
        "production_authorized": False,
        "paid_execution_authorized": False,
        "authorization_id": auth.get("authorization_id"),
        "authorization_receipt_path": _repo_relative(repo_root, authorization_path),
        "authorization_receipt_sha256": sha256_file(authorization_path),
        "click_nonce": auth.get("authorization_id"),
    }
    return master


def _download_candidate(
    *,
    repo_root: Path,
    image_url: str,
    task_uuid: str,
    auth_reference: Mapping[str, Any],
    input_hashes: Mapping[str, str],
) -> bytes:
    url_hash = hashlib.sha256(image_url.encode("utf-8")).hexdigest()
    request = PaidOperationRequest(
        repo_root=repo_root,
        episode_id=EPISODE_ID,
        stage=STAGE,
        operation_type="RUNWARE_CANONICAL_REFERENCE_DOWNLOAD",
        provider="RUNWARE",
        model="ASSET_DOWNLOAD",
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload={"taskUUID": task_uuid, "asset_url_sha256": url_hash},
        input_artifact_hashes={**dict(input_hashes), "asset_url_sha256": url_hash},
        master_authorization_reference=auth_reference,
        operation_nonce=task_uuid + ":download",
    )
    result = execute_paid_bytes(
        request,
        http_download_transport(
            url=image_url,
            headers={"User-Agent": "SIRAJ-Desktop-Canonical-Reference/2"},
            timeout_seconds=240,
        ),
    )
    return result.raw_response_path.read_bytes()


def _persist_candidate(
    *,
    repo_root: Path,
    reference_id: str,
    task_uuid: str,
    image_bytes: bytes,
    payload: Mapping[str, Any],
    provider_item: Mapping[str, Any],
) -> Path:
    path = candidate_directory(repo_root) / reference_id / f"{task_uuid}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(image_bytes).hexdigest()
    if path.is_file():
        if sha256_file(path) != digest:
            raise CanonicalReferenceGenerationError("REFERENCE_CANDIDATE_HASH_CONFLICT")
    else:
        with path.open("xb") as handle:
            handle.write(image_bytes)
            handle.flush()
            import os
            os.fsync(handle.fileno())
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "status": "GENERATED_PENDING_HUMAN_REVIEW",
        "episode_id": EPISODE_ID,
        "reference_id": reference_id,
        "task_uuid": task_uuid,
        "candidate_path": _repo_relative(repo_root, path),
        "candidate_sha256": sha256_file(path),
        "payload_sha256": canonical_sha256(dict(payload)),
        "provider_image_uuid": provider_item.get("imageUUID"),
        "provider_cost": provider_item.get("cost"),
        "generated_at_utc": utc_now(),
    }
    receipt_path = path.with_suffix(".receipt.json")
    if not receipt_path.exists():
        write_new_json(receipt_path, receipt)
    return path


def _update_intake_candidate(
    repo_root: Path,
    reference_id: str,
    candidate_path: Path,
) -> dict[str, Any]:
    intake = load_intake(repo_root)
    entry = _intake_entry(intake, reference_id)
    entry["status"] = "CANDIDATE_PENDING_HUMAN_REVIEW"
    entry["candidate_path"] = _repo_relative(repo_root, candidate_path)
    entry["candidate_sha256"] = sha256_file(candidate_path)
    entry["human_review"] = "PENDING"
    entry["accepted"] = False
    entry["candidate_generated_at_utc"] = utc_now()
    intake["status"] = "REFERENCE_REVIEW_IN_PROGRESS"
    intake["accepted_count"] = sum(
        1
        for item in intake["required_assets"]
        if isinstance(item, dict) and item.get("accepted") is True
    )
    intake["reclassification_allowed"] = False
    intake["regeneration_allowed"] = False
    atomic_write_json(intake_path(repo_root), intake)
    return intake


def generate_reference_asset(
    repo_root: Path,
    authorization_path: Path,
    *,
    poll_limit: int = 60,
    poll_sleep_seconds: float = 5.0,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    authorization_path = _resolve_repo_path(repo_root, str(authorization_path))
    auth, plan = _load_authorized_plan(repo_root, authorization_path)
    reference_id = str(auth["reference_id"])
    current = _intake_entry(load_intake(repo_root), reference_id)
    if current.get("accepted") is True:
        raise CanonicalReferenceGenerationError(
            "REFERENCE_ALREADY_ACCEPTED_CHANGE_CONTROL_REQUIRED:" + reference_id
        )
    payload = dict(plan["payload"])
    validated = validate_runware_task(payload, require_uuid_v4=True)
    payload = dict(validated.payload)
    _consume_authorization(repo_root, auth, plan=plan)
    auth_reference = _master_with_reference_approval(
        repo_root,
        auth,
        authorization_path,
    )
    request = PaidOperationRequest(
        repo_root=repo_root,
        episode_id=EPISODE_ID,
        stage=STAGE,
        operation_type="RUNWARE_CANONICAL_REFERENCE_IMAGE",
        provider="RUNWARE",
        model=str(payload.get("model") or ""),
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=payload,
        input_artifact_hashes={
            "briefs_sha256": sha256_file(briefs_path(repo_root)),
            "checklist_sha256": sha256_file(checklist_path(repo_root)),
            "intake_sha256": sha256_file(intake_path(repo_root)),
            **{
                "dependency_" + key.lower(): value
                for key, value in dict(plan.get("dependency_hashes") or {}).items()
            },
        },
        master_authorization_reference=auth_reference,
        operation_nonce=str(auth["authorization_id"]),
    )
    enforce_pr01_desktop_canonical_reference_gate(
        request=request,
        reference_id=reference_id,
    )
    _, response = execute_paid_json(
        request,
        http_json_transport(
            url=RUNWARE_URL,
            method="POST",
            payload=[payload],
            headers={
                "Authorization": "Bearer " + _provider_api_key(),
                "Content-Type": "application/json",
            },
            timeout_seconds=240,
        ),
    )
    task_uuid = str(payload["taskUUID"])
    item = _matching_item(response, task_uuid)
    if item is not None and str(item.get("imageUUID") or "").strip():
        record_provider_operation_id(
            request,
            str(item.get("imageUUID")),
            details={"provider_task_uuid": task_uuid, "reference_id": reference_id},
        )

    poll_count = 0
    while True:
        if item is not None:
            image_url = str(item.get("imageURL") or "").strip()
            status = str(item.get("status") or "").lower()
            if image_url:
                image_bytes = _download_candidate(
                    repo_root=repo_root,
                    image_url=image_url,
                    task_uuid=task_uuid,
                    auth_reference=auth_reference,
                    input_hashes=request.input_artifact_hashes,
                )
                candidate = _persist_candidate(
                    repo_root=repo_root,
                    reference_id=reference_id,
                    task_uuid=task_uuid,
                    image_bytes=image_bytes,
                    payload=payload,
                    provider_item=item,
                )
                intake = _update_intake_candidate(
                    repo_root,
                    reference_id,
                    candidate,
                )
                return {
                    "status": "PASS_CANONICAL_REFERENCE_GENERATED_PENDING_HUMAN_REVIEW",
                    "reference_id": reference_id,
                    "candidate_path": str(candidate),
                    "candidate_sha256": sha256_file(candidate),
                    "poll_count": poll_count,
                    "intake_status": intake.get("status"),
                }
            if status == "error":
                raise CanonicalReferenceGenerationError(
                    "RUNWARE_REFERENCE_GENERATION_FAILED:"
                    + str(item.get("message") or "UNKNOWN")
                )
        if poll_count >= poll_limit:
            raise CanonicalReferenceGenerationError(
                "RUNWARE_REFERENCE_GENERATION_TIMEOUT_NO_AUTOMATIC_RESUBMISSION"
            )
        poll_count += 1
        lookup_payload = {"taskType": "getResponse", "taskUUID": task_uuid}
        lookup_request = PaidOperationRequest(
            repo_root=repo_root,
            episode_id=EPISODE_ID,
            stage=STAGE,
            operation_type="RUNWARE_CANONICAL_REFERENCE_LOOKUP",
            provider="RUNWARE",
            model="LOOKUP",
            provider_contract_version=PROVIDER_CONTRACT_VERSION,
            payload=lookup_payload,
            input_artifact_hashes=request.input_artifact_hashes,
            master_authorization_reference=auth_reference,
            operation_nonce=f"{auth['authorization_id']}:poll:{poll_count}",
        )
        _, lookup_response = execute_paid_json(
            lookup_request,
            http_json_transport(
                url=RUNWARE_URL,
                method="POST",
                payload=[lookup_payload],
                headers={
                    "Authorization": "Bearer " + _provider_api_key(),
                    "Content-Type": "application/json",
                },
                timeout_seconds=240,
            ),
        )
        item = _matching_item(lookup_response, task_uuid)
        time.sleep(poll_sleep_seconds)


def _candidate_for_review(
    repo_root: Path,
    reference_id: str,
) -> tuple[dict[str, Any], Path]:
    intake = load_intake(repo_root)
    entry = _intake_entry(intake, reference_id)
    candidate_text = str(entry.get("candidate_path") or "").strip()
    if not candidate_text:
        raise CanonicalReferenceGenerationError("REFERENCE_CANDIDATE_REQUIRED")
    candidate = _resolve_repo_path(repo_root, candidate_text)
    if not candidate.is_file():
        raise CanonicalReferenceGenerationError("REFERENCE_CANDIDATE_MISSING")
    if sha256_file(candidate) != entry.get("candidate_sha256"):
        raise CanonicalReferenceGenerationError("REFERENCE_CANDIDATE_HASH_MISMATCH")
    return intake, candidate


def validate_reference_candidate_machine_checks(
    candidate: Path,
) -> dict[str, Any]:
    """Decode actual PNG candidate bytes before any human PASS can bind them.

    QImageReader.format() is not used as the format authority because it can
    remain empty after successful content-based decoding on some Qt builds.
    PNG identity is instead proven from the canonical 8-byte PNG signature,
    while QImageReader independently proves that the image bytes decode.
    """

    candidate = Path(candidate).resolve()
    if not candidate.is_file():
        raise CanonicalReferenceGenerationError(
            "REFERENCE_CANDIDATE_MISSING:" + str(candidate)
        )
    raw_prefix = candidate.read_bytes()[:8]
    if raw_prefix != b"\x89PNG\r\n\x1a\n":
        raise CanonicalReferenceGenerationError(
            "REFERENCE_CANDIDATE_FORMAT_NOT_PNG:SIGNATURE_MISMATCH"
        )
    try:
        from PySide6.QtGui import QImageReader
    except Exception as exc:
        raise CanonicalReferenceGenerationError(
            "REFERENCE_IMAGE_DECODER_UNAVAILABLE"
        ) from exc

    reader = QImageReader(str(candidate))
    reader.setDecideFormatFromContent(True)
    if not reader.canRead():
        raise CanonicalReferenceGenerationError(
            "REFERENCE_CANDIDATE_IMAGE_DECODE_FAILED:"
            + str(reader.errorString() or "UNREADABLE_IMAGE")
        )
    image = reader.read()
    if image.isNull() or image.width() <= 0 or image.height() <= 0:
        raise CanonicalReferenceGenerationError(
            "REFERENCE_CANDIDATE_IMAGE_DECODE_FAILED:"
            + str(reader.errorString() or "NULL_DECODED_IMAGE")
        )
    return {
        "FILE_EXISTS_AND_DECODES": True,
        "detected_format": "PNG",
        "png_signature_verified": True,
        "width": int(image.width()),
        "height": int(image.height()),
        "candidate_sha256": sha256_file(candidate),
    }


def accept_reference_asset(
    repo_root: Path,
    reference_id: str,
    *,
    confirmed_checks: Sequence[str],
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    intake, candidate = _candidate_for_review(repo_root, reference_id)
    machine_validation = validate_reference_candidate_machine_checks(candidate)
    required = set(required_checks(repo_root, reference_id))
    confirmed = {str(x) for x in confirmed_checks}
    if confirmed != required:
        missing = sorted(required - confirmed)
        raise CanonicalReferenceGenerationError(
            "HUMAN_REFERENCE_CHECKLIST_INCOMPLETE:" + ",".join(missing)
        )
    entry = _intake_entry(intake, reference_id)
    final_path = asset_directory(repo_root) / str(
        entry.get("filename") or f"{reference_id}.png"
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    candidate_hash = sha256_file(candidate)
    if final_path.is_file():
        if entry.get("accepted") is True and sha256_file(final_path) == candidate_hash:
            return intake
        raise CanonicalReferenceGenerationError(
            "CANONICAL_REFERENCE_ALREADY_EXISTS_CHANGE_CONTROL_REQUIRED:" + reference_id
        )
    with final_path.open("xb") as handle:
        raw = candidate.read_bytes()
        handle.write(raw)
        handle.flush()
        import os
        os.fsync(handle.fileno())
    if sha256_file(final_path) != candidate_hash:
        raise CanonicalReferenceGenerationError("CANONICAL_REFERENCE_COPY_HASH_MISMATCH")

    entry["status"] = "ACCEPTED_SHA256_BOUND"
    entry["sha256"] = candidate_hash
    entry["human_review"] = "PASS"
    entry["accepted"] = True
    entry["reviewed_at_utc"] = utc_now()
    entry["confirmed_checks"] = sorted(confirmed)
    entry["machine_validation"] = machine_validation
    intake["accepted_count"] = sum(
        1
        for item in intake["required_assets"]
        if isinstance(item, dict) and item.get("accepted") is True
    )
    intake["status"] = (
        "ALL_6_ACCEPTED"
        if intake["accepted_count"] == int(intake.get("required_count") or 6)
        else "HUMAN_REVIEW_IN_PROGRESS"
    )
    intake["reclassification_allowed"] = False
    intake["regeneration_allowed"] = False
    atomic_write_json(intake_path(repo_root), intake)

    review = {
        "schema_version": SCHEMA_VERSION,
        "reference_id": reference_id,
        "decision": "PASS",
        "candidate_path": _repo_relative(repo_root, candidate),
        "candidate_sha256": candidate_hash,
        "canonical_asset_path": _repo_relative(repo_root, final_path),
        "canonical_asset_sha256": sha256_file(final_path),
        "confirmed_checks": sorted(confirmed),
        "machine_validation": machine_validation,
        "human_review_required": True,
        "automatic_pass": False,
        "reviewed_at_utc": utc_now(),
    }
    review_path = review_directory(repo_root) / f"{reference_id}-PASS-{uuid.uuid4()}.json"
    write_new_json(review_path, review)
    return intake


def reject_reference_asset(
    repo_root: Path,
    reference_id: str,
    *,
    reason: str,
) -> dict[str, Any]:
    repo_root = Path(repo_root).resolve()
    intake, candidate = _candidate_for_review(repo_root, reference_id)
    reason = str(reason or "").strip()
    if not reason:
        raise CanonicalReferenceGenerationError("REFERENCE_REJECTION_REASON_REQUIRED")
    entry = _intake_entry(intake, reference_id)
    entry["status"] = "REJECTED_CANDIDATE_PRESERVED"
    entry["human_review"] = "REJECTED"
    entry["accepted"] = False
    entry["reviewed_at_utc"] = utc_now()
    entry["rejection_reason"] = reason
    intake["status"] = "HUMAN_REVIEW_IN_PROGRESS"
    intake["reclassification_allowed"] = False
    intake["regeneration_allowed"] = False
    atomic_write_json(intake_path(repo_root), intake)
    review = {
        "schema_version": SCHEMA_VERSION,
        "reference_id": reference_id,
        "decision": "REJECT",
        "reason": reason,
        "candidate_path": _repo_relative(repo_root, candidate),
        "candidate_sha256": sha256_file(candidate),
        "candidate_preserved": True,
        "reviewed_at_utc": utc_now(),
    }
    review_path = review_directory(repo_root) / f"{reference_id}-REJECT-{uuid.uuid4()}.json"
    write_new_json(review_path, review)
    return intake
