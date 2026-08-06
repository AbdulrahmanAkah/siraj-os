from __future__ import annotations

from src.application.luna_cinematic_prompt_director_v2 import (
    QUALITY_THRESHOLD,
    apply_certified_prompt_to_task,
    audit_prompt_text,
    prompt_output_schema,
)


def _certification(kind: str) -> dict:
    positive = (
        "A restrained premium cinematic wide shot of weathered basalt "
        "and wet clay, foreground fissures leading into a deep layered "
        "landscape, 32mm lens, low controlled dolly movement, amber rim "
        "light through suspended dust, physically coherent water flow, "
        "charcoal and ochre palette, tactile mineral texture, one clear "
        "visual focus, symbolic and non-literal, no visible supernatural "
        "being, stable geometry and continuity."
    )
    import hashlib
    negative = "no text, no logo, no morphing, no duplicate forms"
    return {
        "status": "PASS",
        "prompt_kind": kind,
        "final_score": QUALITY_THRESHOLD,
        "blocking_flags": [],
        "luna_response_id": "resp_test",
        "certified_positive_prompt_en": positive,
        "certified_negative_prompt_en": negative,
        "negative_prompt_delivery": "SEPARATE_PROVIDER_FIELD",
        "positive_prompt_sha256": hashlib.sha256(
            positive.encode("utf-8")
        ).hexdigest(),
        "negative_prompt_sha256": hashlib.sha256(
            negative.encode("utf-8")
        ).hexdigest(),
    }


def test_schema_requires_high_score_and_empty_blockers() -> None:
    schema = prompt_output_schema(3)
    item = schema["properties"]["items"]["items"]
    assert item["properties"]["final_score"]["minimum"] == 95
    assert item["properties"]["blocking_flags"]["maxItems"] == 0


def test_direct_religious_depiction_is_blocking() -> None:
    issues = audit_prompt_text(
        "A literal angel portrait with visible wings and human face, "
        "camera close-up, dramatic light, stone texture.",
        kind="IMAGE_GENERATION",
    )
    assert any(
        issue.code == "RELIGIOUS_DIRECT_DEPICTION_FORBIDDEN"
        for issue in issues
    )


def test_provider_task_is_replaced_by_certified_prompt() -> None:
    cert = _certification("IMAGE_GENERATION")
    task, proof = apply_certified_prompt_to_task(
        {"luna_prompt_certification_v2": cert},
        {
            "positivePrompt": "weak draft",
            "negativePrompt": "old",
        },
        "RUNWARE_IMAGE",
    )
    assert task["positivePrompt"] == cert[
        "certified_positive_prompt_en"
    ]
    assert task["negativePrompt"] == cert[
        "certified_negative_prompt_en"
    ]
    assert proof["luna_response_id"] == "resp_test"


def test_uncertified_provider_task_is_blocked() -> None:
    import pytest
    with pytest.raises(
        RuntimeError,
        match="LUNA_PROMPT_CERTIFICATION_REQUIRED",
    ):
        apply_certified_prompt_to_task(
            {},
            {"positivePrompt": "raw"},
            "RUNWARE_VIDEO",
        )
