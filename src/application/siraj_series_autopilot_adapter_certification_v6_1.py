from __future__ import annotations
import json, os
from pathlib import Path

CERTIFIED={
"AUDIO_TIMESTAMPS_AND_BEATS":"src.application.siraj_audio_timeline_v6_1:build_audio_timestamps_and_beats",
"AUDIO_BOUND_STORYBOARD":"src.application.siraj_downstream_luna_adapters_v6_1:audio_bound_storyboard",
"LUNA_SEMANTIC_PROMPT_DIRECTION":"src.application.siraj_downstream_luna_adapters_v6_1:semantic_prompt_direction",
"NARRATION_VISUAL_ALIGNMENT_GATE":"src.application.siraj_downstream_luna_adapters_v6_1:narration_visual_alignment",
"PROMPT_SIMILARITY_AND_DUPLICATE_GATE":"src.application.siraj_prompt_duplicate_gate_v6_1:run_prompt_similarity_gate",
"MEDIA_COST_PREFLIGHT":"src.application.siraj_media_cost_preflight_v6_1:build_media_cost_preflight",
"SEMANTIC_EDITORIAL_AND_TECHNICAL_QA":"src.application.siraj_downstream_luna_adapters_v6_1:semantic_editorial_qa",
}

def apply_wave1_certification(repo_root:Path):
    repo=Path(repo_root).resolve()
    path=repo/"projects/_series/siraj-series-autopilot-backend-certifications-v6.1.json"
    payload={"schema_version":"siraj-series-autopilot-backend-certifications-v6.1","status":"ACTIVE","certified":CERTIFIED,
             "not_yet_certified":["PROVIDER_EXECUTION","LOCAL_ASSEMBLY_AND_MONTAGE"],
             "automatic_paid_retry":False,"structural_change_requires_human":True}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return path
