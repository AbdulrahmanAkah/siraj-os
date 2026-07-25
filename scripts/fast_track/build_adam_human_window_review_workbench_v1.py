from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EPISODE_ID = "episode-001-adam"
SCHEMA_VERSION = "siraj-adam-human-window-review-workbench-v1"
STAGE_MAP = {
    "CREATION_DECREE": "01_CREATION_DECREE",
    "CREATION_MATERIAL": "02_CREATION_MATERIAL",
    "SPIRIT_AND_FORM": "03_SPIRIT_AND_FORM",
    "TEACHING_NAMES": "04_TEACHING_NAMES",
    "HONOUR_AND_STATUS": "05_HONOUR_AND_STATUS",
    "ANGELIC_PROSTRATION": "06_ANGELIC_PROSTRATION",
    "PARADISE_RESIDENCE": "07_PARADISE_RESIDENCE",
    "HADITH_ANCHORS": "08_HADITH_ANCHORS",
    "ADAM_PRIMARY": "00_GENERAL_ADAM",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{line_number}"
                )
            yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def tier_count(window: dict[str, Any], tier: str) -> int:
    counts = window.get("candidate_tier_counts") or {}
    return safe_int(counts.get(tier), 0)


def stage_labels(window: dict[str, Any]) -> list[str]:
    categories = list(window.get("matched_categories") or [])
    labels = sorted(
        {
            STAGE_MAP[category]
            for category in categories
            if category in STAGE_MAP
        }
    )
    return labels or ["99_UNMAPPED"]


def review_priority(window: dict[str, Any]) -> int:
    return (
        safe_int(window.get("aggregate_window_score"))
        + tier_count(window, "A") * 80
        + tier_count(window, "B") * 30
        + tier_count(window, "C") * 8
        + len(window.get("matched_categories") or []) * 12
        + (120 if window.get("attribution_profiles") else 0)
        - (30 if window.get("text_truncated") else 0)
    )


def compact_window(window: dict[str, Any], queue: str) -> dict[str, Any]:
    pages = []
    for page in window.get("pages") or []:
        pages.append(
            {
                "sequence_num": page.get("sequence_num"),
                "shamela_page_id": page.get("shamela_page_id"),
                "canonical_locator": page.get("canonical_locator"),
                "volume": page.get("volume"),
                "page_num": page.get("page_num"),
                "page_label": page.get("page_label"),
                "headings": page.get("headings") or [],
                "text": page.get("text") or "",
                "text_truncated": bool(page.get("text_truncated")),
            }
        )

    return {
        "window_id": window["window_id"],
        "queue": queue,
        "work_source_id": window["work_source_id"],
        "book_id": window["book_id"],
        "book_title": window.get("book_title", ""),
        "sequence_start": window.get("sequence_start"),
        "sequence_end": window.get("sequence_end"),
        "page_count": window.get("page_count"),
        "candidate_count": window.get("candidate_count"),
        "candidate_tier_counts": window.get("candidate_tier_counts") or {},
        "maximum_candidate_score": window.get("maximum_candidate_score"),
        "aggregate_window_score": window.get("aggregate_window_score"),
        "review_priority": review_priority(window),
        "matched_categories": window.get("matched_categories") or [],
        "stages": stage_labels(window),
        "attribution_profiles": window.get("attribution_profiles") or [],
        "character_count": window.get("character_count"),
        "text_truncated": bool(window.get("text_truncated")),
        "source_locators": window.get("source_locators") or [],
        "pages": pages,
        "permissions": {
            "candidate_only": True,
            "allowed_for_gemini": False,
            "approved_for_evidence": False,
            "approved_for_quotation": False,
        },
    }


def choose_shortlist(
    windows: list[dict[str, Any]],
    *,
    shortlist_limit: int,
    minimum_per_source: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ordered = sorted(
        windows,
        key=lambda row: (
            -review_priority(row),
            str(row["work_source_id"]),
            safe_int(row.get("sequence_start")),
        ),
    )

    selected_ids: set[str] = set()
    selected: list[dict[str, Any]] = []

    def add(row: dict[str, Any]) -> bool:
        window_id = str(row["window_id"])
        if window_id in selected_ids or len(selected) >= shortlist_limit:
            return False
        selected_ids.add(window_id)
        selected.append(row)
        return True

    # Attribution windows are always surfaced for human inspection.
    for row in ordered:
        if row.get("attribution_profiles"):
            add(row)

    # Ensure a minimum source representation.
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        by_source[str(row["work_source_id"])].append(row)

    for source_id in sorted(by_source):
        count = sum(
            1 for row in selected
            if str(row["work_source_id"]) == source_id
        )
        for row in by_source[source_id]:
            if count >= minimum_per_source:
                break
            if add(row):
                count += 1

    # Greedy coverage of source/category and source/stage pairs.
    uncovered: set[tuple[str, str, str]] = set()
    for row in ordered:
        source = str(row["work_source_id"])
        for category in row.get("matched_categories") or []:
            uncovered.add(("CATEGORY", source, str(category)))
        for stage in stage_labels(row):
            uncovered.add(("STAGE", source, stage))

    for row in selected:
        source = str(row["work_source_id"])
        for category in row.get("matched_categories") or []:
            uncovered.discard(("CATEGORY", source, str(category)))
        for stage in stage_labels(row):
            uncovered.discard(("STAGE", source, stage))

    while uncovered and len(selected) < shortlist_limit:
        best = None
        best_key = None
        for row in ordered:
            if str(row["window_id"]) in selected_ids:
                continue
            source = str(row["work_source_id"])
            covered = {
                ("CATEGORY", source, str(category))
                for category in row.get("matched_categories") or []
            }
            covered.update(
                ("STAGE", source, stage)
                for stage in stage_labels(row)
            )
            gain = len(covered & uncovered)
            key = (
                gain,
                review_priority(row),
                tier_count(row, "A"),
                tier_count(row, "B"),
                -safe_int(row.get("sequence_start")),
            )
            if best_key is None or key > best_key:
                best = row
                best_key = key

        if best is None or best_key is None or best_key[0] == 0:
            break

        add(best)
        source = str(best["work_source_id"])
        for category in best.get("matched_categories") or []:
            uncovered.discard(("CATEGORY", source, str(category)))
        for stage in stage_labels(best):
            uncovered.discard(("STAGE", source, stage))

    for row in ordered:
        if len(selected) >= shortlist_limit:
            break
        add(row)

    selected.sort(
        key=lambda row: (
            -review_priority(row),
            str(row["work_source_id"]),
            safe_int(row.get("sequence_start")),
        )
    )
    reserve = [
        row for row in ordered
        if str(row["window_id"]) not in selected_ids
    ]
    return selected, reserve


def write_queue_csv(
    path: Path,
    rows: list[dict[str, Any]],
    queue_name: str,
) -> None:
    fields = [
        "queue",
        "rank",
        "window_id",
        "work_source_id",
        "book_id",
        "book_title",
        "sequence_start",
        "sequence_end",
        "page_count",
        "candidate_count",
        "review_priority",
        "aggregate_window_score",
        "tier_A",
        "tier_B",
        "tier_C",
        "tier_D",
        "stages",
        "matched_categories",
        "attribution_profiles",
        "character_count",
        "text_truncated",
        "decision",
        "scope_fit",
        "duplicate_group",
        "reviewer_notes",
        "first_locator",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for rank, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "queue": queue_name,
                    "rank": rank,
                    "window_id": row["window_id"],
                    "work_source_id": row["work_source_id"],
                    "book_id": row["book_id"],
                    "book_title": row.get("book_title", ""),
                    "sequence_start": row.get("sequence_start"),
                    "sequence_end": row.get("sequence_end"),
                    "page_count": row.get("page_count"),
                    "candidate_count": row.get("candidate_count"),
                    "review_priority": review_priority(row),
                    "aggregate_window_score": row.get(
                        "aggregate_window_score"
                    ),
                    "tier_A": tier_count(row, "A"),
                    "tier_B": tier_count(row, "B"),
                    "tier_C": tier_count(row, "C"),
                    "tier_D": tier_count(row, "D"),
                    "stages": " | ".join(stage_labels(row)),
                    "matched_categories": " | ".join(
                        row.get("matched_categories") or []
                    ),
                    "attribution_profiles": " | ".join(
                        row.get("attribution_profiles") or []
                    ),
                    "character_count": row.get("character_count"),
                    "text_truncated": bool(row.get("text_truncated")),
                    "decision": "",
                    "scope_fit": "",
                    "duplicate_group": "",
                    "reviewer_notes": "",
                    "first_locator": (
                        (row.get("source_locators") or [""])[0]
                    ),
                }
            )


def html_document(
    *,
    manifest: dict[str, Any],
    windows: list[dict[str, Any]],
) -> str:
    embedded = json.dumps(
        {
            "manifest": manifest,
            "windows": windows,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return """<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SIRAJ — مراجعة نوافذ حلقة آدم</title>
<style>
:root { font-family: "Segoe UI", Tahoma, Arial, sans-serif; }
body { margin: 0; background: #f3f4f6; color: #111827; }
header { position: sticky; top: 0; z-index: 5; background: white; padding: 14px 18px; border-bottom: 1px solid #d1d5db; }
h1 { font-size: 20px; margin: 0 0 8px; }
.toolbar { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 8px; }
input, select, button, textarea { font: inherit; }
input, select { padding: 8px; border: 1px solid #9ca3af; border-radius: 6px; background: white; }
button { padding: 8px 11px; border: 1px solid #6b7280; border-radius: 6px; background: white; cursor: pointer; }
button:hover { background: #e5e7eb; }
.summary { margin-top: 8px; font-size: 13px; color: #374151; }
main { padding: 16px; max-width: 1500px; margin: auto; }
.card { background: white; border: 1px solid #d1d5db; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.card-head { padding: 12px; display: grid; grid-template-columns: 1fr auto; gap: 12px; }
.meta { font-size: 13px; color: #374151; line-height: 1.7; }
.badge { display: inline-block; padding: 2px 7px; margin: 2px; border-radius: 999px; background: #e5e7eb; font-size: 12px; }
.badge.attr { background: #fef3c7; }
.badge.stage { background: #dbeafe; }
.actions { display: flex; flex-wrap: wrap; gap: 6px; align-content: start; }
.actions button.active { background: #111827; color: white; }
.details { border-top: 1px solid #e5e7eb; padding: 12px; display: none; }
.details.open { display: block; }
.page { border-right: 4px solid #9ca3af; padding: 8px 12px; margin: 10px 0; background: #f9fafb; }
.page-head { font-size: 12px; color: #4b5563; direction: ltr; text-align: left; }
.page-text { white-space: pre-wrap; line-height: 1.85; font-size: 15px; }
.notes { width: 100%; min-height: 70px; box-sizing: border-box; padding: 8px; margin-top: 8px; }
.hidden { display: none; }
footer { padding: 20px; text-align: center; color: #6b7280; font-size: 12px; }
@media (max-width: 900px) {
  .toolbar { grid-template-columns: 1fr 1fr; }
  .card-head { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
  <h1>مراجعة نوافذ حلقة آدم عليه السلام</h1>
  <div class="toolbar">
    <select id="queueFilter">
      <option value="SHORTLIST">القائمة الأولية</option>
      <option value="RESERVE">الاحتياط</option>
      <option value="ALL">الكل</option>
    </select>
    <select id="sourceFilter"><option value="">كل المصادر</option></select>
    <select id="stageFilter"><option value="">كل المراحل</option></select>
    <select id="decisionFilter">
      <option value="">كل القرارات</option>
      <option value="PENDING">قيد المراجعة</option>
      <option value="INCLUDE">تضمين</option>
      <option value="EXCLUDE">استبعاد</option>
      <option value="DEFER">تأجيل</option>
    </select>
    <input id="searchBox" placeholder="بحث في العناوين والنص">
    <button id="exportButton">تصدير القرارات JSON</button>
  </div>
  <div class="summary" id="summary"></div>
</header>
<main id="cards"></main>
<footer>لا يغيّر هذا الملف أي اعتماد. تُصدَّر القرارات للمراجعة والاستيراد المنضبط لاحقًا.</footer>
<script id="siraj-data" type="application/json">""" + embedded + """</script>
<script>
const data = JSON.parse(document.getElementById("siraj-data").textContent);
const windows = data.windows;
const storageKey = "siraj-adam-window-review-v1";
let decisions = JSON.parse(localStorage.getItem(storageKey) || "{}");

const queueFilter = document.getElementById("queueFilter");
const sourceFilter = document.getElementById("sourceFilter");
const stageFilter = document.getElementById("stageFilter");
const decisionFilter = document.getElementById("decisionFilter");
const searchBox = document.getElementById("searchBox");
const cards = document.getElementById("cards");
const summary = document.getElementById("summary");

function unique(values) {
  return [...new Set(values)].sort();
}

for (const source of unique(windows.map(w => w.work_source_id))) {
  const option = document.createElement("option");
  option.value = source;
  option.textContent = source;
  sourceFilter.appendChild(option);
}
for (const stage of unique(windows.flatMap(w => w.stages))) {
  const option = document.createElement("option");
  option.value = stage;
  option.textContent = stage;
  stageFilter.appendChild(option);
}

function getDecision(id) {
  return decisions[id] || {
    decision: "PENDING",
    scope_fit: "",
    duplicate_group: "",
    reviewer_notes: ""
  };
}

function saveDecision(id, patch) {
  decisions[id] = {...getDecision(id), ...patch};
  localStorage.setItem(storageKey, JSON.stringify(decisions));
}

function textForSearch(w) {
  return [
    w.work_source_id,
    w.book_title,
    ...(w.matched_categories || []),
    ...(w.stages || []),
    ...(w.attribution_profiles || []),
    ...w.pages.flatMap(p => [...(p.headings || []), p.text || ""])
  ].join(" ").toLowerCase();
}

function visibleWindows() {
  const q = searchBox.value.trim().toLowerCase();
  return windows.filter(w => {
    const decision = getDecision(w.window_id).decision;
    if (queueFilter.value !== "ALL" && w.queue !== queueFilter.value) return false;
    if (sourceFilter.value && w.work_source_id !== sourceFilter.value) return false;
    if (stageFilter.value && !w.stages.includes(stageFilter.value)) return false;
    if (decisionFilter.value && decision !== decisionFilter.value) return false;
    if (q && !textForSearch(w).includes(q)) return false;
    return true;
  });
}

function badge(text, cls="") {
  const span = document.createElement("span");
  span.className = "badge " + cls;
  span.textContent = text;
  return span;
}

function render() {
  const visible = visibleWindows();
  cards.innerHTML = "";
  const counts = {PENDING: 0, INCLUDE: 0, EXCLUDE: 0, DEFER: 0};
  for (const w of windows) counts[getDecision(w.window_id).decision]++;

  summary.textContent =
    `المعروض: ${visible.length} | الأولية: ${windows.filter(w => w.queue === "SHORTLIST").length}` +
    ` | الاحتياط: ${windows.filter(w => w.queue === "RESERVE").length}` +
    ` | تضمين: ${counts.INCLUDE} | استبعاد: ${counts.EXCLUDE} | تأجيل: ${counts.DEFER}` +
    ` | قيد المراجعة: ${counts.PENDING}`;

  for (const w of visible) {
    const state = getDecision(w.window_id);
    const card = document.createElement("section");
    card.className = "card";

    const head = document.createElement("div");
    head.className = "card-head";

    const info = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = `${w.work_source_id} — ${w.book_title}`;
    info.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      `النافذة ${w.window_id} | التسلسل ${w.sequence_start}–${w.sequence_end}` +
      ` | الصفحات ${w.page_count} | المرشحون ${w.candidate_count}` +
      ` | الأولوية ${w.review_priority}`;
    info.appendChild(meta);

    for (const stage of w.stages) info.appendChild(badge(stage, "stage"));
    for (const category of w.matched_categories) info.appendChild(badge(category));
    for (const attr of w.attribution_profiles) info.appendChild(badge(attr, "attr"));

    const actions = document.createElement("div");
    actions.className = "actions";

    for (const decision of ["INCLUDE", "EXCLUDE", "DEFER"]) {
      const button = document.createElement("button");
      button.textContent =
        decision === "INCLUDE" ? "تضمين" :
        decision === "EXCLUDE" ? "استبعاد" : "تأجيل";
      if (state.decision === decision) button.classList.add("active");
      button.onclick = () => {
        saveDecision(w.window_id, {decision});
        render();
      };
      actions.appendChild(button);
    }

    const reset = document.createElement("button");
    reset.textContent = "إلغاء القرار";
    reset.onclick = () => {
      saveDecision(w.window_id, {decision: "PENDING"});
      render();
    };
    actions.appendChild(reset);

    const toggle = document.createElement("button");
    toggle.textContent = "عرض النص";
    actions.appendChild(toggle);

    head.appendChild(info);
    head.appendChild(actions);
    card.appendChild(head);

    const details = document.createElement("div");
    details.className = "details";

    for (const page of w.pages) {
      const pageBox = document.createElement("div");
      pageBox.className = "page";

      const pageHead = document.createElement("div");
      pageHead.className = "page-head";
      pageHead.textContent =
        `${page.canonical_locator} | sequence=${page.sequence_num}`;
      pageBox.appendChild(pageHead);

      if (page.headings && page.headings.length) {
        const headings = document.createElement("strong");
        headings.textContent = page.headings.join(" | ");
        pageBox.appendChild(headings);
      }

      const text = document.createElement("div");
      text.className = "page-text";
      text.textContent = page.text;
      pageBox.appendChild(text);
      details.appendChild(pageBox);
    }

    const scope = document.createElement("select");
    scope.innerHTML =
      '<option value="">ملاءمة النطاق: غير محدد</option>' +
      '<option value="IN_SCOPE">داخل النطاق</option>' +
      '<option value="MIXED">مختلط</option>' +
      '<option value="OUT_OF_SCOPE">خارج النطاق</option>';
    scope.value = state.scope_fit || "";
    scope.onchange = () => saveDecision(
      w.window_id, {scope_fit: scope.value}
    );
    details.appendChild(scope);

    const duplicate = document.createElement("input");
    duplicate.placeholder = "مجموعة التكرار، مثل DUP-01";
    duplicate.value = state.duplicate_group || "";
    duplicate.oninput = () => saveDecision(
      w.window_id, {duplicate_group: duplicate.value}
    );
    details.appendChild(duplicate);

    const notes = document.createElement("textarea");
    notes.className = "notes";
    notes.placeholder = "ملاحظات المراجع";
    notes.value = state.reviewer_notes || "";
    notes.oninput = () => saveDecision(
      w.window_id, {reviewer_notes: notes.value}
    );
    details.appendChild(notes);

    toggle.onclick = () => details.classList.toggle("open");
    card.appendChild(details);
    cards.appendChild(card);
  }
}

for (const control of [
  queueFilter, sourceFilter, stageFilter, decisionFilter, searchBox
]) {
  control.addEventListener("input", render);
  control.addEventListener("change", render);
}

document.getElementById("exportButton").onclick = () => {
  const rows = windows.map(w => {
    const state = getDecision(w.window_id);
    return {
      window_id: w.window_id,
      queue: w.queue,
      work_source_id: w.work_source_id,
      book_id: w.book_id,
      decision: state.decision,
      scope_fit: state.scope_fit,
      duplicate_group: state.duplicate_group,
      reviewer_notes: state.reviewer_notes
    };
  });

  const payload = {
    schema_version: "siraj-adam-human-window-decisions-v1",
    episode_id: "episode-001-adam",
    source_manifest_sha256: data.manifest.source_manifest_sha256,
    exported_at: new Date().toISOString(),
    decisions: rows
  };

  const blob = new Blob(
    [JSON.stringify(payload, null, 2)],
    {type: "application/json"}
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "adam-human-window-decisions-v1.json";
  link.click();
  URL.revokeObjectURL(url);
};

render();
</script>
</body>
</html>
"""


def write_test(repo: Path) -> Path:
    path = (
        repo
        / "tests"
        / "integration"
        / "test_adam_human_window_review_workbench_v1.py"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """from __future__ import annotations

import json
from pathlib import Path


def test_adam_human_window_review_workbench_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = (
        project
        / "sources"
        / "secondary"
        / "human-window-review"
    )
    manifest = json.loads(
        (root / "human-window-review-manifest-v1.json").read_text(
            encoding="utf-8-sig"
        )
    )

    assert manifest["status"] == "PASS_REVIEW_WORKBENCH_READY"
    assert manifest["source_window_count"] == 207
    assert manifest["shortlist_count"] > 0
    assert manifest["reserve_count"] >= 0
    assert (
        manifest["shortlist_count"] + manifest["reserve_count"]
        == manifest["source_window_count"]
    )
    assert manifest["permissions"]["gemini_execution_enabled"] is False
    assert manifest["permissions"]["source_approval_changed"] is False
    assert manifest["permissions"]["quotation_approval_changed"] is False
    assert manifest["permissions"]["report_classification_changed"] is False
    assert manifest["permissions"]["israiliyyat_classification_changed"] is False

    html_path = root / "adam-human-window-review-workbench-v1.html"
    assert html_path.is_file()
    document = html_path.read_text(encoding="utf-8")
    assert "siraj-adam-window-review-v1" in document
    assert "تصدير القرارات JSON" in document
    assert "allowed_for_gemini" in document
""",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--shortlist-limit", type=int, default=72)
    parser.add_argument("--minimum-per-source", type=int, default=4)
    args = parser.parse_args()

    if not 36 <= args.shortlist_limit <= 160:
        raise ValueError("SHORTLIST_LIMIT_OUT_OF_RANGE")
    if not 1 <= args.minimum_per_source <= 12:
        raise ValueError("MINIMUM_PER_SOURCE_OUT_OF_RANGE")

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    source_root = (
        project
        / "sources"
        / "secondary"
        / "bounded-review-windows"
    )
    source_manifest_path = (
        source_root / "bounded-review-window-manifest-v1.json"
    )
    source_manifest = read_json(source_manifest_path)

    if source_manifest.get("status") != (
        "PASS_HUMAN_REVIEW_QUEUE_READY"
    ):
        raise ValueError("BOUNDED_REVIEW_WINDOWS_NOT_READY")
    if safe_int(source_manifest.get("book_count")) != 9:
        raise ValueError("EXPECTED_NINE_BOOKS")
    if source_manifest.get("permissions", {}).get(
        "gemini_execution_enabled"
    ) is not False:
        raise ValueError("GEMINI_MUST_REMAIN_DISABLED")

    windows: list[dict[str, Any]] = []
    for book in source_manifest["books"]:
        path = project / book["outputs"]["review_windows"]["project_path"]
        if sha256_file(path) != book["outputs"]["review_windows"]["sha256"]:
            raise ValueError(
                f"WINDOW_CHECKSUM_MISMATCH:{book['work_source_id']}"
            )
        windows.extend(iter_jsonl(path))

    if len(windows) != safe_int(source_manifest["review_window_count"]):
        raise ValueError(
            "SOURCE_WINDOW_COUNT_MISMATCH:"
            f"manifest={source_manifest['review_window_count']}:"
            f"actual={len(windows)}"
        )

    shortlist, reserve = choose_shortlist(
        windows,
        shortlist_limit=args.shortlist_limit,
        minimum_per_source=args.minimum_per_source,
    )

    output_root = (
        project
        / "sources"
        / "secondary"
        / "human-window-review"
    )
    if output_root.exists():
        for child in output_root.iterdir():
            if child.is_file():
                child.unlink()
    output_root.mkdir(parents=True, exist_ok=True)

    shortlist_csv = output_root / "human-review-shortlist-v1.csv"
    reserve_csv = output_root / "human-review-reserve-v1.csv"
    write_queue_csv(shortlist_csv, shortlist, "SHORTLIST")
    write_queue_csv(reserve_csv, reserve, "RESERVE")

    compact_rows = [
        compact_window(row, "SHORTLIST") for row in shortlist
    ] + [
        compact_window(row, "RESERVE") for row in reserve
    ]

    source_counts = Counter(
        str(row["work_source_id"]) for row in shortlist
    )
    stage_counts = Counter(
        stage for row in shortlist for stage in stage_labels(row)
    )
    attribution_shortlist_count = sum(
        1 for row in shortlist if row.get("attribution_profiles")
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": EPISODE_ID,
        "status": "PASS_REVIEW_WORKBENCH_READY",
        "source_manifest": source_manifest_path.relative_to(
            project
        ).as_posix(),
        "source_manifest_sha256": sha256_file(
            source_manifest_path
        ),
        "source_window_count": len(windows),
        "shortlist_limit": args.shortlist_limit,
        "shortlist_count": len(shortlist),
        "reserve_count": len(reserve),
        "minimum_per_source": args.minimum_per_source,
        "shortlist_source_counts": dict(sorted(source_counts.items())),
        "shortlist_stage_counts": dict(sorted(stage_counts.items())),
        "shortlist_attribution_window_count": (
            attribution_shortlist_count
        ),
        "outputs": {
            "workbench_html": (
                "sources/secondary/human-window-review/"
                "adam-human-window-review-workbench-v1.html"
            ),
            "shortlist_csv": shortlist_csv.relative_to(
                project
            ).as_posix(),
            "reserve_csv": reserve_csv.relative_to(project).as_posix(),
            "expected_decisions_filename": (
                "adam-human-window-decisions-v1.json"
            ),
        },
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "evidence_approval_changed": False,
            "quotation_approval_changed": False,
            "report_classification_changed": False,
            "israiliyyat_classification_changed": False,
        },
        "next_gate": "HUMAN_REVIEW_DECISIONS_EXPORT",
        "created_at": now_utc(),
    }

    html_path = (
        output_root / "adam-human-window-review-workbench-v1.html"
    )
    html_path.write_text(
        html_document(manifest=manifest, windows=compact_rows),
        encoding="utf-8",
        newline="\n",
    )

    manifest["outputs"]["workbench_html_sha256"] = sha256_file(
        html_path
    )
    manifest["outputs"]["shortlist_csv_sha256"] = sha256_file(
        shortlist_csv
    )
    manifest["outputs"]["reserve_csv_sha256"] = sha256_file(
        reserve_csv
    )

    manifest_path = (
        output_root / "human-window-review-manifest-v1.json"
    )
    write_json(manifest_path, manifest)
    test_path = write_test(repo)

    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": str(manifest_path),
                "workbench_html": str(html_path),
                "shortlist_csv": str(shortlist_csv),
                "reserve_csv": str(reserve_csv),
                "integration_test": str(test_path),
                "counts": {
                    "source_windows": len(windows),
                    "shortlist": len(shortlist),
                    "reserve": len(reserve),
                    "attribution_windows_in_shortlist": (
                        attribution_shortlist_count
                    ),
                    "shortlist_source_counts": dict(
                        sorted(source_counts.items())
                    ),
                    "shortlist_stage_counts": dict(
                        sorted(stage_counts.items())
                    ),
                },
                "gemini_execution_enabled": False,
                "source_approval_changed": False,
                "quotation_approval_changed": False,
                "report_classification_changed": False,
                "israiliyyat_classification_changed": False,
                "next_gate": manifest["next_gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
