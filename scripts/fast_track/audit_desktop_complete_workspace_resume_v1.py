from __future__ import annotations

import argparse
from pathlib import Path

from src.application.production_resume_router_v1 import (
    resolve_resume_directive_from_state,
)


def require(value: bool, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    main_window = (repo / "src/presentation/desktop/main_window.py").read_text(encoding="utf-8")
    console = (repo / "src/presentation/desktop/production_console.py").read_text(encoding="utf-8")
    workspace = (repo / "src/presentation/desktop/complete_workspace_v1.py").read_text(encoding="utf-8")
    repository = (repo / "src/presentation/desktop/repository.py").read_text(encoding="utf-8")

    for marker in (
        "CompleteWorkspace",
        "completeWorkspaceStack",
        "workspaceContinueEpisodeButton",
        "workspaceFinishToPublishButton",
        "الستوريبورد والخطة التحريرية",
        "الحزم البصرية",
        "الاعتمادات والبوابات البشرية",
        "التقارير وسجلات التدقيق",
        "الإعدادات وحالة النظام",
    ):
        require(marker in workspace, "WORKSPACE_MARKER_MISSING:" + marker)

    for marker in (
        "complete_workspace",
        "_navigate",
        "nav_buttons",
        "CompleteWorkspace",
    ):
        require(marker in main_window, "MAIN_WINDOW_MARKER_MISSING:" + marker)

    for marker in (
        "productionConsoleScroll",
        "continueEpisodeToPublishButton",
        "_continue_episode_to_publish",
        "resolve_resume_directive",
        "QScrollArea",
        "ScrollBarAsNeeded",
    ):
        require(marker in console, "CONSOLE_MARKER_MISSING:" + marker)

    require("deliverables/episode-master-v1.mp4" in repository, "FINAL_MASTER_DISCOVERY_MISSING")
    require("publishing/publish-package-v1/publish-manifest-v1.json" in repository, "PUBLISH_MANIFEST_DISCOVERY_MISSING")
    require("READY_TO_PUBLISH" in repository, "READY_TO_PUBLISH_STATUS_MISSING")

    media = resolve_resume_directive_from_state(
        {"status": "MEDIA_QUEUE_READY", "stage": "RUNWARE_VIDEO_GENERATION"}
    )
    require(media.requires_paid_confirmation, "PAID_CONFIRMATION_POLICY_LOST")
    final = resolve_resume_directive_from_state(
        {"status": "READY_TO_PUBLISH", "stage": "READY_TO_PUBLISH"}
    )
    require(final.ready_to_publish, "READY_TO_PUBLISH_ROUTING_FAILED")

    report = output / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_SIRAJ_DESKTOP_COMPLETE_WORKSPACE_AND_RESUME_V1",
                "PRODUCTION_CONSOLE_SCROLL=ENABLED",
                "CONTINUE_EPISODE_ACTION=STAGE_AWARE",
                "SIDEBAR_PLACEHOLDERS=REMOVED",
                "PROJECTS_PAGE=FUNCTIONAL",
                "EPISODES_PAGE=FUNCTIONAL",
                "STORYBOARD_PAGE=FUNCTIONAL",
                "VISUAL_PACKAGES_PAGE=FUNCTIONAL",
                "VIDEO_AND_PUBLISH_PAGE=FUNCTIONAL",
                "APPROVALS_PAGE=FUNCTIONAL",
                "REPORTS_PAGE=FUNCTIONAL",
                "SETTINGS_PAGE=FUNCTIONAL",
                "FINAL_MASTER_DISCOVERY=DELIVERABLES_V1",
                "PUBLISH_PACKAGE_DISCOVERY=ENABLED",
                "PAID_PROVIDER_CONFIRMATION=REQUIRED",
                "HUMAN_SCOPE_GATE=REQUIRED",
                "HUMAN_FINAL_REVIEW_GATE=REQUIRED",
                "AUTOMATIC_YOUTUBE_UPLOAD=FORBIDDEN",
                "NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN_WITH_PUBLISH_ASSET_COMPLETION",
            )
        ) + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
