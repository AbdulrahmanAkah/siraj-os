import json

from src.application.siraj_luna_iconic_cinematic_brain_v5_1 import (
    detect_stage,
)


def test_explicit_system_stage_beats_later_next_stage_reference():
    request = {
        "input": [
            {
                "role": "system",
                "content": [{
                    "type": "input_text",
                    "text": (
                        "المرحلة: FINAL_SCRIPT.\n"
                        "لا تعد PASS إلا عندما يصبح النص جاهزاً للانتقال إلى "
                        "PRONUNCIATION_AND_PERFORMANCE_GATE."
                    ),
                }],
            }
        ]
    }
    assert detect_stage(request) == "FINAL_SCRIPT"


def test_json_context_stage_is_detected_exactly():
    context = {
        "stage": "FINAL_SCRIPT",
        "next_stage": "PRONUNCIATION_AND_PERFORMANCE_GATE",
    }
    request = {
        "input": [{
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": json.dumps(context),
            }],
        }]
    }
    assert detect_stage(request) == "FINAL_SCRIPT"


def test_actual_pronunciation_stage_detects_pronunciation():
    request = {
        "input": [{
            "role": "system",
            "content": [{
                "type": "input_text",
                "text": "المرحلة: PRONUNCIATION_AND_PERFORMANCE_GATE.",
            }],
        }]
    }
    assert detect_stage(request) == "PRONUNCIATION_AND_PERFORMANCE_GATE"
