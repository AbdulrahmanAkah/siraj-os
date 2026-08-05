from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from src.application.artifact_dependency_graph_v1 import canonical_sha256
from src.application.episode_cost_ledger_v1 import scan_episode_costs
from src.application.openai_luna_editorial_v1 import (
    EditorialLunaError,
    EditorialLunaResult,
    request_evidence_package,
    request_script_package,
    request_storyboard_plan,
)

EDITORIAL_RUNNER_RELEASE = (
    "AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1"
)
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
RUNNER_STATE_REL = Path(
    "orchestration/editorial-runner-state-v1.json"
)
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path(
    "orchestration/artifact-dependency-graph-v1.json"
)
APPROVED_SCOPE_REL = Path("contracts/approved-scope-v1.json")
EVIDENCE_REL = Path("research/evidence-package-v1.json")
SCRIPT_REL = Path("script/episode-script-v1.json")
STORYBOARD_REL = Path(
    "cinematic/storyboard-and-media-plan-v1.json"
)
PROVIDER_RESPONSES_REL = Path(
    "orchestration/provider-responses"
)
COST_RECEIPTS_REL = Path("orchestration/cost-receipts")

HARD_CAP_USD = 40.0
STAGE_MAX_BUDGET_USD = {
    "EVIDENCE_RESEARCH": 0.80,
    "SCRIPT_WRITING": 0.70,
    "STORYBOARD_AND_MEDIA_PLANNING": 1.50,
}
EDITORIAL_MAX_BUDGET_USD = round(
    sum(STAGE_MAX_BUDGET_USD.values()),
    2,
)

ProgressCallback = Callable[[str, int | None], None]


class EditorialPipelineError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EditorialPipelineResult:
    episode_id: str
    status: str
    evidence_path: Path
    script_path: Path
    storyboard_path: Path
    estimated_text_cost_usd: float
    web_search_calls: int
    completed_stages: tuple[str, ...]


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditorialPipelineError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise EditorialPipelineError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _atomic_write_json(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _repo_path(
    repo_root: Path,
    relative: Path,
) -> Path:
    return repo_root.resolve() / relative


def _orchestrator_state_path(repo_root: Path) -> Path:
    return _repo_path(repo_root, ORCHESTRATOR_STATE_REL)


def _load_orchestrator_state(
    repo_root: Path,
) -> dict[str, Any]:
    path = _orchestrator_state_path(repo_root)
    if not path.is_file():
        raise EditorialPipelineError(
            "AUTONOMOUS_ORCHESTRATOR_STATE_MISSING"
        )
    return _read_json(path)


def _save_orchestrator_state(
    repo_root: Path,
    state: Mapping[str, Any],
) -> None:
    _atomic_write_json(
        _orchestrator_state_path(repo_root),
        state,
    )


def _episode_id_from_state(
    repo_root: Path,
) -> tuple[str, dict[str, Any]]:
    state = _load_orchestrator_state(repo_root)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise EditorialPipelineError(
            "NO_APPROVED_EPISODE_FOR_EDITORIAL_PIPELINE"
        )
    root = repo_root.resolve() / "projects" / episode_id
    if not root.is_dir():
        raise EditorialPipelineError(
            f"CURRENT_EPISODE_DIRECTORY_MISSING:{episode_id}"
        )
    return episode_id, state


def _episode_root(
    repo_root: Path,
    episode_id: str,
) -> Path:
    return repo_root.resolve() / "projects" / episode_id


def _base_runner_state(
    episode_id: str,
) -> dict[str, Any]:
    return {
        "schema_version": "siraj-editorial-runner-state-v1",
        "release": EDITORIAL_RUNNER_RELEASE,
        "episode_id": episode_id,
        "status": "READY_AFTER_SCOPE_APPROVAL",
        "current_stage": "EVIDENCE_RESEARCH",
        "completed_stages": [],
        "artifacts": {},
        "provider_responses": {},
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0,
            "web_search_calls": 0,
        },
        "budget": {
            "episode_hard_cap_usd": HARD_CAP_USD,
            "editorial_max_authorized_usd": (
                EDITORIAL_MAX_BUDGET_USD
            ),
            "stage_max_budget_usd": STAGE_MAX_BUDGET_USD,
        },
        "automatic_after_scope_approval": True,
        "hidden_paid_retry": "FORBIDDEN",
        "completed_provider_response_reuse": "REQUIRED",
        "last_error": None,
        "created_at_utc": _now_utc(),
        "updated_at_utc": _now_utc(),
    }


def load_editorial_runner_state(
    repo_root: Path,
) -> dict[str, Any]:
    try:
        episode_id, _ = _episode_id_from_state(repo_root)
    except EditorialPipelineError:
        return {
            "schema_version": "siraj-editorial-runner-state-v1",
            "release": EDITORIAL_RUNNER_RELEASE,
            "episode_id": None,
            "status": "NO_APPROVED_EPISODE",
            "current_stage": None,
            "completed_stages": [],
            "artifacts": {},
            "usage": {
                "estimated_text_cost_usd": 0.0,
                "web_search_calls": 0,
            },
            "last_error": None,
        }
    path = _episode_root(
        repo_root,
        episode_id,
    ) / RUNNER_STATE_REL
    if not path.is_file():
        state = _base_runner_state(episode_id)
        _atomic_write_json(path, state)
        return state
    state = _read_json(path)
    if state.get("episode_id") != episode_id:
        raise EditorialPipelineError(
            "EDITORIAL_RUNNER_EPISODE_MISMATCH"
        )
    return state


def _save_runner_state(
    repo_root: Path,
    episode_id: str,
    state: Mapping[str, Any],
) -> None:
    path = _episode_root(
        repo_root,
        episode_id,
    ) / RUNNER_STATE_REL
    _atomic_write_json(path, state)


def _approved_scope(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    path = _episode_root(
        repo_root,
        episode_id,
    ) / APPROVED_SCOPE_REL
    scope = _read_json(path)
    if scope.get("human_approval") is not True:
        raise EditorialPipelineError(
            "HUMAN_SCOPE_APPROVAL_REQUIRED"
        )
    if scope.get("episode_id") != episode_id:
        raise EditorialPipelineError(
            "APPROVED_SCOPE_EPISODE_MISMATCH"
        )
    events = scope.get("events")
    if not isinstance(events, list) or not 3 <= len(events) <= 15:
        raise EditorialPipelineError(
            "APPROVED_SCOPE_EVENTS_INVALID"
        )
    return scope


def _validate_source_ids(
    payload: Mapping[str, Any],
) -> set[str]:
    sources = payload.get("source_register")
    if not isinstance(sources, list) or not sources:
        raise EditorialPipelineError(
            "EVIDENCE_SOURCE_REGISTER_REQUIRED"
        )
    ids: set[str] = set()
    for source in sources:
        if not isinstance(source, Mapping):
            raise EditorialPipelineError(
                "EVIDENCE_SOURCE_INVALID"
            )
        source_id = str(source.get("source_id", ""))
        url = str(source.get("url", ""))
        if not source_id or source_id in ids:
            raise EditorialPipelineError(
                "EVIDENCE_SOURCE_ID_INVALID_OR_DUPLICATE"
            )
        if not url.startswith(
            ("http://", "https://", "shamela://local/")
        ):
            raise EditorialPipelineError(
                f"EVIDENCE_SOURCE_URL_INVALID:{source_id}"
            )
        ids.add(source_id)
    return ids


def validate_evidence_package(
    payload: Mapping[str, Any],
    episode_id: str,
    approved_scope: Mapping[str, Any],
) -> None:
    if payload.get("episode_id") != episode_id:
        raise EditorialPipelineError(
            "EVIDENCE_EPISODE_ID_MISMATCH"
        )
    source_ids = _validate_source_ids(payload)
    expected_events = {
        str(item.get("event_id"))
        for item in approved_scope.get("events", [])
        if isinstance(item, Mapping)
    }
    events = payload.get("events")
    if not isinstance(events, list):
        raise EditorialPipelineError(
            "EVIDENCE_EVENTS_REQUIRED"
        )
    received_events = {
        str(item.get("event_id"))
        for item in events
        if isinstance(item, Mapping)
    }
    if received_events != expected_events:
        raise EditorialPipelineError(
            "EVIDENCE_EVENT_SET_MISMATCH"
        )
    claim_ids: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            raise EditorialPipelineError(
                "EVIDENCE_EVENT_INVALID"
            )
        claims = event.get("claims")
        if not isinstance(claims, list) or not claims:
            raise EditorialPipelineError(
                "EVIDENCE_EVENT_CLAIMS_REQUIRED"
            )
        for claim in claims:
            if not isinstance(claim, Mapping):
                raise EditorialPipelineError(
                    "EVIDENCE_CLAIM_INVALID"
                )
            claim_id = str(claim.get("claim_id", ""))
            if not claim_id or claim_id in claim_ids:
                raise EditorialPipelineError(
                    "EVIDENCE_CLAIM_ID_INVALID_OR_DUPLICATE"
                )
            claim_ids.add(claim_id)
            references = claim.get("source_ids")
            if (
                not isinstance(references, list)
                or not references
                or not set(map(str, references)).issubset(source_ids)
            ):
                raise EditorialPipelineError(
                    f"EVIDENCE_CLAIM_SOURCE_INVALID:{claim_id}"
                )


def _evidence_indexes(
    evidence: Mapping[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    source_ids = {
        str(item.get("source_id"))
        for item in evidence.get("source_register", [])
        if isinstance(item, Mapping)
    }
    allowed_claims: set[str] = set()
    excluded_claims: set[str] = set()
    for event in evidence.get("events", []):
        if not isinstance(event, Mapping):
            continue
        for claim in event.get("claims", []):
            if not isinstance(claim, Mapping):
                continue
            claim_id = str(claim.get("claim_id", ""))
            if claim.get("use_policy") == "EXCLUDED":
                excluded_claims.add(claim_id)
            else:
                allowed_claims.add(claim_id)
    return source_ids, allowed_claims, excluded_claims


def validate_script_package(
    payload: Mapping[str, Any],
    episode_id: str,
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    if payload.get("episode_id") != episode_id:
        raise EditorialPipelineError(
            "SCRIPT_EPISODE_ID_MISMATCH"
        )
    if payload.get("music") != "FORBIDDEN":
        raise EditorialPipelineError(
            "SCRIPT_MUSIC_MUST_BE_FORBIDDEN"
        )
    target = int(payload.get("target_duration_seconds", 0))
    if not 1080 <= target <= 1500:
        raise EditorialPipelineError(
            "SCRIPT_DURATION_OUT_OF_RANGE"
        )
    source_ids, allowed_claims, excluded_claims = (
        _evidence_indexes(evidence)
    )
    approved_events = {
        str(item.get("event_id"))
        for item in approved_scope.get("events", [])
        if isinstance(item, Mapping)
    }
    segments = payload.get("segments")
    if not isinstance(segments, list) or len(segments) < 5:
        raise EditorialPipelineError(
            "SCRIPT_SEGMENTS_REQUIRED"
        )
    segment_ids: set[str] = set()
    covered_events: set[str] = set()
    total_duration = 0
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise EditorialPipelineError(
                "SCRIPT_SEGMENT_INVALID"
            )
        segment_id = str(segment.get("segment_id", ""))
        if not segment_id or segment_id in segment_ids:
            raise EditorialPipelineError(
                "SCRIPT_SEGMENT_ID_INVALID_OR_DUPLICATE"
            )
        segment_ids.add(segment_id)
        total_duration += int(
            segment.get("estimated_duration_seconds", 0)
        )
        event_id = str(segment.get("event_id", ""))
        if event_id in approved_events:
            covered_events.add(event_id)
        claim_refs = {
            str(item)
            for item in segment.get("claim_ids", [])
        }
        if claim_refs & excluded_claims:
            raise EditorialPipelineError(
                f"SCRIPT_USES_EXCLUDED_CLAIM:{segment_id}"
            )
        if not claim_refs.issubset(allowed_claims):
            raise EditorialPipelineError(
                f"SCRIPT_UNKNOWN_CLAIM_REFERENCE:{segment_id}"
            )
        source_refs = {
            str(item)
            for item in segment.get("source_ids", [])
        }
        if not source_refs.issubset(source_ids):
            raise EditorialPipelineError(
                f"SCRIPT_UNKNOWN_SOURCE_REFERENCE:{segment_id}"
            )
    if covered_events != approved_events:
        raise EditorialPipelineError(
            "SCRIPT_DOES_NOT_COVER_ALL_APPROVED_EVENTS"
        )
    if not 1080 <= total_duration <= 1500:
        raise EditorialPipelineError(
            "SCRIPT_SEGMENT_DURATION_SUM_INVALID"
        )


def validate_storyboard_plan(
    payload: Mapping[str, Any],
    episode_id: str,
    approved_scope: Mapping[str, Any],
    script: Mapping[str, Any],
) -> None:
    del approved_scope
    if payload.get("episode_id") != episode_id:
        raise EditorialPipelineError(
            "STORYBOARD_EPISODE_ID_MISMATCH"
        )
    if payload.get("music") != "FORBIDDEN":
        raise EditorialPipelineError(
            "STORYBOARD_MUSIC_MUST_BE_FORBIDDEN"
        )
    if payload.get("flat_slideshow") != "FORBIDDEN":
        raise EditorialPipelineError(
            "FLAT_SLIDESHOW_MUST_BE_FORBIDDEN"
        )
    if payload.get("total_shots") != 70:
        raise EditorialPipelineError(
            "STORYBOARD_MUST_HAVE_70_SHOTS"
        )
    shots = payload.get("shots")
    if not isinstance(shots, list) or len(shots) != 70:
        raise EditorialPipelineError(
            "STORYBOARD_SHOT_COUNT_INVALID"
        )
    expected_segments = {
        str(item.get("segment_id"))
        for item in script.get("segments", [])
        if isinstance(item, Mapping)
    }
    referenced_segments: set[str] = set()
    shot_ids: set[str] = set()
    queue_indexes: list[int] = []
    counts = {
        "GENERATED_VIDEO": 0,
        "ANIMATED_STILL_COMPOSITING": 0,
        "GRAPHICS": 0,
    }
    generated_seconds = 0
    for shot in shots:
        if not isinstance(shot, Mapping):
            raise EditorialPipelineError(
                "STORYBOARD_SHOT_INVALID"
            )
        shot_id = str(shot.get("shot_id", ""))
        if not shot_id or shot_id in shot_ids:
            raise EditorialPipelineError(
                "STORYBOARD_SHOT_ID_INVALID_OR_DUPLICATE"
            )
        shot_ids.add(shot_id)
        queue_indexes.append(int(shot.get("queue_index", 0)))
        treatment = str(
            shot.get("final_budget_treatment", "")
        )
        if treatment not in counts:
            raise EditorialPipelineError(
                f"STORYBOARD_TREATMENT_INVALID:{shot_id}"
            )
        counts[treatment] += 1
        seconds = int(
            shot.get("planned_generated_video_seconds", 0)
        )
        if treatment == "GENERATED_VIDEO" and seconds != 8:
            raise EditorialPipelineError(
                f"GENERATED_VIDEO_MUST_BE_8_SECONDS:{shot_id}"
            )
        if treatment != "GENERATED_VIDEO" and seconds != 0:
            raise EditorialPipelineError(
                f"NON_VIDEO_GENERATED_SECONDS_FORBIDDEN:{shot_id}"
            )
        generated_seconds += seconds
        if shot.get("sound_policy") != "SFX_ONLY_NO_MUSIC":
            raise EditorialPipelineError(
                f"SHOT_SOUND_POLICY_INVALID:{shot_id}"
            )
        if shot.get("contains_music") is not False:
            raise EditorialPipelineError(
                f"SHOT_MUSIC_FORBIDDEN:{shot_id}"
            )
        if shot.get("depicts_unseen_beings") is not False:
            raise EditorialPipelineError(
                f"UNSEEN_BEING_DEPICTION_FORBIDDEN:{shot_id}"
            )
        segment_refs = {
            str(item)
            for item in shot.get("segment_ids", [])
        }
        if not segment_refs or not segment_refs.issubset(
            expected_segments
        ):
            raise EditorialPipelineError(
                f"STORYBOARD_SEGMENT_REFERENCE_INVALID:{shot_id}"
            )
        referenced_segments.update(segment_refs)
    if queue_indexes != list(range(1, 71)):
        raise EditorialPipelineError(
            "STORYBOARD_QUEUE_INDEX_MUST_BE_1_TO_70"
        )
    if counts != {
        "GENERATED_VIDEO": 20,
        "ANIMATED_STILL_COMPOSITING": 44,
        "GRAPHICS": 6,
    }:
        raise EditorialPipelineError(
            f"STORYBOARD_TREATMENT_COUNTS_INVALID:{counts}"
        )
    if generated_seconds != 160:
        raise EditorialPipelineError(
            "STORYBOARD_GENERATED_VIDEO_SECONDS_MUST_BE_160"
        )
    if referenced_segments != expected_segments:
        raise EditorialPipelineError(
            "STORYBOARD_DOES_NOT_COVER_ALL_SCRIPT_SEGMENTS"
        )


def _stage_paths(
    episode_root: Path,
    stage: str,
) -> tuple[Path, Path, Path]:
    mapping = {
        "EVIDENCE_RESEARCH": (
            episode_root / EVIDENCE_REL,
            episode_root
            / PROVIDER_RESPONSES_REL
            / "evidence-research-response-v1.json",
            episode_root
            / COST_RECEIPTS_REL
            / "openai-luna-evidence-research-receipt-v1.json",
        ),
        "SCRIPT_WRITING": (
            episode_root / SCRIPT_REL,
            episode_root
            / PROVIDER_RESPONSES_REL
            / "script-writing-response-v1.json",
            episode_root
            / COST_RECEIPTS_REL
            / "openai-luna-script-writing-receipt-v1.json",
        ),
        "STORYBOARD_AND_MEDIA_PLANNING": (
            episode_root / STORYBOARD_REL,
            episode_root
            / PROVIDER_RESPONSES_REL
            / "storyboard-media-plan-response-v1.json",
            episode_root
            / COST_RECEIPTS_REL
            / "openai-luna-storyboard-media-plan-receipt-v1.json",
        ),
    }
    try:
        return mapping[stage]
    except KeyError as exc:
        raise EditorialPipelineError(
            f"UNKNOWN_EDITORIAL_STAGE:{stage}"
        ) from exc


def _result_envelope(
    episode_id: str,
    stage: str,
    result: EditorialLunaResult,
) -> dict[str, Any]:
    return {
        "schema_version": "siraj-luna-editorial-response-envelope-v1",
        "episode_id": episode_id,
        "stage": stage,
        "provider": "OPENAI",
        "model": "gpt-5.6-luna",
        "provider_response_id": result.response_id,
        "payload": result.payload,
        "usage": {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cached_input_tokens": result.cached_input_tokens,
            "estimated_text_cost_usd": (
                result.estimated_text_cost_usd
            ),
            "web_search_calls": result.web_search_calls,
        },
        "captured_at_utc": _now_utc(),
    }


def _result_from_envelope(
    envelope: Mapping[str, Any],
) -> EditorialLunaResult:
    payload = envelope.get("payload")
    usage = envelope.get("usage")
    if not isinstance(payload, dict) or not isinstance(
        usage,
        Mapping,
    ):
        raise EditorialPipelineError(
            "EDITORIAL_RESPONSE_ENVELOPE_INVALID"
        )
    return EditorialLunaResult(
        response_id=str(
            envelope.get("provider_response_id", "")
        ),
        payload=payload,
        raw_output_text=json.dumps(
            payload,
            ensure_ascii=False,
        ),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
        cached_input_tokens=int(
            usage.get("cached_input_tokens", 0)
        ),
        estimated_text_cost_usd=float(
            usage.get("estimated_text_cost_usd", 0.0)
        ),
        web_search_calls=int(
            usage.get("web_search_calls", 0)
        ),
    )


def _assert_budget(
    repo_root: Path,
    episode_id: str,
    stage: str,
) -> None:
    snapshot = scan_episode_costs(
        repo_root,
        episode_id,
    )
    reserve = STAGE_MAX_BUDGET_USD[stage]
    projected = snapshot.recorded_total_usd + reserve
    if projected > HARD_CAP_USD + 1e-9:
        raise EditorialPipelineError(
            "EPISODE_BUDGET_HARD_CAP_BLOCKED:"
            f"episode={episode_id}:"
            f"recorded={snapshot.recorded_total_usd:.4f}:"
            f"stage_reserve={reserve:.4f}:"
            f"cap={HARD_CAP_USD:.2f}"
        )


def _write_cost_receipt(
    path: Path,
    episode_id: str,
    stage: str,
    result: EditorialLunaResult,
) -> None:
    receipt = {
        "schema_version": "siraj-provider-cost-receipt-v1",
        "episode_id": episode_id,
        "provider": "OPENAI",
        "model": "gpt-5.6-luna",
        "service": stage,
        "cost_category": "OPENAI_LUNA",
        "cost_basis": (
            "ESTIMATED_FROM_PROVIDER_REPORTED_TOKEN_USAGE"
        ),
        "estimated_cost_usd": round(
            result.estimated_text_cost_usd,
            8,
        ),
        "web_search_calls": result.web_search_calls,
        "web_search_tool_cost_usd": None,
        "provider_billing_is_source_of_truth": True,
        "provider_response_id": result.response_id,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "cached_input_tokens": result.cached_input_tokens,
        "maximum_authorized_stage_usd": (
            STAGE_MAX_BUDGET_USD[stage]
        ),
        "hidden_paid_retry": "FORBIDDEN",
        "created_at_utc": _now_utc(),
    }
    _atomic_write_json(path, receipt)


def _record_usage(
    runner_state: dict[str, Any],
    result: EditorialLunaResult,
) -> None:
    usage = runner_state.setdefault("usage", {})
    usage["input_tokens"] = int(
        usage.get("input_tokens", 0)
    ) + result.input_tokens
    usage["output_tokens"] = int(
        usage.get("output_tokens", 0)
    ) + result.output_tokens
    usage["cached_input_tokens"] = int(
        usage.get("cached_input_tokens", 0)
    ) + result.cached_input_tokens
    usage["estimated_text_cost_usd"] = round(
        float(usage.get("estimated_text_cost_usd", 0.0))
        + result.estimated_text_cost_usd,
        8,
    )
    usage["web_search_calls"] = int(
        usage.get("web_search_calls", 0)
    ) + result.web_search_calls


def _record_global_luna_usage(
    orchestrator_state: dict[str, Any],
    result: EditorialLunaResult,
) -> None:
    usage = orchestrator_state.setdefault("luna_usage", {})
    usage["input_tokens"] = int(
        usage.get("input_tokens", 0)
    ) + result.input_tokens
    usage["output_tokens"] = int(
        usage.get("output_tokens", 0)
    ) + result.output_tokens
    usage["cached_input_tokens"] = int(
        usage.get("cached_input_tokens", 0)
    ) + result.cached_input_tokens
    usage["estimated_text_cost_usd"] = round(
        float(usage.get("estimated_text_cost_usd", 0.0))
        + result.estimated_text_cost_usd,
        8,
    )


def _artifact_relative(
    repo_root: Path,
    path: Path,
) -> str:
    return str(
        path.relative_to(repo_root.resolve())
    ).replace("\\", "/")


def _mark_stage_ledger(
    episode_root: Path,
    stage: str,
    status: str,
    artifact_relative: str | None = None,
) -> None:
    path = episode_root / STAGE_LEDGER_REL
    ledger = _read_json(path)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise EditorialPipelineError(
            "STAGE_LEDGER_STAGES_REQUIRED"
        )
    found = False
    for item in stages:
        if (
            isinstance(item, dict)
            and item.get("stage") == stage
        ):
            item["status"] = status
            item["updated_at_utc"] = _now_utc()
            if artifact_relative is not None:
                item["artifact_path_relative"] = (
                    artifact_relative
                )
            found = True
            break
    if not found:
        raise EditorialPipelineError(
            f"STAGE_LEDGER_STAGE_MISSING:{stage}"
        )
    ledger["status"] = (
        "EDITORIAL_PIPELINE_COMPLETE"
        if stage == "STORYBOARD_AND_MEDIA_PLANNING"
        and status == "COMPLETE"
        else "AUTOMATIC_PIPELINE_RUNNING"
    )
    ledger["resume_from"] = {
        "EVIDENCE_RESEARCH": "SCRIPT_WRITING",
        "SCRIPT_WRITING": (
            "STORYBOARD_AND_MEDIA_PLANNING"
        ),
        "STORYBOARD_AND_MEDIA_PLANNING": (
            "BUDGET_PREFLIGHT"
        ),
    }.get(stage, ledger.get("resume_from"))
    ledger["updated_at_utc"] = _now_utc()
    _atomic_write_json(path, ledger)


def _mark_graph_nodes(
    episode_root: Path,
    node_kind: str,
    artifact_relative: str,
    artifact_sha256: str,
) -> None:
    path = episode_root / DEPENDENCY_GRAPH_REL
    graph = _read_json(path)
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        raise EditorialPipelineError(
            "DEPENDENCY_GRAPH_NODES_REQUIRED"
        )
    changed = 0
    for node in nodes:
        if (
            isinstance(node, dict)
            and node.get("kind") == node_kind
        ):
            node["status"] = "COMPLETE"
            node["artifact_path_relative"] = (
                artifact_relative
            )
            node["artifact_sha256"] = artifact_sha256
            node["invalidated_at_utc"] = None
            node["invalidation_reason"] = None
            changed += 1
    if changed == 0:
        raise EditorialPipelineError(
            f"DEPENDENCY_GRAPH_KIND_MISSING:{node_kind}"
        )
    graph["updated_at_utc"] = _now_utc()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _atomic_write_json(path, graph)


def _validate_stage_payload(
    stage: str,
    payload: Mapping[str, Any],
    episode_id: str,
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> None:
    if stage == "EVIDENCE_RESEARCH":
        validate_evidence_package(
            payload,
            episode_id,
            approved_scope,
        )
    elif stage == "SCRIPT_WRITING":
        if evidence is None:
            raise EditorialPipelineError(
                "EVIDENCE_REQUIRED_BEFORE_SCRIPT"
            )
        validate_script_package(
            payload,
            episode_id,
            approved_scope,
            evidence,
        )
    elif stage == "STORYBOARD_AND_MEDIA_PLANNING":
        if evidence is None or script is None:
            raise EditorialPipelineError(
                "EVIDENCE_AND_SCRIPT_REQUIRED_BEFORE_STORYBOARD"
            )
        validate_storyboard_plan(
            payload,
            episode_id,
            approved_scope,
            script,
        )
    else:
        raise EditorialPipelineError(
            f"UNKNOWN_EDITORIAL_STAGE:{stage}"
        )


def _commit_stage(
    repo_root: Path,
    episode_id: str,
    stage: str,
    result: EditorialLunaResult,
    runner_state: dict[str, Any],
    orchestrator_state: dict[str, Any],
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> dict[str, Any]:
    episode_root = _episode_root(
        repo_root,
        episode_id,
    )
    artifact_path, _, receipt_path = _stage_paths(
        episode_root,
        stage,
    )
    _validate_stage_payload(
        stage,
        result.payload,
        episode_id,
        approved_scope,
        evidence,
        script,
    )
    artifact_payload = dict(result.payload)
    artifact_payload["schema_version"] = {
        "EVIDENCE_RESEARCH": "siraj-evidence-package-v1",
        "SCRIPT_WRITING": "siraj-episode-script-v1",
        "STORYBOARD_AND_MEDIA_PLANNING": (
            "siraj-storyboard-media-plan-v1"
        ),
    }[stage]
    artifact_payload["provider"] = "OPENAI"
    artifact_payload["model"] = "gpt-5.6-luna"
    artifact_payload["provider_response_id"] = (
        result.response_id
    )
    artifact_payload["created_at_utc"] = _now_utc()
    artifact_payload["human_scope_gate_preserved"] = True
    artifact_payload["additional_human_gate_added"] = False
    _atomic_write_json(artifact_path, artifact_payload)
    artifact_hash = _file_sha256(artifact_path)
    _write_cost_receipt(
        receipt_path,
        episode_id,
        stage,
        result,
    )

    artifact_relative = _artifact_relative(
        repo_root,
        artifact_path,
    )
    _mark_stage_ledger(
        episode_root,
        stage,
        "COMPLETE",
        artifact_relative,
    )
    graph_kind = {
        "EVIDENCE_RESEARCH": "EVIDENCE_PACKAGE",
        "SCRIPT_WRITING": "SCRIPT_SEGMENT",
        "STORYBOARD_AND_MEDIA_PLANNING": "SHOT_PLAN",
    }[stage]
    _mark_graph_nodes(
        episode_root,
        graph_kind,
        artifact_relative,
        artifact_hash,
    )

    completed = runner_state.setdefault(
        "completed_stages",
        [],
    )
    if stage not in completed:
        completed.append(stage)
        _record_usage(runner_state, result)
        _record_global_luna_usage(
            orchestrator_state,
            result,
        )
    runner_state.setdefault("artifacts", {})[stage] = {
        "path_relative": artifact_relative,
        "sha256": artifact_hash,
    }
    runner_state.setdefault(
        "provider_responses",
        {},
    )[stage] = result.response_id
    runner_state["updated_at_utc"] = _now_utc()
    _save_runner_state(
        repo_root,
        episode_id,
        runner_state,
    )
    _save_orchestrator_state(
        repo_root,
        orchestrator_state,
    )
    return artifact_payload


def _existing_stage_artifact(
    repo_root: Path,
    episode_id: str,
    stage: str,
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    episode_root = _episode_root(
        repo_root,
        episode_id,
    )
    artifact_path, _, _ = _stage_paths(
        episode_root,
        stage,
    )
    if not artifact_path.is_file():
        return None
    payload = _read_json(artifact_path)
    _validate_stage_payload(
        stage,
        payload,
        episode_id,
        approved_scope,
        evidence,
        script,
    )
    return payload


def _request_stage(
    repo_root: Path,
    api_key: str,
    episode_id: str,
    stage: str,
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> EditorialLunaResult:
    if stage == "EVIDENCE_RESEARCH":
        return request_evidence_package(
            repo_root,
            api_key,
            episode_id,
            approved_scope,
        )
    if stage == "SCRIPT_WRITING":
        if evidence is None:
            raise EditorialPipelineError(
                "EVIDENCE_REQUIRED_BEFORE_SCRIPT"
            )
        return request_script_package(
            repo_root,
            api_key,
            episode_id,
            approved_scope,
            evidence,
        )
    if stage == "STORYBOARD_AND_MEDIA_PLANNING":
        if evidence is None or script is None:
            raise EditorialPipelineError(
                "EVIDENCE_AND_SCRIPT_REQUIRED_BEFORE_STORYBOARD"
            )
        return request_storyboard_plan(
            repo_root,
            api_key,
            episode_id,
            approved_scope,
            evidence,
            script,
        )
    raise EditorialPipelineError(
        f"UNKNOWN_EDITORIAL_STAGE:{stage}"
    )


def _set_running_status(
    repo_root: Path,
    episode_id: str,
    stage: str,
    runner_state: dict[str, Any],
    orchestrator_state: dict[str, Any],
) -> None:
    runner_state.update(
        {
            "status": f"RUNNING_{stage}",
            "current_stage": stage,
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    orchestrator_state.update(
        {
            "status": f"RUNNING_{stage}",
            "stage": stage,
            "next_stage": f"WAIT_FOR_{stage}_RESULT",
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    _save_runner_state(
        repo_root,
        episode_id,
        runner_state,
    )
    _save_orchestrator_state(
        repo_root,
        orchestrator_state,
    )


def _set_failed_status(
    repo_root: Path,
    episode_id: str,
    stage: str,
    error: str,
    runner_state: dict[str, Any],
    orchestrator_state: dict[str, Any],
) -> None:
    runner_state.update(
        {
            "status": "EDITORIAL_PIPELINE_FAILED",
            "current_stage": stage,
            "last_error": error,
            "updated_at_utc": _now_utc(),
        }
    )
    orchestrator_state.update(
        {
            "status": "EDITORIAL_PIPELINE_FAILED",
            "stage": stage,
            "next_stage": (
                "RESUME_EDITORIAL_PIPELINE_FROM_SAVED_STATE"
            ),
            "last_error": error,
            "updated_at_utc": _now_utc(),
        }
    )
    _save_runner_state(
        repo_root,
        episode_id,
        runner_state,
    )
    _save_orchestrator_state(
        repo_root,
        orchestrator_state,
    )


def _recover_or_request(
    repo_root: Path,
    api_key: str,
    episode_id: str,
    stage: str,
    approved_scope: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
    script: Mapping[str, Any] | None,
) -> EditorialLunaResult:
    episode_root = _episode_root(
        repo_root,
        episode_id,
    )
    _, envelope_path, _ = _stage_paths(
        episode_root,
        stage,
    )
    if envelope_path.is_file():
        envelope = _read_json(envelope_path)
        if (
            envelope.get("episode_id") != episode_id
            or envelope.get("stage") != stage
        ):
            raise EditorialPipelineError(
                "EDITORIAL_RESPONSE_ENVELOPE_MISMATCH"
            )
        result = _result_from_envelope(envelope)
        _validate_stage_payload(
            stage,
            result.payload,
            episode_id,
            approved_scope,
            evidence,
            script,
        )
        return result

    _assert_budget(
        repo_root,
        episode_id,
        stage,
    )
    try:
        result = _request_stage(
            repo_root,
            api_key,
            episode_id,
            stage,
            approved_scope,
            evidence,
            script,
        )
    except EditorialLunaError as exc:
        raise EditorialPipelineError(str(exc)) from exc
    envelope = _result_envelope(
        episode_id,
        stage,
        result,
    )
    _atomic_write_json(envelope_path, envelope)
    return result


def _progress(
    callback: ProgressCallback | None,
    message: str,
    value: int | None,
) -> None:
    if callback is not None:
        callback(message, value)


def run_editorial_pipeline(
    repo_root: Path,
    openai_api_key: str,
    progress: ProgressCallback | None = None,
) -> EditorialPipelineResult:
    if not openai_api_key.strip():
        raise EditorialPipelineError(
            "OPENAI_API_KEY_REQUIRED"
        )

    episode_id, orchestrator_state = (
        _episode_id_from_state(repo_root)
    )
    allowed_statuses = {
        "SCOPE_APPROVED_AUTOMATIC_PIPELINE_QUEUED",
        "EDITORIAL_PIPELINE_FAILED",
        "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
        "RUNNING_EVIDENCE_RESEARCH",
        "RUNNING_SCRIPT_WRITING",
        "RUNNING_STORYBOARD_AND_MEDIA_PLANNING",
    }
    status = str(
        orchestrator_state.get("status", "")
    )
    if status not in allowed_statuses:
        raise EditorialPipelineError(
            f"EDITORIAL_PIPELINE_NOT_ALLOWED:{status}"
        )

    runner_state = load_editorial_runner_state(
        repo_root,
    )
    approved_scope = _approved_scope(
        repo_root,
        episode_id,
    )
    episode_root = _episode_root(
        repo_root,
        episode_id,
    )

    if (
        runner_state.get("status")
        == "EDITORIAL_PIPELINE_COMPLETE"
    ):
        evidence = _read_json(
            episode_root / EVIDENCE_REL
        )
        script = _read_json(
            episode_root / SCRIPT_REL
        )
        storyboard = _read_json(
            episode_root / STORYBOARD_REL
        )
        validate_evidence_package(
            evidence,
            episode_id,
            approved_scope,
        )
        validate_script_package(
            script,
            episode_id,
            approved_scope,
            evidence,
        )
        validate_storyboard_plan(
            storyboard,
            episode_id,
            approved_scope,
            script,
        )
        usage = runner_state.get("usage", {})
        return EditorialPipelineResult(
            episode_id=episode_id,
            status="EDITORIAL_PIPELINE_COMPLETE",
            evidence_path=episode_root / EVIDENCE_REL,
            script_path=episode_root / SCRIPT_REL,
            storyboard_path=episode_root / STORYBOARD_REL,
            estimated_text_cost_usd=float(
                usage.get(
                    "estimated_text_cost_usd",
                    0.0,
                )
            ),
            web_search_calls=int(
                usage.get("web_search_calls", 0)
            ),
            completed_stages=tuple(
                runner_state.get(
                    "completed_stages",
                    [],
                )
            ),
        )

    stages = (
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
    )
    progress_values = {
        "EVIDENCE_RESEARCH": (5, 35),
        "SCRIPT_WRITING": (40, 65),
        "STORYBOARD_AND_MEDIA_PLANNING": (70, 95),
    }
    messages = {
        "EVIDENCE_RESEARCH": (
            "Luna يبحث ويبني حزمة الأدلة الموثقة…"
        ),
        "SCRIPT_WRITING": (
            "Luna يكتب النص من حزمة الأدلة فقط…"
        ),
        "STORYBOARD_AND_MEDIA_PLANNING": (
            "Luna يبني 70 لقطة وخطة الوسائط…"
        ),
    }

    evidence: dict[str, Any] | None = None
    script: dict[str, Any] | None = None

    for stage in stages:
        start_value, end_value = progress_values[stage]
        _progress(
            progress,
            messages[stage],
            start_value,
        )
        existing = _existing_stage_artifact(
            repo_root,
            episode_id,
            stage,
            approved_scope,
            evidence,
            script,
        )
        if existing is not None:
            artifact = existing
            artifact_path, envelope_path, _ = _stage_paths(
                episode_root,
                stage,
            )
            artifact_relative = _artifact_relative(
                repo_root,
                artifact_path,
            )
            _mark_stage_ledger(
                episode_root,
                stage,
                "COMPLETE",
                artifact_relative,
            )
            _mark_graph_nodes(
                episode_root,
                {
                    "EVIDENCE_RESEARCH": "EVIDENCE_PACKAGE",
                    "SCRIPT_WRITING": "SCRIPT_SEGMENT",
                    "STORYBOARD_AND_MEDIA_PLANNING": "SHOT_PLAN",
                }[stage],
                artifact_relative,
                _file_sha256(artifact_path),
            )
            completed = runner_state.setdefault(
                "completed_stages",
                [],
            )
            if stage not in completed:
                completed.append(stage)
                if envelope_path.is_file():
                    recovered_result = _result_from_envelope(
                        _read_json(envelope_path)
                    )
                    _record_usage(
                        runner_state,
                        recovered_result,
                    )
                    _record_global_luna_usage(
                        orchestrator_state,
                        recovered_result,
                    )
                runner_state.setdefault(
                    "artifacts",
                    {},
                )[stage] = {
                    "path_relative": artifact_relative,
                    "sha256": _file_sha256(artifact_path),
                }
                runner_state["updated_at_utc"] = (
                    _now_utc()
                )
                _save_runner_state(
                    repo_root,
                    episode_id,
                    runner_state,
                )
                _save_orchestrator_state(
                    repo_root,
                    orchestrator_state,
                )
        else:
            _set_running_status(
                repo_root,
                episode_id,
                stage,
                runner_state,
                orchestrator_state,
            )
            try:
                result = _recover_or_request(
                    repo_root,
                    openai_api_key,
                    episode_id,
                    stage,
                    approved_scope,
                    evidence,
                    script,
                )
                artifact = _commit_stage(
                    repo_root,
                    episode_id,
                    stage,
                    result,
                    runner_state,
                    orchestrator_state,
                    approved_scope,
                    evidence,
                    script,
                )
            except Exception as exc:
                error = str(exc)
                _set_failed_status(
                    repo_root,
                    episode_id,
                    stage,
                    error,
                    runner_state,
                    orchestrator_state,
                )
                raise EditorialPipelineError(
                    error
                ) from exc

        if stage == "EVIDENCE_RESEARCH":
            evidence = artifact
        elif stage == "SCRIPT_WRITING":
            script = artifact
        _progress(
            progress,
            f"اكتملت مرحلة {stage}.",
            end_value,
        )

    runner_state.update(
        {
            "status": "EDITORIAL_PIPELINE_COMPLETE",
            "current_stage": "BUDGET_PREFLIGHT",
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    orchestrator_state.update(
        {
            "status": (
                "EDITORIAL_PIPELINE_COMPLETE_"
                "BUDGET_PREFLIGHT_QUEUED"
            ),
            "stage": "BUDGET_PREFLIGHT",
            "next_stage": (
                "RUNWARE_MEDIA_QUEUE_AND_"
                "ELEVENLABS_TTS_V1"
            ),
            "last_error": None,
            "updated_at_utc": _now_utc(),
        }
    )
    _save_runner_state(
        repo_root,
        episode_id,
        runner_state,
    )
    _save_orchestrator_state(
        repo_root,
        orchestrator_state,
    )
    _progress(
        progress,
        (
            "اكتمل البحث والنص والستوريبورد. "
            "المرحلة التالية: فحص الميزانية وطوابير الوسائط."
        ),
        100,
    )

    usage = runner_state.get("usage", {})
    return EditorialPipelineResult(
        episode_id=episode_id,
        status="EDITORIAL_PIPELINE_COMPLETE",
        evidence_path=episode_root / EVIDENCE_REL,
        script_path=episode_root / SCRIPT_REL,
        storyboard_path=episode_root / STORYBOARD_REL,
        estimated_text_cost_usd=float(
            usage.get(
                "estimated_text_cost_usd",
                0.0,
            )
        ),
        web_search_calls=int(
            usage.get("web_search_calls", 0)
        ),
        completed_stages=tuple(
            runner_state.get(
                "completed_stages",
                [],
            )
        ),
    )
