from __future__ import annotations

from pathlib import Path
import unittest


class SirajDesktopDashboardV12SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[1]
        desktop = cls.repo / "src" / "presentation" / "desktop"
        cls.main = (desktop / "main_window.py").read_text(encoding="utf-8-sig")
        cls.widgets = (desktop / "widgets.py").read_text(encoding="utf-8-sig")
        cls.theme = (desktop / "theme.py").read_text(encoding="utf-8-sig")

    def test_release_marker(self) -> None:
        self.assertIn('SIRAJ_DESKTOP_DASHBOARD_V1_2', self.main)

    def test_compact_hero_is_outside_scroll(self) -> None:
        hero_index = self.main.index('layout.addWidget(self._build_compact_hero())')
        scroll_index = self.main.index('scroll = QScrollArea()')
        self.assertLess(hero_index, scroll_index)
        self.assertIn('setObjectName("projectHero")', self.main)

    def test_preview_has_hard_minimum_contract(self) -> None:
        self.assertIn('panel.setMinimumHeight(292)', self.main)
        self.assertIn('MIN_PREVIEW_HEIGHT = 169', self.widgets)
        self.assertIn('setFixedHeight(target)', self.widgets)

    def test_outputs_use_filename_only(self) -> None:
        self.assertIn('QLabel(path.name)', self.main)
        self.assertIn('setObjectName("fileName")', self.main)
        self.assertIn('label.setToolTip(relative)', self.main)

    def test_activities_wrap(self) -> None:
        self.assertIn('setObjectName("activityText")', self.main)
        self.assertIn('label.setWordWrap(True)', self.main)
        self.assertIn('item.setSizeHint(QSize(0, 54))', self.main)

    def test_horizontal_scroll_is_blocked(self) -> None:
        self.assertGreaterEqual(self.main.count('ScrollBarAlwaysOff'), 5)
        self.assertIn('QScrollBar:horizontal', self.theme)

    def test_ready_and_work_queues_remain_separate(self) -> None:
        self.assertIn('self.ready_table', self.main)
        self.assertIn('self.work_table', self.main)

    def test_paid_execution_is_not_added(self) -> None:
        self.assertNotIn('api.runware.ai', self.main)
        self.assertNotIn('RUNWARE_API_KEY', self.main)


if __name__ == "__main__":
    unittest.main()
