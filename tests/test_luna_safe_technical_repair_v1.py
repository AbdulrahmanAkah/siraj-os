from pathlib import Path

from src.application.luna_safe_technical_repair_v1 import (
    MAX_CHANGED_LINES_PER_REPAIR,
    MAX_FILES_PER_REPAIR,
    MAX_REPAIR_CALLS_PER_PRODUCTION_RUN,
    SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD,
    _classify_without_provider,
    _is_allowed_path,
)


def test_safe_repair_limits_are_strict() -> None:
    assert SAFE_TECHNICAL_REPAIR_TOTAL_RESERVE_USD == 0.15
    assert MAX_REPAIR_CALLS_PER_PRODUCTION_RUN == 3
    assert MAX_FILES_PER_REPAIR == 5
    assert MAX_CHANGED_LINES_PER_REPAIR == 200


def test_provider_and_authorization_errors_require_user_action() -> None:
    assert _classify_without_provider(
        "PROMPT_BATCH_ALREADY_LOCKED_NO_AUTOMATIC_RETRY",
        "",
    ) == "USER_ACTION_REQUIRED"
    assert _classify_without_provider(
        "OPENAI_API_KEY_REQUIRED",
        "",
    ) == "USER_ACTION_REQUIRED"
    assert _classify_without_provider(
        "NETWORK_OR_PROVIDER_RESULT_UNKNOWN",
        "",
    ) == "USER_ACTION_REQUIRED"


def test_local_python_failures_are_candidates() -> None:
    assert _classify_without_provider(
        "KeyError: field",
        'File "src/application/example.py", line 12',
    ) == "SAFE_REPAIR_CANDIDATE"
    assert _classify_without_provider(
        "SyntaxError: unmatched ')'",
        'File "src/application/example.py", line 12',
    ) == "SAFE_REPAIR_CANDIDATE"


def test_path_policy_blocks_production_and_core_guard_files() -> None:
    assert _is_allowed_path(
        Path("src/application/example.py")
    ) is True
    assert _is_allowed_path(
        Path("projects/episode-001-adam/orchestration/state.json")
    ) is False
    assert _is_allowed_path(
        Path("src/application/luna_safe_technical_repair_v1.py")
    ) is False
