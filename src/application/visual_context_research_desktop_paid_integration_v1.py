from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorize_stage,
    canonical_sha256,
    execute_authorized_visual_context_research_stage,
)
from src.application.visual_context_research_executor_v1 import (
    VisualContextResearchExecutionResult,
    build_executor_request,
    execute_visual_context_research,
)
from src.application.visual_context_research_v1 import (
    dossier_path,
    load_series_policy,
    validate_visual_context_dossier,
)

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
VISUAL_CONTEXT_RESEARCH_STAGE = "VISUAL_CONTEXT_RESEARCH"
VISUAL_CONTEXT_AUTHORIZATION_PHRASE = "أوافق على تنفيذ مرحلة لونا المدفوعة"
INTAKE_REL = Path(
    "reports/pr01-production-readiness/"
    "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json"
)


class VisualContextResearchDesktopIntegrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VisualContextDesktopPlan:
    episode_id: str
    reference_id: str
    narration_text: str
    visual_brief: dict[str, Any]
    provider_request: dict[str, Any]
    provider_request_sha256: str
    paid_call_required: bool
    refresh_existing: bool
    refresh_reason: str
    authorization_path: Path | None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_DESKTOP_JSON_READ_FAILED:" + str(path)
        ) from exc
    if not isinstance(value, dict):
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_DESKTOP_JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _find_reference_row(
    repo_root: Path,
    *,
    reference_id: str,
) -> dict[str, Any]:
    path = Path(repo_root).resolve() / INTAKE_REL
    if not path.is_file():
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_REFERENCE_INTAKE_MISSING:" + str(path)
        )
    payload = _read_json(path)

    def walk(value: Any):
        if isinstance(value, Mapping):
            if str(value.get("reference_id") or "").strip() == reference_id:
                yield dict(value)
            for child in value.values():
                yield from walk(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk(child)

    matches = list(walk(payload))
    if not matches:
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_REFERENCE_NOT_IN_INTAKE:" + reference_id
        )
    return matches[0]


def _narration_text(row: Mapping[str, Any], reference_id: str) -> str:
    keys = (
        "narration_text",
        "narration",
        "script_excerpt",
        "story_text",
        "approved_narration_text",
        "description",
        "purpose",
    )
    values: list[str] = []
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    if values:
        return "\n\n".join(dict.fromkeys(values))
    return (
        "Canonical visual context for "
        + reference_id
        + ". Research every visually necessary fact not directly specified."
    )


def _visual_brief(row: Mapping[str, Any], reference_id: str) -> dict[str, Any]:
    nested = row.get("brief")
    brief = dict(nested) if isinstance(nested, Mapping) else dict(row)
    brief["reference_id"] = reference_id
    brief["canonical_reference_generation"] = True
    return brief


def build_reference_visual_context_input(
    repo_root: Path,
    *,
    reference_id: str,
) -> dict[str, Any]:
    row = _find_reference_row(repo_root, reference_id=reference_id)
    return {
        "episode_id": EPISODE_ID,
        "reference_id": reference_id,
        "narration_text": _narration_text(row, reference_id),
        "visual_brief": _visual_brief(row, reference_id),
    }


def visual_context_dossier_location(
    repo_root: Path,
    *,
    reference_id: str,
) -> Path:
    return dossier_path(
        Path(repo_root).resolve(),
        episode_id=EPISODE_ID,
        context_id=reference_id,
    )


def _existing_dossier_is_valid(
    repo_root: Path,
    *,
    reference_id: str,
) -> bool:
    target = visual_context_dossier_location(
        repo_root,
        reference_id=reference_id,
    )
    if not target.is_file():
        return False
    try:
        dossier = _read_json(target)
        validate_visual_context_dossier(
            dossier=dossier,
            policy=load_series_policy(repo_root),
            episode_id=EPISODE_ID,
            context_id=reference_id,
        )
    except Exception:
        return False
    return True


def _assert_explicit_desktop_context() -> None:
    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_DESKTOP_QT_REQUIRED"
        ) from exc

    app = QApplication.instance()
    if app is None:
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_DESKTOP_APPLICATION_REQUIRED"
        )
    if QThread.currentThread() is not app.thread():
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_AUTHORIZATION_MUST_RUN_ON_GUI_THREAD"
        )

    visible_main = any(
        widget.isVisible()
        and widget.__class__.__name__ == "SirajDesktopWindow"
        for widget in app.topLevelWidgets()
    )
    if not visible_main:
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_VISIBLE_SIRAJ_DESKTOP_REQUIRED"
        )


def prepare_visual_context_research_from_desktop(
    repo_root: Path,
    *,
    reference_id: str,
    refresh_existing: bool = False,
    refresh_reason: str = "",
) -> VisualContextDesktopPlan:
    repo = Path(repo_root).resolve()
    prepared = build_reference_visual_context_input(
        repo,
        reference_id=reference_id,
    )

    if refresh_existing and not str(refresh_reason).strip():
        raise VisualContextResearchDesktopIntegrationError(
            "VISUAL_CONTEXT_REFRESH_REASON_REQUIRED"
        )

    existing_valid = _existing_dossier_is_valid(
        repo,
        reference_id=reference_id,
    )
    paid_call_required = refresh_existing or not existing_valid

    provider_request = build_executor_request(
        repo,
        episode_id=EPISODE_ID,
        context_id=reference_id,
        narration_text=prepared["narration_text"],
        visual_brief=prepared["visual_brief"],
    )
    request_sha = canonical_sha256(provider_request)

    authorization_path: Path | None = None
    if paid_call_required:
        _assert_explicit_desktop_context()
        authorization_path = authorize_stage(
            repo,
            EPISODE_ID,
            VISUAL_CONTEXT_RESEARCH_STAGE,
            provider_request,
            VISUAL_CONTEXT_AUTHORIZATION_PHRASE,
        )

    return VisualContextDesktopPlan(
        episode_id=EPISODE_ID,
        reference_id=reference_id,
        narration_text=prepared["narration_text"],
        visual_brief=prepared["visual_brief"],
        provider_request=provider_request,
        provider_request_sha256=request_sha,
        paid_call_required=paid_call_required,
        refresh_existing=refresh_existing,
        refresh_reason=str(refresh_reason).strip(),
        authorization_path=authorization_path,
    )


def execute_prepared_visual_context_research(
    repo_root: Path,
    *,
    plan: VisualContextDesktopPlan,
) -> VisualContextResearchExecutionResult:
    repo = Path(repo_root).resolve()

    def provider_call(request: Mapping[str, Any]):
        actual_sha = canonical_sha256(request)
        if actual_sha != plan.provider_request_sha256:
            raise VisualContextResearchDesktopIntegrationError(
                "VISUAL_CONTEXT_PREPARED_REQUEST_BINDING_CHANGED"
            )
        if not plan.paid_call_required:
            raise VisualContextResearchDesktopIntegrationError(
                "VISUAL_CONTEXT_UNEXPECTED_PROVIDER_CALL_FOR_REUSE"
            )
        return execute_authorized_visual_context_research_stage(
            repo,
            plan.episode_id,
            input_payload=request,
        )

    return execute_visual_context_research(
        repo,
        episode_id=plan.episode_id,
        context_id=plan.reference_id,
        narration_text=plan.narration_text,
        visual_brief=plan.visual_brief,
        provider_call=provider_call,
        refresh_existing=plan.refresh_existing,
        refresh_reason=plan.refresh_reason,
    )
