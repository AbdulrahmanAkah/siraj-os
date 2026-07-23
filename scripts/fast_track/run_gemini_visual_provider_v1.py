"""Run one bounded Gemini visual plan only with explicit quota acknowledgement."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[2]
if str(REPOSITORY) not in sys.path: sys.path.insert(0, str(REPOSITORY))

from src.application.local_video_production.visual_execution_v1 import execute_visual_plan, load_gemini_quota_policy
from src.application.local_video_production.visual_provider_v1 import GeminiImageProvider


def exit_code_for_execution(result: dict[str, object]) -> int:
    return 0 if result.get("status") == "PASS" else 1


def _usable_reason(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized in {"PASS", "SUCCESS", "FAIL", "PARTIAL"}:
        return None
    return "PROVIDER_FAILURE" if normalized in {"VISUAL_PROVIDER_FAILURE", "INTERNAL_ERROR"} else normalized


def failure_reason_for_execution(result: dict[str, object]) -> str:
    """Return the most specific in-memory failure reason without reading reports."""
    quota_report = result.get("quota_report_summary")
    nested_execution = result.get("live_execution")
    candidates = [
        result.get("stopped_reason"),
        result.get("provider_error_category"),
        result.get("provider_error_code"),
        quota_report.get("stopped_reason") if isinstance(quota_report, dict) else None,
        nested_execution.get("stopped_reason") if isinstance(nested_execution, dict) else None,
        result.get("status"),
    ]
    for candidate in candidates:
        if reason := _usable_reason(candidate):
            return reason
    return "PROVIDER_FAILURE"


def execution_message(result: dict[str, object]) -> str:
    return "SUCCESS" if exit_code_for_execution(result) == 0 else f"FAIL: {failure_reason_for_execution(result)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--quota-policy")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirm-quota-use", action="store_true")
    parser.add_argument("--maximum-assets", type=int)
    parser.add_argument("--maximum-requests", type=int)
    parser.add_argument("--maximum-retries", type=int)
    args = parser.parse_args()
    if not (args.live and args.confirm_quota_use and args.quota_policy):
        raise RuntimeError("LIVE_CONFIRMATION_OR_QUOTA_POLICY_REQUIRED")
    root = Path(args.project_root)
    result = execute_visual_plan(
        root / "working" / "visual-provider-v1" / "production-visual-generation-plan-v1.json", root,
        GeminiImageProvider(), quota_policy=load_gemini_quota_policy(Path(args.quota_policy)),
        live=True, confirm_quota_use=True, maximum_assets=args.maximum_assets,
        maximum_requests=args.maximum_requests, maximum_retries=args.maximum_retries,
    )
    exit_code = exit_code_for_execution(result)
    print(execution_message(result))
    return exit_code


if __name__ == "__main__": raise SystemExit(main())
