import pytest

from src.application.siraj_global_arabic_pronunciation_law_v5_3 import (
    FULL_PRONUNCIATION_DIACRITIZATION_REQUIRED,
    SELECTIVE_DIACRITIZATION_ONLY_ALLOWED,
    assert_no_bare_arabic_words,
    assert_pronunciation_layer_preserves_lexical_content,
    audit_spoken_arabic,
    lexical_skeleton,
)


def test_global_law_requires_full_pronunciation_diacritization():
    assert FULL_PRONUNCIATION_DIACRITIZATION_REQUIRED is True
    assert SELECTIVE_DIACRITIZATION_ONLY_ALLOWED is False


def test_bare_arabic_words_are_rejected():
    with pytest.raises(ValueError):
        assert_no_bare_arabic_words(
            "هذا نص غير مشكل كما يجب",
            "TEST",
        )


def test_vocalized_arabic_passes_no_bare_word_gate():
    assert_no_bare_arabic_words(
        "هَذَا نَصٌّ مُشَكَّلٌ لِلنُّطْقِ.",
        "TEST",
    )


def test_safe_diacritization_preserves_lexical_content():
    assert_pronunciation_layer_preserves_lexical_content(
        "ربنا ظلمنا أنفسنا",
        "رَبَّنَا ظَلَمْنَا أَنْفُسَنَا",
        "TEST",
    )


def test_madda_hamza_orthography_is_safe_for_lexical_comparison():
    assert lexical_skeleton("السوءات") == lexical_skeleton("السَّوْآتِ")


def test_true_rewrite_still_rejected():
    with pytest.raises(ValueError):
        assert_pronunciation_layer_preserves_lexical_content(
            "قال آدم",
            "قال آدم ثم تاب",
            "TEST",
        )


def test_word_initial_and_internal_madda_are_context_sensitive():
    assert lexical_skeleton("آدَمُ، عليه السلام.") == lexical_skeleton("ادم عليه السلام")
    assert lexical_skeleton("السوءات") == lexical_skeleton("السَّوْآتِ")
