from __future__ import annotations
import json, os
from pathlib import Path

class MediaCostPreflightV6Error(RuntimeError): pass

def build_media_cost_preflight(repo_root: Path, episode_id: str, queue_relative: str):
    repo=Path(repo_root).resolve()
    p=repo/"projects"/episode_id/queue_relative
    q=json.loads(p.read_text(encoding="utf-8-sig"))
    items=q.get("items")
    if not isinstance(items,list):
        queues=q.get("queues")
        if isinstance(queues,dict):
            items=[]
            for value in queues.values():
                if isinstance(value,list): items.extend(value)
    if not isinstance(items,list) or not items: raise MediaCostPreflightV6Error("MEDIA_QUEUE_ITEMS_REQUIRED")
    expected=0.0; billable=0
    normalized=[]
    for item in items:
        if not isinstance(item,dict): raise MediaCostPreflightV6Error("MEDIA_QUEUE_ITEM_OBJECT_REQUIRED")
        amount=item.get("expected_cost_usd")
        if amount is None: amount=item.get("maximum_authorized_usd")
        if item.get("media_kind") in {"LOCAL_GRAPHICS","LOCAL","LOCAL_ASSEMBLY"}:
            amount=0.0 if amount is None else float(amount)
        elif amount is None:
            raise MediaCostPreflightV6Error("BILLABLE_ITEM_COST_MISSING:"+str(item.get("queue_id")))
        amount=float(amount or 0)
        if amount<0: raise MediaCostPreflightV6Error("NEGATIVE_EXPECTED_COST")
        expected+=amount
        if amount>0: billable+=1
        normalized.append({"queue_id":item.get("queue_id"),"expected_cost_usd":round(amount,8),"status":item.get("status")})
    out=repo/"projects"/episode_id/"orchestration/media-cost-preflight-v6-1.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({
        "schema_version":"siraj-media-cost-preflight-v6.1",
        "status":"PASS",
        "episode_id":episode_id,
        "expected_cost_usd":round(expected,8),
        "billable_item_count":billable,
        "assistant_authored_cost_cap_usd":None,
        "automatic_paid_retry":False,
        "explicit_paid_authorization_required":billable>0,
        "items":normalized,
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return out
