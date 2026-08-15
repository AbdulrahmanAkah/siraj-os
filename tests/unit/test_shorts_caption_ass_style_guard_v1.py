from __future__ import annotations

from src.application.shorts_derivative_engine_v1 import _caption_ass_content


def _style_fields(ass: str) -> list[str]:
    line = next(line for line in ass.splitlines() if line.startswith("Style: Default,"))
    return line[len("Style: "):].split(",")


def test_caption_ass_uses_outline_border_not_opaque_box() -> None:
    plan = {
        "style": {"font_name": "Arial"},
        "placement": {"geometry": {"y": 0.64, "height": 0.16}},
        "cues": [
            {
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "display_lines": ["ومخلوقات سبقت الإنسان إلى الوجود."],
            }
        ],
    }
    ass = _caption_ass_content(plan)
    fields = _style_fields(ass)
    assert fields[15] == "1"
    assert fields[16] == "3"
    assert fields[17] == "1"


def test_caption_ass_preserves_ascii_space_between_arabic_words() -> None:
    phrase = "سبقت الإنسان"
    plan = {
        "style": {"font_name": "Arial"},
        "placement": {"geometry": {"y": 0.64, "height": 0.16}},
        "cues": [
            {
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "display_lines": [phrase],
            }
        ],
    }
    ass = _caption_ass_content(plan)
    dialogue = next(line for line in ass.splitlines() if line.startswith("Dialogue:"))
    assert phrase in dialogue
