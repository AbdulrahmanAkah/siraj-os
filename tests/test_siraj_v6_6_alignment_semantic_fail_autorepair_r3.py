from pathlib import Path
import json

from src.application.siraj_alignment_semantic_autorepair_v6_6_r3 import (
    ALIGNMENT_STAGE,
    is_semantic_alignment_fail,
    semantic_fail_artifact,
)


class ExampleError(RuntimeError):
    pass


def test_semantic_fail_is_not_transport_failure(tmp_path):
    episode = "episode-x"
    path = (
        tmp_path
        / "projects"
        / episode
        / "preproduction/narration-visual-alignment-gate-v6-2-1.json"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"status": "FAIL", "findings": [{"shot_id": "S1"}]}),
        encoding="utf-8",
    )
    assert semantic_fail_artifact(tmp_path, episode)["status"] == "FAIL"
    assert is_semantic_alignment_fail(
        tmp_path,
        episode,
        ExampleError("STAGE_DID_NOT_PRODUCE_PASS:" + ALIGNMENT_STAGE),
    )


def test_v66_wrapper_has_semantic_autorepair_branch():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/application/siraj_autopilot_v6_6.py"
    ).read_text(encoding="utf-8-sig")
    assert "SIRAJ_ALIGNMENT_SEMANTIC_AUTOREPAIR_V6_6_R3" in source
    assert "is_semantic_alignment_fail" in source
    assert "resolve_until_pass" in source
    assert "mark_paid_failure" in source
