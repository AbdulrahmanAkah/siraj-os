from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.adam_authorized_tts_sample_v2 import (
    EXPECTED_AUTHORIZED_MAXIMUM_USD,
    execute_authorized_sample,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument(
        "--authorized-maximum-usd",
        type=float,
        required=True,
    )
    args = parser.parse_args()

    if abs(
        args.authorized_maximum_usd
        - EXPECTED_AUTHORIZED_MAXIMUM_USD
    ) > 1e-9:
        raise RuntimeError(
            "AUTHORIZED_MAXIMUM_MUST_EQUAL_0.07_USD"
        )

    repo = Path(args.repo).resolve()
    if not (repo / ".git").is_dir():
        raise RuntimeError(f"NOT_A_GIT_REPOSITORY:{repo}")

    result = execute_authorized_sample(
        repo,
        confirmed_maximum_usd=args.authorized_maximum_usd,
    )
    print(
        json.dumps(
            {
                "release": "SIRAJ_ADAM_AUTHORIZED_TTS_SAMPLE_V2",
                "status": result.status,
                "authorization": {
                    "maximum_authorized_usd": (
                        EXPECTED_AUTHORIZED_MAXIMUM_USD
                    ),
                    "maximum_provider_requests": 1,
                    "authorization_source": (
                        "USER_EXPLICIT_YES_IN_CHAT"
                    ),
                },
                "execution": result.as_dict(repo),
                "full_episode_tts_authorized": False,
                "next_stage": "HUMAN_TTS_SAMPLE_REVIEW",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
