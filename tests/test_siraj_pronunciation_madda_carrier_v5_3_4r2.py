from src.application.siraj_global_arabic_pronunciation_law_v5_3 import (
    assert_minimum_full_diacritization,
)
from src.application.siraj_luna_pronunciation_performance_gate_v5_2 import (
    _v53_alias_collapse,
)


def test_madda_is_self_vocalized_pronunciation_carrier():
    for token in (
        "آدَمُ",
        "لِآدَمَ",
        "الْآخَرِ",
        "الْقُرْآنُ",
        "الْآنَ",
    ):
        assert_minimum_full_diacritization(token, token)


def test_ta_ha_alias_is_context_scoped():
    value = _v53_alias_collapse(
        "وفي سورة طه ترد العبارة",
        "وَفِي سُورَةِ طَا هَا تَرِدُ الْعِبَارَةُ",
    )
    assert "طه" in value
    assert _v53_alias_collapse("نص آخر", "طَا هَا") == "طَا هَا"
