from __future__ import annotations

from pathlib import Path
import unittest


class SirajDesktopDashboardV13Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.main_window = (
            cls.repo_root
            / "src"
            / "presentation"
            / "desktop"
            / "main_window.py"
        ).read_text(encoding="utf-8-sig")
        cls.smoke = (
            cls.repo_root
            / "scripts"
            / "desktop"
            / "smoke_siraj_desktop_dashboard_v1_3.py"
        ).read_text(encoding="utf-8-sig")
        cls.audit = (
            cls.repo_root
            / "scripts"
            / "fast_track"
            / "audit_siraj_desktop_dashboard_v1_3.py"
        ).read_text(encoding="utf-8-sig")

    def test_release_marker_is_v1_3(self) -> None:
        self.assertIn(
            'RELEASE = "SIRAJ_DESKTOP_DASHBOARD_V1_3"',
            self.main_window,
        )
        self.assertIn(
            'setWindowTitle("سراج — إدارة إنتاج الحلقات — v1.3")',
            self.main_window,
        )

    def test_columns_have_independent_scroll_areas(self) -> None:
        self.assertIn(
            'setObjectName("mainColumnScroll")',
            self.main_window,
        )
        self.assertIn(
            'setObjectName("utilityColumnScroll")',
            self.main_window,
        )
        self.assertNotIn(
            'setObjectName("workspaceScroll")',
            self.main_window,
        )

    def test_queue_and_preview_have_non_collapsible_minimums(self) -> None:
        self.assertIn(
            "main_content.setMinimumHeight(720)",
            self.main_window,
        )
        self.assertIn(
            "utility_content.setMinimumHeight(760)",
            self.main_window,
        )
        self.assertIn(
            "queue.setMinimumHeight(240)",
            self.main_window,
        )
        self.assertIn(
            "panel.setMinimumHeight(315)",
            self.main_window,
        )

    def test_smoke_uses_effective_visible_geometry(self) -> None:
        self.assertIn("effective_visible_rect", self.smoke)
        self.assertIn(
            "MAIN_QUEUE_EFFECTIVE_VISIBILITY",
            self.smoke,
        )
        self.assertIn(
            "PREVIEW_EFFECTIVE_VISIBILITY",
            self.smoke,
        )

    def test_smoke_uses_pixel_visibility_assertions(self) -> None:
        self.assertIn("pixel_signature", self.smoke)
        self.assertIn("visible_pixel_signature", self.smoke)
        self.assertIn("PREVIEW_PIXEL_DIVERSITY", self.smoke)
        self.assertIn("QUEUE_PIXEL_DIVERSITY", self.smoke)
        self.assertIn("QUEUE_PIXEL_LUMINANCE_SPAN", self.smoke)
        self.assertIn("FONT_RENDERING_DEPENDENCY=NOT_REQUIRED", self.smoke)
        self.assertIn('queue_pixels["diversity"] >= 4', self.smoke)
        self.assertNotIn('queue_pixels["diversity"] >= 8', self.smoke)

    def test_audit_keeps_paid_execution_blocked(self) -> None:
        self.assertIn(
            '"paid_video_execution": "BLOCKED_IN_V1_3"',
            self.audit,
        )


if __name__ == "__main__":
    unittest.main()
