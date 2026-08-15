from __future__ import annotations

from dataclasses import replace

import pytest

from src.application.shorts_burned_caption_engine_v1 import (
    CAPTION_MODE,
    CAPTIONS_DEFAULT_ENABLED,
    CaptionBlockedError,
    CaptionTranscript,
    ShortsBurnedCaptionEngine,
    ShortEditPlan,
    TIMING_AUTHORITY_PHRASE,
    TIMING_AUTHORITY_WORD,
    build_caption_plan,
    build_caption_cache_key,
    build_render_contract,
    choose_caption_placement,
    qa_caption_plan,
    remap_cues_to_short_timebase,
    validate_caption_scope,
)


TRANSCRIPT_HASH = "a" * 64
TIMING_HASH = "b" * 64
VIDEO_HASH = "c" * 64
AUDIO_HASH = "d" * 64


def _transcript(
    segments: list[dict[str, object]],
    *,
    provenance: str = "CANONICAL_TIMED_TRANSCRIPT",
) -> CaptionTranscript:
    return CaptionTranscript.from_segments(
        segments,
        episode_id="EP-TEST-001",
        canonical_transcript_sha256=TRANSCRIPT_HASH,
        timing_source_sha256=TIMING_HASH,
        source_video_sha256=VIDEO_HASH,
        source_audio_sha256=AUDIO_HASH,
        text_provenance=provenance,
        duration_seconds=30.0,
    )


def _edit_plan(
    ranges: list[dict[str, object]],
    *,
    duration: float | None = None,
    short_id: str = "SHORT-001",
) -> ShortEditPlan:
    return ShortEditPlan.from_mapping(
        {
            "short_id": short_id,
            "source_episode_id": "EP-TEST-001",
            "ranges": ranges,
            "short_duration_seconds": duration,
            "source_video_sha256": VIDEO_HASH,
            "source_audio_sha256": AUDIO_HASH,
        }
    )


def _basic_plan(*, subject_regions: list[dict[str, object]] | None = None):
    transcript = _transcript(
        [
            {
                "segment_id": "S1",
                "start_seconds": 10.0,
                "end_seconds": 12.0,
                "text": "هذا نص عربي واضح.",
            }
        ]
    )
    edit = _edit_plan(
        [{"range_id": "R1", "source_start": 10.0, "source_end": 12.0, "short_start": 0.0}],
        duration=2.0,
    )
    return build_caption_plan(transcript, edit, subject_regions=subject_regions)


def test_short_plan_defaults_on_and_is_narration_only() -> None:
    plan = _basic_plan()
    assert plan.captions_enabled is True
    assert plan.default_enabled is CAPTIONS_DEFAULT_ENABLED
    assert plan.caption_mode == CAPTION_MODE
    assert plan.text_authority == "NARRATION_ONLY"
    assert plan.timebase == "SHORT_LOCAL_TIMEBASE"
    assert plan.cues[0].text == "هذا نص عربي واضح."
    assert plan.cues[0].direction == "RTL"


def test_mixed_arabic_english_and_numbers_are_marked_rtl_mixed() -> None:
    transcript = _transcript(
        [
            {
                "segment_id": "S1",
                "start_seconds": 0.0,
                "end_seconds": 2.0,
                "text": "المرحلة V1 رقم 2.",
            }
        ]
    )
    plan = build_caption_plan(
        transcript,
        _edit_plan(
            [{"source_start": 0.0, "source_end": 2.0, "short_start": 0.0}],
            duration=2.0,
        ),
    )
    assert plan.cues[0].direction == "RTL_MIXED"
    assert plan.render_contract["rtl"] is True
    assert plan.render_contract["mixed_direction_strategy"]


def test_longform_burned_caption_scope_is_blocked() -> None:
    with pytest.raises(CaptionBlockedError, match="LONGFORM_BURNED_CAPTIONS_FORBIDDEN"):
        validate_caption_scope(
            "LONGFORM",
            burned_captions=True,
            on_screen_subtitles=False,
        )
    with pytest.raises(CaptionBlockedError, match="LONGFORM_BURNED_CAPTIONS_FORBIDDEN"):
        validate_caption_scope(
            "LONGFORM",
            burned_captions=False,
            on_screen_subtitles=True,
        )


def test_shorts_on_screen_subtitle_mode_is_not_a_bypass() -> None:
    with pytest.raises(CaptionBlockedError, match="SHORTS_ON_SCREEN_SUBTITLES_FORBIDDEN"):
        build_caption_plan(
            _transcript(
                [{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}]
            ),
            _edit_plan(
                [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
                duration=1.0,
            ),
            on_screen_subtitles=True,
        )


def test_non_narration_provenance_is_rejected() -> None:
    with pytest.raises(CaptionBlockedError, match="CAPTION_TEXT_AUTHORITY_FORBIDDEN"):
        _basic_plan_from_transcript_provenance("INVENTED_HOOK")


def _basic_plan_from_transcript_provenance(provenance: str):
    return build_caption_plan(
        _transcript(
            [{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}],
            provenance=provenance,
        ),
        _edit_plan(
            [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
            duration=1.0,
        ),
    )


def test_missing_hash_binding_is_fail_closed() -> None:
    with pytest.raises(CaptionBlockedError, match="CAPTION_HASH_BINDING_REQUIRED"):
        build_caption_plan(
            [{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}],
            _edit_plan(
                [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
                duration=1.0,
            ),
        )


def test_coarse_sentence_timing_blocks_instead_of_guessing() -> None:
    with pytest.raises(CaptionBlockedError, match="CAPTION_TIMING_INSUFFICIENT"):
        build_caption_plan(
            _transcript(
                [
                    {
                        "segment_id": "COARSE",
                        "start_seconds": 0.0,
                        "end_seconds": 30.0,
                        "text": "هذه جملة زمنها طويل ولا توجد حدود أدق يمكن الوثوق بها.",
                    }
                ]
            ),
            _edit_plan(
                [{"source_start": 0.0, "source_end": 30.0, "short_start": 0.0}],
                duration=30.0,
            ),
        )


def test_phrase_boundaries_are_used_when_available() -> None:
    plan = build_caption_plan(
        _transcript(
            [
                {
                    "segment_id": "S1",
                    "start_seconds": 0.0,
                    "end_seconds": 4.0,
                    "text": "بدأ الأمر ثم ظهر الدليل.",
                    "phrase_boundaries": [
                        {"start_seconds": 0.0, "end_seconds": 1.5, "text": "بدأ الأمر"},
                        {"start_seconds": 1.5, "end_seconds": 4.0, "text": "ثم ظهر الدليل."},
                    ],
                }
            ]
        ),
        _edit_plan(
            [{"source_start": 0.0, "source_end": 4.0, "short_start": 0.0}],
            duration=4.0,
        ),
    )
    assert plan.timing_authority == TIMING_AUTHORITY_PHRASE
    assert len(plan.cues) == 2
    assert [cue.text for cue in plan.cues] == ["بدأ الأمر", "ثم ظهر الدليل."]


def test_legacy_canonical_document_with_mapping_provenance_is_accepted() -> None:
    transcript_document = {
        "schema_version": "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1",
        "episode_id": "EP-TEST-001",
        "timing_source_type": "LEGACY_ABSOLUTE_TTS_TIMELINE",
        "timing_source_sha256": TIMING_HASH,
        "canonical_transcript_sha256": TRANSCRIPT_HASH,
        "source_video_sha256": VIDEO_HASH,
        "source_audio_sha256": AUDIO_HASH,
        "provenance": {"authority_level": 3, "bound_hashes": {"audio": AUDIO_HASH}},
        "segments": [
            {
                "segment_id": "S1",
                "start_seconds": 2.0,
                "end_seconds": 3.0,
                "text": "نص من الدليل.",
            }
        ],
    }
    plan = build_caption_plan(
        transcript_document,
        _edit_plan(
            [{"source_start": 2.0, "source_end": 3.0, "short_start": 0.0}],
            duration=1.0,
        ),
    )
    assert plan.text_authority == "NARRATION_ONLY"
    assert plan.cues[0].text == "نص من الدليل."


def test_transcript_and_edit_episode_binding_must_match() -> None:
    transcript = _transcript([{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}])
    edit = ShortEditPlan.from_mapping(
        {
            "short_id": "SHORT-001",
            "source_episode_id": "OTHER-EPISODE",
            "ranges": [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
            "short_duration_seconds": 1.0,
            "source_video_sha256": VIDEO_HASH,
            "source_audio_sha256": AUDIO_HASH,
        }
    )
    with pytest.raises(CaptionBlockedError, match="CAPTION_EPISODE_BINDING_MISMATCH"):
        build_caption_plan(transcript, edit)


def test_word_boundaries_are_grouped_without_proportional_timing() -> None:
    plan = build_caption_plan(
        _transcript(
            [
                {
                    "segment_id": "S1",
                    "start_seconds": 0.0,
                    "end_seconds": 2.0,
                    "text": "هذا نص قصير.",
                    "word_boundaries": [
                        {"start_seconds": 0.0, "end_seconds": 0.4, "text": "هذا"},
                        {"start_seconds": 0.4, "end_seconds": 1.0, "text": "نص"},
                        {"start_seconds": 1.0, "end_seconds": 2.0, "text": "قصير."},
                    ],
                }
            ]
        ),
        _edit_plan(
            [{"source_start": 0.0, "source_end": 2.0, "short_start": 0.0}],
            duration=2.0,
        ),
    )
    assert plan.timing_authority == TIMING_AUTHORITY_WORD
    assert len(plan.cues) == 1
    assert plan.cues[0].text == "هذا نص قصير."
    assert plan.render_contract["karaoke"] is False


def test_long_word_timed_arabic_phrase_splits_at_trusted_boundaries() -> None:
    words = [
        "هذه",
        "عبارة",
        "عربية",
        "طويلة",
        "تحتاج",
        "إلى",
        "عدة",
        "مقاطع",
        "زمنية",
        "متتابعة",
        "دون",
        "حذف.",
    ]
    text = " ".join(words)
    boundaries = [
        {
            "start_seconds": index * 0.2,
            "end_seconds": (index + 1) * 0.2,
            "text": word,
        }
        for index, word in enumerate(words)
    ]
    plan = build_caption_plan(
        _transcript(
            [
                {
                    "segment_id": "LONG-WORD-TIMED",
                    "start_seconds": 0.0,
                    "end_seconds": 2.4,
                    "text": text,
                    "word_boundaries": boundaries,
                }
            ]
        ),
        _edit_plan(
            [{"source_start": 0.0, "source_end": 2.4, "short_start": 0.0}],
            duration=2.4,
        ),
    )

    assert len(plan.cues) >= 2
    assert " ".join(cue.text for cue in plan.cues) == text
    assert all(cue.line_count <= 2 for cue in plan.cues)
    assert all(
        current.end_seconds <= following.start_seconds + 1e-6
        for current, following in zip(plan.cues, plan.cues[1:])
    )
    assert plan.cues[0].start_seconds == 0.0
    assert plan.cues[-1].end_seconds == pytest.approx(2.4)


def test_single_cut_maps_to_short_local_timebase() -> None:
    plan = _basic_plan()
    cue = plan.cues[0]
    assert cue.start_seconds == pytest.approx(0.0)
    assert cue.end_seconds == pytest.approx(2.0)
    assert cue.source_start_seconds == pytest.approx(10.0)
    assert cue.source_range_id == "R1"


def test_multi_cut_and_reorder_use_explicit_output_order() -> None:
    transcript = _transcript(
        [
            {"segment_id": "A", "start_seconds": 10.0, "end_seconds": 11.0, "text": "المقطع الأول."},
            {"segment_id": "B", "start_seconds": 20.0, "end_seconds": 21.0, "text": "المقطع الثاني."},
        ]
    )
    plan = build_caption_plan(
        transcript,
        _edit_plan(
            [
                {"range_id": "R-B", "source_start": 20.0, "source_end": 21.0, "short_start": 0.0},
                {"range_id": "R-A", "source_start": 10.0, "source_end": 11.0, "short_start": 1.0},
            ],
            duration=2.0,
        ),
    )
    assert [cue.text for cue in plan.cues] == ["المقطع الثاني.", "المقطع الأول."]
    assert [cue.start_seconds for cue in plan.cues] == [0.0, 1.0]


def test_explicit_retime_mapping_is_affine_not_guessed() -> None:
    transcript = _transcript(
        [{"start_seconds": 10.0, "end_seconds": 12.0, "text": "نص قابل للتحويل."}]
    )
    plan = build_caption_plan(
        transcript,
        _edit_plan(
            [
                {
                    "source_start": 10.0,
                    "source_end": 12.0,
                    "short_start": 0.0,
                    "short_end": 1.0,
                }
            ],
            duration=1.0,
        ),
    )
    assert plan.cues[0].end_seconds == pytest.approx(1.0)


def test_cut_through_caption_is_rejected() -> None:
    transcript = _transcript(
        [{"start_seconds": 10.0, "end_seconds": 12.0, "text": "جملة لا تقطع عشوائيا."}]
    )
    with pytest.raises(CaptionBlockedError, match="CUT_THROUGH_CAPTION"):
        build_caption_plan(
            transcript,
            _edit_plan(
                [{"source_start": 11.0, "source_end": 12.0, "short_start": 0.0}],
                duration=1.0,
            ),
        )


def test_subject_collision_uses_allowed_fallback_region() -> None:
    placement = choose_caption_placement(
        [{"id": "subject-low", "x": 0.0, "y": 0.64, "width": 0.84, "height": 0.16}]
    )
    assert placement["region_id"] == "MIDDLE_CENTER"
    assert placement["alternative_attempted"] is True


def test_no_safe_placement_blocks() -> None:
    occupied = [
        {"id": "lower", "x": 0.0, "y": 0.64, "width": 0.84, "height": 0.16},
        {"id": "middle", "x": 0.0, "y": 0.42, "width": 0.84, "height": 0.16},
        {"id": "upper", "x": 0.0, "y": 0.24, "width": 0.84, "height": 0.16},
    ]
    with pytest.raises(CaptionBlockedError, match="CAPTION_PLACEMENT_BLOCKED"):
        choose_caption_placement(occupied)


def test_failed_visual_policy_is_blocked_when_explicitly_supplied() -> None:
    with pytest.raises(CaptionBlockedError, match="CAPTION_CANNOT_SALVAGE_VISUAL_FAIL"):
        build_caption_plan(
            _transcript([{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}]),
            _edit_plan(
                [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
                duration=1.0,
            ),
            visual_policy_status="FAIL_FORBIDDEN_FACE",
        )


def test_render_contract_is_offline_and_never_invokes_render() -> None:
    contract = build_render_contract(_basic_plan())
    assert contract["frame"] == {"width": 1080, "height": 1920, "aspect_ratio": "9:16"}
    assert contract["provider_calls"] == 0
    assert contract["network_calls"] == 0
    assert contract["paid_calls"] == 0
    assert contract["render_invoked"] is False


def test_qa_detects_stale_transcript_and_edit_plan_hashes() -> None:
    plan = _basic_plan()
    result = qa_caption_plan(
        plan,
        expected_canonical_transcript_sha256="e" * 64,
        expected_edit_plan_sha256="f" * 64,
    )
    assert result.status == "BLOCKED"
    assert "STALE_TRANSCRIPT_HASH" in result.failures
    assert "STALE_EDIT_PLAN_HASH" in result.failures


def test_qa_detects_cue_beyond_short_duration() -> None:
    plan = _basic_plan()
    cue = replace(plan.cues[0], end_seconds=3.0)
    mutated = replace(plan, cues=(cue,))
    result = qa_caption_plan(mutated)
    assert result.status == "BLOCKED"
    assert any(item.startswith("CAPTION_CUE_BEYOND_DURATION") for item in result.failures)


def test_qa_detects_overlap() -> None:
    transcript = _transcript(
        [
            {"start_seconds": 0.0, "end_seconds": 1.0, "text": "الأول."},
            {"start_seconds": 1.0, "end_seconds": 2.0, "text": "الثاني."},
        ]
    )
    plan = build_caption_plan(
        transcript,
        _edit_plan(
            [{"source_start": 0.0, "source_end": 2.0, "short_start": 0.0}],
            duration=2.0,
        ),
    )
    mutated = replace(
        plan,
        cues=(plan.cues[0], replace(plan.cues[1], start_seconds=0.5)),
    )
    result = qa_caption_plan(mutated)
    assert result.status == "BLOCKED"


def test_two_line_limit_is_enforced_without_rewriting_text() -> None:
    text = "كلمة طويلة " * 10
    with pytest.raises(CaptionBlockedError, match="CAPTION_MAX_LINES_EXCEEDED"):
        build_caption_plan(
            _transcript(
                [
                    {
                        "start_seconds": 0.0,
                        "end_seconds": 2.0,
                        "text": text,
                        "phrase_boundaries": [
                            {"start_seconds": 0.0, "end_seconds": 2.0, "text": text}
                        ],
                    }
                ]
            ),
            _edit_plan(
                [{"source_start": 0.0, "source_end": 2.0, "short_start": 0.0}],
                duration=2.0,
            ),
        )


def test_invalid_transcript_overlap_is_blocked() -> None:
    with pytest.raises(CaptionBlockedError, match="CAPTION_TIMING_INVALID"):
        build_caption_plan(
            _transcript(
                [
                    {"start_seconds": 0.0, "end_seconds": 2.0, "text": "الأول."},
                    {"start_seconds": 1.0, "end_seconds": 3.0, "text": "الثاني."},
                ]
            ),
            _edit_plan(
                [{"source_start": 0.0, "source_end": 3.0, "short_start": 0.0}],
                duration=3.0,
            ),
        )


def test_remap_mapping_api_accepts_plain_cues() -> None:
    edit = _edit_plan(
        [{"source_start": 120.0, "source_end": 126.0, "short_start": 2.0}],
        duration=8.0,
    )
    result = remap_cues_to_short_timebase(
        [
            {
                "cue_id": "C1",
                "segment_id": "S1",
                "start": 122.0,
                "end": 124.0,
                "text": "النص.",
                "timing_authority": "SENTENCE_BOUNDARY",
            }
        ],
        edit,
    )
    assert result[0].start_seconds == pytest.approx(4.0)
    assert result[0].end_seconds == pytest.approx(6.0)


def test_edit_plan_hash_is_stable_and_bound() -> None:
    first = _edit_plan(
        [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
        duration=1.0,
    )
    second = _edit_plan(
        [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
        duration=1.0,
    )
    assert first.edit_plan_sha256 == second.edit_plan_sha256


def test_integrator_facade_exposes_pure_plan_validation_and_scope() -> None:
    facade = ShortsBurnedCaptionEngine()
    plan = facade.build_caption_plan(
        _transcript([{"start_seconds": 0.0, "end_seconds": 1.0, "text": "نص."}]),
        _edit_plan(
            [{"source_start": 0.0, "source_end": 1.0, "short_start": 0.0}],
            duration=1.0,
        ),
    )
    assert facade.validate_caption_plan(plan).passed is True
    facade.validate_scope(
        "SHORTS",
        burned_captions=True,
        on_screen_subtitles=False,
    )
    with pytest.raises(CaptionBlockedError, match="LONGFORM_BURNED_CAPTIONS_FORBIDDEN"):
        facade.validate_scope(
            "LONGFORM",
            burned_captions=True,
            on_screen_subtitles=False,
        )


def test_caption_cache_key_changes_when_any_upstream_hash_changes() -> None:
    kwargs = {
        "episode_id": "EP-TEST-001",
        "short_id": "SHORT-001",
        "source_video_sha256": VIDEO_HASH,
        "source_audio_sha256": AUDIO_HASH,
        "canonical_transcript_sha256": TRANSCRIPT_HASH,
        "timing_source_sha256": TIMING_HASH,
        "edit_plan_sha256": "e" * 64,
    }
    first = build_caption_cache_key(**kwargs)
    second = build_caption_cache_key(**{**kwargs, "edit_plan_sha256": "f" * 64})
    facade_key = ShortsBurnedCaptionEngine().build_caption_cache_key(**kwargs)
    assert first != second
    assert facade_key == first
