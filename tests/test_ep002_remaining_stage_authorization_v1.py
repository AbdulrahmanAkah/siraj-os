from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def test_live_remaining_stage_authorization_matches_current_39_plus_56():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )
    from src.application.desktop_provider_execution_v1 import (
        CanonicalDesktopProviderExecutionExecutor,
        STAGE_RECEIPT_LEDGER,
        _siraj_durable_completed_provider_units_v2,
    )
    from src.application.provider_remaining_stage_authorization_v1 import (
        remaining_stage_authorization_for_episode,
        validate_remaining_stage_authorization_current,
    )

    auth = remaining_stage_authorization_for_episode(
        REPO, EPISODE
    )
    assert auth is not None
    assert auth["status"] == "AUTHORIZED"
    assert auth["authorized_remaining_units_count"] == 56
    assert auth["baseline_durable_completed_count"] == 39
    assert abs(auth["authorized_planned_total_usd"] - 15.16755) < 1e-9
    assert abs(auth["maximum_total_usd"] - 16.0) < 1e-9
    assert auth["maximum_provider_submissions"] == 56
    assert auth["automatic_paid_retry"] is False
    assert auth["automatic_paid_resubmission"] is False
    assert auth["stop_on_first_unresolved_or_failed_attempt"] is True
    assert auth["skip_durable_completed_units"] is True

    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    provider_units = [
        dict(row)
        for row in preflight["units"]
        if str(row.get("provider") or "").upper() == "RUNWARE"
    ]
    executor = CanonicalDesktopProviderExecutionExecutor(
        REPO, EPISODE
    )
    review = read_persisted_media_cost_preflight(
        REPO, EPISODE
    )
    binding = executor._binding(review)
    durable = _siraj_durable_completed_provider_units_v2(
        REPO,
        EPISODE,
        provider_units,
        binding,
    )
    assert len(durable) == 39

    stage_path = (
        REPO
        / "projects"
        / EPISODE
        / "orchestration"
        / "provider-execution-v1"
        / STAGE_RECEIPT_LEDGER
    )
    stage_rows = [
        json.loads(raw)
        for raw in stage_path.read_text(
            encoding="utf-8-sig"
        ).splitlines()
        if raw.strip()
    ]
    pauses = [
        row
        for row in stage_rows
        if row.get("status")
        == "STAGE_PAUSED_AUTHORIZATION_SCOPE"
        and row.get("remaining_stage_not_authorized") is True
    ]
    assert pauses
    snapshot = validate_remaining_stage_authorization_current(
        auth,
        episode_id=EPISODE,
        binding=binding.as_dict(),
        provider_units=provider_units,
        durable_completed=durable,
        prior_scope_pause=pauses[-1],
    )
    assert snapshot["baseline_completed_count"] == 39
    assert snapshot["current_remaining_count"] == 56
    assert len(snapshot["authorized_unit_ids"]) == 56


def test_authorized_units_cover_exact_remaining_provider_universe():
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))

    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )
    from src.application.desktop_provider_execution_v1 import (
        CanonicalDesktopProviderExecutionExecutor,
        _siraj_durable_completed_provider_units_v2,
    )
    from src.application.provider_remaining_stage_authorization_v1 import (
        remaining_stage_authorization_for_episode,
    )

    auth = remaining_stage_authorization_for_episode(
        REPO, EPISODE
    )
    preflight = json.loads(
        (
            REPO
            / "projects"
            / EPISODE
            / "orchestration"
            / "media-cost-preflight-v2.json"
        ).read_text(encoding="utf-8-sig")
    )
    units = [
        dict(row)
        for row in preflight["units"]
        if str(row.get("provider") or "").upper() == "RUNWARE"
    ]
    executor = CanonicalDesktopProviderExecutionExecutor(
        REPO, EPISODE
    )
    review = read_persisted_media_cost_preflight(
        REPO, EPISODE
    )
    durable = _siraj_durable_completed_provider_units_v2(
        REPO,
        EPISODE,
        units,
        executor._binding(review),
    )

    current_remaining = {
        str(row.get("request_id") or row.get("unit_id") or "")
        for row in units
        if str(row.get("request_id") or row.get("unit_id") or "")
        not in durable
    }
    authorized = {
        str(row["unit_id"])
        for row in auth["authorized_units"]
    }
    assert current_remaining == authorized
    assert len(authorized) == 56
    assert not (authorized & set(auth["baseline_durable_completed"]))


def test_source_skips_completed_and_checks_batch_budget_before_paid_request():
    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    execute = None
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name
            == "CanonicalDesktopProviderExecutionExecutor"
        ):
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef)
                    and child.name == "execute"
                ):
                    execute = child
                    break
    assert execute is not None

    loops = [
        node
        for node in ast.walk(execute)
        if isinstance(node, ast.For)
        and "enumerate" in ast.unparse(node.iter)
        and "provider_units" in ast.unparse(node.iter)
    ]
    assert len(loops) == 1
    loop = loops[0]

    skip_guards = []
    for node in ast.walk(loop):
        if not isinstance(node, ast.If):
            continue
        rendered_test = ast.unparse(node.test)
        if (
            "_siraj_remaining_stage_unit_id_v1"
            in rendered_test
            and "_siraj_durable_completed_units_v2"
            in rendered_test
        ):
            has_continue = any(
                isinstance(child, ast.Continue)
                for child in node.body
            )
            if has_continue:
                skip_guards.append(node)
    assert len(skip_guards) == 1

    # The batch scope check must be inside the provider loop and before
    # PaidOperationRequest / gateway submit.
    loop_text = ast.unparse(loop)
    assert (
        "REMAINING_STAGE_UNIT_OUTSIDE_AUTHORIZATION"
        in loop_text
    )
    assert (
        "REMAINING_STAGE_AUTHORIZATION_TOTAL_COST_CAP_EXCEEDED"
        in loop_text
    )
    assert "PaidOperationRequest" in loop_text
    assert "gateway.submit" in loop_text

    loop_source = ast.get_source_segment(source, loop)
    assert loop_source is not None
    scope_pos = loop_source.index(
        "REMAINING_STAGE_UNIT_OUTSIDE_AUTHORIZATION"
    )
    budget_pos = loop_source.index(
        "REMAINING_STAGE_AUTHORIZATION_TOTAL_COST_CAP_EXCEEDED"
    )
    paid_pos = loop_source.index("PaidOperationRequest(")
    submit_pos = loop_source.index("gateway.submit(")
    assert scope_pos < budget_pos < paid_pos < submit_pos

def test_source_blocks_reuse_after_any_tagged_incomplete_attempt():
    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    execute = None
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name
            == "CanonicalDesktopProviderExecutionExecutor"
        ):
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef)
                    and child.name == "execute"
                ):
                    execute = child
                    break
    assert execute is not None

    loops = [
        node
        for node in ast.walk(execute)
        if isinstance(node, ast.For)
        and "enumerate" in ast.unparse(node.iter)
        and "provider_units" in ast.unparse(node.iter)
    ]
    assert len(loops) == 1
    provider_loop = loops[0]

    # Find the fail-closed raise semantically. Adjacent Python string
    # literals are folded by the parser, so AST is the correct layer.
    partial_raises = []
    for node in ast.walk(execute):
        if not isinstance(node, ast.Raise):
            continue
        rendered = ast.unparse(node)
        if (
            "REMAINING_STAGE_AUTHORIZATION_PARTIAL_ATTEMPT_"
            "REQUIRES_REAUTHORIZATION:"
            in rendered
        ):
            partial_raises.append(node)

    assert len(partial_raises) == 1
    partial_raise = partial_raises[0]
    assert partial_raise.lineno < provider_loop.lineno

    # Its enclosing pre-loop region must prove that tagged intents are
    # examined against durable-completed evidence before entering the loop.
    before_loop = "\n".join(
        source.splitlines()[: provider_loop.lineno - 1]
    )
    assert "ATTEMPT_INTENT_PERSISTED" in before_loop
    assert "_siraj_remaining_stage_tagged_intents_v1" in before_loop
    assert "_siraj_durable_completed_units_v2" in before_loop

def test_intent_receipt_records_batch_authorization_and_runtime_policy():
    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert '"remaining_stage_authorization_id": (' in source
    assert '"remaining_stage_authorization_sha256": (' in source
    assert '"remaining_stage_submission_ordinal": (' in source
    assert '"remaining_stage_planned_cost_usd": (' in source
    assert (
        '"remaining_stage_authorized_exposure_usd_after_intent": ('
        in source
    )
    assert '"runtime_person_generation_policy": (' in source


def test_mena_runtime_policy_still_installed_for_remaining_veo():
    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert (
        "SIRAJ_EP002_VEO_MENA_ALLOW_ADULT_RUNTIME_POLICY_V1"
        in source
    )
    assert (
        "_siraj_ep002_veo_mena_allow_adult_runtime_policy_v1("
        in source
    )


def test_batch_authorization_bypasses_legacy_one_unit_lookup_only_when_active():
    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert (
        "_siraj_first_remaining_unit_v2 is not None"
        in source
    )
    assert (
        "and not _siraj_remaining_stage_guard_active_v1"
        in source
    )
    batch = source.index(
        "_siraj_remaining_stage_guard_active_v1 = False"
    )
    bypass = source.index(
        "and not _siraj_remaining_stage_guard_active_v1",
        batch,
    )
    legacy_lookup = source.index(
        "terminal_replacement_authorization_for_request(",
        bypass,
    )
    provider_loop = source.index(
        "for ordinal, unit in enumerate(",
        legacy_lookup,
    )
    assert batch < bypass < legacy_lookup < provider_loop


def test_old_unconditional_prior_scope_raise_was_replaced_not_duplicated():
    import ast

    source = (
        REPO
        / "src/application/desktop_provider_execution_v1.py"
    ).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)

    execute = None
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name
            == "CanonicalDesktopProviderExecutionExecutor"
        ):
            for child in node.body:
                if (
                    isinstance(child, ast.FunctionDef)
                    and child.name == "execute"
                ):
                    execute = child
                    break
    assert execute is not None

    direct_tests = [
        node
        for node in ast.walk(execute)
        if isinstance(node, ast.If)
        and ast.unparse(node.test).strip()
        == "_siraj_prior_scope_pauses_v2"
    ]
    assert len(direct_tests) >= 1

    old_direct_raises = []
    for node in direct_tests:
        body = "\n".join(
            ast.unparse(statement)
            for statement in node.body
        )
        if (
            "REMAINING_STAGE_REQUIRES_SEPARATE_AUTHORIZATION"
            in body
            and "remaining_stage_authorization_for_episode"
            not in body
        ):
            old_direct_raises.append(node)
    assert old_direct_raises == []

    assert (
        "remaining_stage_authorization_for_episode("
        in source
    )
