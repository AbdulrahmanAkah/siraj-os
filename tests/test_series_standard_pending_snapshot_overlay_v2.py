import json
from pathlib import Path

from src.presentation.desktop import series_standard_v2_panel as panel


def test_pending_snapshot_patch_overlays_unavailable_base(
    tmp_path: Path,
) -> None:
    pending = (
        tmp_path
        / "projects/episode-001-adam/orchestration/"
        "desktop-series-production-standard-v2-snapshot.pending.json"
    )
    pending.parent.mkdir(parents=True, exist_ok=True)
    pending.write_text(
        json.dumps(
            {
                "patch": {
                    "next_action_ar": "استكمال تنفيذ الوسائط",
                    "consolidated_production_v2": {
                        "certified_prompts": 70,
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    result = panel._read_snapshot(tmp_path)
    assert result["next_action_ar"] == "استكمال تنفيذ الوسائط"
    assert result["consolidated_production_v2"][
        "certified_prompts"
    ] == 70
