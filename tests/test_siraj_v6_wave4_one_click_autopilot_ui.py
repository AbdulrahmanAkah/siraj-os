from src.application.siraj_one_click_autopilot_v6_4 import (
    BOOTSTRAP_ID,
    LUNA_STAGES,
    PAID_STAGES,
    stage_complete,
)
from src.application.siraj_wave4_source_hardening_v6_4 import (
    DOWNSTREAM_LUNA_STAGES,
    UPSTREAM_STAGES,
    expand_luna_paid_stage_set,
    patch_runware_credential_fallback,
)


def test_bootstrap_id_does_not_reserve_episode_number():
    assert not BOOTSTRAP_ID.startswith("episode-")


def test_paid_stage_contract():
    assert "FINAL_TTS" in PAID_STAGES
    assert "PROVIDER_EXECUTION" in PAID_STAGES
    assert "AUDIO_BOUND_STORYBOARD" in LUNA_STAGES
    assert "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA" in LUNA_STAGES


def test_ready_marker_is_terminal(tmp_path):
    episode = "episode-003-test"
    marker = (
        tmp_path
        / "projects"
        / episode
        / "orchestration/ready-for-final-human-review-v6-4.json"
    )
    marker.parent.mkdir(parents=True)
    marker.write_text(
        '{"status":"PASS"}',
        encoding="utf-8",
    )
    assert stage_complete(
        tmp_path,
        episode,
        "READY_FOR_FINAL_HUMAN_REVIEW",
    )


def _transport_fixture():
    return (
        'PAID_UPSTREAM_STAGES = {\n'
        '    "TOPIC_SELECTION",\n'
        '    "SOURCE_RESEARCH_FROM_ZERO",\n'
        '    "SOURCE_CLAIM_MATRIX",\n'
        '    "STORY_ARCHITECTURE",\n'
        '    "ICONIC_CINEMATIC_REVIEW",\n'
        '    "FINAL_SCRIPT",\n'
        '    "PRONUNCIATION_AND_PERFORMANCE_GATE",\n'
        '    "AUDIO_BOUND_STORYBOARD",\n'
        '    "LUNA_SEMANTIC_PROMPT_DIRECTION",\n'
        '    "NARRATION_VISUAL_ALIGNMENT_GATE",\n'
        '    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",\n'
        '}\n\n'
        'def authorize(stage):\n'
        '    if stage not in PAID_UPSTREAM_STAGES:\n'
        '        raise RuntimeError()\n\n'
        'def execute(stage):\n'
        '    if stage not in PAID_UPSTREAM_STAGES:\n'
        '        raise RuntimeError()\n'
    )


def test_separated_luna_stage_contract_is_idempotent(tmp_path):
    path = tmp_path / "transport.py"
    path.write_text(
        _transport_fixture(),
        encoding="utf-8",
    )

    first = expand_luna_paid_stage_set(path)
    second = expand_luna_paid_stage_set(path)
    third = expand_luna_paid_stage_set(path)
    text = path.read_text(encoding="utf-8")

    assert first == "SEPARATED_CONTRACT_INSTALLED"
    assert second == "ALREADY_SEPARATED_CONTRACT_NORMALIZED"
    assert third == "ALREADY_SEPARATED_CONTRACT_NORMALIZED"
    assert text.count(
        "if stage not in PAID_LUNA_STAGES:"
    ) == 2

    namespace = {}
    exec(
        compile(
            text,
            str(path),
            "exec",
        ),
        namespace,
    )
    assert namespace[
        "PAID_UPSTREAM_STAGES"
    ] == set(UPSTREAM_STAGES)
    assert namespace[
        "PAID_LUNA_DOWNSTREAM_STAGES"
    ] == set(DOWNSTREAM_LUNA_STAGES)
    assert namespace[
        "PAID_LUNA_STAGES"
    ] == (
        set(UPSTREAM_STAGES)
        | set(DOWNSTREAM_LUNA_STAGES)
    )


def test_normalizer_repairs_partially_mutated_contract(tmp_path):
    path = tmp_path / "transport.py"
    path.write_text(
        _transport_fixture(),
        encoding="utf-8",
    )
    expand_luna_paid_stage_set(path)

    # Simulate a stale partial mutation without touching guards.
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '    "AUDIO_BOUND_STORYBOARD",\n',
        "",
        1,
    )
    path.write_text(text, encoding="utf-8")

    result = expand_luna_paid_stage_set(path)
    assert result == "SEPARATED_CONTRACT_INSTALLED"

    namespace = {}
    repaired = path.read_text(encoding="utf-8")
    exec(
        compile(
            repaired,
            str(path),
            "exec",
        ),
        namespace,
    )
    assert namespace[
        "PAID_UPSTREAM_STAGES"
    ] == set(UPSTREAM_STAGES)
    assert namespace[
        "PAID_LUNA_DOWNSTREAM_STAGES"
    ] == set(DOWNSTREAM_LUNA_STAGES)


def test_runware_credential_patch(tmp_path):
    path = tmp_path / "provider.py"
    path.write_text(
        'import os\n'
        'class ProviderExecutionV621Error(RuntimeError): pass\n'
        'def _runware_key():\n'
        '    value = (\n'
        '        os.environ.get("RUNWARE_API_KEY", "").strip()\n'
        '        or os.environ.get("SIRAJ_RUNWARE_API_KEY", "").strip()\n'
        '    )\n'
        '    if not value:\n'
        '        raise ProviderExecutionV621Error("RUNWARE_API_KEY_REQUIRED")\n'
        '    return value\n'
        '\n'
        'def next_function():\n'
        '    return 1\n',
        encoding="utf-8",
    )
    assert (
        patch_runware_credential_fallback(path)
        == "PATCHED"
    )
    assert (
        patch_runware_credential_fallback(path)
        == "ALREADY_PATCHED"
    )
    text = path.read_text(encoding="utf-8")
    assert "read_runware_api_key" in text
    compile(
        text,
        str(path),
        "exec",
    )
