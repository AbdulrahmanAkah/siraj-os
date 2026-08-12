
from __future__ import annotations
from pathlib import Path


class ProfessionalCleanupV65Error(RuntimeError):
    pass


def patch_main_window(path: Path) -> dict[str, str]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    result = {}

    call = "        install_series_standard_v2_dock(self)\n"
    if call in text:
        text = text.replace(call, "", 1)
        result["legacy_v2_dock"] = "REMOVED"
    else:
        result["legacy_v2_dock"] = "ALREADY_REMOVED"

    old_title = 'self.setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")'
    new_title = 'self.setWindowTitle("سراج — Production Studio — V6.5")'
    if old_title in text:
        text = text.replace(old_title, new_title, 1)
        result["window_title"] = "PATCHED"
    elif new_title in text:
        result["window_title"] = "ALREADY_PATCHED"
    else:
        raise ProfessionalCleanupV65Error("WINDOW_TITLE_ANCHOR_NOT_FOUND")

    release_marker = 'CURRENT_RELEASE = "SIRAJ_PRODUCTION_STUDIO_V6_5"'
    if release_marker not in text:
        anchor = 'RELEASE = "SIRAJ_DESKTOP_DASHBOARD_V1_3"\n'
        if anchor not in text:
            raise ProfessionalCleanupV65Error("RELEASE_ANCHOR_NOT_FOUND")
        text = text.replace(anchor, anchor + release_marker + "\n", 1)

    text = text.replace(
        'subtitle = QLabel("من اختيار الموضوع والبحث إلى الصوت والوسائط والمونتاج ثم المراجعة البشرية النهائية")',
        'subtitle = QLabel("خط إنتاج واحد: بحث موثّق → صوت → وسائط → مونتاج → مراجعة بشرية")',
    )
    text = text.replace(
        'heading = QLabel("إدارة الحلقات — الحالة الفعلية لمحرك Autopilot V6")',
        'heading = QLabel("الحلقات — الإنتاج النشط والسجل المكتمل")',
    )
    text = text.replace(
        'self.queue_tabs.setTabText(0, f"جاهزة للتحويل ({ready_count})")',
        'self.queue_tabs.setTabText(0, f"مكتملة / للمراجعة ({ready_count})")',
    )
    text = text.replace(
        'self.queue_tabs.setTabText(1, f"قيد العمل ({work_count})")',
        'self.queue_tabs.setTabText(1, f"قيد الإنتاج ({work_count})")',
    )

    combo_old = (
        '        for episode in snapshot.episodes:\n'
        '            self.project_combo.addItem(\n'
        '                f"{episode.title_ar} — {episode.episode_id}",\n'
        '                episode.episode_id,\n'
        '            )\n'
        '        self.project_combo.blockSignals(False)\n'
    )
    combo_new = (
        '        for episode in snapshot.episodes:\n'
        '            self.project_combo.addItem(\n'
        '                f"{episode.title_ar} — {episode.episode_id}",\n'
        '                episode.episode_id,\n'
        '            )\n'
        '        if snapshot.active_episode_id:\n'
        '            active_index = self.project_combo.findData(\n'
        '                snapshot.active_episode_id\n'
        '            )\n'
        '            if active_index >= 0:\n'
        '                self.project_combo.setCurrentIndex(active_index)\n'
        '        self.project_combo.blockSignals(False)\n'
    )
    if combo_new not in text:
        if combo_old not in text:
            raise ProfessionalCleanupV65Error(
                "ACTIVE_COMBO_SELECTION_ANCHOR_NOT_FOUND"
            )
        text = text.replace(combo_old, combo_new, 1)
        result["active_selector"] = "PATCHED"
    else:
        result["active_selector"] = "ALREADY_PATCHED"

    shot_old = '        self.shot_count_badge.set_text(f"{episode.shot_count} لقطة مخططة")\n'
    shot_new = (
        '        v6_stage = next(\n'
        '            (\n'
        '                blocker.split("=", 1)[1]\n'
        '                for blocker in episode.blockers\n'
        '                if blocker.startswith("V6_STAGE=")\n'
        '            ),\n'
        '            "",\n'
        '        )\n'
        '        pre_storyboard_stages = {\n'
        '            "TOPIC_SELECTION",\n'
        '            "SOURCE_RESEARCH_FROM_ZERO",\n'
        '            "SOURCE_CLAIM_MATRIX",\n'
        '            "STORY_ARCHITECTURE",\n'
        '            "ICONIC_CINEMATIC_REVIEW",\n'
        '            "FINAL_SCRIPT",\n'
        '            "PRONUNCIATION_AND_PERFORMANCE_GATE",\n'
        '            "FINAL_TTS",\n'
        '            "AUDIO_TIMESTAMPS_AND_BEATS",\n'
        '        }\n'
        '        if episode.shot_count == 0 and v6_stage in pre_storyboard_stages:\n'
        '            self.shot_count_badge.set_text(\n'
        '                "اللقطات: تُبنى بعد اكتمال الصوت"\n'
        '            )\n'
        '        else:\n'
        '            self.shot_count_badge.set_text(\n'
        '                f"{episode.shot_count} لقطة مخططة"\n'
        '            )\n'
    )
    if shot_new not in text:
        if shot_old not in text:
            raise ProfessionalCleanupV65Error("SHOT_BADGE_ANCHOR_NOT_FOUND")
        text = text.replace(shot_old, shot_new, 1)

    video_old = (
        '        if episode.generated_shot_count > 0:\n'
        '            return "مقاطع قيد المراجعة"\n'
        '        return "غير مولد"\n'
    )
    video_new = (
        '        if episode.generated_shot_count > 0:\n'
        '            return "مقاطع قيد المراجعة"\n'
        '        v6_stage = next(\n'
        '            (\n'
        '                blocker.split("=", 1)[1]\n'
        '                for blocker in episode.blockers\n'
        '                if blocker.startswith("V6_STAGE=")\n'
        '            ),\n'
        '            "",\n'
        '        )\n'
        '        if v6_stage and v6_stage not in {\n'
        '            "PROVIDER_EXECUTION",\n'
        '            "LOCAL_ASSEMBLY_AND_MONTAGE",\n'
        '            "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",\n'
        '            "READY_FOR_FINAL_HUMAN_REVIEW",\n'
        '            "COMPLETED_PRIVATE",\n'
        '        }:\n'
        '            return "بانتظار مرحلة الوسائط"\n'
        '        return "غير مولد"\n'
    )
    if video_new not in text:
        if video_old not in text:
            raise ProfessionalCleanupV65Error("VIDEO_STATE_ANCHOR_NOT_FOUND")
        text = text.replace(video_old, video_new, 1)

    text = text.replace(
        'MetricCard("اللقطات المخططة", str(snapshot.total_shot_count), "إجمالي خطة الإنتاج")',
        'MetricCard("لقطات الحلقة النشطة", str(snapshot.total_shot_count), "تُبنى بعد الصوت والستوريبورد")',
    )
    text = text.replace(
        'MetricCard("المقاطع المنتجة", str(snapshot.generated_clip_count), "توليد فعلي فقط")',
        'MetricCard("وسائط مولّدة", str(snapshot.generated_clip_count), "للحلقة النشطة فقط")',
    )
    text = text.replace('"جاهزية النشر",', '"تقدم خط الإنتاج",', 1)
    text = text.replace('"فيديو نهائي معتمد",', '"نسبة المراحل المكتملة",', 1)
    text = text.replace(
        '("dashboard", "dashboard", "لوحة التحكم", True),',
        '("dashboard", "dashboard", "لوحة الإنتاج", True),',
        1,
    )

    path.write_text(text, encoding="utf-8")
    return result


def patch_legacy_v2_panel(path: Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    marker = "LEGACY_V2_DOCK_DISABLED_BY_V6_5 = True"
    if marker not in text:
        anchor = "SNAPSHOT_REL = Path(\n"
        if anchor not in text:
            raise ProfessionalCleanupV65Error(
                "V2_PANEL_SNAPSHOT_ANCHOR_NOT_FOUND"
            )
        text = text.replace(anchor, marker + "\n\n" + anchor, 1)

    start = text.find("def install_series_standard_v2_dock(window: Any) -> None:\n")
    if start < 0:
        raise ProfessionalCleanupV65Error(
            "V2_PANEL_INSTALL_FUNCTION_ANCHOR_NOT_FOUND"
        )
    end_marker = "\n# SIRAJ_DESKTOP_SNAPSHOT_PENDING_OVERLAY_V2"
    end = text.find(end_marker, start)
    if end < 0:
        raise ProfessionalCleanupV65Error(
            "V2_PANEL_INSTALL_FUNCTION_END_NOT_FOUND"
        )
    replacement = (
        "def install_series_standard_v2_dock(window: Any) -> None:\n"
        '    """Legacy compatibility no-op for V6.5."""\n'
        "    del window\n"
        "    return\n"
    )
    current = text[start:end]
    if "Legacy compatibility no-op for V6.5." not in current:
        text = text[:start] + replacement + text[end:]
    path.write_text(text, encoding="utf-8")
    return "DISABLED_NOOP"


def validate(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    required = (
        'CURRENT_RELEASE = "SIRAJ_PRODUCTION_STUDIO_V6_5"',
        'self.setWindowTitle("سراج — Production Studio — V6.5")',
        "snapshot.active_episode_id",
        '"اللقطات: تُبنى بعد اكتمال الصوت"',
        '"بانتظار مرحلة الوسائط"',
        'f"مكتملة / للمراجعة ({ready_count})"',
        'f"قيد الإنتاج ({work_count})"',
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise ProfessionalCleanupV65Error(
            "PROFESSIONAL_CLEANUP_INCOMPLETE:" + ",".join(missing)
        )
    if "        install_series_standard_v2_dock(self)\n" in text:
        raise ProfessionalCleanupV65Error(
            "LEGACY_V2_DOCK_CALL_STILL_ACTIVE"
        )
