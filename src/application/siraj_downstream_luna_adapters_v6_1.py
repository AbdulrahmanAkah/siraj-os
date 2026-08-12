from __future__ import annotations
from pathlib import Path
from src.application.siraj_luna_stage_transport_v6_1 import execute_authorized_json_stage

def audio_bound_storyboard(repo_root:Path,episode_id:str,timeline:dict,script:dict):
    return execute_authorized_json_stage(repo_root,episode_id,"AUDIO_BOUND_STORYBOARD",
    """Create an audio-bound cinematic storyboard. Preserve claim/script truth. Every shot must bind to exact narration time ranges. One memorable visual idea per major beat. Paradise/unseen material must be transcendent and restrained. Return JSON object with status PASS, shots list, continuity anchors, and self_review PASS.""",
    {"timeline":timeline,"script":script},"preproduction/audio-bound-storyboard-v6-1.json")

def semantic_prompt_direction(repo_root:Path,episode_id:str,storyboard:dict):
    return execute_authorized_json_stage(repo_root,episode_id,"LUNA_SEMANTIC_PROMPT_DIRECTION",
    """Convert each certified storyboard shot into production prompts. Include semantic beat, subject, environment, composition, lens/camera, movement, lighting, materials/palette, continuity anchors, relation to adjacent shots, forbidden/generic elements. No generated Arabic text. Return JSON with status PASS and items.""",
    storyboard,"preproduction/luna-semantic-prompt-direction-v6-1.json")

def narration_visual_alignment(repo_root:Path,episode_id:str,script:dict,prompts:dict):
    return execute_authorized_json_stage(repo_root,episode_id,"NARRATION_VISUAL_ALIGNMENT_GATE",
    """Audit every visual prompt against the exact narration semantic beat. Fail any generic, contradictory, temporally misplaced, theologically invented, or weakly supportive visual. Return JSON status PASS only when every item passes.""",
    {"script":script,"prompts":prompts},"preproduction/narration-visual-alignment-gate-v6-1.json")

def semantic_editorial_qa(repo_root:Path,episode_id:str,master_manifest:dict):
    return execute_authorized_json_stage(repo_root,episode_id,"SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
    """Perform final semantic/editorial review of the assembled episode manifest and technical QA evidence. Check narration-visual meaning, dignity, continuity, pacing, accidental repetition, generic AI visuals, religious/source fidelity, and readiness for human watch. Return PASS only if ready for final human review.""",
    master_manifest,"deliverables/final-semantic-editorial-qa-v6-1.json")
