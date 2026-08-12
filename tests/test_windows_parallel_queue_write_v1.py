from __future__ import annotations

import json
import threading
from pathlib import Path

from src.application import desktop_media_execution_v1 as media


def test_windows_atomic_write_retries_transient_access_denied(
    monkeypatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "queue.json"
    destination.write_text(
        json.dumps({"before": True}),
        encoding="utf-8",
    )

    real_replace = media.os.replace
    attempts = {"count": 0}

    def transient_replace(source, target):
        attempts["count"] += 1
        if attempts["count"] <= 3:
            error = PermissionError(
                5,
                "Access is denied",
                str(source),
                str(target),
            )
            error.winerror = 5
            raise error
        return real_replace(source, target)

    monkeypatch.setattr(media.os, "replace", transient_replace)

    media._write(destination, {"after": True})

    assert attempts["count"] == 4
    assert json.loads(
        destination.read_text(encoding="utf-8")
    ) == {"after": True}


def test_parallel_writes_leave_valid_json(tmp_path: Path) -> None:
    destination = tmp_path / "queue.json"
    destination.write_text("{}", encoding="utf-8")

    errors = []

    def writer(index: int) -> None:
        try:
            media._write(
                destination,
                {
                    "writer": index,
                    "payload": "x" * 1000,
                },
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(index,))
        for index in range(12)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    value = json.loads(destination.read_text(encoding="utf-8"))
    assert isinstance(value["writer"], int)
    assert value["payload"] == "x" * 1000
    assert not list(tmp_path.glob(".*.tmp"))
