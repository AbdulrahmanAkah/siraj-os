"""End-to-end Desktop workflow for local Shorts derivatives."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import atomic_write_json
from src.application.shorts_derivative_engine_v1 import (
    Candidate,
    EngineAnalysis,
    EpisodePackage,
    HumanReviewReceipt,
    HumanReviewSession,
    PortfolioResult,
    QAResult,
    RenderPlan,
    RenderResult,
    ShortsBlockedError,
    ShortsDerivativeEngine,
    approve_local_render,
    build_human_review_package,
    create_human_review_receipt,
    export_approved_package,
    human_review_receipt_from_dict,
    analysis_from_dict,
    portfolio_from_dict,
    qa_result_from_dict,
    render_plan_from_dict,
    render_result_from_dict,
    prepare_output_workspace,
)
from src.application.shorts_derivative_execution_v1 import (
    REAL_MODE,
    ShortsLocalRenderAuthorization,
    issue_authorization,
    utc_now,
)
from src.application.shorts_derivative_storage_v1 import CanonicalShortsLibrary, ShortsLibraryError


@dataclass(frozen=True, slots=True)
class DesktopWorkflowStatus:
    workflow_id: str
    state: str
    episode_id: str | None
    candidate_count: int
    selected_count: int
    render_plan_count: int
    rendered_count: int
    qa_pass_count: int
    review_required_count: int
    exported_count: int
    provider_calls: int
    network_calls: int
    paid_calls: int
    public_title_owner: str
    thumbnail_owner: str
    automatic_publication: bool
    resume_status: str = "NOT_AVAILABLE"
    error_code: str | None = None


class ShortsDerivativeDesktopWorkflow:
    """One resumable, hash-bound workflow owned by the existing SIRAJ UI."""

    workflow_id = "SHORTS_DERIVATIVES"
    stage_order = ("SOURCE", "ANALYZE", "CANDIDATES", "PORTFOLIO", "RENDER_PLANS", "LOCAL_RENDERS", "QA_REVIEW", "EXPORT")

    def __init__(self, repo_root: Path, *, desktop_location: Path | None = None, settings_path: Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.engine = ShortsDerivativeEngine(self.repo_root)
        self.library = CanonicalShortsLibrary(self.repo_root, desktop_location=desktop_location, settings_path=settings_path)
        self.episode: EpisodePackage | None = None
        self.analysis: EngineAnalysis | None = None
        self.portfolio_result: PortfolioResult | None = None
        self.render_plans: dict[str, RenderPlan] = {}
        self.render_authorizations: dict[str, ShortsLocalRenderAuthorization] = {}
        self.render_results: dict[str, RenderResult] = {}
        self.qa_results: dict[str, QAResult] = {}
        self.review_receipts: dict[str, HumanReviewReceipt] = {}
        self.export_manifests: dict[str, dict[str, Any]] = {}
        self.review_sessions: dict[str, HumanReviewSession] = {}
        self.longform_publish_day: str | None = None
        self.resume_status = "NOT_AVAILABLE"
        self.error_code: str | None = None
        self._workspace: dict[str, Path] | None = None

    @property
    def workspace(self) -> dict[str, Path]:
        if self._workspace is None:
            if self.episode is None:
                raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
            self._workspace = prepare_output_workspace(self.repo_root, self.episode.episode_id)
        return self._workspace

    @property
    def state_path(self) -> Path:
        return self.workspace["root"] / "workflow-state.json"

    def _persist(self) -> None:
        if self.episode is None:
            return
        state = {
            "schema_version": "siraj-shorts-desktop-workflow-state-v1",
            "workflow_id": self.workflow_id,
            "episode": self.episode.to_dict(),
            "analysis": None if self.analysis is None else self.analysis.to_dict(),
            "portfolio": None if self.portfolio_result is None else self.portfolio_result.to_dict(),
            "render_plans": {key: value.to_dict() for key, value in self.render_plans.items()},
            "render_results": {key: value.to_dict() for key, value in self.render_results.items()},
            "qa_results": {key: value.to_dict() for key, value in self.qa_results.items()},
            "review_receipts": {key: value.to_dict() for key, value in self.review_receipts.items()},
            "export_manifests": self.export_manifests,
            "longform_publish_day": self.longform_publish_day,
            "resume_status": self.resume_status,
            "updated_at": utc_now(),
            "source_episode_sha256": self.episode.source_episode_sha256,
            "source_metadata_hashes": dict(self.episode.source_metadata_hashes),
            "profile_sha256": self.engine.profile_sha256,
            "constitution_bundle_sha256": self.engine.constitution_bundle_sha256,
        }
        atomic_write_json(self.state_path, state, preserve_previous=True)

    def _restore(self) -> None:
        path = self.state_path
        if not path.is_file() or self.episode is None:
            return
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("source_episode_sha256") != self.episode.source_episode_sha256:
                self.resume_status = "STALE_SOURCE"
                return
            if state.get("source_metadata_hashes") != dict(self.episode.source_metadata_hashes):
                self.resume_status = "STALE_SOURCE_EVIDENCE"
                return
            if state.get("profile_sha256") != self.engine.profile_sha256:
                self.resume_status = "STALE_PROFILE"
                return
            if state.get("constitution_bundle_sha256") != self.engine.constitution_bundle_sha256:
                self.resume_status = "STALE_CONSTITUTION"
                return
            self.analysis = None if state.get("analysis") is None else analysis_from_dict(state["analysis"])
            self.portfolio_result = None if state.get("portfolio") is None else portfolio_from_dict(state["portfolio"])
            self.render_plans = {key: render_plan_from_dict(value) for key, value in state.get("render_plans", {}).items()}
            self.render_results = {key: render_result_from_dict(value) for key, value in state.get("render_results", {}).items()}
            self.qa_results = {key: qa_result_from_dict(value) for key, value in state.get("qa_results", {}).items()}
            self.review_receipts = {key: human_review_receipt_from_dict(value) for key, value in state.get("review_receipts", {}).items()}
            self.export_manifests = {key: dict(value) for key, value in state.get("export_manifests", {}).items()}
            self.longform_publish_day = state.get("longform_publish_day")
            self.resume_status = "RESUMED_HASH_MATCH"
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            self.resume_status = "STATE_CORRUPT_BLOCKED"

    def select_episode(self, *, mode: str, **kwargs: Any) -> EpisodePackage:
        self.episode = self.engine.ingest(mode=mode, **kwargs)
        self.analysis = None
        self.portfolio_result = None
        self.render_plans.clear()
        self.render_authorizations.clear()
        self.render_results.clear()
        self.qa_results.clear()
        self.review_receipts.clear()
        self.export_manifests.clear()
        self.review_sessions.clear()
        self._workspace = prepare_output_workspace(self.repo_root, self.episode.episode_id)
        self.resume_status = "NEW_SOURCE"
        self.error_code = None
        self._restore()
        self._persist()
        return self.episode

    def source_admission(self) -> Mapping[str, Any]:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        return self.episode.source_admission

    def set_longform_publish_day(self, day: str | None) -> None:
        self.longform_publish_day = day
        self._persist()

    def analyze_episode(self) -> EngineAnalysis:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        if self.episode.source_admission.get("status") != "PASS":
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "SOURCE_ADMISSION_REQUIRED")
        self.analysis = self.engine.analyze(self.episode)
        self.portfolio_result = None
        self._persist()
        return self.analysis

    def candidates(self) -> tuple[Candidate, ...]:
        if self.analysis is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "ANALYSIS_REQUIRED")
        return self.analysis.candidates

    def select_candidates(self, candidate_ids: Sequence[str] | None = None, *, reviewed: bool = False) -> PortfolioResult:
        if self.analysis is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "ANALYSIS_REQUIRED")
        self.portfolio_result = self.engine.portfolio(self.analysis, candidate_ids=candidate_ids, longform_publish_day=self.longform_publish_day, human_selection_reviewed=reviewed)
        self._persist()
        return self.portfolio_result

    def generate_render_plans(self) -> tuple[RenderPlan, ...]:
        if self.analysis is None or self.portfolio_result is None:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PORTFOLIO_REQUIRED")
        if self.portfolio_result.portfolio_status != "PORTFOLIO_READY":
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "SELECTION_REVIEW_REQUIRED")
        self.render_plans = {short_id: self.engine.render_plan(self.analysis, self.portfolio_result, short_id, human_selection_approved=True) for short_id in self.portfolio_result.selected_candidate_ids}
        self._persist()
        return tuple(self.render_plans.values())

    def approve_local_render(self, short_id: str) -> RenderPlan:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        try:
            plan = self.render_plans[short_id]
        except KeyError as exc:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND") from exc
        approved = approve_local_render(plan, explicit_human_click=True)
        authorization_path = self.workspace["authorization"] / f"{short_id}.json"
        authorization = issue_authorization(
            episode_id=self.episode.episode_id,
            source_episode_sha256=self.episode.source_episode_sha256,
            short_plan_sha256=approved.plan_sha256,
            profile_sha256=approved.profile_sha256,
            constitution_bundle_sha256=approved.constitution_bundle_sha256,
            execution_origin="SIRAJ_DESKTOP",
            execution_mode=REAL_MODE,
            authorized_output_directory=self.workspace["renders"],
            authorized_short_ids=(short_id,),
            explicit_human_click=True,
            authorization_path=authorization_path,
        )
        self.render_plans[short_id] = approved
        self.render_authorizations[short_id] = authorization
        self._persist()
        return approved

    def render_local(self, short_id: str, output_path: Path | None = None, *, cancel_event: Any | None = None) -> RenderResult:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        if short_id not in self.render_plans:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND")
        authorization = self.render_authorizations.get(short_id)
        if authorization is None:
            raise ShortsBlockedError("SHORT_RENDER_AUTHORIZATION_REQUIRED", "LOCAL_RENDER_CLICK_REQUIRED")
        target = Path(output_path).resolve() if output_path is not None else self.workspace["renders"] / f"{short_id}.mp4"
        result = self.engine.render(self.render_plans[short_id], Path(self.episode.source_video_path), target, explicit_human_click=True, authorization=authorization, cancel_event=cancel_event)
        self.render_results[short_id] = result
        self._persist()
        return result

    def render_local_fixture(self, short_id: str, output_path: Path, *, source_video_path: Path | None = None) -> RenderResult:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        plan = self.render_plans.get(short_id)
        if plan is None:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND")
        approved = plan if plan.local_render_approved else approve_local_render(plan, explicit_human_click=True)
        self.render_plans[short_id] = approved
        result = self.engine.render(approved, source_video_path or Path(self.episode.source_video_path), output_path, explicit_human_click=True, fixture_only=True)
        self.render_results[short_id] = result
        self._persist()
        return result

    def inspect_qa(self, short_id: str) -> QAResult:
        try:
            plan = self.render_plans[short_id]
            render = self.render_results[short_id]
        except KeyError as exc:
            raise ShortsBlockedError("SHORT_QA_FAIL", "RENDER_REQUIRED") from exc
        result = self.engine.qa(plan, render)
        self.qa_results[short_id] = result
        self._persist()
        return result

    def begin_human_review(self, short_id: str) -> HumanReviewSession:
        render = self.render_results.get(short_id)
        if render is None:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "RENDER_REQUIRED")
        duration = float(render.output_probe.get("duration_seconds") or 0.0)
        frames = int(render.output_probe.get("decoded_frame_count") or 0)
        if duration <= 0 or frames <= 0:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "DECODED_FRAME_COUNT_REQUIRED")
        session = HumanReviewSession(short_id, duration, frames)
        self.review_sessions[short_id] = session
        return session

    def complete_human_review(self, short_id: str, *, reviewer: str, decision: str, constitutional_review: bool, quality_review: bool, notes: str = "") -> HumanReviewReceipt:
        plan = self.render_plans.get(short_id)
        render = self.render_results.get(short_id)
        qa = self.qa_results.get(short_id)
        session = self.review_sessions.get(short_id)
        if not plan or not render or not qa or not session:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "REVIEW_WORKFLOW_INCOMPLETE")
        receipt = create_human_review_receipt(plan, render, qa, reviewer=reviewer, decision=decision, all_frame_visual_review=session.valid, constitutional_review=constitutional_review, quality_review=quality_review, notes=notes, review_session=session)
        self.review_receipts[short_id] = receipt
        self._persist()
        return receipt

    def review_package(self) -> dict[str, Any]:
        if self.analysis is None or self.portfolio_result is None:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "PORTFOLIO_REQUIRED")
        return build_human_review_package(self.analysis, self.portfolio_result, render_results=self.render_results, qa_results=self.qa_results)

    def export_short(self, short_id: str, *, caption_formats: Sequence[str] = (".vtt", ".srt")) -> dict[str, Any]:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        plan = self.render_plans.get(short_id)
        render = self.render_results.get(short_id)
        qa = self.qa_results.get(short_id)
        receipt = self.review_receipts.get(short_id)
        if not plan or not render or not qa or not receipt:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "EXPORT_REQUIRES_HUMAN_REVIEW")
        if self.portfolio_result is None:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PORTFOLIO_REQUIRED")
        number = self.portfolio_result.recommended_order.index(short_id) + 1 if short_id in self.portfolio_result.recommended_order else 1
        if caption_formats:
            from src.application.shorts_derivative_engine_v1 import captions_to_srt, captions_to_vtt
            payloads = {suffix: captions_to_vtt(plan.external_caption_plan) if suffix == ".vtt" else captions_to_srt(plan.external_caption_plan) for suffix in caption_formats}
        else:
            payloads = {}
        manifest = self.library.export_approved_short(episode_id=self.episode.episode_id, episode_display_name=self.episode.episode_display_name, source_episode_sha256=plan.source_episode_sha256, render_plan_sha256=plan.plan_sha256, approved_render_sha256=render.render_sha256, profile_sha256=plan.profile_sha256, constitution_bundle_sha256=plan.constitution_bundle_sha256, human_review_receipt_sha256=receipt.receipt_sha256, render_path=Path(render.output_path), review_receipt=receipt.to_dict(), caption_payloads=payloads, short_number=number)
        self.export_manifests[short_id] = manifest
        self._persist()
        return manifest

    def open_library(self) -> Path:
        return self.library.root

    def open_episode_folder(self) -> Path:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        return self.library.episode_directory(self.episode.episode_id, self.episode.episode_display_name, create=True, source_episode_sha256=self.episode.source_episode_sha256)

    def status(self) -> DesktopWorkflowStatus:
        state = "EXPORT_READY" if self.export_manifests else "HUMAN_VISUAL_REVIEW_REQUIRED" if self.render_results else "SHORT_QA_PENDING" if self.render_plans else "RENDER_PLAN_READY" if self.portfolio_result and self.portfolio_result.portfolio_status == "PORTFOLIO_READY" else "HUMAN_SELECTION_REQUIRED" if self.portfolio_result else "ANALYZED" if self.analysis else "INGESTED" if self.episode else "BLOCKED"
        return DesktopWorkflowStatus(workflow_id=self.workflow_id, state=state, episode_id=self.episode.episode_id if self.episode else None, candidate_count=len(self.analysis.candidates) if self.analysis else 0, selected_count=len(self.portfolio_result.selected_candidate_ids) if self.portfolio_result else 0, render_plan_count=len(self.render_plans), rendered_count=len(self.render_results), qa_pass_count=sum(1 for result in self.qa_results.values() if result.status == "SHORT_QA_PASS"), review_required_count=sum(1 for result in self.qa_results.values() if result.human_all_frame_visual_review_required), exported_count=len(self.export_manifests), provider_calls=0, network_calls=0, paid_calls=0, public_title_owner="HUMAN", thumbnail_owner="HUMAN", automatic_publication=False, resume_status=self.resume_status, error_code=self.error_code)


def desktop_workflow_descriptor() -> Mapping[str, Any]:
    return {
        "workflow_id": "SHORTS_DERIVATIVES",
        "label": "Shorts Derivatives",
        "stages": list(ShortsDerivativeDesktopWorkflow.stage_order),
        "actions": ["Select Episode", "Select Transcript", "Analyze Episode", "View Candidates", "View Score Breakdown", "Preview Source Range", "Preview Exact 9:16 Crop", "Keep / Reject", "Reorder Portfolio", "Approve Portfolio", "Generate Local Render Plans", "Approve Local Render", "Local Render", "Cancel Local Render", "Automated QA", "Review Short", "Full Uninterrupted Playback", "Frame Step", "Approve / Reject Short", "Export Approved Short", "Open Shorts Library", "Open Episode Shorts Folder"],
        "boundaries": {"provider_calls": False, "network_calls": False, "paid_calls": False, "youtube_api": False, "automatic_publication": False, "public_title_owner": "HUMAN", "thumbnail_owner": "HUMAN", "real_local_render": "DESKTOP_HASH_BOUND_SINGLE_USE_AUTHORIZATION"},
        "integration_point": "src.application.shorts_derivative_desktop_integration_v1.ShortsDerivativeDesktopWorkflow",
    }


__all__ = ["DesktopWorkflowStatus", "ShortsDerivativeDesktopWorkflow", "desktop_workflow_descriptor"]
