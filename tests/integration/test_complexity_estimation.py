from src.application.documentary_planning.models import DocumentaryPlan, DocumentarySection
from src.application.narrative_architecture.models import NarrativeBeat


def test_complexity_estimation_has_deterministic_low_medium_high_thresholds(
    narrative_architect,
    documentary_plan,
):
    low_plan = DocumentaryPlan(
        "plan_low",
        "Low",
        [DocumentarySection("introduction", "Introduction", ["event_1"])],
        ["event_1"],
    )
    medium_plan = DocumentaryPlan(
        "plan_medium",
        "Medium",
        [DocumentarySection(f"section_{index}", str(index), [f"event_{index}"]) for index in range(4)],
        [f"event_{index}" for index in range(4)],
    )
    medium_beats = [
        NarrativeBeat(f"beat_{index}", str(index), f"section_{index}", [f"event_{index}"])
        for index in range(4)
    ]

    assert narrative_architect.estimate_complexity(low_plan, []) == "LOW"
    assert narrative_architect.estimate_complexity(medium_plan, medium_beats) == "MEDIUM"
    assert narrative_architect.estimate_complexity(documentary_plan) == "HIGH"
