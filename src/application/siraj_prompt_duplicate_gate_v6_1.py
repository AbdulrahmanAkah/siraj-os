from __future__ import annotations
import json, math, os, re
from collections import Counter
from pathlib import Path

class PromptDuplicateGateV6Error(RuntimeError): pass
WORD=re.compile(r"[\w\u0600-\u06ff]+",re.UNICODE)

def _tokens(s): return [x.lower() for x in WORD.findall(str(s or ""))]

def _cos(a,b):
    ca,cb=Counter(_tokens(a)),Counter(_tokens(b))
    if not ca or not cb: return 0.0
    dot=sum(v*cb.get(k,0) for k,v in ca.items())
    na=math.sqrt(sum(v*v for v in ca.values())); nb=math.sqrt(sum(v*v for v in cb.values()))
    return dot/(na*nb) if na and nb else 0.0

def prompt_text(item):
    """Return the canonical provider-ready prompt without provider activity."""
    return str(
        item.get("provider_ready_prompt")
        or item.get("runware_positive_prompt_en")
        or item.get("prompt")
        or item.get("prompt_en")
        or item.get("prompt_text")
        or ""
    )


def validate_prompt_similarity(items, threshold=0.93):
    problems=[]
    for i,a in enumerate(items):
        pa=prompt_text(a)
        if not pa.strip(): problems.append({"type":"EMPTY_PROMPT","index":i}); continue
        for j in range(i):
            b=items[j]
            pb=prompt_text(b)
            score=_cos(pa,pb)
            if score>=threshold:
                problems.append({"type":"NEAR_DUPLICATE","a":j,"b":i,"score":round(score,4)})
    return problems

def run_prompt_similarity_gate(repo_root: Path, episode_id: str, prompt_plan_relative: str):
    repo=Path(repo_root).resolve()
    p=repo/"projects"/episode_id/prompt_plan_relative
    data=json.loads(p.read_text(encoding="utf-8-sig"))
    items=data.get("items") or data.get("shots") or data.get("prompts")
    if not isinstance(items,list): raise PromptDuplicateGateV6Error("PROMPT_ITEMS_REQUIRED")
    problems=validate_prompt_similarity(items)
    out=repo/"projects"/episode_id/"orchestration/prompt-similarity-duplicate-gate-v6-1.json"
    payload={"schema_version":"siraj-prompt-similarity-duplicate-gate-v6.1","status":"PASS" if not problems else "FAIL","problems":problems}
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if problems: raise PromptDuplicateGateV6Error("PROMPT_DUPLICATE_GATE_FAILED")
    return out
