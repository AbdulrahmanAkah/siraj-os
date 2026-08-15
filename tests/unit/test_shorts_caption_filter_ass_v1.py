from __future__ import annotations

from pathlib import Path

from src.application.shorts_derivative_engine_v1 import _caption_filter_for_ass


def test_burned_caption_filter_uses_ass_filter_for_ass_input() -> None:
    path = Path(r"C:\Temp\caption test.ass")
    actual = _caption_filter_for_ass(path)

    assert actual.startswith("ass=filename='")
    assert "subtitles=" not in actual
    assert "charenc=" not in actual
    assert r"C\:/Temp/caption test.ass" in actual


def test_burned_caption_filter_escapes_single_quote() -> None:
    path = Path(r"C:\Temp\caption's test.ass")
    actual = _caption_filter_for_ass(path)

    assert r"caption\'s test.ass" in actual
