from __future__ import annotations
import json, os, uuid, urllib.request, urllib.error
from pathlib import Path
from typing import Any, Mapping

class LunaStageV6Error(RuntimeError): pass

PAID_STAGES={
"AUDIO_BOUND_STORYBOARD",
"LUNA_SEMANTIC_PROMPT_DIRECTION",
"NARRATION_VISUAL_ALIGNMENT_GATE",
"SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
}

def _read(p):
    v=json.loads(Path(p).read_text(encoding="utf-8-sig"))
    if not isinstance(v,dict): raise LunaStageV6Error("JSON_OBJECT_REQUIRED")
    return v

def _write(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    os.replace(t,p)

def _key():
    value=os.environ.get("OPENAI_API_KEY","").strip()
    if value: return value
    try:
        import src.application.provider_credentials_v1 as c
        fn=getattr(c,"read_openai_api_key",None)
        if callable(fn):
            value=str(fn() or "").strip()
            if value: return value
    except Exception:
        pass
    raise LunaStageV6Error("OPENAI_API_KEY_REQUIRED")

def prepare_authorization(repo_root:Path,episode_id:str,stage:str,input_sha256:str):
    if stage not in PAID_STAGES: raise LunaStageV6Error("UNKNOWN_LUNA_STAGE")
    repo=Path(repo_root).resolve()
    path=repo/"projects"/episode_id/"orchestration"/f"{stage.lower()}-paid-authorization-v6-1.json"
    return path

def execute_authorized_json_stage(repo_root:Path,episode_id:str,stage:str,instructions:str,input_payload:Mapping[str,Any],output_path_relative:str):
    if stage not in PAID_STAGES: raise LunaStageV6Error("UNKNOWN_LUNA_STAGE")
    repo=Path(repo_root).resolve()
    auth=repo/"projects"/episode_id/"orchestration"/f"{stage.lower()}-paid-authorization-v6-1.json"
    if not auth.is_file(): raise LunaStageV6Error("EXPLICIT_PAID_AUTHORIZATION_REQUIRED:"+stage)
    a=_read(auth)
    if a.get("status")!="ACTIVE" or a.get("stage")!=stage or a.get("automatic_retry") is not False:
        raise LunaStageV6Error("PAID_AUTHORIZATION_INVALID:"+stage)
    request_id=str(uuid.uuid4())
    lock=repo/"projects"/episode_id/"orchestration"/"luna-v6-1"/stage.lower()/f"{request_id}.lock.json"
    if lock.exists(): raise LunaStageV6Error("ATTEMPT_ALREADY_LOCKED")
    _write(lock,{"stage":stage,"request_id":request_id,"status":"LOCKED_BEFORE_NETWORK","automatic_retry":False})
    body={
      "model":a.get("model") or os.environ.get("SIRAJ_LUNA_MODEL") or "gpt-5.6-luna",
      "input":[{"role":"system","content":[{"type":"input_text","text":"You are Luna, SIRAJ's MAX cinematic research and production director. Return valid JSON only."}]},
               {"role":"user","content":[{"type":"input_text","text":instructions+"\n\nINPUT:\n"+json.dumps(input_payload,ensure_ascii=False)}]}],
      "reasoning":{"effort":"high"},
    }
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(body,ensure_ascii=False).encode("utf-8"),method="POST",headers={"Authorization":"Bearer "+_key(),"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=300) as r:
            response=json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        _write(lock,{**_read(lock),"status":"RESULT_UNKNOWN_OR_FAILED_NO_AUTOMATIC_RETRY","error":str(exc)})
        raise LunaStageV6Error("PAID_STAGE_FAILED_RETRY_AUTH_REQUIRED:"+stage+":"+str(exc)) from exc
    texts=[]
    for item in response.get("output",[]):
        if isinstance(item,dict):
            for b in item.get("content",[]):
                if isinstance(b,dict) and b.get("type")=="output_text": texts.append(str(b.get("text") or ""))
    raw="".join(texts).strip()
    try: payload=json.loads(raw)
    except Exception as exc:
        _write(lock,{**_read(lock),"status":"INVALID_OUTPUT_NO_AUTOMATIC_RETRY"})
        raise LunaStageV6Error("INVALID_LUNA_OUTPUT_RETRY_AUTH_REQUIRED:"+stage) from exc
    out=repo/"projects"/episode_id/output_path_relative
    _write(out,payload if isinstance(payload,dict) else {"result":payload})
    _write(lock,{**_read(lock),"status":"COMPLETE","response_id":response.get("id"),"output_path_relative":output_path_relative})
    return out
