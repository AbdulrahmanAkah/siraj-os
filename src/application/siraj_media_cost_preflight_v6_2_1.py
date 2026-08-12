"""V6.2.1 media preflight: exact scope, no invented provider price."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class MediaPreflightV621Error(RuntimeError):
    pass


def build_media_cost_preflight(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id
    queue_path = (
        ep / "orchestration/media-production-queue-v6-2-1.json"
    )
    queue = json.loads(
        queue_path.read_text(encoding="utf-8-sig")
    )
    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise MediaPreflightV621Error(
            "MEDIA_QUEUE_ITEMS_REQUIRED"
        )

    billable = []
    local = []
    known_estimate_total = 0.0
    unknown_price_count = 0

    for item in items:
        if not isinstance(item, Mapping):
            raise MediaPreflightV621Error(
                "MEDIA_QUEUE_ITEM_OBJECT_REQUIRED"
            )
        kind = str(item.get("media_kind") or "")
        row = {
            "queue_id": item.get("queue_id"),
            "media_kind": kind,
            "duration_seconds": item.get("duration_seconds"),
            "expected_cost_usd": item.get(
                "expected_cost_usd"
            ),
        }
        if kind == "LOCAL_GRAPHICS":
            local.append(row)
        else:
            billable.append(row)
            amount = item.get("expected_cost_usd")
            if isinstance(amount, (int, float)):
                known_estimate_total += float(amount)
            else:
                unknown_price_count += 1

    policy = queue.get("generated_video_policy") or {}
    if (
        float(policy.get("planned_seconds", 0) or 0)
        > float(policy.get("maximum_seconds", 0) or 0)
        + 1e-9
    ):
        raise MediaPreflightV621Error(
            "GENERATED_VIDEO_POLICY_FAILED"
        )

    out = ep / "orchestration/media-cost-preflight-v6-2-1.json"
    out.write_text(
        json.dumps(
            {
                "schema_version": (
                    "siraj-media-cost-preflight-v6.2.1"
                ),
                "status": "PASS",
                "episode_id": episode_id,
                "planned_provider_requests": len(billable),
                "planned_local_items": len(local),
                "known_estimated_cost_usd": round(
                    known_estimate_total,
                    8,
                ),
                "unknown_provider_price_item_count": (
                    unknown_price_count
                ),
                "provider_billing_is_source_of_truth": True,
                "assistant_authored_cost_cap_usd": None,
                "explicit_paid_authorization_required": bool(
                    billable
                ),
                "automatic_paid_retry": False,
                "generated_video_policy": policy,
                "billable_items": billable,
                "local_items": local,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return out
