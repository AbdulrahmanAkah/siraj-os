from pathlib import Path

from src.application.siraj_luna_story_architecture_iconic_review_v5_1 import (
    SUBSTAGE,
    _request,
)


def test_iconic_review_is_story_architecture_substage():
    assert SUBSTAGE == "STORY_ARCHITECTURE_ICONIC_CREATIVE_REVIEW"


def test_request_explicitly_uses_max_pro_and_no_output_cap():
    dummy_package = {"status": "PASS"}
    dummy_matrix = {"status": "PASS"}
    candidate = {"status": "PASS"}
    request = _request(
        dummy_package,
        dummy_matrix,
        candidate,
        1,
    )
    assert request["reasoning"]["effort"] == "max"
    assert request["reasoning"]["mode"] == "pro"
    assert "max_output_tokens" not in request


def test_review_runner_has_no_fixed_caps_or_pacing():
    text = Path(
        "src/application/"
        "siraj_luna_story_architecture_iconic_review_v5_1.py"
    ).read_text(encoding="utf-8-sig")
    assert "MAX_LUNA_CALLS" not in text
    assert "TOTAL_CAP_USD" not in text
    assert "time.sleep(" not in text
    assert "AUTOMATIC_PROVIDER_RETRIES=0" in text


def test_review_promotes_only_after_pass():
    text = Path(
        "src/application/"
        "siraj_luna_story_architecture_iconic_review_v5_1.py"
    ).read_text(encoding="utf-8-sig")
    pass_pos = text.find('if status == "PASS":')
    promote_pos = text.find(
        "_atomic_write(canonical_architecture_path, final)"
    )
    assert pass_pos >= 0
    assert promote_pos > pass_pos
