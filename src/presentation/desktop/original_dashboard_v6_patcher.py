from __future__ import annotations

import re
from pathlib import Path


class OriginalDashboardPatchError(RuntimeError):
    pass


def patch_main_window(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    result = {}

    import_block = (
        "from .v6_dashboard_state_adapter import build_v6_dashboard_snapshot\n"
        "from .v6_dashboard_integration import (\n"
        "    V6CommandCenter,\n"
        "    install_v6_runtime_bridge,\n"
        ")\n"
    )
    if "from .v6_dashboard_integration import" not in text:
        anchor = "from .widgets import MetricCard, Panel, PreviewCanvas, StatusPill, WorkflowStrip\n"
        if anchor not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_WIDGET_IMPORT_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            anchor,
            anchor + import_block,
            1,
        )
        result["imports"] = "PATCHED"
    else:
        result["imports"] = "ALREADY_PATCHED"

    init_anchor = "        super().__init__()\n        install_series_standard_v2_dock(self)\n"
    init_replacement = (
        "        super().__init__()\n"
        "        install_v6_runtime_bridge()\n"
        "        install_series_standard_v2_dock(self)\n"
    )
    if "install_v6_runtime_bridge()" not in text:
        if init_anchor not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_INIT_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            init_anchor,
            init_replacement,
            1,
        )
        result["runtime_bridge"] = "PATCHED"
    else:
        result["runtime_bridge"] = "ALREADY_PATCHED"

    old_snapshot = "        self.snapshot = build_dashboard_snapshot(repo_root)\n"
    new_snapshot = "        self.snapshot = build_v6_dashboard_snapshot(repo_root)\n"
    if new_snapshot not in text:
        if old_snapshot not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_INITIAL_SNAPSHOT_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            old_snapshot,
            new_snapshot,
            1,
        )
        result["initial_snapshot"] = "PATCHED"
    else:
        result["initial_snapshot"] = "ALREADY_PATCHED"

    hero_anchor = "        layout.addWidget(self._build_compact_hero())\n"
    command_center = (
        "        layout.addWidget(self._build_compact_hero())\n"
        "        self.v6_command_center = V6CommandCenter(self.repo_root, self)\n"
        "        self.v6_command_center.refresh_requested.connect(self._refresh)\n"
        "        self.v6_command_center.log_message.connect(self._log)\n"
        "        layout.addWidget(self.v6_command_center)\n"
    )
    if "self.v6_command_center = V6CommandCenter" not in text:
        if hero_anchor not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_HERO_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            hero_anchor,
            command_center,
            1,
        )
        result["command_center"] = "PATCHED"
    else:
        result["command_center"] = "ALREADY_PATCHED"

    populate_anchor = "        self.complete_workspace.refresh(snapshot)\n"
    populate_replacement = (
        "        self.complete_workspace.refresh(snapshot)\n"
        "        self.v6_command_center.refresh_state(snapshot)\n"
    )
    if "self.v6_command_center.refresh_state(snapshot)" not in text:
        if populate_anchor not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_POPULATE_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            populate_anchor,
            populate_replacement,
            1,
        )
        result["populate"] = "PATCHED"
    else:
        result["populate"] = "ALREADY_PATCHED"

    refresh_old = (
        "    def _refresh(self) -> None:\n"
        "        self._populate(build_dashboard_snapshot(self.repo_root))\n"
    )
    refresh_new = (
        "    def _refresh(self) -> None:\n"
        "        self._populate(build_v6_dashboard_snapshot(self.repo_root))\n"
    )
    if refresh_new not in text:
        if refresh_old not in text:
            raise OriginalDashboardPatchError(
                "MAIN_WINDOW_REFRESH_ANCHOR_NOT_FOUND"
            )
        text = text.replace(
            refresh_old,
            refresh_new,
            1,
        )
        result["refresh"] = "PATCHED"
    else:
        result["refresh"] = "ALREADY_PATCHED"

    method_pattern = re.compile(
        r"    def _open_production_console\(self\) -> None:\n"
        r".*?"
        r"(?=    def _navigate\(self, section: str\) -> None:)",
        re.DOTALL,
    )
    current_match = method_pattern.search(text)
    if not current_match:
        raise OriginalDashboardPatchError(
            "MAIN_WINDOW_PRODUCTION_METHOD_NOT_FOUND"
        )
    if "self.v6_command_center.primary_action()" not in current_match.group(0):
        replacement = (
            "    def _open_production_console(self) -> None:\n"
            "        try:\n"
            "            self.complete_workspace.show_section(\"dashboard\")\n"
            "            self.v6_command_center.primary_action()\n"
            "        except Exception as exc:\n"
            "            QMessageBox.critical(\n"
            "                self,\n"
            "                \"تعذر تشغيل Autopilot V6\",\n"
            "                str(exc),\n"
            "            )\n"
            "        finally:\n"
            "            self._refresh()\n\n"
        )
        text = (
            text[: current_match.start()]
            + replacement
            + text[current_match.end() :]
        )
        result["production_action"] = "PATCHED"
    else:
        result["production_action"] = "ALREADY_PATCHED"

    old_subtitle = "من النص والستوريبورد حتى الفيديو الجاهز للنشر"
    new_subtitle = (
        "من اختيار الموضوع والبحث إلى الصوت والوسائط والمونتاج "
        "ثم المراجعة البشرية النهائية"
    )
    if old_subtitle in text:
        text = text.replace(
            old_subtitle,
            new_subtitle,
            1,
        )
        result["hero_subtitle"] = "PATCHED"
    else:
        result["hero_subtitle"] = (
            "ALREADY_PATCHED"
            if new_subtitle in text
            else "NOT_FOUND_NON_BLOCKING"
        )

    old_heading = "إدارة جاهزية الحلقات للفيديو والنشر"
    new_heading = "إدارة الحلقات — الحالة الفعلية لمحرك Autopilot V6"
    if old_heading in text:
        text = text.replace(
            old_heading,
            new_heading,
            1,
        )
        result["queue_heading"] = "PATCHED"
    else:
        result["queue_heading"] = "ALREADY_PATCHED"

    path.write_text(text, encoding="utf-8")
    return result


def patch_complete_workspace(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8-sig")
    old = (
        "السياسات الملزمة: حد الحلقة 40$، لا إنفاق مدفوع دون تأكيد، "
        "\"\n            \"لا موسيقى، إصلاح جزئي فقط، بوابتان بشريتان، ورفع YouTube يدوي."
    )

    # Simpler robust replacement across the source string fragments.
    legacy_fragments = (
        "السياسات الملزمة: حد الحلقة 40$، لا إنفاق مدفوع دون تأكيد، ",
        "لا موسيقى، إصلاح جزئي فقط، بوابتان بشريتان، ورفع YouTube يدوي.",
    )
    if legacy_fragments[0] in text:
        text = text.replace(
            legacy_fragments[0],
            (
                "السياسات الملزمة V6: لا سقف تكلفة يضعه النظام، "
                "كل إنفاق مدفوع يحتاج تفويضًا صريحًا، "
            ),
            1,
        )
    if legacy_fragments[1] in text:
        text = text.replace(
            legacy_fragments[1],
            (
                "لا إعادة محاولة مدفوعة تلقائية، الإصلاح المحلي الآمن تلقائي، "
                "الفيديو المولد لا يتجاوز ثلثي الحلقة، لا موسيقى، والنشر يدوي."
            ),
            1,
        )

    if "حد الحلقة 40$" in text:
        raise OriginalDashboardPatchError(
            "LEGACY_40_DOLLAR_POLICY_STILL_PRESENT"
        )

    path.write_text(text, encoding="utf-8")
    return {"settings_policy": "PATCHED_OR_ALREADY_CURRENT"}


def validate_main_window(path: Path) -> None:
    text = path.read_text(encoding="utf-8-sig")
    required = (
        "V6CommandCenter",
        "build_v6_dashboard_snapshot",
        "install_v6_runtime_bridge()",
        "self.v6_command_center = V6CommandCenter",
        "self.v6_command_center.primary_action()",
        "build_v6_dashboard_snapshot(self.repo_root)",
    )
    missing = [
        marker
        for marker in required
        if marker not in text
    ]
    if missing:
        raise OriginalDashboardPatchError(
            "MAIN_WINDOW_V6_INTEGRATION_INCOMPLETE:"
            + ",".join(missing)
        )
