from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any


AUTO_BEGIN = "<!-- SIRAJ_AUTO_PROGRESS_BEGIN -->"
AUTO_END = "<!-- SIRAJ_AUTO_PROGRESS_END -->"

DEFAULT_PROGRAM_STATE = {
    "north_star_ar": (
        "إنشاء خط إنتاج آلي وموثّق لفيديوهات التاريخ وفق المصادر "
        "الإسلامية، من خلق آدم عليه السلام إلى قيام الساعة."
    ),
    "short_term_objective_ar": (
        "إنتاج أول حلقة وثائقية قابلة للنشر من المصدر إلى ملف MP4، "
        "ثم تحويل المسار إلى قالب إنتاج متكرر."
    ),
    "long_term_objective_ar": (
        "بناء مصنع محتوى معرفي يعيد استخدام المعرفة الموثقة في "
        "الوثائقيات والمقاطع القصيرة والمقالات والبودكاست والدورات."
    ),
    "gold_20_role_ar": (
        "Gold-20 بوابة معايرة وجودة محدودة داخل مسار المعرفة، "
        "وليس الهدف الرئيسي للمشروع."
    ),
    "progress_policy_ar": (
        "يجب تحديث PROJECT_PROGRESS.md وسجل milestones آليًا بعد "
        "كل خطوة تنفيذية كبيرة، دون انتظار طلب المستخدم."
    ),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(
    path: Path,
    text: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    handle, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(
            handle,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as stream:
            stream.write(text)

        os.replace(temporary_name, path)

    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def atomic_write_json(
    path: Path,
    value: Any,
) -> None:
    atomic_write_text(
        path,
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def load_ledger(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "schema_version": "siraj-project-milestones-v1",
            "program_state": deepcopy(DEFAULT_PROGRAM_STATE),
            "milestones": [],
        }

    payload = json.loads(
        path.read_text(encoding="utf-8-sig")
    )

    if not isinstance(payload, dict):
        raise ValueError("PROJECT_MILESTONE_LEDGER_INVALID")

    payload.setdefault(
        "schema_version",
        "siraj-project-milestones-v1",
    )

    payload.setdefault(
        "program_state",
        deepcopy(DEFAULT_PROGRAM_STATE),
    )

    payload.setdefault("milestones", [])

    return payload


def render_managed_block(
    ledger: dict[str, Any],
) -> str:
    state = {
        **DEFAULT_PROGRAM_STATE,
        **ledger.get("program_state", {}),
    }

    milestones = list(
        ledger.get("milestones", [])
    )

    milestones.sort(
        key=lambda item: (
            str(item.get("recorded_at", "")),
            str(item.get("milestone_id", "")),
        )
    )

    latest = milestones[-1] if milestones else None

    lines = [
        AUTO_BEGIN,
        "## الحالة التنفيذية الآلية للمشروع",
        "",
        f"**آخر مزامنة:** {ledger.get('updated_at', '')}",
        "",
        "### الهدف المرجعي",
        "",
        f"- **الهدف قصير المدى:** {state['short_term_objective_ar']}",
        f"- **الهدف طويل المدى:** {state['long_term_objective_ar']}",
        f"- **الهدف الأعلى:** {state['north_star_ar']}",
        f"- **دور Gold-20:** {state['gold_20_role_ar']}",
        "",
        "### قاعدة تحديث المشروع",
        "",
        state["progress_policy_ar"],
        "",
    ]

    if latest:
        lines.extend(
            [
                "### أحدث خطوة كبيرة",
                "",
                f"- **المعرّف:** `{latest.get('milestone_id', '')}`",
                f"- **العنوان:** {latest.get('title_ar', '')}",
                f"- **الحالة:** `{latest.get('status', '')}`",
                f"- **الملخص:** {latest.get('summary_ar', '')}",
                f"- **الخطوة التالية:** {latest.get('next_action_ar', '')}",
                "",
            ]
        )

    if milestones:
        lines.extend(
            [
                "### أحدث Milestones",
                "",
            ]
        )

        for milestone in reversed(milestones[-8:]):
            lines.append(
                "- "
                f"`{milestone.get('status', '')}` — "
                f"{milestone.get('title_ar', '')} "
                f"(`{milestone.get('milestone_id', '')}`)"
            )

        lines.append("")

    lines.extend(
        [
            "السجل المنظم:",
            "",
            "`docs/execution/project-milestones.json`",
            AUTO_END,
        ]
    )

    return "\n".join(lines)


def update_progress_document(
    path: Path,
    managed_block: str,
) -> None:
    original = (
        path.read_text(encoding="utf-8-sig")
        if path.is_file()
        else "# SIRAJ OS\n## Master Development Roadmap\n"
    )

    if AUTO_BEGIN in original and AUTO_END in original:
        start = original.index(AUTO_BEGIN)
        end = original.index(
            AUTO_END,
            start,
        ) + len(AUTO_END)

        updated = (
            original[:start].rstrip()
            + "\n\n"
            + managed_block
            + "\n\n"
            + original[end:].lstrip()
        )

    else:
        lines = original.splitlines()

        insert_at = 0

        if lines and lines[0].startswith("# "):
            insert_at = 1

            if (
                len(lines) > 1
                and lines[1].startswith("## ")
            ):
                insert_at = 2

        lines[insert_at:insert_at] = [
            "",
            managed_block,
            "",
        ]

        updated = "\n".join(lines)

    if not updated.endswith("\n"):
        updated += "\n"

    atomic_write_text(path, updated)


def record_milestone(
    *,
    project_progress_path: Path,
    ledger_path: Path,
    milestone_id: str,
    title_ar: str,
    status: str,
    summary_ar: str,
    next_action_ar: str,
    recorded_at: str | None = None,
    changed_files: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    program_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    milestone_id = milestone_id.strip()

    if not milestone_id:
        raise ValueError("MILESTONE_ID_REQUIRED")

    ledger = load_ledger(ledger_path)

    ledger["program_state"] = {
        **DEFAULT_PROGRAM_STATE,
        **ledger.get("program_state", {}),
        **(program_state or {}),
    }

    milestone = {
        "milestone_id": milestone_id,
        "recorded_at": recorded_at or utc_now(),
        "title_ar": title_ar.strip(),
        "status": status.strip(),
        "summary_ar": summary_ar.strip(),
        "next_action_ar": next_action_ar.strip(),
        "changed_files": sorted(
            set(changed_files or [])
        ),
        "evidence": evidence or [],
        "metadata": metadata or {},
    }

    milestones = [
        item
        for item in ledger.get("milestones", [])
        if item.get("milestone_id") != milestone_id
    ]

    milestones.append(milestone)

    milestones.sort(
        key=lambda item: (
            str(item.get("recorded_at", "")),
            str(item.get("milestone_id", "")),
        )
    )

    ledger["milestones"] = milestones
    ledger["updated_at"] = utc_now()

    atomic_write_json(
        ledger_path,
        ledger,
    )

    update_progress_document(
        project_progress_path,
        render_managed_block(ledger),
    )

    return milestone
