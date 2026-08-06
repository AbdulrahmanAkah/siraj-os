"""Stable fail-closed certification gate for the native V2 production runtime."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


REPORT_REL = Path(
    "projects/episode-001-adam/orchestration/"
    "full-production-pipeline-certification-v3.json"
)
FINGERPRINT_PATHS = (
    "src/application/production_standard_v2_native_assets.py",
    "src/application/production_standard_v2_runtime.py",
    "src/application/production_pipeline_certification_gate_v1.py",
    "src/application/consolidated_episode_production_controller_v2.py",
    "src/application/desktop_media_execution_v1.py",
    "src/application/end_to_end_production_v1.py",
    "src/application/luna_cinematic_prompt_director_v2.py",
    "src/application/luna_safe_technical_repair_v1.py",
    "projects/episode-001-adam/cinematic/"
    "storyboard-and-media-plan-luna-certified-v2.json",
    "projects/episode-001-adam/orchestration/"
    "production-standard-v2-native-asset-plan-v1.json",
    "projects/episode-001-adam/orchestration/"
    "full-episode-tts-execution-plan-production-standard-v2.json",
)


class ProductionPipelineCertificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_pipeline_fingerprint(
    repo_root: Path,
) -> tuple[str, list[dict[str, str]]]:
    repo = repo_root.resolve()
    entries: list[dict[str, str]] = []
    # SIRAJ_MUTABLE_ASSET_PLAN_FINGERPRINT_EXCLUSION_V1
    for relative in FINGERPRINT_PATHS:
        # This generated plan contains timestamps and is rewritten during an
        # authorized materialization. Raw hashing it invalidates the certificate
        # immediately after a production attempt starts.
        if relative.endswith(
            "production-standard-v2-native-asset-plan-v1.json"
        ):
            continue
        path = repo / relative
        if not path.is_file():
            raise ProductionPipelineCertificationError(
                "PIPELINE_CRITICAL_FILE_MISSING:" + relative
            )
        entries.append(
            {
                "path": relative,
                "sha256": _sha256(path),
            }
        )
    payload = json.dumps(
        entries,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest(), entries


def ensure_full_pipeline_certified(
    repo_root: Path,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    path = repo / REPORT_REL
    if not path.is_file():
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_CERTIFICATION_MISSING"
        )
    try:
        report = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_CERTIFICATION_UNREADABLE:"
            + str(exc)
        ) from exc
    if not isinstance(report, dict):
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_CERTIFICATION_INVALID"
        )
    if str(report.get("status") or "") != (
        "PASS_FULL_PRODUCTION_PIPELINE_CERTIFIED"
    ):
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_CERTIFICATION_NOT_PASS"
        )
    if int(report.get("blocking_issue_count", -1)) != 0:
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_HAS_BLOCKERS"
        )
    current, _ = build_pipeline_fingerprint(repo)
    if current != str(
        report.get("critical_fingerprint") or ""
    ):
        raise ProductionPipelineCertificationError(
            "USER_ACTION_REQUIRED:"
            "FULL_PRODUCTION_PIPELINE_CERTIFICATION_STALE"
        )
    return report
