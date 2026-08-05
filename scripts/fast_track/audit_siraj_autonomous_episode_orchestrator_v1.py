from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.autonomous_episode_orchestrator_v1 import (
        FULL_STAGE_ORDER,
        load_orchestrator_state,
    )
    from src.application.openai_luna_orchestrator_v1 import (
        LUNA_MODEL,
        build_scope_request,
    )

    policy_path = (
        repo
        / "projects/_orchestrator/contracts/"
        "autonomous-episode-orchestrator-policy-v1.json"
    )
    policy = json.loads(policy_path.read_text(encoding="utf-8-sig"))
    state = load_orchestrator_state(repo)
    request = build_scope_request(repo)

    require(policy["status"] == "HUMAN_DIRECTIVES_ACTIVE", "POLICY_INACTIVE")
    require(policy["episode_budget_hard_cap_usd"] == 40.0, "CAP_CHANGED")
    require(policy["budget_override"] == "FORBIDDEN", "CAP_OVERRIDE_ENABLED")
    require(policy["music"] == "FORBIDDEN", "MUSIC_ENABLED")
    require(
        policy["sound_effects"]
        == "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
        "SFX_POLICY_CHANGED",
    )
    require(LUNA_MODEL == "gpt-5.6-luna", "LUNA_MODEL_CHANGED")
    require(request["tools"] == [{"type": "web_search"}], "WEB_SEARCH_MISSING")
    require(
        request["text"]["format"]["type"] == "json_schema",
        "STRUCTURED_OUTPUT_MISSING",
    )
    require(request["text"]["format"]["strict"] is True, "SCHEMA_NOT_STRICT")
    require(request["store"] is False, "OPENAI_STORAGE_MUST_BE_FALSE")
    require(
        state["autonomy_contract"]["human_gates"]
        == ["HUMAN_SCOPE_REVIEW", "HUMAN_FINAL_REVIEW"],
        "HUMAN_GATES_CHANGED",
    )
    require(len(FULL_STAGE_ORDER) == 14, "STAGE_COUNT_CHANGED")
    require(
        state["autonomy_contract"]["partial_rebuild_only"] is True,
        "PARTIAL_REBUILD_DISABLED",
    )

    result = {
        "status": "PASS_SIRAJ_AUTONOMOUS_EPISODE_ORCHESTRATOR_V1",
        "release": "SIRAJ_AUTONOMOUS_EPISODE_ORCHESTRATOR_V1",
        "editorial_model": "gpt-5.6-luna",
        "openai_api": "RESPONSES_API",
        "web_search": "ENABLED_FOR_SCOPE_PROPOSAL",
        "structured_output": "STRICT_JSON_SCHEMA",
        "human_gates": 2,
        "scope_discussion_with_luna": True,
        "partial_rebuild": True,
        "music": "FORBIDDEN",
        "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
        "episode_hard_cap_usd": 40.0,
        "openai_requests_during_audit": 0,
        "runware_requests_during_audit": 0,
        "elevenlabs_requests_during_audit": 0,
        "credit_spent_during_audit": False,
        "next_stage": "AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1",
    }
    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "siraj-autonomous-episode-orchestrator-v1-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for key, value in result.items():
        print(f"{key.upper()}={value}")
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
