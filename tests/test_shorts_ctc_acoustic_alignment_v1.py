from pathlib import Path


def test_ctc_adapter_capability_boundary():
    from src.application import shorts_ctc_acoustic_alignment_v1 as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert '"provider_calls": 0' in source
    assert '"asr_text_authority": False' in source
    assert "TRANSFORMERS_OFFLINE" in source


def test_ctc_adapter_episode_agnostic():
    from src.application import shorts_ctc_acoustic_alignment_v1 as module

    source = Path(module.__file__).read_text(
        encoding="utf-8"
    ).lower()
    assert 'if episode_id == "episode-001' not in source
    assert 'if "adam" in' not in source
    assert "ep001" not in source


def test_native_timing_fast_path(tmp_path):
    from src.application.shorts_ctc_acoustic_alignment_v1 import (
        refine_candidate_caption_segments,
    )

    result = refine_candidate_caption_segments(
        source_video_path=tmp_path / "unused.mp4",
        episode_id="generic-episode",
        all_segments=[
            {
                "segment_id": "s1",
                "start_time": 1.0,
                "end_time": 3.0,
                "text": "نص عربي قصير",
            }
        ],
        candidate_start=1.0,
        candidate_end=3.0,
        source_video_sha256="a" * 64,
        source_audio_sha256="b" * 64,
        canonical_transcript_sha256="c" * 64,
        coarse_timing_sha256="d" * 64,
    )
    assert result.status == "READY"
    assert result.authority == "NATIVE_TRUSTED_TIMING"


def test_ctc_model_input_normalization_preserves_source_word():
    from types import SimpleNamespace

    from scripts.shorts_alignment.ctc_sidecar_v1 import tokenize_words

    seen = []

    class Tokenizer:
        unk_token_id = 99

        def __call__(self, text, add_special_tokens=False):
            seen.append(text)
            return SimpleNamespace(input_ids=[1, 2])

    lexical, target, _token_word = tokenize_words(
        "حركة واحدة الأمر يرى أن أُمر", Tokenizer(), blank_id=0, unk_id=99
    )
    assert not [item for item in lexical if item["status"] != "TARGET"]
    assert [item["original"] for item in lexical] == [
        "حركة",
        "واحدة",
        "الأمر",
        "يرى",
        "أن",
        "أُمر",
    ]
    assert seen == ["حركه", "واحده", "الامر", "يري", "ان", "امر"]
    assert target == [1, 2] * 6
