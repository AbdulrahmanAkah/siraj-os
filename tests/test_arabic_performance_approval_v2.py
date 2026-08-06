from __future__ import annotations

from src.application.series_production_quality_v2 import (
    assert_tts_text_ready,
    diacritic_coverage,
)


def test_fully_vocalized_arabic_passes_linguistic_coverage() -> None:
    text = "كَانَ اللَّهُ، وَلَمْ يَكُنْ شَيْءٌ غَيْرَهُ."
    assert diacritic_coverage(text) >= 0.88
    assert_tts_text_ready(text)


def test_unvocalized_arabic_fails_linguistic_coverage() -> None:
    assert diacritic_coverage("كان الله ولم يكن شيء غيره") < 0.88
