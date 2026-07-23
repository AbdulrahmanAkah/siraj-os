"""Small localhost-only, server-rendered operator UI.

This module deliberately renders stable view models, not raw manifests, and
never invokes a shell or an external provider itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class EpisodeSummaryView:
    episode_id: str
    status: str
    current_stage: str | None
    next_action: str
    blockers: tuple[str, ...]


class LocalOperatorApplication:
    def __init__(self, project_root: Path, orchestrator_factory: Callable[[str], Any]) -> None:
        self.project_root = project_root.resolve()
        self.orchestrator_factory = orchestrator_factory
        self.csrf_token = secrets.token_urlsafe(24)

    def _orchestrator(self, episode_id: str) -> Any:
        if not isinstance(episode_id, str) or not episode_id.strip() or "/" in episode_id or "\\" in episode_id or ".." in episode_id:
            raise ValueError("EPISODE_ID_INVALID")
        return self.orchestrator_factory(episode_id)

    def dashboard(self, episode_ids: list[str]) -> list[EpisodeSummaryView]:
        values: list[EpisodeSummaryView] = []
        for episode_id in sorted(set(episode_ids)):
            manifest = self._orchestrator(episode_id).execute(mode="status")["manifest"]
            values.append(EpisodeSummaryView(episode_id, str(manifest["status"]), manifest.get("current_stage"), str(manifest.get("next_action", "")), tuple(str(item.get("code", "")) for item in manifest.get("blockers", []) if isinstance(item, dict))))
        return values

    def episode_detail(self, episode_id: str) -> dict[str, Any]:
        manifest = self._orchestrator(episode_id).execute(mode="status")["manifest"]
        return {"schema_version": "siraj-operator-episode-view-v1", "episode_id": episode_id, "status": manifest["status"], "current_stage": manifest.get("current_stage"), "next_action": manifest.get("next_action"), "stages": [{"stage_id": key, "status": value.get("status"), "next_action": value.get("next_action"), "warnings": value.get("warnings", []), "blocker": value.get("blocker")} for key, value in manifest.get("stage_states", {}).items()], "approvals": [{key: item.get(key) for key in ("approval_id", "stage_id", "status", "reviewer", "notes", "resolved_at")} for item in manifest.get("approvals", [])], "qa": next((item for item in manifest.get("artifact_index", []) if item.get("artifact_type") == "episode-qa-report"), None), "publication": next((item for item in manifest.get("artifact_index", []) if item.get("artifact_type") == "episode-publication-package"), None), "artifact_index": [{key: item.get(key) for key in ("artifact_id", "artifact_type", "stage_id", "path", "approval_status", "fingerprint")} for item in manifest.get("artifact_index", [])], "execution_history": manifest.get("execution_history", [])}

    def _artifact_json(self, detail: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
        artifact = next((item for item in detail["artifact_index"] if item.get("artifact_type") == artifact_type), None)
        if not artifact:
            return None
        path = (self.project_root / str(artifact["path"])).resolve(strict=False)
        try:
            path.relative_to(self.project_root)
        except ValueError as error:
            raise ValueError("ARTIFACT_PATH_OUTSIDE_PROJECT") from error
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else None

    def research_review(self, episode_id: str) -> dict[str, Any]:
        detail = self.episode_detail(episode_id)
        return {"schema_version": "siraj-operator-research-review-v1", "episode_id": episode_id, "dossier": self._artifact_json(detail, "episode-research-dossier"), "verification": self._artifact_json(detail, "episode-research-verification"), "evidence_approval": next((item for item in detail["approvals"] if item.get("stage_id") == "evidence_approval"), None)}

    def script_review(self, episode_id: str) -> dict[str, Any]:
        detail = self.episode_detail(episode_id)
        return {"schema_version": "siraj-operator-script-review-v1", "episode_id": episode_id, "script": self._artifact_json(detail, "episode-script"), "verification": self._artifact_json(detail, "script-verification"), "approval": next((item for item in detail["approvals"] if item.get("stage_id") == "script_approval"), None)}

    def media_review(self, episode_id: str) -> dict[str, Any]:
        detail = self.episode_detail(episode_id)
        media = [item for item in detail["artifact_index"] if item.get("artifact_type") in {"episode-storyboard", "visual-asset", "generated-video", "rendered-video"}]
        return {"schema_version": "siraj-operator-media-review-v1", "episode_id": episode_id, "assets": media, "video_seconds_budget": 300, "approvals": [item for item in detail["approvals"] if item.get("stage_id") in {"storyboard_approval", "master_visual_approval", "video_approval", "final_render_approval"}]}

    def qa_publication_view(self, episode_id: str) -> dict[str, Any]:
        detail = self.episode_detail(episode_id)
        return {"schema_version": "siraj-operator-qa-publication-view-v1", "episode_id": episode_id, "qa_report": self._artifact_json(detail, "episode-qa-report"), "publication_package": self._artifact_json(detail, "episode-publication-package"), "publication_approval": next((item for item in detail["approvals"] if item.get("stage_id") == "publication"), None)}

    def action(self, episode_id: str, action: str, *, reviewer: str | None = None, notes: str | None = None, artifact_ids: tuple[str, ...] = ()) -> dict[str, Any]:
        orchestrator = self._orchestrator(episode_id)
        if action in {"plan", "status", "run-next", "resume"}:
            return orchestrator.execute(mode=action)
        if action == "run-qa":
            return orchestrator.execute(mode="run-stage", stage_id="qa_gate")
        if action == "build-publication-package":
            return orchestrator.execute(mode="run-stage", stage_id="publication_package")
        if action == "invalidate-stage":
            if not notes:
                raise ValueError("STAGE_ID_REQUIRED")
            return orchestrator.execute(mode="invalidate-stage", stage_id=notes)
        approvals = {"approve-evidence": ("evidence_approval", "APPROVED"), "reject-evidence": ("evidence_approval", "REJECTED"), "approve-script": ("script_approval", "APPROVED"), "reject-script": ("script_approval", "REJECTED"), "approve-storyboard": ("storyboard_approval", "APPROVED"), "reject-storyboard": ("storyboard_approval", "REJECTED"), "approve-visual": ("master_visual_approval", "APPROVED"), "approve-video": ("video_approval", "APPROVED"), "approve-render": ("final_render_approval", "APPROVED"), "approve-publication": ("publication", "APPROVED")}
        if action not in approvals:
            raise ValueError("OPERATOR_ACTION_INVALID")
        stage_id, decision = approvals[action]
        return orchestrator.record_approval(stage_id=stage_id, decision=decision, reviewer=reviewer, notes=notes, artifact_ids=artifact_ids)


def build_operator_server(application: LocalOperatorApplication, *, host: str = "127.0.0.1", port: int = 8765, episode_ids: list[str] | None = None) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise ValueError("LOCALHOST_BIND_REQUIRED")
    episodes = episode_ids or []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - avoid leaking request content
            return
        def _send(self, status: int, body: str, content_type: str = "text/html; charset=utf-8") -> None:
            data = body.encode("utf-8"); self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    rows = "".join(f"<li><a href='/episode?id={escape(item.episode_id)}'>{escape(item.episode_id)}</a> — {escape(item.status)}</li>" for item in application.dashboard(episodes))
                    self._send(HTTPStatus.OK, f"<!doctype html><html dir='rtl'><meta charset='utf-8'><body><h1>SIRAJ Operator</h1><ul>{rows}</ul></body></html>")
                    return
                if parsed.path == "/episode":
                    episode_id = parse_qs(parsed.query).get("id", [""])[0]; detail = application.episode_detail(episode_id)
                    stages = "".join(f"<li>{escape(str(item['stage_id']))}: {escape(str(item['status']))}</li>" for item in detail["stages"])
                    self._send(HTTPStatus.OK, f"<!doctype html><html dir='rtl'><meta charset='utf-8'><body><h1>{escape(episode_id)}</h1><p>{escape(str(detail['status']))}</p><h2>المراحل</h2><ul>{stages}</ul></body></html>")
                    return
                self._send(HTTPStatus.NOT_FOUND, "Not found")
            except ValueError:
                self._send(HTTPStatus.BAD_REQUEST, "Invalid local request")
        def do_POST(self) -> None:  # noqa: N802
            if self.headers.get("X-Siraj-CSRF") != application.csrf_token:
                self._send(HTTPStatus.FORBIDDEN, "CSRF validation failed"); return
            try:
                length = int(self.headers.get("Content-Length", "0")); value = json.loads(self.rfile.read(length).decode("utf-8"))
                result = application.action(str(value.get("episode_id", "")), str(value.get("action", "")), reviewer=value.get("reviewer"), notes=value.get("notes"), artifact_ids=tuple(value.get("artifact_ids", [])))
                self._send(HTTPStatus.OK, json.dumps({"status": result.get("status", "UPDATED")}, ensure_ascii=False), "application/json; charset=utf-8")
            except (ValueError, json.JSONDecodeError, TypeError):
                self._send(HTTPStatus.BAD_REQUEST, "Invalid local action")
    return ThreadingHTTPServer((host, port), Handler)
