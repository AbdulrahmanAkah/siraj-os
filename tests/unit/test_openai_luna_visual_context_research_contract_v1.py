from __future__ import annotations

import json

from src.application.provider_model_contracts import (
    validate_openai_responses_payload,
)

from src.application.openai_luna_visual_context_research_contract_v1 import (
    build_openai_visual_research_request,
    extract_grounded_urls,
    parse_openai_visual_research_response,
)


def _provider_request():
    return {
        "source_sweep": {
            "required_source_classes": [
                "PRIMARY_OR_CANONICAL_TEXT",
                "ACADEMIC_SCHOLARLY_CONTEXT",
            ]
        },
        "dossier_requirements": {
            "required_dimensions": [
                "environment",
                "character_physical_context",
            ]
        },
        "episode_id": "episode-x",
        "context_id": "CTX",
    }


def test_openai_contract_enables_web_search_and_strict_schema():
    req = build_openai_visual_research_request(_provider_request())
    assert req["tools"] == [{"type": "web_search"}]
    assert req["text"]["format"]["strict"] is True
    assert "max_output_tokens" not in req
    validate_openai_responses_payload(req)
    schema = req["text"]["format"]["schema"]
    assert schema["properties"]["face_and_body_policy"]["properties"]["head_required"]["enum"] == [False]


def test_grounded_urls_come_from_search_sources_and_url_annotations():
    response = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "sources": [
                        {"type": "url", "url": "https://a.example"}
                    ],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "{}",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://b.example",
                            }
                        ],
                    }
                ],
            },
        ]
    }
    assert extract_grounded_urls(response) == (
        "https://a.example",
        "https://b.example",
    )


def test_parse_response_preserves_grounded_urls():
    payload = {"schema_version": "siraj-visual-context-dossier-v1"}
    response = {
        "id": "resp-1",
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "type": "search",
                    "sources": [
                        {"type": "url", "url": "https://a.example"}
                    ],
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload),
                        "annotations": [],
                    }
                ],
            },
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 3},
        },
    }
    result = parse_openai_visual_research_response(response)
    assert result.provider_response_id == "resp-1"
    assert result.web_search_calls == 1
    assert result.cited_urls == ("https://a.example",)


def _walk_schema_nodes(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_schema_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_schema_nodes(child)


def test_strict_schema_is_provider_compatible_before_paid_transport():
    req = build_openai_visual_research_request(_provider_request())
    schema = req["text"]["format"]["schema"]
    nodes = list(_walk_schema_nodes(schema))

    assert all("uniqueItems" not in node for node in nodes)
    assert all(
        node.get("additionalProperties") is False
        for node in nodes
        if node.get("type") == "object"
    )
    assert all(
        set(node.get("required", []))
        == set(node.get("properties", {}).keys())
        for node in nodes
        if node.get("type") == "object"
        and isinstance(node.get("properties"), dict)
    )

    unavailable = (
        schema["properties"]["research_exhaustion"]
        ["properties"]["unavailable_source_classes"]
    )
    assert unavailable["type"] == "array"
    assert unavailable["items"]["type"] == "object"
    assert unavailable["items"]["additionalProperties"] is False
    assert set(unavailable["items"]["required"]) == {
        "authority_class",
        "reason",
    }


def test_parse_response_normalises_wire_unavailable_sources_to_internal_mapping():
    payload = {
        "schema_version": "siraj-visual-context-dossier-v1",
        "research_exhaustion": {
            "unavailable_source_classes": [
                {
                    "authority_class": "ACADEMIC_SCHOLARLY_CONTEXT",
                    "reason": "No sufficiently specific source located.",
                }
            ]
        },
    }
    response = {
        "id": "resp-normalise-1",
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": json.dumps(payload),
                        "annotations": [],
                    }
                ],
            }
        ],
        "usage": {},
    }
    result = parse_openai_visual_research_response(response)
    assert result.payload["research_exhaustion"][
        "unavailable_source_classes"
    ] == {
        "ACADEMIC_SCHOLARLY_CONTEXT":
            "No sufficiently specific source located."
    }
