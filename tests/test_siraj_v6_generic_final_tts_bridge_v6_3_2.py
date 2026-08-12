from src.application.siraj_generic_final_tts_v6_3_2 import (
    EP2_ID,
    final_tts_backend_kind,
)
from src.application.siraj_final_tts_queue_selector_v6_3_2 import (
    resolve_final_tts_queue_path,
)


def test_episode2_stays_on_canonical_v5_backend():
    assert (
        final_tts_backend_kind(EP2_ID)
        == "EPISODE_002_CANONICAL_V5_4_3"
    )


def test_future_episode_uses_generic_backend():
    assert (
        final_tts_backend_kind("episode-003-example")
        == "GENERIC_V6_3_2"
    )


def test_queue_selector_prefers_generic_for_future(tmp_path):
    ep = tmp_path / "projects/episode-003-example/orchestration"
    ep.mkdir(parents=True)
    generic = ep / "final-tts-queue-v6-3-2.json"
    generic.write_text("{}", encoding="utf-8")
    assert (
        resolve_final_tts_queue_path(
            tmp_path,
            "episode-003-example",
        )
        == generic
    )


def test_queue_selector_requires_episode2_legacy(tmp_path):
    ep = tmp_path / f"projects/{EP2_ID}/orchestration"
    ep.mkdir(parents=True)
    legacy = ep / "final-tts-queue-v5-4-3.json"
    legacy.write_text("{}", encoding="utf-8")
    assert resolve_final_tts_queue_path(tmp_path, EP2_ID) == legacy
