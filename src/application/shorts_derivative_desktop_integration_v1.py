"""Read-only/action-bound Desktop integration for the Shorts derivative service.

The existing Qt application can call this service without importing any
provider or publication module.  The adapter exposes the workflow stages and
keeps every local render behind an explicit approval action.  It intentionally
does not implement upload, scheduling writes, title generation, thumbnail
generation, or public metadata mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.shorts_derivative_engine_v1 import (
    Candidate,
    EngineAnalysis,
    EpisodePackage,
    PortfolioResult,
    QAResult,
    RenderPlan,
    RenderResult,
    ShortsBlockedError,
    ShortsDerivativeEngine,
    approve_local_render,
    build_human_review_package,
)


@dataclass(frozen=True, slots=True)
class DesktopWorkflowStatus:
    workflow_id: str
    state: str
    episode_id: str | None
    candidate_count: int
    selected_count: int
    render_plan_count: int
    qa_pass_count: int
    provider_calls: int
    network_calls: int
    paid_calls: int
    public_title_owner: str
    thumbnail_owner: str
    automatic_publication: bool


class ShortsDerivativeDesktopWorkflow:
    """Desktop-facing orchestration with explicit human action boundaries."""

    workflow_id = "SHORTS_DERIVATIVES"

    def __init__(self, repo_root: Path) -> None:
        self.engine = ShortsDerivativeEngine(repo_root)
        self.episode: EpisodePackage | None = None
        self.analysis: EngineAnalysis | None = None
        self.portfolio_result: PortfolioResult | None = None
        self.render_plans: dict[str, RenderPlan] = {}
        self.render_results: dict[str, RenderResult] = {}
        self.qa_results: dict[str, QAResult] = {}
        self.longform_publish_day: str | None = None

    def select_episode(self, *, mode: str, **kwargs: Any) -> EpisodePackage:
        self.episode = self.engine.ingest(mode=mode, **kwargs)
        self.analysis = None
        self.portfolio_result = None
        self.render_plans.clear()
        self.render_results.clear()
        self.qa_results.clear()
        return self.episode

    def set_longform_publish_day(self, day: str | None) -> None:
        self.longform_publish_day = day

    def analyze_episode(self) -> EngineAnalysis:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        self.analysis = self.engine.analyze(self.episode)
        self.portfolio_result = None
        return self.analysis

    def candidates(self) -> tuple[Candidate, ...]:
        if self.analysis is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "ANALYSIS_REQUIRED")
        return self.analysis.candidates

    def select_candidates(
        self,
        candidate_ids: Sequence[str] | None = None,
        *,
        reviewed: bool = False,
    ) -> PortfolioResult:
        if self.analysis is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "ANALYSIS_REQUIRED")
        self.portfolio_result = self.engine.portfolio(
            self.analysis,
            candidate_ids=candidate_ids,
            longform_publish_day=self.longform_publish_day,
            human_selection_reviewed=reviewed,
        )
        return self.portfolio_result

    def generate_render_plans(self) -> tuple[RenderPlan, ...]:
        if self.analysis is None or self.portfolio_result is None:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PORTFOLIO_REQUIRED")
        if self.portfolio_result.portfolio_status != "PORTFOLIO_READY":
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "SELECTION_REVIEW_REQUIRED")
        self.render_plans = {
            short_id: self.engine.render_plan(
                self.analysis,
                self.portfolio_result,
                short_id,
                human_selection_approved=True,
            )
            for short_id in self.portfolio_result.selected_candidate_ids
        }
        return tuple(self.render_plans.values())

    def approve_local_render(self, short_id: str) -> RenderPlan:
        try:
            plan = self.render_plans[short_id]
        except KeyError as exc:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND") from exc
        approved = approve_local_render(plan, explicit_human_click=True)
        self.render_plans[short_id] = approved
        return approved

    def render_local_fixture(self, short_id: str, output_path: Path, *, source_video_path: Path | None = None) -> RenderResult:
        if self.episode is None:
            raise ShortsBlockedError("SHORT_SOURCE_MISSING", "EPISODE_SELECTION_REQUIRED")
        try:
            plan = self.render_plans[short_id]
        except KeyError as exc:
            raise ShortsBlockedError("SHORT_RENDER_PLAN_INVALID", "PLAN_NOT_FOUND") from exc
        source = source_video_path or Path(self.episode.source_video_path)
        result = self.engine.render(
            plan,
            source,
            output_path,
            explicit_human_click=True,
            fixture_only=True,
        )
        self.render_results[short_id] = result
        return result

    def inspect_qa(self, short_id: str) -> QAResult:
        try:
            plan = self.render_plans[short_id]
            render = self.render_results[short_id]
        except KeyError as exc:
            raise ShortsBlockedError("SHORT_QA_FAIL", "RENDER_REQUIRED") from exc
        result = self.engine.qa(plan, render)
        self.qa_results[short_id] = result
        return result

    def review_package(self) -> dict[str, Any]:
        if self.analysis is None or self.portfolio_result is None:
            raise ShortsBlockedError("SHORT_HUMAN_REVIEW_REQUIRED", "PORTFOLIO_REQUIRED")
        return build_human_review_package(
            self.analysis,
            self.portfolio_result,
            render_results=self.render_results,
            qa_results=self.qa_results,
        )

    def status(self) -> DesktopWorkflowStatus:
        return DesktopWorkflowStatus(
            workflow_id=self.workflow_id,
            state=(
                "SHORT_QA_PENDING" if self.render_plans and not self.qa_results else
                "HUMAN_SELECTION_REQUIRED" if self.portfolio_result is not None and self.portfolio_result.human_selection_required else
                "ANALYZED" if self.analysis is not None else
                "INGESTED" if self.episode is not None else
                "BLOCKED"
            ),
            episode_id=self.episode.episode_id if self.episode else None,
            candidate_count=len(self.analysis.candidates) if self.analysis else 0,
            selected_count=len(self.portfolio_result.selected_candidate_ids) if self.portfolio_result else 0,
            render_plan_count=len(self.render_plans),
            qa_pass_count=sum(1 for result in self.qa_results.values() if result.status == "SHORT_QA_PASS"),
            provider_calls=0,
            network_calls=0,
            paid_calls=0,
            public_title_owner="HUMAN",
            thumbnail_owner="HUMAN",
            automatic_publication=False,
        )


def desktop_workflow_descriptor() -> Mapping[str, Any]:
    """Stable descriptor for an existing Desktop navigation surface."""

    return {
        "workflow_id": "SHORTS_DERIVATIVES",
        "label": "Shorts Derivatives",
        "actions": [
            "Select Episode",
            "Select Episode Metadata Package",
            "Set Long-form Publish Day",
            "Analyze Episode",
            "View Candidates",
            "View Score Breakdown",
            "Preview Source Range",
            "Select / Deselect Candidates",
            "View Recommended Portfolio",
            "Generate Local Render Plans",
            "Approve Local Test/Derivative Render Explicitly",
            "View QA Results",
            "Export Approved Package",
        ],
        "boundaries": {
            "provider_calls": False,
            "network_calls": False,
            "paid_calls": False,
            "youtube_api": False,
            "automatic_publication": False,
            "public_title_owner": "HUMAN",
            "thumbnail_owner": "HUMAN",
        },
        "integration_point": "src.application.shorts_derivative_desktop_integration_v1.ShortsDerivativeDesktopWorkflow",
    }


__all__ = ["DesktopWorkflowStatus", "ShortsDerivativeDesktopWorkflow", "desktop_workflow_descriptor"]
