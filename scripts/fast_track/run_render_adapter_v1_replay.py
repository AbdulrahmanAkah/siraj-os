from __future__ import annotations

import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from scripts.project_progress.recorder import (
    record_milestone,
)
from src.application.local_video_production.render_adapter_v1 import (
    render_local_video_manifest,
)


PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

MANIFEST = (
    PROJECT_ROOT
    / "manifests"
    / "render-adapter-v1-replay.json"
)


def main() -> int:
    result = render_local_video_manifest(
        PROJECT_ROOT,
        MANIFEST,
        replace=True,
    )

    report = json.loads(
        Path(result["report"]).read_text(
            encoding="utf-8-sig"
        )
    )

    if result["status"] != "VALID":
        raise RuntimeError(
            "RENDER_ADAPTER_V1_OUTPUT_INVALID"
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
        milestone_id=(
            "2026-07-21-render-adapter-v1-replay"
        ),
        title_ar=(
            "إنتاج فيديو ثانٍ من Render Manifest عام"
        ),
        status="COMPLETED",
        summary_ar=(
            "تم فصل بيانات الفيديو عن منطق FFmpeg، "
            "وإنتاج render-adapter-v1-replay.mp4 من "
            "manifest مستقل باستخدام LocalVideoRenderAdapter. "
            "اجتاز الفيديو فحوص الترميز والدقة والصوت "
            "والإطارات السوداء."
        ),
        next_action_ar=(
            "ربط Render Manifest بمخرجات الحلقة الأولى "
            "بدل بيانات quality-gate، ثم توسيع الـadapter "
            "لدعم توقيت المشاهد والترجمة المحروقة اختياريًا."
        ),
        changed_files=[
            (
                "src/application/local_video_production/"
                "render_adapter_v1.py"
            ),
            (
                "scripts/fast_track/"
                "build_render_adapter_v1_replay_manifest.py"
            ),
            (
                "scripts/fast_track/"
                "run_render_adapter_v1_replay.py"
            ),
            (
                "tests/integration/"
                "test_render_adapter_v1.py"
            ),
            "PROJECT_PROGRESS.md",
        ],
        metadata={
            "output": result["output"],
            "output_sha256": (
                report["output_sha256"]
            ),
            "duration_seconds": (
                report["duration_seconds"]
            ),
            "checks": result["checks"],
            "manifest_driven": True,
        },
    )

    print(
        json.dumps(
            {
                "status": result["status"],
                "output": result["output"],
                "report": result["report"],
                "sha256": (
                    report["output_sha256"]
                ),
                "duration_seconds": (
                    report["duration_seconds"]
                ),
                "checks": result["checks"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
