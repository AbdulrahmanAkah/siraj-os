import json
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QScrollArea,
)

from src.application.production_standard_v2_native_assets import (
    _SIRAJ_VEO_ALLOWED_PARAMETERS_V1,
    build_native_asset_plan,
)
from src.presentation.desktop.production_console import (
    ProductionConsoleDialog,
)


def test_veo_requests_use_only_supported_parameters() -> None:
    plan = build_native_asset_plan(Path.cwd())
    videos = plan["queues"]["runware_videos"]
    assert len(videos) == 137
    for item in videos:
        task = item["task_draft"]
        assert "negativePrompt" not in task
        assert set(task) <= _SIRAJ_VEO_ALLOWED_PARAMETERS_V1
        assert (
            "Strict exclusion constraints for this provider request:"
            in task["positivePrompt"]
        )
        certification = item[
            "luna_prompt_certification_v2"
        ]
        assert certification[
            "positive_prompt_sha256"
        ]
        assert certification["asset_derivation"][
            "unsupported_negativePrompt_parameter"
        ] == "REMOVED"


def test_live_queue_first_video_is_resumable_and_sanitized() -> None:
    path = Path(
        "projects/episode-001-adam/orchestration/"
        "media-production-queue-v1.json"
    )
    queue = json.loads(
        path.read_text(encoding="utf-8-sig")
    )
    videos = queue["queues"]["runware_videos"]
    first = next(
        item
        for item in videos
        if item["queue_id"] == "VID-SH-001-C01"
    )
    assert first["status"] == (
        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
    )
    assert "negativePrompt" not in first["task_draft"]


def test_console_has_one_resume_action_and_vertical_scroll() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = ProductionConsoleDialog(Path.cwd())
    dialog.resize(1100, 650)
    dialog.show()
    app.processEvents()

    visible_texts = [
        button.text()
        for button in dialog.findChildren(
            QAbstractButton
        )
        if button.isVisible()
    ]
    assert not any(
        "استكمال تنفيذ الوسائط" in text
        for text in visible_texts
    )
    assert sum(
        (
            "استكمال إنتاج الحلقة" in text
            or "تفويض موحد وبدء إنتاج الحلقة كاملة"
            in text
        )
        for text in visible_texts
    ) == 1

    scroll = dialog.findChild(
        QScrollArea,
        "sirajProductionConsoleRootScrollArea",
    )
    assert scroll is not None
    app.processEvents()
    assert scroll.verticalScrollBar().maximum() > 0

    dialog.close()
    app.processEvents()
