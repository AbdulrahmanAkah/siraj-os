"""Future-episode event review gate for SIRAJ V6.6."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping
import urllib.request
import urllib.error
import uuid

from src.application.provider_credentials_v1 import read_openai_api_key
from src.application.artifact_provenance_v1 import record_invalidation
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    execute_json as execute_paid_json,
    http_json_transport,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_openai_responses_payload,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    OPENAI_RESPONSES_URL,
    resolve_luna_model,
    resolve_reasoning_effort,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_active,
    master_authorization_reference,
)

EP2_ID = "episode-002-adam-temptation-fall-repentance"


class EventsReviewV66Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise EventsReviewV66Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


def _canonical(value: Any) -> str:
    import hashlib
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def event_plan_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "preproduction/episode-events-plan-v6-6.json"
    )


def event_approval_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "preproduction/episode-events-approval-v6-6.json"
    )


def _claim_matrix_path(repo: Path, episode_id: str) -> Path:
    return (
        repo
        / "projects"
        / episode_id
        / "research/source-claim-matrix-v6-3.json"
    )


def _first_list(value: Any, keys: tuple[str, ...]) -> list[Any] | None:
    if isinstance(value, Mapping):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, list) and candidate:
                return candidate
        for item in value.values():
            found = _first_list(item, keys)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _first_list(item, keys)
            if found:
                return found
    return None


def _claim_ids(matrix: Mapping[str, Any]) -> set[str]:
    result: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                lowered = str(key).lower()
                if (
                    lowered in {"claim_id", "id"}
                    and isinstance(item, (str, int))
                ):
                    text = str(item).strip()
                    if text:
                        result.add(text)
                if isinstance(item, (Mapping, list)):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    claims = matrix.get("claims")
    if isinstance(claims, list):
        visit(claims)
    return result


def _normalize_event(
    raw: Any,
    index: int,
) -> dict[str, Any]:
    if isinstance(raw, str):
        title = raw.strip()
        return {
            "event_id": f"EV{index:03d}",
            "order": index,
            "title_ar": title,
            "summary_ar": title,
            "claim_ids": [],
            "source_ids": [],
        }
    if not isinstance(raw, Mapping):
        raise EventsReviewV66Error(
            "EVENT_OBJECT_OR_STRING_REQUIRED"
        )

    event_id = str(
        raw.get("event_id")
        or raw.get("id")
        or f"EV{index:03d}"
    ).strip()
    title = str(
        raw.get("title_ar")
        or raw.get("title")
        or raw.get("name_ar")
        or raw.get("name")
        or raw.get("event")
        or raw.get("summary_ar")
        or raw.get("summary")
        or ""
    ).strip()
    summary = str(
        raw.get("summary_ar")
        or raw.get("summary")
        or raw.get("description_ar")
        or raw.get("description")
        or title
    ).strip()
    if not title:
        raise EventsReviewV66Error(
            "EVENT_TITLE_REQUIRED:" + event_id
        )

    def values(*keys: str) -> list[str]:
        for key in keys:
            candidate = raw.get(key)
            if isinstance(candidate, list):
                return [
                    str(item).strip()
                    for item in candidate
                    if str(item).strip()
                ]
            if isinstance(candidate, (str, int)):
                text = str(candidate).strip()
                return [text] if text else []
        return []

    return {
        "event_id": event_id,
        "order": index,
        "title_ar": title,
        "summary_ar": summary,
        "claim_ids": values(
            "claim_ids",
            "claims",
            "supported_claim_ids",
        ),
        "source_ids": values(
            "source_ids",
            "sources",
            "supported_source_ids",
        ),
    }


def _plan_payload(
    episode_id: str,
    events: list[dict[str, Any]],
    *,
    revision: int,
    origin: str,
) -> dict[str, Any]:
    core = {
        "episode_id": episode_id,
        "revision": revision,
        "origin": origin,
        "events": events,
    }
    return {
        "schema_version": "siraj-episode-events-plan-v6.6",
        "status": "DRAFT",
        **core,
        "event_count": len(events),
        "plan_sha256": _canonical(core),
        "human_approval_required": True,
        "created_at_utc": _now(),
    }


def materialize_event_plan(
    repo_root: Path,
    episode_id: str,
) -> Path:
    if episode_id == EP2_ID:
        raise EventsReviewV66Error(
            "EPISODE_002_EVENT_REVIEW_NOT_APPLICABLE"
        )

    repo = Path(repo_root).resolve()
    path = event_plan_path(repo, episode_id)
    if path.is_file():
        return path

    matrix = _read(
        _claim_matrix_path(repo, episode_id)
    )
    candidates = _first_list(
        matrix,
        (
            "canonical_events",
            "canonical_event_sequence",
            "event_sequence",
            "events",
            "narrative_events",
        ),
    )
    if not candidates:
        raise EventsReviewV66Error(
            "SOURCE_CLAIM_MATRIX_CANONICAL_EVENTS_REQUIRED"
        )

    events = [
        _normalize_event(item, index)
        for index, item in enumerate(
            candidates,
            start=1,
        )
    ]
    _write(
        path,
        _plan_payload(
            episode_id,
            events,
            revision=1,
            origin="SOURCE_CLAIM_MATRIX",
        ),
    )
    return path


def load_event_plan(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    path = materialize_event_plan(
        repo_root,
        episode_id,
    )
    return _read(path)


def events_approved(
    repo_root: Path,
    episode_id: str,
) -> bool:
    plan_path = event_plan_path(
        repo_root,
        episode_id,
    )
    approval_path = event_approval_path(
        repo_root,
        episode_id,
    )
    if not plan_path.is_file() or not approval_path.is_file():
        return False
    try:
        plan = _read(plan_path)
        approval = _read(approval_path)
    except Exception:
        return False
    return (
        approval.get("status") == "APPROVED"
        and approval.get("plan_sha256") == plan.get("plan_sha256")
    )


def approve_events(
    repo_root: Path,
    episode_id: str,
) -> Path:
    plan = load_event_plan(repo_root, episode_id)
    path = event_approval_path(repo_root, episode_id)
    _write(
        path,
        {
            "schema_version": "siraj-episode-events-approval-v6.6",
            "status": "APPROVED",
            "episode_id": episode_id,
            "plan_sha256": plan.get("plan_sha256"),
            "revision": plan.get("revision"),
            "event_count": plan.get("event_count"),
            "approval_source": "EXPLICIT_HUMAN_DESKTOP_ACTION",
            "approved_at_utc": _now(),
        },
    )
    return path


def _extract_output_text(response: Mapping[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    output = response.get("output")
    texts: list[str] = []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
    if not texts:
        raise EventsReviewV66Error(
            "LUNA_EVENTS_DIALOGUE_OUTPUT_TEXT_MISSING"
        )
    return "\n".join(texts)


def _conversation_path(repo: Path, episode_id: str) -> Path:
    return (
        repo
        / "projects"
        / episode_id
        / "orchestration/events-review-v6-6/conversation.jsonl"
    )


def conversation_entries(
    repo_root: Path,
    episode_id: str,
) -> list[dict[str, Any]]:
    path = _conversation_path(
        Path(repo_root).resolve(),
        episode_id,
    )
    if not path.is_file():
        return []
    entries = []
    for line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            entries.append(value)
    return entries


def discuss_events_with_luna(
    repo_root: Path,
    episode_id: str,
    user_message: str,
) -> dict[str, Any]:
    message = str(user_message or "").strip()
    if not message:
        raise EventsReviewV66Error(
            "EVENT_DISCUSSION_MESSAGE_REQUIRED"
        )

    repo = Path(repo_root).resolve()
    if not master_authorization_active(
        repo,
        episode_id,
    ):
        raise EventsReviewV66Error(
            "EPISODE_MASTER_AUTHORIZATION_REQUIRED"
        )

    master = master_authorization_reference(
        repo,
        episode_id,
    )
    plan = load_event_plan(
        repo,
        episode_id,
    )
    matrix = _read(
        _claim_matrix_path(repo, episode_id)
    )
    known_claims = _claim_ids(matrix)

    api_key = str(
        read_openai_api_key() or ""
    ).strip()
    if not api_key:
        raise EventsReviewV66Error(
            "OPENAI_API_KEY_REQUIRED"
        )

    attempt_id = str(uuid.uuid4())
    attempt_root = (
        repo
        / "projects"
        / episode_id
        / "orchestration/events-review-v6-6/attempts"
    )
    attempt_root.mkdir(
        parents=True,
        exist_ok=True,
    )
    lock_path = (
        attempt_root
        / f"{attempt_id}.lock.json"
    )
    raw_path = (
        attempt_root
        / f"{attempt_id}.raw-response.json"
    )

    lock = {
        "schema_version": "siraj-events-luna-attempt-lock-v6.6",
        "status": "LOCKED_BEFORE_NETWORK",
        "episode_id": episode_id,
        "attempt_id": attempt_id,
        "master_authorization_sha256": master["sha256"],
        "automatic_retry": False,
        "automatic_resubmission": False,
        "created_at_utc": _now(),
    }
    _write(lock_path, lock)

    history = conversation_entries(
        repo,
        episode_id,
    )[-12:]
    input_payload = {
        "episode_id": episode_id,
        "current_event_plan": plan,
        "source_claim_matrix": matrix,
        "recent_discussion": history,
        "human_message_ar": message,
        "rules": {
            "truth_before_drama": True,
            "may_reorder_merge_split_or_remove_supported_events": True,
            "may_not_add_unsupported_event": True,
            "revised_events_require_claim_traceability": True,
            "do_not_write_final_script": True,
            "respond_in_arabic": True,
        },
    }

    request_payload = {
        "model": resolve_luna_model(),
        "store": False,
        "reasoning": {
            "effort": resolve_reasoning_effort(),
        },
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "أنت Luna، المديرة التحريرية المركزية لسراج. "
                            "ناقش مع الإنسان أحداث الحلقة فقط. "
                            "لا تضف حدثًا غير مسنود بمصفوفة الادعاءات. "
                            "إذا طلب الإنسان تعديل الأحداث فأعد قائمة events كاملة "
                            "بالترتيب الجديد مع claim_ids، واشرح التعديل باختصار."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            input_payload,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_events_review_v66",
                "strict": False,
                "schema": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        },
    }

    lock["status"] = "NETWORK_REQUEST_STARTED"
    _write(lock_path, lock)

    validate_openai_responses_payload(request_payload)
    paid_request = PaidOperationRequest(
        repo_root=repo, episode_id=episode_id, stage="EVENTS_REVIEW_AND_APPROVAL",
        operation_type="OPENAI_EVENT_REVIEW", provider="OPENAI",
        model=resolve_luna_model(), provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=request_payload,
        input_artifact_hashes={"event_plan": str(lock.get("input_sha256") or "")},
        master_authorization_reference=master_authorization_reference(repo, episode_id),
        operation_nonce=str(lock.get("input_sha256") or attempt_id), attempt_id=attempt_id,
    )
    try:
        paid_result, payload = execute_paid_json(
            paid_request,
            http_json_transport(
                url=OPENAI_RESPONSES_URL, method="POST", payload=request_payload,
                headers={"Authorization": "Bearer " + api_key,
                         "Content-Type": "application/json"}, timeout_seconds=600,
            ),
        )
    except Exception as exc:
        lock["status"] = "FAILED_OR_UNKNOWN_NO_AUTOMATIC_RETRY"
        lock["error"] = str(exc)
        _write(lock_path, lock)
        raise EventsReviewV66Error(
            "LUNA_EVENTS_DIALOGUE_FAILED_NO_AUTOMATIC_RETRY:"
            + str(exc)
        ) from exc

    raw_path = paid_result.raw_response_path
    lock["status"] = "RAW_RESPONSE_PERSISTED"
    _write(lock_path, lock)

    text = _extract_output_text(payload)
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        lock["status"] = "INVALID_JSON_NO_AUTOMATIC_RETRY"
        _write(lock_path, lock)
        raise EventsReviewV66Error(
            "LUNA_EVENTS_DIALOGUE_INVALID_JSON_NO_AUTOMATIC_RETRY"
        ) from exc

    if not isinstance(result, dict):
        raise EventsReviewV66Error(
            "LUNA_EVENTS_DIALOGUE_OBJECT_REQUIRED"
        )

    assistant_message = str(
        result.get("assistant_message_ar")
        or result.get("message_ar")
        or result.get("message")
        or ""
    ).strip()
    if not assistant_message:
        assistant_message = "تمت مراجعة خطة الأحداث."

    revised = result.get("events")
    plan_changed = False
    if isinstance(revised, list) and revised:
        normalized = [
            _normalize_event(item, index)
            for index, item in enumerate(
                revised,
                start=1,
            )
        ]

        if known_claims:
            for event in normalized:
                claims = set(event.get("claim_ids") or [])
                if not claims:
                    raise EventsReviewV66Error(
                        "REVISED_EVENT_CLAIM_IDS_REQUIRED:"
                        + event["event_id"]
                    )
                unknown = sorted(claims - known_claims)
                if unknown:
                    raise EventsReviewV66Error(
                        "REVISED_EVENT_UNKNOWN_CLAIMS:"
                        + event["event_id"]
                        + ":"
                        + ",".join(unknown)
                    )

        next_plan = _plan_payload(
            episode_id,
            normalized,
            revision=int(plan.get("revision", 1) or 1) + 1,
            origin="LUNA_HUMAN_EVENTS_DIALOGUE",
        )
        _write(
            event_plan_path(repo, episode_id),
            next_plan,
        )
        plan = next_plan
        plan_changed = True

        approval = event_approval_path(
            repo,
            episode_id,
        )
        if approval.is_file():
            record_invalidation(
                repo,
                episode_id,
                approval,
                reason="EVENT_PLAN_CHANGED_AFTER_PRIOR_APPROVAL",
                classification="STALE_BUT_PRESERVED",
                invalidated_by_input_hash=str(next_plan.get("plan_sha256") or ""),
            )

    entry = {
        "timestamp_utc": _now(),
        "attempt_id": attempt_id,
        "human_message_ar": message,
        "assistant_message_ar": assistant_message,
        "plan_changed": plan_changed,
        "plan_sha256": plan.get("plan_sha256"),
        "automatic_retry": False,
    }
    conversation = _conversation_path(
        repo,
        episode_id,
    )
    conversation.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    with conversation.open(
        "a",
        encoding="utf-8",
        newline="\n",
    ) as handle:
        handle.write(
            json.dumps(
                entry,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )

    lock["status"] = "COMPLETE"
    lock["plan_changed"] = plan_changed
    _write(lock_path, lock)

    return {
        "status": "PASS",
        "assistant_message_ar": assistant_message,
        "plan_changed": plan_changed,
        "event_count": plan.get("event_count"),
        "revision": plan.get("revision"),
    }
