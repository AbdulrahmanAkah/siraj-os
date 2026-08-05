from __future__ import annotations

from pathlib import Path


def test_editorial_runner_desktop_contract() -> None:
    source = Path(
        "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")

    required = (
        "EditorialPipelineThread",
        "run_editorial_pipeline",
        "load_editorial_runner_state",
        "editorialPipelineStatusLabel",
        "editorialPipelineProgress",
        "resumeEditorialPipelineButton",
        "اعتماد الموضوع والأحداث وبدء البحث والنص والستوريبورد",
        "البحث والنص والستوريبورد الآلي",
        "_start_editorial_pipeline",
        "_on_editorial_success",
    )
    for marker in required:
        assert marker in source


def test_no_third_human_gate_is_added() -> None:
    runner = Path(
        "src/application/"
        "automatic_research_script_storyboard_runner_v1.py"
    ).read_text(encoding="utf-8")
    assert "additional_human_gate_added" in runner
    assert "HUMAN_SCRIPT_REVIEW" not in runner
    assert "HUMAN_STORYBOARD_REVIEW" not in runner
