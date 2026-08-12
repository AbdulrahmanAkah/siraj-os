from __future__ import annotations
import json, os
from pathlib import Path
from src.application.siraj_final_tts_queue_selector_v6_3_2 import resolve_final_tts_queue_path

class AudioTimelineV6Error(RuntimeError): pass

def _read(p):
    v=json.loads(Path(p).read_text(encoding="utf-8-sig"))
    if not isinstance(v,dict): raise AudioTimelineV6Error("JSON_OBJECT_REQUIRED")
    return v

def _write(p,v):
    p=Path(p); p.parent.mkdir(parents=True,exist_ok=True)
    t=p.with_suffix(p.suffix+".tmp")
    t.write_text(json.dumps(v,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    os.replace(t,p)

def build_audio_timestamps_and_beats(repo_root: Path, episode_id: str):
    repo=Path(repo_root).resolve()
    ep=repo/"projects"/episode_id
    q=_read(resolve_final_tts_queue_path(repo, episode_id))
    items=q.get("items")
    if not isinstance(items,list) or not items:
        raise AudioTimelineV6Error("FINAL_TTS_QUEUE_ITEMS_REQUIRED")
    timeline=[]; cursor=0.0
    for item in sorted(items,key=lambda x:int(x.get("queue_index",0) or 0)):
        if item.get("status")!="COMPLETE":
            raise AudioTimelineV6Error("FINAL_TTS_NOT_COMPLETE:"+str(item.get("queue_id")))
        duration=item.get("duration_seconds")
        if not isinstance(duration,(int,float)) or duration<=0:
            raise AudioTimelineV6Error("TTS_DURATION_REQUIRED:"+str(item.get("queue_id")))
        start=cursor; end=start+float(duration)
        pause=float(item.get("pause_after_seconds",0) or 0)
        timeline.append({
            "queue_id":item.get("queue_id"),
            "segment_id":item.get("segment_id"),
            "beat_id":item.get("beat_id"),
            "start_seconds":round(start,3),
            "speech_end_seconds":round(end,3),
            "pause_after_seconds":round(pause,3),
            "end_seconds":round(end+pause,3),
            "audio_path_relative":item.get("output_path_relative"),
        })
        cursor=end+pause
    out=ep/"preproduction/audio-timestamps-and-beats-v6-1.json"
    _write(out,{
        "schema_version":"siraj-audio-timestamps-and-beats-v6.1",
        "status":"PASS",
        "episode_id":episode_id,
        "total_duration_seconds":round(cursor,3),
        "beats":timeline,
        "next_stage":"AUDIO_BOUND_STORYBOARD",
    })
    return out
