from pathlib import Path

from src.application.luna_cinematic_prompt_director_v2 import (
    _extract_output_text,
    _parse_luna_output_payload,
    _read_json,
    build_luna_batch_request,
    PROMPT_PLAN_REL,
)


def test_output_extractor_ignores_reasoning_items() -> None:
    response = {
        "status": "completed",
        "output": [
            {
                "type": "reasoning",
                "content": [
                    {
                        "type": "reasoning_text",
                        "text": "not json",
                    }
                ],
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"batch_id":"B","items":[]}',
                    }
                ],
            },
        ],
    }
    assert _extract_output_text(response) == (
        '{"batch_id":"B","items":[]}'
    )


def test_parser_accepts_one_json_code_fence() -> None:
    payload = _parse_luna_output_payload(
        '```json\n{"batch_id":"B","items":[]}\n```'
    )
    assert payload["batch_id"] == "B"


def test_pending_requests_use_hardened_generation_settings() -> None:
    repo = Path.cwd()
    plan = _read_json(
        repo / "projects" / "episode-001-adam" / PROMPT_PLAN_REL
    )
    request = build_luna_batch_request(
        plan,
        "LUNA-PROMPT-BATCH-01",
    )
    assert request["reasoning"]["effort"] == "medium"
    assert request["text"]["verbosity"] == "low"
    assert request["max_output_tokens"] == 45000
