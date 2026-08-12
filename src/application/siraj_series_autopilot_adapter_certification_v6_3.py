"""Wave 3 certification for all seven future-episode upstream stages."""

from __future__ import annotations

import json
from pathlib import Path

WAVE3_CERTIFIED = {
    "TOPIC_SELECTION": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_topic_selection"
    ),
    "SOURCE_RESEARCH_FROM_ZERO": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_source_research"
    ),
    "SOURCE_CLAIM_MATRIX": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_source_claim_matrix"
    ),
    "STORY_ARCHITECTURE": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_story_architecture"
    ),
    "ICONIC_CINEMATIC_REVIEW": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_iconic_cinematic_review"
    ),
    "FINAL_SCRIPT": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_final_script"
    ),
    "PRONUNCIATION_AND_PERFORMANCE_GATE": (
        "src.application.siraj_upstream_autopilot_v6_3:"
        "run_pronunciation_performance_gate"
    ),
}


def apply_wave3_certification(repo_root: Path) -> Path:
    repo = Path(repo_root).resolve()
    path = (
        repo
        / "projects/_series/"
        "siraj-series-autopilot-backend-certifications-v6.1.json"
    )
    if path.is_file():
        payload = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    else:
        payload = {
            "schema_version": (
                "siraj-series-autopilot-backend-certifications-v6.1"
            ),
            "status": "ACTIVE",
            "certified": {},
        }

    certified = payload.setdefault("certified", {})
    certified.update(WAVE3_CERTIFIED)
    payload["wave3_status"] = "V6.3_ACTIVE"
    payload["future_episode_upstream"] = "CERTIFIED"
    payload["fresh_research_from_zero"] = True
    payload["full_pronunciation_gate"] = True
    payload["automatic_paid_retry"] = False
    payload["assistant_authored_luna_cost_cap_usd"] = None
    payload["assistant_authored_luna_call_cap"] = None

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
