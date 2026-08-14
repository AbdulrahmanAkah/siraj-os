"""Offline integration contract for Shorts conversion and burned narration captions.

This file is intentionally owned by the integration/evidence workstream.  It
does not render media and it never invokes a provider, network, paid path, or
publication path.  The public contracts exercised here are the boundary that
the conversion director and caption engine must expose to the rest of SIRAJ.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

import pytest

from src.application.shorts_derivative_engine_v1 import HashBoundCache, capability_boundary_evidence


REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = REPO_ROOT / "reports" / "shorts-conversion-captions-v1"
CONVERSION_MODULE = "src.application.shorts_conversion_director_v1"
CAPTION_MODULE = "src.application.shorts_burned_caption_engine_v1"

SAFETY_KEYS = (
    "provider_calls",
    "paid_calls",
    "network_production_calls",
    "new_tts",
    "new_narration",
    "new_visual_generation",
    "production_render",
    "paid_render",
    "publication",
    "youtube_api",
    "retry",
    "resubmission",
)

REQUIRED_CONVERSION_FIELDS = (
    "SHORT_QUALITY",
    "HOOK_STRENGTH",
    "RETENTION_POTENTIAL",
    "STANDALONE_VALUE",
    "OPEN_LOOP_STRENGTH",
    "LONGFORM_CONVERSION_SCORE",
    "SPOILER_COST",
    "PAYOFF_DISCLOSURE_LEVEL",
    "PAYOFF_OVERDISCLOSURE",
    "WITHHELD_PAYOFF_SUMMARY",
    "CONVERSION_BRIDGE_STATUS",
    "CONVERSION_BRIDGE_REASON",
    "SOURCE_EPISODE_ID",
)

REQUIRED_REPORTS = (
    "SHORTS_CAPTION_POLICY_AMENDMENT_V1.json",
    "SHORTS_CONVERSION_DIRECTOR_AUDIT_V1.json",
    "SHORTS_CONVERSION_DIRECTOR_CERTIFICATION_V1.json",
    "SHORTS_BURNED_CAPTION_ENGINE_CERTIFICATION_V1.json",
    "SHORTS_CAPTION_VISUAL_QA_V1.json",
    "SHORTS_CAPTION_TIMING_AUTHORITY_V1.json",
    "SIRAJ_PRODUCTION_READINESS_REBIND_AFTER_SHORTS_CAPTION_POLICY_V1.json",
    "SIRAJ_SHORTS_CONVERSION_CAPTIONS_FINAL_CERTIFICATION_V1.json",
)


def _load_module(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        pytest.fail(f"REQUIRED_OFFLINE_MODULE_MISSING:{name}:{exc}")


def _as_mapping(value: Any, *, context: str) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        converted = to_dict()
        if isinstance(converted, Mapping):
            return converted
    pytest.fail(f"PUBLIC_CONTRACT_MUST_BE_MAPPING:{context}")


def _component(module: Any, class_name: str) -> Any:
    component_type = getattr(module, class_name, None)
    if component_type is None:
        pytest.fail(f"PUBLIC_COMPONENT_MISSING:{module.__name__}:{class_name}")
    parameters = inspect.signature(component_type).parameters
    if "repo_root" in parameters:
        return component_type(repo_root=REPO_ROOT)
    if "root" in parameters:
        return component_type(root=REPO_ROOT)
    return component_type()


def _public_callable(module: Any, component_name: str, names: tuple[str, ...]) -> Callable[..., Any]:
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    component = _component(module, component_name)
    for name in names:
        candidate = getattr(component, name, None)
        if callable(candidate):
            return candidate
    pytest.fail(f"PUBLIC_OPERATION_MISSING:{module.__name__}:{','.join(names)}")


def _conversion_assess(candidate: Mapping[str, Any]) -> Mapping[str, Any]:
    module = _load_module(CONVERSION_MODULE)
    operation = _public_callable(
        module,
        "ConversionDirector",
        ("evaluate_candidate", "score_candidate"),
    )
    return _as_mapping(operation(candidate, source_episode_id="EP001"), context="conversion_assessment")


def _conversion_portfolio(candidates: list[Mapping[str, Any]]) -> Mapping[str, Any]:
    module = _load_module(CONVERSION_MODULE)
    operation = _public_callable(
        module,
        "ConversionDirector",
        ("account_portfolio",),
    )
    return _as_mapping(
        operation(
            candidates,
            source_episode_id="EP001",
            max_cumulative_spoiler_cost=0.80,
            max_cumulative_payoff_coverage=0.80,
        ),
        context="conversion_portfolio",
    )


def _caption_module() -> Any:
    return _load_module(CAPTION_MODULE)


def _caption_build(transcript: Mapping[str, Any], edit_plan: Mapping[str, Any]) -> Any:
    operation = getattr(_caption_module(), "build_caption_plan", None)
    if not callable(operation):
        pytest.fail("PUBLIC_OPERATION_MISSING:caption_module:build_caption_plan")
    return operation(
        transcript=transcript,
        edit_plan=edit_plan,
        scope="SHORT_DERIVATIVE",
        captions_enabled=True,
        visual_policy_status="PASS",
    )


def _caption_validate(
    plan: Any,
    transcript: Mapping[str, Any],
    edit_plan: Mapping[str, Any],
    *,
    expected_canonical_transcript_sha256: str | None = None,
    expected_timing_source_sha256: str | None = None,
) -> Mapping[str, Any]:
    operation = getattr(_caption_module(), "qa_caption_plan", None)
    if not callable(operation):
        pytest.fail("PUBLIC_OPERATION_MISSING:caption_module:qa_caption_plan")
    edit_module = _caption_module()
    edit_hash = edit_module.ShortEditPlan.from_mapping(edit_plan).edit_plan_sha256
    return _as_mapping(
        operation(
            plan,
            expected_canonical_transcript_sha256=expected_canonical_transcript_sha256 or transcript["canonical_transcript_sha256"],
            expected_timing_source_sha256=expected_timing_source_sha256 or transcript["timing_source_sha256"],
            expected_edit_plan_sha256=edit_hash,
            expected_source_audio_sha256=transcript["source_audio_sha256"],
            expected_source_video_sha256=transcript["source_video_sha256"],
        ),
        context="caption_validation",
    )


def _status(payload: Mapping[str, Any]) -> str:
    return str(payload.get("status", payload.get("decision", ""))).upper()


def _strong_candidate(candidate_id: str = "C-OPEN-LOOP") -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "episode_id": "EP001",
        "source_episode_id": "EP001",
        "text": "ما الذي حدث بعد ذلك؟ ظهرت العلامة الأولى، لكن السؤال الأكبر بقي بلا جواب.",
        "narration_text": "ما الذي حدث بعد ذلك؟ ظهرت العلامة الأولى، لكن السؤال الأكبر بقي بلا جواب.",
        "source_text": "ما الذي حدث بعد ذلك؟ ظهرت العلامة الأولى، لكن السؤال الأكبر بقي بلا جواب.",
        "hook_strength": 0.94,
        "retention_potential": 0.86,
        "standalone_value": 0.82,
        "open_loop_strength": 0.92,
        "longform_conversion_score": 0.91,
        "spoiler_cost": 0.16,
        "payoff_disclosure_level": 0.30,
        "payoff_overdisclosure": False,
        "withheld_payoff_summary": "السبب الكامل للعلامة محفوظ للحلقة الأصلية.",
        "conversion_bridge_status": "OPEN_LOOP_PRESERVED",
        "conversion_bridge_reason": "يقدم تطورًا حقيقيًا ويبقي السؤال الأكبر مفتوحًا دون وعد زائف.",
        "gate_flags": [],
        "conversion_gates": {},
        "hard_gate_results": {},
        "cta_plan": {"mode": "NONE", "invented_text": False},
    }


def _timed_transcript() -> dict[str, Any]:
    return {
        "schema_version": "SIRAJ_CANONICAL_TIMED_TRANSCRIPT_V1",
        "episode_id": "EP001",
        "source_video_sha256": "b" * 64,
        "source_audio_sha256": "a" * 64,
        "timing_source_sha256": "c" * 64,
        "canonical_transcript_sha256": "d" * 64,
        "duration_seconds": 10.0,
        "timing_authority": "LEVEL_A_TRUSTED_WORD_BOUNDARIES",
        "segments": [
            {
                "segment_id": "S1",
                "start_seconds": 0.0,
                "end_seconds": 4.0,
                "text": "ما الذي حدث بعد ذلك؟",
                "word_boundaries": [
                    {"text": "ما", "start_seconds": 0.0, "end_seconds": 0.7},
                    {"text": "الذي", "start_seconds": 0.7, "end_seconds": 1.5},
                    {"text": "حدث", "start_seconds": 1.5, "end_seconds": 2.5},
                    {"text": "بعد", "start_seconds": 2.5, "end_seconds": 3.1},
                    {"text": "ذلك؟", "start_seconds": 3.1, "end_seconds": 4.0},
                ],
            },
            {
                "segment_id": "S2",
                "start_seconds": 4.0,
                "end_seconds": 10.0,
                "text": "ظهرت العلامة الأولى، لكن السؤال الأكبر بقي بلا جواب.",
                "word_boundaries": [
                    {"text": "ظهرت", "start_seconds": 4.0, "end_seconds": 5.0},
                    {"text": "العلامة", "start_seconds": 5.0, "end_seconds": 6.0},
                    {"text": "الأولى،", "start_seconds": 6.0, "end_seconds": 7.0},
                    {"text": "لكن", "start_seconds": 7.0, "end_seconds": 7.7},
                    {"text": "السؤال", "start_seconds": 7.7, "end_seconds": 8.5},
                    {"text": "الأكبر", "start_seconds": 8.5, "end_seconds": 9.2},
                    {"text": "بقي", "start_seconds": 9.2, "end_seconds": 9.6},
                    {"text": "بلا", "start_seconds": 9.6, "end_seconds": 9.8},
                    {"text": "جواب.", "start_seconds": 9.8, "end_seconds": 10.0},
                ],
            },
        ],
    }


def _edit_plan() -> dict[str, Any]:
    return {
        "schema_version": "SIRAJ_SHORT_EDIT_PLAN_V1",
        "short_id": "SHORT-EP001",
        "source_episode_id": "EP001",
        "source_video_sha256": "b" * 64,
        "source_audio_sha256": "a" * 64,
        "short_duration_seconds": 10.0,
        "ranges": [
            {"range_id": "R1", "source_start": 0.0, "source_end": 4.0, "short_start": 0.0, "short_end": 4.0},
            {"range_id": "R2", "source_start": 4.0, "source_end": 10.0, "short_start": 4.0, "short_end": 10.0},
        ],
    }


def test_required_evidence_scaffolding_is_machine_readable_and_fail_closed() -> None:
    for filename in REQUIRED_REPORTS:
        path = REPORT_ROOT / filename
        assert path.is_file(), f"MISSING_REQUIRED_EVIDENCE:{filename}"
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"] == filename.removesuffix(".json")
        assert document["task"] == "SIRAJ_SHORTS_CONVERSION_AND_BURNED_CAPTIONS_DIRECTOR_V1"
        assert document["status"] in {
            "NOT_RUN",
            "INCOMPLETE",
            "PASS",
            "BLOCKED_EP001_CAPTION_TIMING_INSUFFICIENT",
        }
        if document["status"] == "BLOCKED_EP001_CAPTION_TIMING_INSUFFICIENT":
            assert document["final_decision"] == "BLOCKED_EP001_CAPTION_TIMING_INSUFFICIENT"
            assert document["critical_unresolved"] == []
            assert document["high_unresolved"] == []
        assert document["offline_only"] is True
        assert all(document["safety_counters"][key] == 0 for key in SAFETY_KEYS)
        assert document["production_authorized"] is False
        assert document["paid_execution_authorized"] is False


def test_conversion_assessment_exposes_required_signals_and_source_binding() -> None:
    assessment = _conversion_assess(_strong_candidate())
    signals = assessment.get("signals", assessment.get("conversion_signals", assessment))
    assert all(field in signals for field in REQUIRED_CONVERSION_FIELDS)
    for field in (
        "SHORT_QUALITY",
        "HOOK_STRENGTH",
        "RETENTION_POTENTIAL",
        "STANDALONE_VALUE",
        "OPEN_LOOP_STRENGTH",
        "LONGFORM_CONVERSION_SCORE",
        "SPOILER_COST",
        "PAYOFF_DISCLOSURE_LEVEL",
    ):
        assert 0.0 <= float(signals[field]) <= 1.0
    assert signals["SOURCE_EPISODE_ID"] == "EP001"
    assert bool(signals["WITHHELD_PAYOFF_SUMMARY"])
    assert str(signals["CONVERSION_BRIDGE_STATUS"]).upper() not in {"REJECT", "BLOCKED"}
    assert signals.get("invented_cta", signals.get("cta_plan", {}).get("invented_text", False)) is False


@pytest.mark.parametrize(
    "gate",
    (
        "FULL_PAYOFF_ALREADY_REVEALED",
        "SHORT_SUMMARIZES_WHOLE_ANSWER",
        "NO_REASON_TO_WATCH_LONGFORM",
        "CONTEXT_REQUIRED_BUT_MISSING",
    ),
)
def test_conversion_overdisclosure_and_context_gates_never_promote_top_candidate(gate: str) -> None:
    candidate = _strong_candidate(candidate_id=f"C-{gate}")
    candidate["gate_flags"] = [gate]
    candidate["conversion_gates"] = {gate: True}
    candidate["hard_gate_results"] = {gate: {"status": "FAIL", "code": gate}}
    assessment = _conversion_assess(candidate)
    assert gate in json.dumps(assessment, ensure_ascii=False)
    assert _status(assessment) in {"REJECT", "REJECTED", "BLOCK", "BLOCKED", "DOWNRANK", "FAIL"}


@pytest.mark.parametrize("gate", ("MISLEADING_OPEN_LOOP", "FABRICATED_CURIOSITY"))
def test_misleading_or_fabricated_curiosity_is_rejected(gate: str) -> None:
    candidate = _strong_candidate(candidate_id=f"C-{gate}")
    candidate["gate_flags"] = [gate]
    candidate["conversion_gates"] = {gate: True}
    candidate["hard_gate_results"] = {gate: {"status": "FAIL", "code": gate}}
    assessment = _conversion_assess(candidate)
    assert _status(assessment) in {"REJECT", "REJECTED", "BLOCK", "BLOCKED", "FAIL"}
    assert gate in json.dumps(assessment, ensure_ascii=False)


def test_conversion_portfolio_accounts_cumulative_spoiler_and_downselects_summary() -> None:
    safe = _strong_candidate("C-SAFE")
    exposed = _strong_candidate("C-EXPOSED")
    exposed["gate_flags"] = ["FULL_PAYOFF_ALREADY_REVEALED"]
    exposed["conversion_gates"] = {"FULL_PAYOFF_ALREADY_REVEALED": True}
    exposed["spoiler_cost"] = 0.98
    exposed["payoff_disclosure_level"] = 0.99
    portfolio = _conversion_portfolio([safe, exposed, _strong_candidate("C-SAFE-2")])
    assert "CUMULATIVE_SPOILER_COST" in portfolio
    assert "CUMULATIVE_PAYOFF_COVERAGE" in portfolio
    selected = portfolio.get("selected_candidate_ids", portfolio.get("selected_ids"))
    assert isinstance(selected, (list, tuple))
    assert "C-EXPOSED" not in selected
    assert portfolio.get("PORTFOLIO_SUMMARIZES_WHOLE_EPISODE", False) is False


def test_caption_plan_is_short_only_narration_only_and_hash_bound() -> None:
    transcript = _timed_transcript()
    edit_plan = _edit_plan()
    plan = _caption_build(transcript, edit_plan)
    payload = _as_mapping(plan, context="caption_plan_payload")
    assert payload["captions_enabled"] is True
    assert payload["scope"] == "SHORT_DERIVATIVE"
    assert payload["text_authority"] == "NARRATION_ONLY"
    assert payload["timebase"] == "SHORT_LOCAL_TIMEBASE"
    assert payload["canonical_transcript_sha256"] == transcript["canonical_transcript_sha256"]
    assert payload["edit_plan_sha256"] == _caption_module().ShortEditPlan.from_mapping(edit_plan).edit_plan_sha256
    assert payload["timing_authority"] in {"WORD_BOUNDARY", "PHRASE_CLAUSE_BOUNDARY", "SENTENCE_BOUNDARY"}
    assert payload["cues"]
    assert plan.render_contract["max_lines"] == 2
    validation = _caption_validate(plan, transcript, edit_plan)
    assert _status(validation) in {"PASS", "SHORT_CAPTION_QA_PASS"}
    narration_text = " ".join(segment["text"] for segment in transcript["segments"])
    assert all(cue["text"] and cue["text"] in narration_text for cue in payload["cues"])


def test_longform_burned_caption_and_on_screen_subtitle_requests_are_blocked() -> None:
    operation = getattr(_caption_module(), "validate_caption_scope", None)
    if not callable(operation):
        pytest.fail("PUBLIC_OPERATION_MISSING:caption_module:validate_caption_scope")
    for field in ("burned_captions", "on_screen_subtitles"):
        try:
            operation("LONGFORM", burned_captions=field == "burned_captions", on_screen_subtitles=field == "on_screen_subtitles")
        except Exception as exc:  # fail-closed scope implementations may raise a typed block error
            assert "LONGFORM" in str(exc).upper()
            continue
        pytest.fail(f"LONGFORM_CAPTION_SCOPE_NOT_BLOCKED:{field}")


def test_invented_caption_text_and_stale_hashes_are_blocked() -> None:
    transcript = _timed_transcript()
    edit_plan = _edit_plan()
    invented = _timed_transcript()
    invented["segments"][0]["word_boundaries"][0]["text"] = "شاهد الحلقة كاملة"
    with pytest.raises(Exception, match="CAPTION_TEXT_NOT_NARRATION|CAPTION_TEXT_AUTHORITY_FORBIDDEN"):
        _caption_build(invented, edit_plan)

    plan = _caption_build(transcript, edit_plan)
    stale = _caption_validate(
        plan,
        transcript,
        edit_plan,
        expected_canonical_transcript_sha256="f" * 64,
    )
    assert _status(stale) == "BLOCKED"
    assert "STALE_TRANSCRIPT_HASH" in json.dumps(stale, ensure_ascii=False)


def test_caption_invariants_reject_negative_overlap_overduration_and_three_lines() -> None:
    transcript = _timed_transcript()
    edit_plan = _edit_plan()
    plan = _caption_build(transcript, edit_plan)
    first = plan.cues[0]
    second = plan.cues[1]
    invalid_plans = (
        replace(plan, cues=(replace(first, start_seconds=-1.0),) + plan.cues[1:]),
        replace(plan, cues=(replace(first, end_seconds=2.0), replace(second, start_seconds=1.0)) + plan.cues[2:]),
        replace(plan, cues=(replace(first, start_seconds=9.0, end_seconds=11.0),) + plan.cues[1:]),
        replace(plan, cues=(replace(first, line_count=3, display_lines=("السطر الأول", "السطر الثاني", "السطر الثالث")),) + plan.cues[1:]),
    )
    for invalid_plan in invalid_plans:
        result = _caption_validate(invalid_plan, transcript, edit_plan)
        assert _status(result) == "BLOCKED"


def test_coarse_timing_is_insufficient_without_silent_proportional_split() -> None:
    transcript = {
        **_timed_transcript(),
        "segments": [{
            "segment_id": "COARSE",
            "start_seconds": 0.0,
            "end_seconds": 10.0,
            "text": "هذه جملة طويلة بلا حدود زمنية أدق من توقيت المقطع الكامل.",
        }],
    }
    edit_plan = {
        **_edit_plan(),
        "ranges": [{"range_id": "R1", "source_start": 0.0, "source_end": 10.0, "short_start": 0.0, "short_end": 10.0}],
    }
    operation = getattr(_caption_module(), "build_caption_plan", None)
    if not callable(operation):
        pytest.fail("PUBLIC_OPERATION_MISSING:caption_module:build_caption_plan")
    try:
        operation(transcript=transcript, edit_plan=edit_plan, scope="SHORT_DERIVATIVE", captions_enabled=True, visual_policy_status="PASS")
    except Exception as exc:
        assert "CAPTION_TIMING_INSUFFICIENT" in str(exc)
    else:
        pytest.fail("COARSE_TIMING_WAS_SILENTLY_ACCEPTED")


def test_hash_bound_cache_invalidates_transcript_edit_and_version_inputs() -> None:
    cache = HashBoundCache()
    key = "caption-plan"
    transcript_hash = "a" * 64
    edit_hash = "b" * 64
    version = "1.0.0"
    cache.put(key, transcript_hash, {"edit_plan_sha256": edit_hash, "resolver_version": version})
    assert cache.get(key, transcript_hash) == {"edit_plan_sha256": edit_hash, "resolver_version": version}
    assert cache.get(key, "c" * 64) is None
    assert cache.invalidate("c" * 64) == [key]


def test_caption_plan_freshness_invalidates_transcript_timing_and_edit_hashes() -> None:
    transcript = _timed_transcript()
    edit_plan = _edit_plan()
    plan = _caption_build(transcript, edit_plan)
    module = _caption_module()
    edit_hash = module.ShortEditPlan.from_mapping(edit_plan).edit_plan_sha256
    for field, value, token in (
        ("canonical_transcript_sha256", "f" * 64, "STALE_TRANSCRIPT_HASH"),
        ("timing_source_sha256", "f" * 64, "STALE_TIMING_SOURCE_HASH"),
        ("edit_plan_sha256", "f" * 64, "STALE_EDIT_PLAN_HASH"),
    ):
        expected = {
            "canonical_transcript_sha256": transcript["canonical_transcript_sha256"],
            "timing_source_sha256": transcript["timing_source_sha256"],
            "edit_plan_sha256": edit_hash,
        }
        expected[field] = value
        result = module.qa_caption_plan(
            plan,
            expected_canonical_transcript_sha256=expected["canonical_transcript_sha256"],
            expected_timing_source_sha256=expected["timing_source_sha256"],
            expected_edit_plan_sha256=expected["edit_plan_sha256"],
        ).to_dict()
        assert _status(result) == "BLOCKED"
        assert token in json.dumps(result, ensure_ascii=False)


def test_new_director_and_caption_modules_have_no_live_capability_surface() -> None:
    for module_name in (CONVERSION_MODULE, CAPTION_MODULE):
        module = _load_module(module_name)
        source_path = Path(inspect.getfile(module))
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        imported_modules = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.extend(alias.name.casefold() for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.append(node.module.casefold())
        for forbidden in ("requests", "httpx", "urllib.request", "openai", "runware", "whisper", "speechrecognition"):
            assert not any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported_modules), f"LIVE_CAPABILITY_IMPORT:{module_name}:{forbidden}"
    boundary = capability_boundary_evidence(REPO_ROOT / "src" / "application" / "shorts_derivative_engine_v1.py")
    assert boundary["pass"] is True
    assert boundary["short_analyzer_can_call_provider"] is False
    assert boundary["shorts_engine_can_upload_youtube"] is False


def test_evidence_scaffolding_records_required_finalization_dimensions() -> None:
    required_fields = {
        "SHORTS_CAPTION_POLICY_AMENDMENT_V1.json": ("constitution_old_version", "constitution_new_version", "old_bundle_sha256", "new_bundle_sha256"),
        "SHORTS_CONVERSION_DIRECTOR_AUDIT_V1.json": ("required_conversion_fields", "required_gate_codes", "portfolio_controls"),
        "SHORTS_CONVERSION_DIRECTOR_CERTIFICATION_V1.json": ("conversion_director", "hook_strength", "open_loop_strength", "spoiler_control"),
        "SHORTS_BURNED_CAPTION_ENGINE_CERTIFICATION_V1.json": ("caption_engine", "text_authority", "timing_authority", "default_on"),
        "SHORTS_CAPTION_VISUAL_QA_V1.json": ("fixture_matrix", "human_visual_certification"),
        "SHORTS_CAPTION_TIMING_AUTHORITY_V1.json": ("authority_order", "no_proportional_guessing", "ep001_granularity"),
        "SIRAJ_PRODUCTION_READINESS_REBIND_AFTER_SHORTS_CAPTION_POLICY_V1.json": ("old_bundle_sha256", "new_bundle_sha256", "invalidation", "production_authorized", "paid_execution_authorized"),
        "SIRAJ_SHORTS_CONVERSION_CAPTIONS_FINAL_CERTIFICATION_V1.json": ("conversion_director", "caption_engine", "longform_protection", "test_matrix", "critical_unresolved", "high_unresolved"),
    }
    for filename, fields in required_fields.items():
        document = json.loads((REPORT_ROOT / filename).read_text(encoding="utf-8"))
        for field in fields:
            assert field in document, f"EVIDENCE_FIELD_MISSING:{filename}:{field}"
