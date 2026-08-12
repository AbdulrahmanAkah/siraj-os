"""Canonical Desktop EP002 semantic/editorial QA executor V3.

SIRAJ_EP002_CANONICAL_DESKTOP_SEMANTIC_QA_V3

No automatic retry/resubmission is introduced. If the existing QA stage is
classified as paid, its existing explicit authorization gate is checked before
the single semantic QA invocation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from src.application.artifact_provenance_v1 import sha256_file
from src.application.episode_transition_ledger_v1 import (
    append_transition_if_head,
    ledger_path,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    DesktopEpisodeState,
    DesktopResumeIntent,
    read_desktop_episode_state,
)

STAGE = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
PREVIOUS_STAGE = "LOCAL_ASSEMBLY_AND_MONTAGE"
NEXT_STAGE = "READY_FOR_FINAL_HUMAN_REVIEW"
AUTH_SCOPE = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA_DESKTOP_RESUME"


class DesktopSemanticQAError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SemanticQAOutcome:
    status: str
    episode_id: str
    stage: str
    next_stage: str
    next_stage_executed: bool
    qa_result_path: str
    qa_result_sha256: str
    ledger_head_sha256: str
    transition_id: str
    recovered_existing_result: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CanonicalDesktopSemanticQAExecutor:
    def __init__(
        self,
        repo_root: Path,
        episode_id: str,
        *,
        state_reader: Callable[
            [Path, str], DesktopEpisodeState
        ] = read_desktop_episode_state,
        ledger_appender: Callable[..., dict[str, Any]] = append_transition_if_head,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id
        self.state_reader = state_reader
        self.ledger_appender = ledger_appender

    @property
    def result_path(self) -> Path:
        return (
            self.repo_root
            / "projects"
            / self.episode_id
            / "deliverables"
            / "final-semantic-editorial-qa-v11.json"
        )

    def _pass_result(self) -> bool:
        if not self.result_path.is_file():
            return False
        try:
            value = json.loads(
                self.result_path.read_text(encoding="utf-8-sig")
            )
        except Exception:
            return False
        return (
            isinstance(value, dict)
            and value.get("status") == "PASS"
            and value.get("episode_id") in {None, self.episode_id}
        )

    def execute(
        self,
        intent: DesktopResumeIntent,
        *,
        authorization: Mapping[str, Any],
    ) -> SemanticQAOutcome:
        if (
            intent.source != DESKTOP_SOURCE
            or intent.episode_id != self.episode_id
            or intent.first_stage != STAGE
        ):
            raise DesktopSemanticQAError(
                "SEMANTIC_QA_RESUME_BINDING_INVALID"
            )
        if (
            authorization.get("source") != DESKTOP_SOURCE
            or authorization.get("scope") != AUTH_SCOPE
            or authorization.get("episode_id") != self.episode_id
            or authorization.get("stage") != STAGE
            or authorization.get("execution_token")
            != intent.execution_token
        ):
            raise DesktopSemanticQAError(
                "SEMANTIC_QA_DESKTOP_AUTHORIZATION_INVALID"
            )

        state = self.state_reader(
            self.repo_root,
            self.episode_id,
        )
        if state.current_stage != STAGE or state.status != "READY":
            raise DesktopSemanticQAError(
                "INVALID_CURRENT_STAGE:"
                + state.current_stage
                + ":"
                + state.status
            )
        if state.ledger_head_sha256 != intent.ledger_head_sha256:
            raise DesktopSemanticQAError(
                "AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED"
            )

        recovered = self._pass_result()
        if not recovered:
            import src.application.siraj_one_click_autopilot_v6_4 as autopilot

            paid_stages = set(getattr(autopilot, "PAID_STAGES", set()))
            if STAGE in paid_stages:
                stage_authorized = getattr(
                    autopilot,
                    "_stage_authorized",
                    None,
                )
                if (
                    not callable(stage_authorized)
                    or not stage_authorized(
                        self.repo_root,
                        self.episode_id,
                        STAGE,
                    )
                ):
                    raise DesktopSemanticQAError(
                        "EXPLICIT_PAID_AUTHORIZATION_REQUIRED:"
                        + STAGE
                    )

            paid_input = getattr(autopilot, "_paid_luna_input", None)
            qa_runner = getattr(autopilot, "semantic_editorial_qa", None)
            mark_ready = getattr(autopilot, "_mark_ready", None)
            if not (
                callable(paid_input)
                and callable(qa_runner)
                and callable(mark_ready)
            ):
                raise DesktopSemanticQAError(
                    "SEMANTIC_QA_RUNTIME_COMPONENT_MISSING"
                )

            payload = paid_input(
                self.repo_root,
                self.episode_id,
                STAGE,
            )
            # Exactly one stage invocation. There is deliberately no loop.
            qa_runner(
                self.repo_root,
                self.episode_id,
                payload,
            )
            mark_ready(self.repo_root, self.episode_id)

        if not self._pass_result():
            raise DesktopSemanticQAError(
                "SEMANTIC_QA_DID_NOT_PRODUCE_PASS"
            )

        reference = {
            "logical_output": "FINAL_SEMANTIC_EDITORIAL_QA",
            "path": str(
                self.result_path.relative_to(self.repo_root)
            ).replace("\\", "/"),
            "sha256": sha256_file(self.result_path),
        }
        try:
            transition = self.ledger_appender(
                self.repo_root,
                self.episode_id,
                expected_ledger_sha256=state.ledger_head_sha256,
                stage=STAGE,
                previous_stage=PREVIOUS_STAGE,
                status="COMPLETED",
                output_artifacts=[reference],
                schema_versions=[
                    "siraj-desktop-semantic-editorial-qa-v3"
                ],
                authorization_references=[
                    {
                        "authorization_id": str(
                            authorization.get("authorization_id")
                            or ""
                        ),
                        "source": DESKTOP_SOURCE,
                        "scope": AUTH_SCOPE,
                    }
                ],
                metadata={
                    "event": (
                        "DESKTOP_SEMANTIC_EDITORIAL_QA_COMPLETED"
                    ),
                    "next_stage_projection": NEXT_STAGE,
                    "next_stage_executed": False,
                    "recovered_existing_result": recovered,
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                },
            )
        except Exception as exc:
            raise DesktopSemanticQAError(
                "QA_RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
            ) from exc

        return SemanticQAOutcome(
            status="PASS",
            episode_id=self.episode_id,
            stage=STAGE,
            next_stage=NEXT_STAGE,
            next_stage_executed=False,
            qa_result_path=str(self.result_path),
            qa_result_sha256=reference["sha256"],
            ledger_head_sha256=sha256_file(
                ledger_path(self.repo_root, self.episode_id)
            ),
            transition_id=str(
                transition.get("transition_id") or ""
            ),
            recovered_existing_result=recovered,
        )
