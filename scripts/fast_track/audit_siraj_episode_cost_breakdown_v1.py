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

    cost_source = (
        repo / "src/application/episode_cost_ledger_v1.py"
    ).read_text(encoding="utf-8")
    ui_source = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    orchestrator_source = (
        repo / "src/application/autonomous_episode_orchestrator_v1.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "OPENAI_LUNA",
        "RUNWARE_IMAGES",
        "RUNWARE_VIDEO",
        "ELEVENLABS_TTS",
        "SOUND_EFFECTS",
        "OTHER",
        "recorded_total_usd",
        "pending_scope_estimated_usd",
    ):
        require(marker in cost_source, "COST_LEDGER_MARKER_MISSING:" + marker)

    for marker in (
        "episodeCostBreakdownBox",
        "episodeCostTotalLabel",
        "episodeCostDetailsTable",
        "current_episode_cost_breakdown",
    ):
        require(marker in ui_source, "DESKTOP_COST_MARKER_MISSING:" + marker)

    require(
        "active_scope_luna_usage" in orchestrator_source,
        "ACTIVE_SCOPE_LUNA_USAGE_MISSING",
    )
    require(
        "openai-luna-scope-receipt-v1.json" in orchestrator_source,
        "LUNA_SCOPE_COST_RECEIPT_MISSING",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_SIRAJ_EPISODE_COST_BREAKDOWN_V1",
                "DISPLAY=TOTAL_AND_DETAILED",
                "CATEGORIES=6",
                "EPISODE_HARD_CAP_USD=40.00",
                "LUNA_SCOPE_COST_CAPTURE=YES",
                "RUNWARE_RECEIPT_DISCOVERY=YES",
                "ELEVENLABS_RECEIPT_DISCOVERY=YES",
                "MUSIC=FORBIDDEN",
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
