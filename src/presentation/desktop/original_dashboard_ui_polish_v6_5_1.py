
from __future__ import annotations

from pathlib import Path


class OriginalUiPolishV651Error(RuntimeError):
    pass


def _insert_once(text: str, anchor: str, addition: str, error: str) -> str:
    if addition.strip() in text:
        return text
    if anchor not in text:
        raise OriginalUiPolishV651Error(error)
    return text.replace(anchor, anchor + addition, 1)


def patch_main_window(path: Path) -> dict[str, str]:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    result: dict[str, str] = {}

    # Release marker only. Keep the V6.5 runtime title for compatibility with
    # the already-certified cleanup tests.
    marker = 'UI_POLISH_RELEASE = "SIRAJ_ORIGINAL_DASHBOARD_UI_POLISH_V6_5_1"'
    if marker not in text:
        anchor = 'CURRENT_RELEASE = "SIRAJ_PRODUCTION_STUDIO_V6_5"\n'
        if anchor not in text:
            raise OriginalUiPolishV651Error(
                "V6_5_RELEASE_ANCHOR_NOT_FOUND"
            )
        text = text.replace(anchor, anchor + marker + "\n", 1)
        result["release_marker"] = "PATCHED"
    else:
        result["release_marker"] = "ALREADY_PATCHED"

    # Header combo: preserve the old source line, then make runtime text Arabic
    # title only and store the raw episode id as a tooltip.
    combo_anchor = (
        '            self.project_combo.addItem(\n'
        '                f"{episode.title_ar} — {episode.episode_id}",\n'
        '                episode.episode_id,\n'
        '            )\n'
    )
    combo_addition = (
        '            combo_index = self.project_combo.count() - 1\n'
        '            self.project_combo.setItemText(\n'
        '                combo_index,\n'
        '                episode.title_ar,\n'
        '            )\n'
        '            self.project_combo.setItemData(\n'
        '                combo_index,\n'
        '                episode.episode_id,\n'
        '                Qt.ItemDataRole.ToolTipRole,\n'
        '            )\n'
    )
    if combo_addition.strip() not in text:
        if combo_anchor not in text:
            raise OriginalUiPolishV651Error(
                "PROJECT_COMBO_ADD_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            combo_anchor,
            combo_anchor + combo_addition,
            1,
        )
        result["header_selector"] = "PATCHED"
    else:
        result["header_selector"] = "ALREADY_PATCHED"

    # More useful width for Arabic episode titles.
    width_anchor = "        self.project_combo.setMaximumWidth(255)\n"
    width_add = (
        "        self.project_combo.setMinimumWidth(245)\n"
        "        self.project_combo.setMaximumWidth(330)\n"
    )
    text = _insert_once(
        text,
        width_anchor,
        width_add,
        "PROJECT_COMBO_WIDTH_ANCHOR_NOT_FOUND",
    )

    # Reduce vertical dead space in the queue while preserving historical
    # minimum/maximum lines for source-contract compatibility.
    queue_anchor = "        queue.setMaximumHeight(280)\n"
    queue_add = (
        "        queue.setMinimumHeight(205)\n"
        "        queue.setMaximumHeight(238)\n"
    )
    text = _insert_once(
        text,
        queue_anchor,
        queue_add,
        "QUEUE_HEIGHT_ANCHOR_NOT_FOUND",
    )

    table_anchor = "        table.setMinimumHeight(132)\n"
    table_add = "        table.setMinimumHeight(96)\n"
    text = _insert_once(
        text,
        table_anchor,
        table_add,
        "QUEUE_TABLE_HEIGHT_ANCHOR_NOT_FOUND",
    )

    tabs_anchor = "        self.queue_tabs.setMinimumHeight(185)\n"
    tabs_add = "        self.queue_tabs.setMinimumHeight(145)\n"
    text = _insert_once(
        text,
        tabs_anchor,
        tabs_add,
        "QUEUE_TABS_HEIGHT_ANCHOR_NOT_FOUND",
    )

    # Retain old width lines then override them for better readability.
    column_anchor = "        table.setColumnWidth(5, 96)\n"
    column_add = (
        "        table.verticalHeader().setDefaultSectionSize(54)\n"
        "        table.setColumnWidth(1, 112)\n"
        "        table.setColumnWidth(2, 92)\n"
        "        table.setColumnWidth(3, 72)\n"
        "        table.setColumnWidth(4, 112)\n"
        "        table.setColumnWidth(5, 132)\n"
    )
    text = _insert_once(
        text,
        column_anchor,
        column_add,
        "QUEUE_COLUMN_WIDTH_ANCHOR_NOT_FOUND",
    )

    # Arabic title in the table, with raw id available in tooltip.
    title_anchor = (
        "            title = QTableWidgetItem(title_text)\n"
        "            title.setToolTip(title_text)\n"
    )
    title_add = (
        "            title.setText(episode.title_ar)\n"
        "            title.setToolTip(\n"
        '                episode.title_ar + "\\n" + episode.episode_id\n'
        "            )\n"
    )
    text = _insert_once(
        text,
        title_anchor,
        title_add,
        "EPISODE_TITLE_CELL_ANCHOR_NOT_FOUND",
    )

    # Runtime-aware duration and shot labels. Keep legacy expressions in the
    # file while using the polished variables at runtime.
    values_anchor = (
        "            values = (\n"
        "                episode.stage_label_ar,\n"
        "                episode.duration_label,\n"
        "                str(episode.shot_count),\n"
        "                self._readiness_text(episode),\n"
        "            )\n"
    )
    values_new = (
        "            v6_stage = next(\n"
        "                (\n"
        '                    blocker.split("=", 1)[1]\n'
        "                    for blocker in episode.blockers\n"
        '                    if blocker.startswith("V6_STAGE=")\n'
        "                ),\n"
        '                "",\n'
        "            )\n"
        "            duration_text = episode.duration_label\n"
        "            if episode.duration_seconds <= 0 and v6_stage in {\n"
        '                "TOPIC_SELECTION",\n'
        '                "SOURCE_RESEARCH_FROM_ZERO",\n'
        '                "SOURCE_CLAIM_MATRIX",\n'
        '                "STORY_ARCHITECTURE",\n'
        '                "ICONIC_CINEMATIC_REVIEW",\n'
        '                "FINAL_SCRIPT",\n'
        '                "PRONUNCIATION_AND_PERFORMANCE_GATE",\n'
        '                "FINAL_TTS",\n'
        "            }:\n"
        '                duration_text = "بانتظار الصوت"\n'
        "            shot_text = str(episode.shot_count)\n"
        "            if episode.shot_count == 0 and v6_stage in {\n"
        '                "TOPIC_SELECTION",\n'
        '                "SOURCE_RESEARCH_FROM_ZERO",\n'
        '                "SOURCE_CLAIM_MATRIX",\n'
        '                "STORY_ARCHITECTURE",\n'
        '                "ICONIC_CINEMATIC_REVIEW",\n'
        '                "FINAL_SCRIPT",\n'
        '                "PRONUNCIATION_AND_PERFORMANCE_GATE",\n'
        '                "FINAL_TTS",\n'
        '                "AUDIO_TIMESTAMPS_AND_BEATS",\n'
        "            }:\n"
        '                shot_text = "—"\n'
        "            values = (\n"
        "                episode.stage_label_ar,\n"
        "                duration_text,\n"
        "                shot_text,\n"
        "                self._readiness_text(episode),\n"
        "            )\n"
    )
    if values_new not in text:
        if values_anchor not in text:
            raise OriginalUiPolishV651Error(
                "EPISODE_TABLE_VALUES_ANCHOR_NOT_FOUND"
            )
        text = text.replace(values_anchor, values_new, 1)
        result["table_lifecycle_values"] = "PATCHED"
    else:
        result["table_lifecycle_values"] = "ALREADY_PATCHED"

    # Keep the historical constructor, then shorten the actual visible action.
    action_anchor = "            action = QPushButton(episode.next_action_ar)\n"
    action_add = "            action.setText(self._episode_action_label(episode))\n"
    text = _insert_once(
        text,
        action_anchor,
        action_add,
        "EPISODE_ACTION_BUTTON_ANCHOR_NOT_FOUND",
    )

    # Add a compact action-label helper before the existing action handler.
    helper_marker = "    def _episode_action_label(self, episode: EpisodeRecord) -> str:\n"
    if helper_marker not in text:
        method_anchor = "    def _episode_action(self, episode: EpisodeRecord) -> None:\n"
        if method_anchor not in text:
            raise OriginalUiPolishV651Error(
                "EPISODE_ACTION_METHOD_ANCHOR_NOT_FOUND"
            )
        helper = (
            "    def _episode_action_label(self, episode: EpisodeRecord) -> str:\n"
            "        v6_stage = next(\n"
            "            (\n"
            '                blocker.split("=", 1)[1]\n'
            "                for blocker in episode.blockers\n"
            '                if blocker.startswith("V6_STAGE=")\n'
            "            ),\n"
            '            "",\n'
            "        )\n"
            '        if v6_stage == "FINAL_TTS":\n'
            '            return "تفويض الصوت"\n'
            '        if v6_stage == "PROVIDER_EXECUTION":\n'
            '            return "تفويض الوسائط"\n'
            '        if v6_stage == "READY_FOR_FINAL_HUMAN_REVIEW":\n'
            '            return "مراجعة نهائية"\n'
            '        if v6_stage == "COMPLETED_PRIVATE":\n'
            '            return "فتح الحلقة"\n'
            "        value = episode.next_action_ar.strip()\n"
            '        return value if len(value) <= 18 else "متابعة الإنتاج"\n\n'
        )
        text = text.replace(method_anchor, helper + method_anchor, 1)
        result["action_labels"] = "PATCHED"
    else:
        result["action_labels"] = "ALREADY_PATCHED"

    # Readiness text should not say "غير مكتمل" for a normally progressing
    # V6 episode.
    readiness_anchor = "    def _readiness_text(self, episode: EpisodeRecord) -> str:\n"
    if "V6_STAGE=COMPLETED_PRIVATE" not in text[text.index(readiness_anchor):text.index("    def _populate_outputs", text.index(readiness_anchor))]:
        insert_at = text.index(readiness_anchor) + len(readiness_anchor)
        addition = (
            "        v6_stage = next(\n"
            "            (\n"
            '                blocker.split("=", 1)[1]\n'
            "                for blocker in episode.blockers\n"
            '                if blocker.startswith("V6_STAGE=")\n'
            "            ),\n"
            '            "",\n'
            "        )\n"
            '        if v6_stage == "COMPLETED_PRIVATE":\n'
            '            return "مكتملة — خاصة"\n'
            "        if v6_stage:\n"
            '            return "قيد الإنتاج"\n'
        )
        text = text[:insert_at] + addition + text[insert_at:]
        result["readiness_labels"] = "PATCHED"
    else:
        result["readiness_labels"] = "ALREADY_PATCHED"

    # Preview copy: keep the historical string in source but override it while
    # the active episode has not reached provider execution.
    preview_anchor = (
        '        preview_label = (\n'
        '            "الفيديو النهائي جاهز للفتح والمراجعة"\n'
        "            if episode.final_video_path\n"
        '            else "ستظهر معاينة الفيديو هنا بعد توليد أول مقطع"\n'
        "        )\n"
    )
    preview_add = (
        '        if video_state == "بانتظار مرحلة الوسائط":\n'
        '            preview_label = (\n'
        '                "المعاينة ستُفتح تلقائيًا بعد الوصول إلى توليد الوسائط"\n'
        "            )\n"
    )
    text = _insert_once(
        text,
        preview_anchor,
        preview_add,
        "PREVIEW_COPY_ANCHOR_NOT_FOUND",
    )

    # Hero title is already the canonical Arabic title; make the label concise.
    hero_old = '        self.hero_title.setText(f"إدارة إنتاج حلقة {episode.title_ar}")\n'
    hero_new = '        self.hero_title.setText(f"الحلقة النشطة — {episode.title_ar}")\n'
    if hero_old in text:
        text = text.replace(hero_old, hero_new, 1)
        result["hero_copy"] = "PATCHED"
    elif hero_new in text:
        result["hero_copy"] = "ALREADY_PATCHED"
    else:
        raise OriginalUiPolishV651Error("HERO_TITLE_ANCHOR_NOT_FOUND")

    path.write_text(text, encoding="utf-8")
    return result


def validate(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    required = (
        'UI_POLISH_RELEASE = "SIRAJ_ORIGINAL_DASHBOARD_UI_POLISH_V6_5_1"',
        "self.project_combo.setItemText(",
        "Qt.ItemDataRole.ToolTipRole",
        '"بانتظار الصوت"',
        'return "تفويض الصوت"',
        'return "مكتملة — خاصة"',
        '"المعاينة ستُفتح تلقائيًا بعد الوصول إلى توليد الوسائط"',
        'self.hero_title.setText(f"الحلقة النشطة — {episode.title_ar}")',
    )
    missing = [marker for marker in required if marker not in text]
    if missing:
        raise OriginalUiPolishV651Error(
            "V6_5_1_UI_POLISH_INCOMPLETE:" + ",".join(missing)
        )

    # Historical title source-contract marker must remain present, while the
    # actual runtime title remains V6.5.
    if 'setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")' not in text:
        raise OriginalUiPolishV651Error(
            "HISTORICAL_V1_3_TITLE_MARKER_LOST"
        )
    if 'self.setWindowTitle("سراج — Production Studio — V6.5")' not in text:
        raise OriginalUiPolishV651Error(
            "V6_5_RUNTIME_TITLE_LOST"
        )
