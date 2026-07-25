from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_adam_secondary_raw_asset_materialization_v1() -> None:
    root = Path(__file__).resolve().parents[2]
    project = root / "projects" / "episode-001-adam"
    secondary = project / "sources" / "secondary"
    selection = json.loads((secondary / "asset-selection-v1.json").read_text(encoding="utf-8-sig"))
    materialization = json.loads((secondary / "raw-asset-materialization-v1.json").read_text(encoding="utf-8-sig"))
    inspection = json.loads((secondary / "shamela-schema-inspection-v1.json").read_text(encoding="utf-8-sig"))
    assert selection["selected_count"] == 9
    assert selection["deferred_count"] == 1
    assert materialization["selected_asset_count"] == 9
    assert materialization["gemini_execution_enabled"] is False
    assert inspection["asset_count"] == 9
    for asset in materialization["assets"]:
        path = project / asset["project_asset_path"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == asset["sha256"]
        assert asset["allowed_for_gemini"] is False
        assert asset["allowed_for_quotation"] is False
