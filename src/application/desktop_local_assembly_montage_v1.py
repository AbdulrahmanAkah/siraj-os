"""Canonical Desktop-only executor for EP002 local assembly and montage.

SIRAJ_EP002_CANONICAL_DESKTOP_LOCAL_ASSEMBLY_RESUME_V1

This executor performs no provider or paid operation. It executes only the
already-reviewed LOCAL_ASSEMBLY_AND_MONTAGE stage, validates the durable
montage receipt/master, then commits the authoritative transition with CAS.
If the receipt already exists from an interrupted post-render commit, it is
validated and committed without rerendering.
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
from src.application.siraj_local_assembly_montage_v6_2_1 import (
    assemble_episode_master,
)
from src.application.episode002_finalization_compatibility_v6 import (
    ensure_montage_media_queue,
)

STAGE = "LOCAL_ASSEMBLY_AND_MONTAGE"
PREVIOUS_STAGE = "PROVIDER_EXECUTION"
NEXT_STAGE = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
LOCAL_AUTH_SCOPE = "LOCAL_ASSEMBLY_AND_MONTAGE_LOCAL_ONLY"
SCHEMA_VERSION = "siraj-desktop-local-assembly-montage-v1"
MONTAGE_RECEIPT_SCHEMA = "siraj-local-assembly-montage-v6.2.1"


class DesktopLocalAssemblyMontageError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LocalAssemblyMontageOutcome:
    status: str
    episode_id: str
    stage: str
    next_stage: str
    next_stage_executed: bool
    receipt_path: str
    receipt_sha256: str
    master_path: str
    master_sha256: str
    ledger_head_sha256: str
    transition_id: str
    recovered_existing_receipt: bool
    provider_calls: int = 0
    paid_attempts_created: int = 0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DesktopLocalAssemblyMontageError(
            "LOCAL_ASSEMBLY_RECEIPT_UNREADABLE:" + str(path)
        ) from exc
    if not isinstance(value, dict):
        raise DesktopLocalAssemblyMontageError(
            "LOCAL_ASSEMBLY_RECEIPT_OBJECT_REQUIRED:" + str(path)
        )
    return value


class CanonicalDesktopLocalAssemblyMontageExecutor:
    def __init__(
        self,
        repo_root: Path,
        episode_id: str,
        *,
        assembler: Callable[[Path, str], Any] = assemble_episode_master,
        ledger_appender: Callable[..., dict[str, Any]] = append_transition_if_head,
        state_reader: Callable[[Path, str], DesktopEpisodeState] = read_desktop_episode_state,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id
        self.assembler = assembler
        self.ledger_appender = ledger_appender
        self.state_reader = state_reader

    @property
    def canonical_receipt_path(self) -> Path:
        return (
            self.repo_root
            / "projects"
            / self.episode_id
            / "deliverables"
            / "autopilot-v6-2-1"
            / "episode-master-autopilot-v6-2-1-receipt.json"
        )

    def _verify(
        self,
        intent: DesktopResumeIntent,
        authorization: Mapping[str, Any],
    ) -> DesktopEpisodeState:
        if intent.source != DESKTOP_SOURCE:
            raise DesktopLocalAssemblyMontageError(
                "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY"
            )
        if intent.episode_id != self.episode_id:
            raise DesktopLocalAssemblyMontageError("RESUME_EPISODE_MISMATCH")
        if intent.first_stage != STAGE:
            raise DesktopLocalAssemblyMontageError(
                "INVALID_RESUME_STAGE:" + intent.first_stage
            )
        if (
            authorization.get("source") != DESKTOP_SOURCE
            or authorization.get("scope") != LOCAL_AUTH_SCOPE
            or authorization.get("episode_id") != self.episode_id
            or authorization.get("stage") != STAGE
            or authorization.get("execution_token") != intent.execution_token
            or authorization.get("paid_operation") is not False
            or authorization.get("provider_calls") != 0
        ):
            raise DesktopLocalAssemblyMontageError(
                "DESKTOP_LOCAL_ASSEMBLY_AUTHORIZATION_INVALID"
            )

        state = self.state_reader(self.repo_root, self.episode_id)
        if state.current_stage != STAGE or state.status != "READY":
            raise DesktopLocalAssemblyMontageError(
                "INVALID_CURRENT_STAGE:" + state.current_stage + ":" + state.status
            )
        if state.ledger_head_sha256 != intent.ledger_head_sha256:
            raise DesktopLocalAssemblyMontageError(
                "AUTHORITATIVE_STATE_CHANGED_REVIEW_REQUIRED"
            )
        if state.promoted_overlay_sha256 != intent.promoted_overlay_sha256:
            raise DesktopLocalAssemblyMontageError("REVIEWED_OVERLAY_CHANGED")
        if (
            state.authoritative_structural_fingerprint
            != intent.structural_fingerprint
        ):
            raise DesktopLocalAssemblyMontageError(
                "REVIEWED_STRUCTURAL_FINGERPRINT_CHANGED"
            )
        return state

    def _validated_outputs(
        self,
        receipt_path: Path,
    ) -> tuple[dict[str, Any], Path]:
        receipt_path = Path(receipt_path).resolve()
        receipt = _read_mapping(receipt_path)
        if (
            receipt.get("schema_version") != MONTAGE_RECEIPT_SCHEMA
            or receipt.get("status") != "PASS"
            or receipt.get("episode_id") != self.episode_id
            or receipt.get("next_stage") != NEXT_STAGE
            or receipt.get("duplicate_gate") != "PASS"
        ):
            raise DesktopLocalAssemblyMontageError(
                "LOCAL_ASSEMBLY_RECEIPT_INVALID"
            )

        raw_master = str(receipt.get("master_path_relative") or "").strip()
        if not raw_master:
            raise DesktopLocalAssemblyMontageError(
                "LOCAL_ASSEMBLY_MASTER_PATH_REQUIRED"
            )
        master_path = Path(raw_master)
        if not master_path.is_absolute():
            master_path = self.repo_root / master_path
        master_path = master_path.resolve()
        if not master_path.is_file():
            raise DesktopLocalAssemblyMontageError(
                "LOCAL_ASSEMBLY_MASTER_MISSING:" + str(master_path)
            )
        expected_master_sha = str(receipt.get("master_sha256") or "")
        actual_master_sha = sha256_file(master_path)
        if not expected_master_sha or actual_master_sha != expected_master_sha:
            raise DesktopLocalAssemblyMontageError(
                "LOCAL_ASSEMBLY_MASTER_HASH_MISMATCH"
            )
        return receipt, master_path

    def execute(
        self,
        intent: DesktopResumeIntent,
        *,
        authorization: Mapping[str, Any],
    ) -> LocalAssemblyMontageOutcome:
        state = self._verify(intent, authorization)

        # Ground-truth V6 bridge: local-only, provider-free.
        ensure_montage_media_queue(self.repo_root, self.episode_id)

        receipt_path = self.canonical_receipt_path
        recovered = receipt_path.is_file()
        if not recovered:
            produced = self.assembler(self.repo_root, self.episode_id)
            if produced is not None:
                receipt_path = Path(produced)
                if not receipt_path.is_absolute():
                    receipt_path = self.repo_root / receipt_path
                receipt_path = receipt_path.resolve()

        if not receipt_path.is_file():
            raise DesktopLocalAssemblyMontageError(
                "LOCAL_ASSEMBLY_RECEIPT_NOT_PRODUCED"
            )

        receipt, master_path = self._validated_outputs(receipt_path)

        receipt_ref = {
            "logical_output": "LOCAL_ASSEMBLY_MONTAGE_RECEIPT",
            "path": str(receipt_path.relative_to(self.repo_root)).replace("\\", "/"),
            "sha256": sha256_file(receipt_path),
        }
        master_ref = {
            "logical_output": "EPISODE_MASTER",
            "path": str(master_path.relative_to(self.repo_root)).replace("\\", "/"),
            "sha256": sha256_file(master_path),
        }
        public_authorization = {
            "authorization_id": str(authorization.get("authorization_id") or ""),
            "source": DESKTOP_SOURCE,
            "scope": LOCAL_AUTH_SCOPE,
            "episode_id": self.episode_id,
            "stage": STAGE,
            "provider_calls": 0,
            "paid_operation": False,
        }

        try:
            transition = self.ledger_appender(
                self.repo_root,
                self.episode_id,
                expected_ledger_sha256=state.ledger_head_sha256,
                stage=STAGE,
                previous_stage=PREVIOUS_STAGE,
                status="COMPLETED",
                output_artifacts=[receipt_ref, master_ref],
                schema_versions=[SCHEMA_VERSION, MONTAGE_RECEIPT_SCHEMA],
                authorization_references=[public_authorization],
                metadata={
                    "event": "DESKTOP_LOCAL_ASSEMBLY_AND_MONTAGE_COMPLETED",
                    "next_stage_projection": NEXT_STAGE,
                    "next_stage_executed": False,
                    "provider_calls": 0,
                    "paid_attempts_created": 0,
                    "recovered_existing_receipt": recovered,
                    "master_sha256": str(receipt.get("master_sha256") or ""),
                },
            )
        except Exception as exc:
            raise DesktopLocalAssemblyMontageError(
                "RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
            ) from exc

        final_head = sha256_file(ledger_path(self.repo_root, self.episode_id))
        return LocalAssemblyMontageOutcome(
            status="PASS",
            episode_id=self.episode_id,
            stage=STAGE,
            next_stage=NEXT_STAGE,
            next_stage_executed=False,
            receipt_path=str(receipt_path),
            receipt_sha256=receipt_ref["sha256"],
            master_path=str(master_path),
            master_sha256=master_ref["sha256"],
            ledger_head_sha256=final_head,
            transition_id=str(transition.get("transition_id") or ""),
            recovered_existing_receipt=recovered,
            provider_calls=0,
            paid_attempts_created=0,
        )
