from pathlib import Path

EP2_ID = "episode-002-adam-temptation-fall-repentance"


class FinalTtsQueueSelectorError(RuntimeError):
    pass


def resolve_final_tts_queue_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id

    if episode_id == EP2_ID:
        legacy = ep / "orchestration/final-tts-queue-v5-4-3.json"
        if not legacy.is_file():
            raise FinalTtsQueueSelectorError(
                "EPISODE_002_FINAL_TTS_QUEUE_MISSING"
            )
        return legacy

    generic = ep / "orchestration/final-tts-queue-v6-3-2.json"
    if generic.is_file():
        return generic

    legacy = ep / "orchestration/final-tts-queue-v5-4-3.json"
    if legacy.is_file():
        return legacy

    raise FinalTtsQueueSelectorError(
        "FINAL_TTS_QUEUE_NOT_FOUND:" + episode_id
    )
