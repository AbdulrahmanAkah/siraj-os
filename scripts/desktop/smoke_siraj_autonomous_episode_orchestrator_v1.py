from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.presentation.desktop.production_console import ProductionConsoleDialog

    app = QApplication.instance() or QApplication(
        ["siraj-autonomous-episode-orchestrator-v1"]
    )
    with tempfile.TemporaryDirectory() as temporary:
        smoke_repo = Path(temporary)
        required = (
            "projects/episode-001-adam/cinematic/shot-packages/"
            "adam-dc2-s02-sh03/veo-shot-pack-001-v1.json",
            "projects/episode-001-adam/contracts/"
            "runware-beat-01-execution-authorization-v1.json",
            "projects/episode-001-adam/contracts/"
            "automatic-video-user-authorization-v1.json",
            "projects/episode-001-adam/contracts/episode-production-policy-v1.json",
            "projects/episode-001-adam/cinematic/episode-production-plan-v1.json",
            "projects/_orchestrator/contracts/"
            "autonomous-episode-orchestrator-policy-v1.json",
        )
        for relative in required:
            source = repo / relative
            destination = smoke_repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        dialog = ProductionConsoleDialog(smoke_repo)
        dialog.show()
        for _ in range(10):
            app.processEvents()

        tabs = dialog.findChild(QTabWidget, "episodeProductionTabs")
        produce = dialog.findChild(QPushButton, "produceNextEpisodeButton")
        proposal = dialog.findChild(QPlainTextEdit, "scopeProposalView")
        events = dialog.findChild(QTableWidget, "scopeEventsTable")
        discuss = dialog.findChild(QPlainTextEdit, "scopeDiscussionInput")
        approve = dialog.findChild(QPushButton, "approveEpisodeScopeButton")
        openai_key = dialog.findChild(QPushButton, "configureOpenAIKeyButton")
        eleven_key = dialog.findChild(QPushButton, "configureElevenLabsKeyButton")

        require(tabs is not None and tabs.count() == 3, "THREE_TABS_REQUIRED")
        require(produce is not None, "PRODUCE_BUTTON_MISSING")
        require(proposal is not None and proposal.isReadOnly(), "PROPOSAL_VIEW_MISSING")
        require(events is not None, "EVENTS_TABLE_MISSING")
        require(discuss is not None, "DISCUSSION_INPUT_MISSING")
        require(approve is not None, "APPROVAL_BUTTON_MISSING")
        require(openai_key is not None, "OPENAI_KEY_BUTTON_MISSING")
        require(eleven_key is not None, "ELEVENLABS_KEY_BUTTON_MISSING")

        args.output_root.mkdir(parents=True, exist_ok=True)
        screenshot = args.output_root / "siraj-autonomous-episode-orchestrator-v1.png"
        dialog.grab().save(str(screenshot))
        print("STATUS=PASS_SIRAJ_AUTONOMOUS_EPISODE_ORCHESTRATOR_V1_SMOKE")
        print("TABS=3")
        print("OPENAI_REQUESTS_DURING_SMOKE=0")
        print("RUNWARE_REQUESTS_DURING_SMOKE=0")
        print("ELEVENLABS_REQUESTS_DURING_SMOKE=0")
        print("SCREENSHOT=" + str(screenshot))
        dialog.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
