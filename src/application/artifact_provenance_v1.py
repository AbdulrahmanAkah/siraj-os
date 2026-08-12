"""Durable, non-destructive artifact IO and provenance primitives.

The production pipeline must never use deletion as a state transition.  This
module therefore preserves the previous bytes before replacing a mutable
projection, appends invalidation receipts instead of unlinking artifacts, and
uses process-safe JSONL appends.  Authoritative records should use
``write_new_json`` or ``append_jsonl`` and are immutable once written.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
from typing import Any, Iterator, Mapping, Sequence
import uuid


SCHEMA_VERSION = "siraj-artifact-provenance-v1"
_THREAD_LOCK = threading.RLock()


class ArtifactProvenanceError(RuntimeError):
    """Raised when an artifact cannot be preserved or committed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_reference(path: Path, *, base: Path | None = None) -> dict[str, Any]:
    target = Path(path).resolve()
    if not target.is_file():
        raise ArtifactProvenanceError("ARTIFACT_FILE_REQUIRED:" + str(target))
    display = str(target)
    if base is not None:
        try:
            display = str(target.relative_to(Path(base).resolve())).replace("\\", "/")
        except ValueError:
            pass
    stat = target.stat()
    return {
        "path": display,
        "size": stat.st_size,
        "sha256": sha256_file(target),
        "mtime_utc": datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat().replace("+00:00", "Z"),
    }


def artifact_references(
    paths: Sequence[Path],
    *,
    base: Path | None = None,
) -> list[dict[str, Any]]:
    return [artifact_reference(path, base=base) for path in paths]


def _fsync_directory(path: Path) -> None:
    """Best-effort directory durability; Windows may reject directory handles."""

    try:
        descriptor = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _history_path(path: Path, old_sha256: str) -> Path:
    history = path.parent / "provenance-history-v1"
    return history / f"{path.name}.{old_sha256}.preserved"


def preserve_existing(path: Path) -> Path | None:
    """Copy existing bytes to a content-addressed history path once."""

    target = Path(path)
    if not target.is_file():
        return None
    old_hash = sha256_file(target)
    destination = _history_path(target, old_hash)
    if destination.is_file():
        if sha256_file(destination) != old_hash:
            raise ArtifactProvenanceError(
                "PRESERVED_HISTORY_HASH_CONFLICT:" + str(destination)
            )
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target, destination)
    if sha256_file(destination) != old_hash:
        raise ArtifactProvenanceError(
            "PRESERVED_HISTORY_COPY_HASH_MISMATCH:" + str(target)
        )
    return destination


def _json_payload(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def atomic_write_json(
    path: Path,
    value: Mapping[str, Any],
    *,
    preserve_previous: bool = True,
) -> None:
    """Write a mutable projection without losing the previous bytes."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_payload(value)
    with _THREAD_LOCK:
        if target.is_file() and target.read_bytes() == payload:
            return
        if preserve_previous:
            preserve_existing(target)
        temporary = target.with_name(
            f"{target.name}.{os.getpid()}.{threading.get_ident()}."
            f"{uuid.uuid4().hex}.tmp-preserved-on-failure"
        )
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        _fsync_directory(target.parent)


def write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    """Create an immutable JSON record and refuse any replacement."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_payload(value)
    with _THREAD_LOCK:
        try:
            descriptor = os.open(
                target,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise ArtifactProvenanceError(
                "IMMUTABLE_ARTIFACT_ALREADY_EXISTS:" + str(target)
            ) from exc
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(target.parent)


@contextmanager
def _process_lock(path: Path) -> Iterator[None]:
    lock_path = Path(str(path) + ".append.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    """Append one durable JSON record under a process-safe file lock."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    row = canonical_json_bytes(value) + b"\n"
    with _THREAD_LOCK, _process_lock(target):
        with target.open("ab") as handle:
            handle.write(row)
            handle.flush()
            os.fsync(handle.fileno())
        _fsync_directory(target.parent)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    with target.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ArtifactProvenanceError(
                    f"CORRUPT_JSONL:{target}:{line_number}"
                ) from exc
            if not isinstance(value, dict):
                raise ArtifactProvenanceError(
                    f"JSONL_OBJECT_REQUIRED:{target}:{line_number}"
                )
            rows.append(value)
    return rows


def invalidation_ledger_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "artifact-invalidations-v1.jsonl"
    )


def record_invalidation(
    repo_root: Path,
    episode_id: str,
    artifact_path: Path,
    *,
    reason: str,
    classification: str = "STALE_BUT_PRESERVED",
    invalidated_by_input_hash: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    target = Path(artifact_path).resolve()
    try:
        relative = str(target.relative_to(repo)).replace("\\", "/")
    except ValueError as exc:
        raise ArtifactProvenanceError(
            "INVALIDATION_TARGET_OUTSIDE_REPOSITORY:" + str(target)
        ) from exc
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": str(uuid.uuid4()),
        "episode_id": episode_id,
        "artifact_path": relative,
        "artifact_existed": target.exists(),
        "artifact_type": "FILE" if target.is_file() else "DIRECTORY" if target.is_dir() else "MISSING",
        "artifact_sha256": sha256_file(target) if target.is_file() else None,
        "classification": classification,
        "reason": reason,
        "invalidated_by_input_hash": invalidated_by_input_hash,
        "created_at_utc": utc_now(),
        "bytes_preserved": True,
    }
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    append_jsonl(invalidation_ledger_path(repo, episode_id), receipt)
    return receipt


def latest_invalidation(
    repo_root: Path,
    episode_id: str,
    artifact_path: Path,
) -> dict[str, Any] | None:
    repo = Path(repo_root).resolve()
    target = Path(artifact_path).resolve()
    try:
        relative = str(target.relative_to(repo)).replace("\\", "/")
    except ValueError:
        return None
    matches = [
        row
        for row in read_jsonl(invalidation_ledger_path(repo, episode_id))
        if row.get("artifact_path") == relative
    ]
    return matches[-1] if matches else None


def is_currently_valid(
    repo_root: Path,
    episode_id: str,
    artifact_path: Path,
    *,
    expected_input_hash: str | None = None,
) -> bool:
    target = Path(artifact_path)
    if not target.is_file():
        return False
    receipt = latest_invalidation(repo_root, episode_id, target)
    if receipt is None:
        return True
    if expected_input_hash is None:
        return False
    return receipt.get("invalidated_by_input_hash") != expected_input_hash
