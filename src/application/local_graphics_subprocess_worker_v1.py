from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

# These values must be set before PySide6 or the renderer is imported.  The
# child process therefore owns its QGuiApplication and never borrows the
# desktop application's GUI objects from a QThread.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QSG_RHI_BACKEND", "software")

RELEASE = "SIRAJ_LOCAL_GRAPHICS_SUBPROCESS_ISOLATION_V1"


def _self_test() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication(
        ["siraj-local-graphics-child-self-test"]
    )
    payload = {
        "status": "PASS",
        "release": RELEASE,
        "pid": os.getpid(),
        "qt_platform": os.environ.get("QT_QPA_PLATFORM"),
        "qt_quick_backend": os.environ.get("QT_QUICK_BACKEND"),
        "qsg_rhi_backend": os.environ.get("QSG_RHI_BACKEND"),
        "application_created": app is not None,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--queue-id")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _self_test()
    if args.repo_root is None or not str(args.queue_id or "").strip():
        parser.error("--repo-root and --queue-id are required")

    try:
        from src.application.desktop_media_execution_v1 import (
            _render_local_graphics_item_in_process,
        )

        result = _render_local_graphics_item_in_process(
            args.repo_root.resolve(),
            str(args.queue_id).strip(),
        )
        payload = {
            "status": result.status,
            "release": RELEASE,
            "queue_id": result.queue_id,
            "media_kind": result.media_kind,
            "output_path": str(result.output_path),
            "receipt_path": str(result.receipt_path),
            "actual_cost_usd": result.actual_cost_usd,
            "estimated_cost_usd": result.estimated_cost_usd,
            "pid": os.getpid(),
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0
    except Exception as exc:
        payload = {
            "status": "FAILED",
            "release": RELEASE,
            "queue_id": str(args.queue_id or ""),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "pid": os.getpid(),
        }
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
