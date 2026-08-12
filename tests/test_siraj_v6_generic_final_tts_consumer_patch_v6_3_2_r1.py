from pathlib import Path

from src.application.siraj_generic_final_tts_consumer_patch_v6_3_2_r1 import (
    patch_audio_timeline,
    patch_montage,
)


def test_audio_patch_handles_wave1_compact_source(tmp_path):
    path = tmp_path / "audio.py"
    path.write_text(
        "from pathlib import Path\n"
        "def f(repo, ep, episode_id):\n"
        '    q=_read(ep/"orchestration/final-tts-queue-v5-4-3.json")\n',
        encoding="utf-8",
    )
    first = patch_audio_timeline(path)
    second = patch_audio_timeline(path)
    text = path.read_text(encoding="utf-8")
    assert first.status == "PATCHED"
    assert second.status == "ALREADY_PATCHED"
    assert "resolve_final_tts_queue_path(repo, episode_id)" in text


def test_montage_patch_handles_wave2_multiline_source(tmp_path):
    path = tmp_path / "montage.py"
    path.write_text(
        "from pathlib import Path\n"
        "def f(repo, episode, episode_id):\n"
        "    tts = _read(\n"
        "        episode\n"
        '        / "orchestration/final-tts-queue-v5-4-3.json"\n'
        "    )\n",
        encoding="utf-8",
    )
    first = patch_montage(path)
    second = patch_montage(path)
    text = path.read_text(encoding="utf-8")
    assert first.status == "PATCHED"
    assert second.status == "ALREADY_PATCHED"
    assert "resolve_final_tts_queue_path(repo, episode_id)" in text
