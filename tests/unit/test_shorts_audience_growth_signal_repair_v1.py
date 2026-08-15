from src.application.shorts_derivative_engine_v1 import ScoreDimension, _audience_growth_repaired_signal_values_v1

def d(v):
    return ScoreDimension(value=v, evidence=("fixture",), reason="fixture")

def scores(curiosity=0.8, visual=0.5, vertical=0.6, conversion=0.7):
    return {
        "HOOK_STRENGTH": d(1.0),
        "RETENTION_POTENTIAL": d(0.8),
        "NOVELTY": d(0.7),
        "EMOTIONAL_FORCE": d(0.4),
        "CURIOSITY": d(curiosity),
        "VISUAL_STRENGTH": d(visual),
        "VERTICAL_COMPATIBILITY": d(vertical),
        "LONGFORM_CONVERSION_POTENTIAL": d(conversion),
    }

def test_signal_repair_returns_four_bounded_dimensions():
    r = _audience_growth_repaired_signal_values_v1(scores(), context_score=0.2, spoiler=0.2, payoff=0.2, duration_seconds=35.0)
    assert set(r) == {"HOOK_STRENGTH","CURIOSITY","VERTICAL_COMPATIBILITY","LONGFORM_CONVERSION_POTENTIAL"}
    assert all(0.0 <= x <= 1.0 for x in r.values())

def test_open_loop_not_worse_than_closed_payoff():
    a = _audience_growth_repaired_signal_values_v1(scores(), context_score=0.2, spoiler=0.2, payoff=0.2, duration_seconds=35.0)
    b = _audience_growth_repaired_signal_values_v1(scores(), context_score=0.2, spoiler=0.8, payoff=0.9, duration_seconds=35.0)
    assert a["CURIOSITY"] >= b["CURIOSITY"]
    assert a["LONGFORM_CONVERSION_POTENTIAL"] >= b["LONGFORM_CONVERSION_POTENTIAL"]
