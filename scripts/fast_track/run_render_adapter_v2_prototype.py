from __future__ import annotations

import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from src.application.local_video_production.render_adapter_v2 import (
    render_episode_manifest_v2,
)


def main() -> int:
    manifest_path = (
        PROJECT_ROOT
        / "manifests"
        / "episode-render-v2-prototype.json"
    )

    result = render_episode_manifest_v2(
        project_root=PROJECT_ROOT,
        manifest_path=manifest_path,
        replace=True,
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if result["status"] != "VALID":
        raise RuntimeError(
            "RENDER_ADAPTER_V2_OUTPUT_INVALID"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())