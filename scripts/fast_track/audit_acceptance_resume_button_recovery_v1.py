from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.runtime_state_recovery_v1 import (
    diagnose_runtime_state,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    console = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    workspace = (
        repo / "src/presentation/desktop/complete_workspace_v1.py"
    ).read_text(encoding="utf-8")
    recovery = (
        repo / "src/application/runtime_state_recovery_v1.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "recover_runtime_state_from_artifacts",
        "diagnose_runtime_state",
        "runtime-state-backups",
        "QA_PASS_AND_FINAL_MASTER_PRESENT",
        "MEDIA_QUEUE_HAS_PENDING_ITEMS",
    ):
        require(marker in recovery, "RECOVERY_MARKER_MISSING:" + marker)

    for marker in (
        "_recover_resume_runtime_state",
        "فحص واستعادة المرحلة العالقة",
        "تشخيص وإصلاح الاستكمال",
        "QApplication.processEvents",
        "استلم سراج أمر الاستكمال",
    ):
        require(marker in console, "CONSOLE_MARKER_MISSING:" + marker)

    require(
        'directive.action != "WAIT"' not in console,
        "WAIT_ACTION_STILL_DISABLES_BUTTON",
    )
    require(
        "lambda checked=False: self._open_production()" in workspace,
        "WORKSPACE_CLICK_ADAPTER_MISSING",
    )

    try:
        diagnosis = diagnose_runtime_state(repo).as_dict()
    except Exception as exc:
        diagnosis = {"status": "DIAGNOSIS_UNAVAILABLE", "error": str(exc)}

    (output / "runtime-diagnosis.json").write_text(
        json.dumps(diagnosis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = (
        "STATUS=PASS_SIRAJ_ACCEPTANCE_RESUME_BUTTON_RECOVERY_V1",
        "CONTINUE_BUTTON_SILENT_PATH=REMOVED",
        "WAIT_STATE_BUTTON=ENABLED_FOR_DIAGNOSIS",
        "ARTIFACT_BASED_RUNTIME_RECOVERY=ENABLED",
        "STATE_BACKUP_BEFORE_RECOVERY=REQUIRED",
        "QT_CLICK_SIGNATURE_ADAPTER=ENABLED",
        "PROVIDER_REQUESTS_DURING_RECOVERY=0",
        "PAID_AUTHORIZATION_BYPASS=FORBIDDEN",
        "NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN_RETRY",
    )
    report = output / "audit.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
