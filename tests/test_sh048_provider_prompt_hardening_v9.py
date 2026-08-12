from __future__ import annotations

from src.application import desktop_media_execution_v1 as media


def _task():
    return {
        "taskType": "videoInference",
        "model": "google:veo@3.1-lite",
        "positivePrompt": (
            "Old reflections prompt with the exact Arabic word «أنا». "
            "The word enlarges in successive reflections. "
            "Stable camera motion."
        ),
        "negativePrompt": (
            "Iblis, demon, humanoid, face, body, text, watermark"
        ),
        "providerSettings": {
            "google": {
                "generateAudio": False,
                "personGeneration": "dont_allow",
            }
        },
    }


def test_c03_c04_use_hardened_nonfigurative_provider_prompts():
    prompts = {}
    for queue_id in ("VID-SH-048-C03", "VID-SH-048-C04"):
        task, cert = media._siraj_prepare_veo_final_submission_v1(
            _task(),
            {"status": "PASS"},
            queue_id,
        )
        prompt = task["positivePrompt"]
        tokens = media._siraj_veo_prompt_tokens_v2(prompt)
        prompts[queue_id] = prompt

        assert not media._SIRAJ_ARABIC_CHAR_RE_V3.search(prompt)
        assert not (tokens & media._SIRAJ_VEO_VISIBLE_TEXT_TOKENS_V3)
        assert not (
            tokens
            & media._SIRAJ_VEO_PROVIDER_BLOCKED_PEOPLE_FACE_TOKENS_V2
        )
        assert "reflection" not in tokens
        assert "reflections" not in tokens
        assert "ego" not in tokens
        assert "obsidian" in tokens
        assert task["providerSettings"]["google"]["personGeneration"] == (
            "dont_allow"
        )
        assert cert is not None
        assert cert["deterministic_text_overlay_required"] is True
        assert cert["provider_prompt_override_version"] == (
            "SIRAJ_SH048_NONFIGURATIVE_GEOMETRIC_V1"
        )

    assert prompts["VID-SH-048-C03"] != prompts["VID-SH-048-C04"]
