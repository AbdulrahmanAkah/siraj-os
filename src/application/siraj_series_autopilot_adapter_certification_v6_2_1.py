"""Certification update for V6.2.1 Wave 2."""
from __future__ import annotations
import json
from pathlib import Path

WAVE2_CERTIFIED = {
    "LUNA_SEMANTIC_PROMPT_DIRECTION": (
        "src.application.siraj_downstream_luna_adapters_v6_2_1:"
        "semantic_prompt_direction"
    ),
    "NARRATION_VISUAL_ALIGNMENT_GATE": (
        "src.application.siraj_downstream_luna_adapters_v6_2_1:"
        "narration_visual_alignment"
    ),
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": (
        "src.application.siraj_duplicate_gates_v6_2_1:"
        "validate_pre_spend_duplicates"
    ),
    "MEDIA_COST_PREFLIGHT": (
        "src.application.siraj_media_cost_preflight_v6_2_1:"
        "build_media_cost_preflight"
    ),
    "PROVIDER_EXECUTION": (
        "src.application.siraj_provider_execution_v6_2_1:"
        "execute_queue"
    ),
    "LOCAL_ASSEMBLY_AND_MONTAGE": (
        "src.application.siraj_local_assembly_montage_v6_2_1:"
        "assemble_episode_master"
    ),
}


def apply_wave2_certification(
    repo_root: Path,
) -> Path:
    repo = Path(repo_root).resolve()
    path = (
        repo
        / "projects/_series/"
        "siraj-series-autopilot-backend-certifications-v6.1.json"
    )
    if path.is_file():
        data = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    else:
        data = {
            "schema_version": (
                "siraj-series-autopilot-backend-certifications-v6.1"
            ),
            "status": "ACTIVE",
            "certified": {},
        }

    certified = data.setdefault(
        "certified",
        {},
    )
    certified.update(WAVE2_CERTIFIED)
    data["wave2_status"] = "V6.2.1_ACTIVE"
    data["visual_mix_policy"] = (
        "TWO_THIRDS_VIDEO_CEILING"
    )
    data["duplicate_hardening"] = "ACTIVE"
    data["automatic_paid_retry"] = False

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
