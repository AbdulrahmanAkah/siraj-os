"""Iterative research-session contract for Luna Research Gateway V4.

This module does not make OpenAI or web calls. It validates Luna research plans
and executes only explicitly requested gateway actions. A future authorized
runner can alternate:
Luna plan -> deterministic retrieval -> Luna adjudication -> follow-up retrieval
until Luna returns RESEARCH_COMPLETE.

Repeated research rounds are intentional calls, not hidden retries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_research_gateway_v4 import (
    ResearchGatewayError,
    ResearchGatewayV4,
)

ALLOWED_OPERATIONS = {
    "SEARCH_SHAMELA",
    "EXPAND_SHAMELA_LOCATOR",
    "SEARCH_HADITH_LOCAL",
    "SEARCH_QURAN_CACHE",
    "MATERIALIZE_QURAN_LOCATOR",
    "MATERIALIZE_HADITH_URL",
    "SEARCH_SOURCE_PACKAGES",
    "SEARCH_WEB_GAP",
}

class LunaResearchLoopError(RuntimeError):
    pass

def validate_luna_research_plan(plan: Mapping[str, Any]) -> None:
    if str(plan.get("stage_owner") or "") != "LUNA":
        raise LunaResearchLoopError("RESEARCH_PLAN_OWNER_MUST_BE_LUNA")
    status = str(plan.get("status") or "")
    if status not in {"CONTINUE_RESEARCH", "RESEARCH_COMPLETE"}:
        raise LunaResearchLoopError(f"RESEARCH_PLAN_STATUS_INVALID:{status}")
    questions = plan.get("research_questions")
    if not isinstance(questions, list) or not questions:
        raise LunaResearchLoopError("RESEARCH_QUESTIONS_REQUIRED")
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise LunaResearchLoopError("RESEARCH_ACTIONS_LIST_REQUIRED")
    if status == "CONTINUE_RESEARCH" and not actions:
        raise LunaResearchLoopError(
            "CONTINUE_RESEARCH_REQUIRES_ACTIONS"
        )
    for index, action in enumerate(actions):
        if not isinstance(action, Mapping):
            raise LunaResearchLoopError(
                f"RESEARCH_ACTION_OBJECT_REQUIRED:{index}"
            )
        operation = str(action.get("operation") or "").upper()
        if operation not in ALLOWED_OPERATIONS:
            raise LunaResearchLoopError(
                f"RESEARCH_OPERATION_NOT_ALLOWED:{operation}"
            )
        purpose = str(action.get("purpose_ar") or "").strip()
        if not purpose:
            raise LunaResearchLoopError(
                f"RESEARCH_ACTION_PURPOSE_REQUIRED:{index}"
            )
        if operation.startswith("SEARCH_") and operation != (
            "EXPAND_SHAMELA_LOCATOR"
        ):
            if not str(action.get("query") or "").strip():
                raise LunaResearchLoopError(
                    f"RESEARCH_ACTION_QUERY_REQUIRED:{operation}"
                )
        if operation == "EXPAND_SHAMELA_LOCATOR":
            if not str(action.get("locator") or "").strip():
                raise LunaResearchLoopError(
                    "EXPAND_SHAMELA_LOCATOR_REQUIRES_LOCATOR"
                )
        if operation == "MATERIALIZE_QURAN_LOCATOR":
            if not str(action.get("locator") or "").strip():
                raise LunaResearchLoopError(
                    "QURAN_MATERIALIZATION_REQUIRES_LOCATOR"
                )
        if operation == "MATERIALIZE_HADITH_URL":
            if not str(action.get("url") or "").strip():
                raise LunaResearchLoopError(
                    "HADITH_MATERIALIZATION_REQUIRES_URL"
                )
            if not str(
                action.get("arabic_anchor_text") or ""
            ).strip():
                raise LunaResearchLoopError(
                    "HADITH_MATERIALIZATION_REQUIRES_ANCHOR"
                )

def execute_luna_research_actions(
    repo_root: Path,
    plan: Mapping[str, Any],
    *,
    allow_network_materialization: bool = False,
) -> dict[str, Any]:
    validate_luna_research_plan(plan)
    gateway = ResearchGatewayV4(repo_root)
    outputs: list[dict[str, Any]] = []
    for index, action in enumerate(plan.get("actions") or [], 1):
        try:
            result = gateway.execute(
                action,
                allow_network=allow_network_materialization,
            )
            outputs.append(
                {
                    "action_index": index,
                    "action": dict(action),
                    "result": result.as_dict(),
                }
            )
        except ResearchGatewayError as exc:
            outputs.append(
                {
                    "action_index": index,
                    "action": dict(action),
                    "result": {
                        "operation": str(
                            action.get("operation") or ""
                        ).upper(),
                        "status": "ERROR",
                        "error": str(exc),
                    },
                }
            )
    return {
        "schema_version": "siraj-luna-research-round-output-v4",
        "stage_owner": "LUNA",
        "plan_status": plan.get("status"),
        "action_count": len(outputs),
        "network_materialization_allowed": (
            allow_network_materialization
        ),
        "outputs": outputs,
    }

def research_plan_json_schema() -> dict[str, Any]:
    action = {
        "type": "object",
        "additionalProperties": True,
        "required": ["operation", "purpose_ar"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": sorted(ALLOWED_OPERATIONS),
            },
            "purpose_ar": {"type": "string", "minLength": 3},
            "query": {"type": "string"},
            "locator": {"type": "string"},
            "url": {"type": "string"},
            "arabic_anchor_text": {"type": "string"},
            "params": {"type": "object"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "stage_owner",
            "status",
            "research_questions",
            "coverage_assessment_ar",
            "actions",
            "unresolved_gaps_ar",
        ],
        "properties": {
            "stage_owner": {"type": "string", "enum": ["LUNA"]},
            "status": {
                "type": "string",
                "enum": [
                    "CONTINUE_RESEARCH",
                    "RESEARCH_COMPLETE",
                ],
            },
            "research_questions": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "coverage_assessment_ar": {
                "type": "string",
                "minLength": 10,
            },
            "actions": {
                "type": "array",
                "items": action,
                "maxItems": 30,
            },
            "unresolved_gaps_ar": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 30,
            },
        },
    }
