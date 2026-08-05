from __future__ import annotations

import argparse
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()

    primary = (
        repo / "src/application/shamela_primary_research_v1.py"
    ).read_text(encoding="utf-8")
    editorial = (
        repo / "src/application/openai_luna_editorial_v1.py"
    ).read_text(encoding="utf-8")
    scope = (
        repo / "src/application/openai_luna_orchestrator_v1.py"
    ).read_text(encoding="utf-8")
    runner = (
        repo
        / "src/application/automatic_research_script_storyboard_runner_v1.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "SHAMELA_PRIMARY_INTERNET_SECONDARY",
        "require_shamela_primary_context",
        "shamela://local/",
    ):
        require(marker in primary, "PRIMARY_SOURCE_MARKER_MISSING:" + marker)

    require(
        "ابحث أولًا في كتب المكتبة الشاملة المختارة" in editorial,
        "EDITORIAL_SHAMELA_FIRST_PROMPT_MISSING",
    )
    require(
        "الويب مصدر ثانوي" in editorial,
        "EDITORIAL_WEB_SECONDARY_PROMPT_MISSING",
    )
    require(
        '"duration_seconds": [1080, 1500]' in editorial,
        "EDITORIAL_DURATION_REQUIREMENT_MISSING",
    )
    require(
        '"minimum": 1080' in editorial
        and '"maximum": 1500' in editorial,
        "SCRIPT_SCHEMA_DURATION_MISSING",
    )
    require(
        '"minimum": 18' in scope and '"maximum": 25' in scope,
        "SCOPE_DURATION_CONSTITUTION_MISSING",
    )
    require(
        "SHAMELA_PRIMARY_INTERNET_SECONDARY" in scope,
        "SCOPE_SOURCE_HIERARCHY_MISSING",
    )
    require(
        "1080 <= target <= 1500" in runner,
        "RUNNER_TARGET_DURATION_VALIDATION_MISSING",
    )
    require(
        "1080 <= total_duration <= 1500" in runner,
        "RUNNER_SEGMENT_DURATION_VALIDATION_MISSING",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_SIRAJ_EDITORIAL_SOURCE_DURATION_CONSTITUTION_FIX_V1",
                "PRIMARY_INFORMATION_SOURCE=SELECTED_SHAMELA_BOOKS",
                "INTERNET_ROLE=SECONDARY_GAP_FILL_ONLY",
                "EPISODE_DURATION_MINUTES=18-25",
                "EPISODE_TARGET_MINUTES=22",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
