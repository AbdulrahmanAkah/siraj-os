import json
from pathlib import Path

import pytest

from src.application.production_pipeline_certification_gate_v1 import (
    ProductionPipelineCertificationError,
    REPORT_REL,
    ensure_full_pipeline_certified,
)


def test_missing_certification_blocks_before_provider(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        ProductionPipelineCertificationError,
        match="CERTIFICATION_MISSING",
    ):
        ensure_full_pipeline_certified(tmp_path)


def test_non_pass_certification_blocks(
    tmp_path: Path,
) -> None:
    path = tmp_path / REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "BLOCKED",
                "blocking_issue_count": 1,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        ProductionPipelineCertificationError,
        match="CERTIFICATION_NOT_PASS",
    ):
        ensure_full_pipeline_certified(tmp_path)
