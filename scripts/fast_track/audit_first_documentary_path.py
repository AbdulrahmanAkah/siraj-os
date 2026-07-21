from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


MODULES = {
    "canonical_cli": "src.cli.generate",
    "production_pipeline": "src.application.pipeline.production_pipeline",
    "documentary_workflow": "src.application.workflow.documentary_workflow",
    "knowledge_extraction": "src.application.knowledge_v2.pipeline",
    "documentary_planning": "src.application.documentary_planning_v2",
    "narrative_architecture": "src.application.narrative_architecture_v2",
    "script_runtime": "src.application.documentary_script_runtime",
    "scene_runtime": "src.application.scene_generation_runtime",
    "storyboard_runtime": "src.application.storyboard_runtime",
    "documentary_assembly": "src.application.documentary_assembly",
    "documentary_verification": "src.application.documentary_verification",
    "publication_packaging": "src.application.publication_packaging",
    "export_architecture": "src.application.export_architecture",
    "production_runtime": "src.application.production_runtime",
    "production_specification": "src.application.documentary_production",
}


def module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, AttributeError):
        return False


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    availability = {
        name: {
            "module": module,
            "available": module_available(module),
        }
        for name, module in MODULES.items()
    }

    readme = (REPO / "README.md").read_text(encoding="utf-8-sig")
    production_doc = (
        REPO
        / "docs"
        / "architecture"
        / "BUNDLE_F_DOCUMENTARY_PRODUCTION_LAYER.md"
    ).read_text(encoding="utf-8-sig")

    rendering_is_dry_run = "rendering remains dry-run" in readme
    production_is_spec_only = "It produces no media" in production_doc

    knowledge_keys = (
        "knowledge_extraction",
        "production_pipeline",
        "documentary_workflow",
    )

    documentary_keys = (
        "documentary_planning",
        "narrative_architecture",
        "script_runtime",
        "scene_runtime",
        "storyboard_runtime",
        "documentary_assembly",
        "documentary_verification",
    )

    knowledge_ready = all(
        availability[key]["available"]
        for key in knowledge_keys
    )

    documentary_ready_count = sum(
        availability[key]["available"]
        for key in documentary_keys
    )

    report = {
        "schema_version": "siraj-fast-track-readiness-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "branch_target": "feature/gold-20-fast-track",
        "north_star": (
            "Automated evidence-traceable Islamic-history video production "
            "from the creation of Adam through the Day of Judgment."
        ),
        "first_episode": "episode-001-adam",
        "modules": availability,
        "stage_status": {
            "knowledge_foundation": (
                "READY" if knowledge_ready else "PARTIAL"
            ),
            "documentary_logic": (
                "READY"
                if documentary_ready_count == len(documentary_keys)
                else "PARTIAL"
            ),
            "media_execution": (
                "BLOCKED"
                if rendering_is_dry_run or production_is_spec_only
                else "UNKNOWN"
            ),
            "first_episode": "STARTED",
        },
        "document_signals": {
            "rendering_is_dry_run": rendering_is_dry_run,
            "production_is_specification_only": production_is_spec_only,
        },
        "critical_path": [
            "reviewed_source_pack",
            "evidence_linked_claim_ledger",
            "episode_plan",
            "arabic_script",
            "storyboard",
            "visual_asset_resolution",
            "voice_generation",
            "subtitle_generation",
            "ffmpeg_composition",
            "documentary_verification",
            "final_mp4",
        ],
        "immediate_blockers": [
            "No real voice execution adapter.",
            "No real visual asset execution adapter.",
            "No real FFmpeg render execution path.",
            "Episode 001 source pack is not populated or reviewed.",
        ],
        "next_action": (
            "Populate the reviewed Episode 001 source pack while implementing "
            "the first real media execution adapter."
        ),
    }

    # SIRAJ_MEDIA_PROTOTYPE_STATE_SYNC_V1
    media_audit_path = (
        REPO
        / "artifacts"
        / "fast-track"
        / "media-prototype-audit.json"
    )

    media_prototype = None

    if media_audit_path.is_file():
        try:
            media_prototype = json.loads(
                media_audit_path.read_text(
                    encoding="utf-8-sig"
                )
            )
        except (
            json.JSONDecodeError,
            OSError,
            TypeError,
        ):
            media_prototype = None

    prototype_confirmed = bool(
        isinstance(media_prototype, dict)
        and (
            media_prototype.get(
                "user_confirmed_video_prototype"
            )
            or media_prototype.get("video_count", 0) > 0
            or media_prototype.get("status")
            == "CONFIRMED_BY_LOCAL_ARTIFACT"
        )
    )

    if prototype_confirmed:
        report["stage_status"][
            "media_execution"
        ] = "PROTOTYPE_WORKING"

        report["stage_status"][
            "publishable_media_execution"
        ] = "BLOCKED"

        report.setdefault(
            "document_signals",
            {},
        )

        report["document_signals"].update(
            {
                "experimental_video_confirmed": True,
                "local_video_artifact_located": (
                    media_prototype.get(
                        "video_count",
                        0,
                    )
                    > 0
                ),
                "temporary_voiceover_detected": bool(
                    media_prototype.get(
                        "latest_video_probe",
                        {},
                    ).get(
                        "has_audio_stream"
                    )
                ),
                "reusable_render_adapter_validated": False,
                "publishable_quality_validated": False,
            }
        )

        report[
            "media_prototype_audit"
        ] = media_prototype

        report["immediate_blockers"] = [
            (
                "The video-production prototype works, but its "
                "execution path is not yet standardized as a "
                "reproducible production adapter."
            ),
            (
                "Temporary narration works, but the final voice "
                "provider, voice profile, and quality gate are "
                "not yet validated."
            ),
            (
                "The experimental editing path works, but the "
                "publishable documentary render profile is not "
                "yet complete."
            ),
            (
                "Episode 001 source pack is not populated or "
                "reviewed."
            ),
        ]

        report["next_action"] = (
            "Convert the confirmed quality-gate-v4 video path "
            "into a reproducible episode render adapter while "
            "populating the reviewed Episode 001 source pack."
        )

    else:
        report["stage_status"].setdefault(
            "publishable_media_execution",
            "BLOCKED",
        )

    artifact_root = REPO / "artifacts" / "fast-track"

    write_json(
        artifact_root / "pipeline-readiness.json",
        report,
    )

    markdown = [
        "# SIRAJ Fast-Track Readiness",
        "",
        f"- Knowledge foundation: {report['stage_status']['knowledge_foundation']}",
        f"- Documentary logic: {report['stage_status']['documentary_logic']}",
        f"- Media execution: {report['stage_status']['media_execution']}",
        (
            "- Publishable media execution: "
            f"{report['stage_status'].get('publishable_media_execution', 'BLOCKED')}"
        ),
        f"- First episode: {report['stage_status']['first_episode']}",
        "",
        "## Immediate blockers",
        "",
    ]

    markdown.extend(
        f"- {item}"
        for item in report["immediate_blockers"]
    )

    markdown.extend(
        [
            "",
            "## Next action",
            "",
            report["next_action"],
            "",
        ]
    )

    (artifact_root / "pipeline-readiness.md").write_text(
        "\n".join(markdown),
        encoding="utf-8",
        newline="\n",
    )

    print(
        json.dumps(
            {
                "stage_status": report["stage_status"],
                "immediate_blockers": report["immediate_blockers"],
                "next_action": report["next_action"],
                "report": str(
                    artifact_root / "pipeline-readiness.json"
                ),
            },
            indent=2,
        )
    )

    from scripts.project_progress.recorder import (
        record_milestone,
    )

    record_milestone(
        project_progress_path=(
            REPO / "PROJECT_PROGRESS.md"
        ),
        ledger_path=(
            REPO
            / "docs"
            / "execution"
            / "project-milestones.json"
        ),
        milestone_id="fast-track-readiness-audit-v1",
        title_ar="تشغيل تدقيق جاهزية خط الوثائقي",
        status="COMPLETED",
        summary_ar=(
            "تم تشغيل تدقيق جاهزية المسار الرأسي للحلقة الأولى "
            "وتسجيل حالة المعرفة والمنطق الوثائقي والوسائط."
        ),
        next_action_ar=report["next_action"],
        changed_files=[
            "artifacts/fast-track/pipeline-readiness.json",
            "artifacts/fast-track/pipeline-readiness.md",
        ],
        metadata={
            "SIRAJ_FAST_TRACK_PROGRESS_RECORDED": True,
            "stage_status": report["stage_status"],
        },
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
