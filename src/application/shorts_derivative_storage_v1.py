"""Canonical, recoverable Desktop storage for approved Shorts outputs."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import atomic_write_json


SCHEMA_VERSION = "siraj-shorts-canonical-desktop-library-v1"
LIBRARY_NAME = "SIRAJ Shorts"
SETTINGS_RELATIVE_PATH = Path("artifacts/shorts-derivatives/.shorts-library-settings.json")
_WINDOWS_DESKTOP_GUID = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class ShortsLibraryError(RuntimeError):
    """A safe, user-facing storage error."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _known_folder_desktop() -> Path | None:
    if os.name != "nt":
        return None
    try:
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        guid_buffer = (ctypes.c_byte * 16)()
        ole32.CLSIDFromString(ctypes.c_wchar_p(_WINDOWS_DESKTOP_GUID), ctypes.byref(guid_buffer))
        path_ptr = ctypes.c_wchar_p()
        result = shell32.SHGetKnownFolderPath(ctypes.byref(guid_buffer), 0, None, ctypes.byref(path_ptr))
        if result != 0 or not path_ptr.value:
            return None
        value = Path(path_ptr.value)
        ole32.CoTaskMemFree(path_ptr)
        return value.resolve()
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def discover_desktop_location() -> Path:
    """Resolve the current Windows Desktop using a known-folder API first."""

    try:
        from PySide6.QtCore import QStandardPaths

        locations = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.DesktopLocation)
        if locations:
            return Path(str(locations[0])).resolve()
    except (ImportError, AttributeError, RuntimeError):
        pass
    known = _known_folder_desktop()
    if known is not None:
        return known
    if os.name == "nt":
        raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "WINDOWS_DESKTOP_KNOWN_FOLDER_UNAVAILABLE")
    fallback = Path.home() / "Desktop"
    if fallback.is_dir():
        return fallback.resolve()
    raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "DESKTOP_LOCATION_UNAVAILABLE")


def _safe_episode_directory_name(episode_id: str, display_name: str | None = None) -> str:
    identity = " ".join(str(episode_id or "").split()).strip()
    if not identity:
        raise ShortsLibraryError("SHORTS_LIBRARY_INVALID_EPISODE", "EPISODE_ID_REQUIRED")
    description = " ".join(str(display_name or "").split()).strip()
    description = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", description)
    description = re.sub(r"\s+", " ", description).strip(" .")
    return identity if not description else f"{identity} - {description[:90].rstrip(' .')}"


safe_episode_directory_name = _safe_episode_directory_name


def _json_read(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _atomic_copy_no_overwrite(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.exporting.tmp")
    if temporary.exists():
        raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", "TASK_OWNED_TEMP_EXISTS")
    try:
        with source.open("rb") as src, temporary.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        digest = sha256_file(temporary)
        if target.exists():
            raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", "FINAL_TARGET_EXISTS")
        try:
            os.rename(temporary, target)
        except FileExistsError as exc:
            raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", "FINAL_TARGET_EXISTS") from exc
        return digest
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


@dataclass(frozen=True, slots=True)
class ShortsLibraryBinding:
    root: Path
    desktop_location: Path
    created: bool
    reused: bool
    settings_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "shorts_library_root": str(self.root),
            "desktop_location": str(self.desktop_location),
            "created": self.created,
            "reused": self.reused,
            "settings_path": str(self.settings_path),
        }


@dataclass(frozen=True, slots=True)
class ShortsLibraryIndexEntry:
    episode_id: str
    episode_folder: str
    shorts_count: int
    latest_export_time: str | None


class CanonicalShortsLibrary:
    """Resolve one stable Desktop root and export approved material into it."""

    def __init__(self, repo_root: Path, *, desktop_location: Path | None = None, settings_path: Path | None = None) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.desktop_location = (Path(desktop_location).resolve() if desktop_location is not None else discover_desktop_location())
        self.settings_path = (Path(settings_path).resolve() if settings_path is not None else self.repo_root / SETTINGS_RELATIVE_PATH).resolve()
        self.binding: ShortsLibraryBinding | None = None

    @property
    def root(self) -> Path:
        if self.binding is None:
            self.resolve(create=True)
        assert self.binding is not None
        return self.binding.root

    def resolve(self, *, create: bool = True) -> ShortsLibraryBinding:
        persisted = _json_read(self.settings_path) if self.settings_path.is_file() else None
        if persisted and persisted.get("shorts_library_root"):
            stored = Path(str(persisted["shorts_library_root"])).resolve()
            if stored.name != LIBRARY_NAME:
                raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "STORED_ROOT_NAME_INVALID")
            if os.path.normcase(str(stored.parent)) != os.path.normcase(str(self.desktop_location)):
                raise ShortsLibraryError("SHORTS_LIBRARY_NOT_FOUND", "STORED_ROOT_MOVED_OR_DESKTOP_CHANGED")
            if not stored.is_dir():
                raise ShortsLibraryError("SHORTS_LIBRARY_NOT_FOUND", str(stored))
            if not os.access(stored, os.W_OK):
                raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "STORED_ROOT_NOT_WRITABLE")
            self.binding = ShortsLibraryBinding(stored, self.desktop_location, False, True, self.settings_path)
            return self.binding
        root = self.desktop_location / LIBRARY_NAME
        if root.exists() and not root.is_dir():
            raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "DESKTOP_ROOT_COLLISION")
        created = False
        if not root.exists():
            if not create:
                raise ShortsLibraryError("SHORTS_LIBRARY_NOT_FOUND", str(root))
            root.mkdir(parents=True, exist_ok=False)
            created = True
        if not os.access(root, os.W_OK):
            raise ShortsLibraryError("SHORTS_LIBRARY_UNAVAILABLE", "ROOT_NOT_WRITABLE")
        self.binding = ShortsLibraryBinding(root.resolve(), self.desktop_location, created, not created, self.settings_path)
        atomic_write_json(self.settings_path, {"schema_version": SCHEMA_VERSION, "shorts_library_root": str(root.resolve()), "created_at": utc_now()}, preserve_previous=True)
        return self.binding

    def _find_episode_directories(self, episode_id: str) -> list[Path]:
        root = self.root
        matches: list[Path] = []
        for directory in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if not directory.is_dir():
                continue
            manifest = _json_read(directory / "episode-shorts-manifest.json")
            if manifest and manifest.get("episode_id") == episode_id:
                matches.append(directory)
                continue
            if directory.name == episode_id or directory.name.startswith(episode_id + " - "):
                matches.append(directory)
        return matches

    def episode_directory(self, episode_id: str, display_name: str | None = None, *, create: bool = True, source_episode_sha256: str | None = None) -> Path:
        matches = self._find_episode_directories(episode_id)
        if len(matches) > 1:
            raise ShortsLibraryError("SHORTS_LIBRARY_AMBIGUOUS_EPISODE", episode_id)
        if matches:
            directory = matches[0]
        else:
            directory = self.root / _safe_episode_directory_name(episode_id, display_name)
            if not create:
                raise ShortsLibraryError("SHORTS_LIBRARY_EPISODE_NOT_FOUND", episode_id)
            directory.mkdir(parents=True, exist_ok=False)
        if create:
            for name in ("Shorts", "Captions", "Manifests", "Reviews"):
                (directory / name).mkdir(parents=True, exist_ok=True)
            manifest_path = directory / "episode-shorts-manifest.json"
            existing = _json_read(manifest_path)
            now = utc_now()
            manifest = existing or {
                "schema_version": SCHEMA_VERSION,
                "episode_id": episode_id,
                "episode_display_name": display_name or episode_id,
                "source_episode_sha256": source_episode_sha256,
                "shorts_library_root": str(self.root),
                "episode_directory": str(directory),
                "created_at": now,
                "last_updated_at": now,
            }
            if source_episode_sha256 and existing and existing.get("source_episode_sha256") not in {None, source_episode_sha256}:
                manifest["source_episode_sha256_previous"] = existing.get("source_episode_sha256")
                manifest["source_episode_sha256"] = source_episode_sha256
            manifest["last_updated_at"] = now
            atomic_write_json(manifest_path, manifest, preserve_previous=True)
        return directory

    def rebuild_index(self) -> tuple[ShortsLibraryIndexEntry, ...]:
        entries: list[ShortsLibraryIndexEntry] = []
        for directory in sorted(self.root.iterdir(), key=lambda p: p.name.casefold()):
            if not directory.is_dir():
                continue
            manifest = _json_read(directory / "episode-shorts-manifest.json")
            if not manifest or not manifest.get("episode_id"):
                continue
            manifests = list((directory / "Manifests").glob("*.manifest.json")) if (directory / "Manifests").is_dir() else []
            latest = max(((_json_read(path) or {}).get("exported_at") for path in manifests), default=None)
            entries.append(ShortsLibraryIndexEntry(str(manifest["episode_id"]), str(directory), len(manifests), latest))
        index_payload = {
            "schema_version": SCHEMA_VERSION,
            "rebuilt_at": utc_now(),
            "entries": [entry.__dict__ if hasattr(entry, "__dict__") else {"episode_id": entry.episode_id, "episode_folder": entry.episode_folder, "shorts_count": entry.shorts_count, "latest_export_time": entry.latest_export_time} for entry in entries],
        }
        atomic_write_json(self.settings_path.with_name("shorts-library-index.json"), index_payload, preserve_previous=True)
        return tuple(entries)

    def export_approved_short(
        self,
        *,
        episode_id: str,
        episode_display_name: str | None,
        source_episode_sha256: str,
        render_plan_sha256: str,
        approved_render_sha256: str,
        profile_sha256: str,
        constitution_bundle_sha256: str,
        human_review_receipt_sha256: str,
        render_path: Path,
        review_receipt: Mapping[str, Any],
        caption_payloads: Mapping[str, str] | None = None,
        short_number: int = 1,
    ) -> dict[str, Any]:
        if not _HASH_RE.fullmatch(approved_render_sha256):
            raise ShortsLibraryError("SHORT_EXPORT_HASH_MISMATCH", "APPROVED_RENDER_HASH_INVALID")
        if sha256_file(render_path) != approved_render_sha256:
            raise ShortsLibraryError("SHORT_EXPORT_HASH_MISMATCH", "INTERNAL_RENDER_HASH_MISMATCH")
        if short_number < 1:
            raise ShortsLibraryError("SHORT_EXPORT_INVALID", "SHORT_NUMBER_INVALID")
        episode_dir = self.episode_directory(episode_id, episode_display_name, source_episode_sha256=source_episode_sha256)
        base_name = f"{episode_id}-SHORT-{short_number:02d}"
        shorts_dir = episode_dir / "Shorts"
        manifests_dir = episode_dir / "Manifests"
        captions_dir = episode_dir / "Captions"
        reviews_dir = episode_dir / "Reviews"
        existing_manifest = None
        existing_path = None
        for candidate in sorted(manifests_dir.glob(f"{base_name}*.manifest.json")):
            value = _json_read(candidate)
            if value and value.get("approved_render_sha256") == approved_render_sha256:
                existing_manifest = value
                existing_path = candidate
                break
        if existing_manifest is not None:
            return {**existing_manifest, "export_status": "ALREADY_EXPORTED", "manifest_path": str(existing_path)}
        versions = [1]
        for candidate in shorts_dir.glob(f"{base_name}-v*.mp4"):
            match = re.search(r"-v(\d+)\.mp4$", candidate.name)
            if match:
                versions.append(int(match.group(1)))
        version = max(versions)
        filename = f"{base_name}.mp4" if version == 1 and not (shorts_dir / f"{base_name}.mp4").exists() else f"{base_name}-v{version + 1}.mp4"
        final_video = shorts_dir / filename
        if final_video.exists():
            version = max(versions) + 1
            filename = f"{base_name}-v{version}.mp4"
            final_video = shorts_dir / filename
        exported_hash = _atomic_copy_no_overwrite(Path(render_path), final_video)
        if exported_hash != approved_render_sha256:
            final_video.unlink(missing_ok=True)
            raise ShortsLibraryError("SHORT_EXPORT_HASH_MISMATCH", "DESTINATION_HASH_MISMATCH")
        exported_captions: list[str] = []
        created_sidecars: list[Path] = []
        try:
            for suffix, payload in (caption_payloads or {}).items():
                if suffix not in {".srt", ".vtt"}:
                    raise ShortsLibraryError("SHORT_EXPORT_INVALID", f"CAPTION_FORMAT_UNSUPPORTED:{suffix}")
                caption_path = captions_dir / f"{final_video.stem}{suffix}"
                if caption_path.exists():
                    raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", str(caption_path))
                temporary = caption_path.with_name(f".{caption_path.name}.{os.getpid()}.exporting.tmp")
                if temporary.exists():
                    raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", "CAPTION_TEMP_EXISTS")
                try:
                    temporary.write_text(payload, encoding="utf-8", newline="\n")
                    os.replace(temporary, caption_path)
                finally:
                    temporary.unlink(missing_ok=True)
                exported_captions.append(str(caption_path))
                created_sidecars.append(caption_path)
            review_path = reviews_dir / f"{final_video.stem}.human-review.json"
            if review_path.exists():
                raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", str(review_path))
            atomic_write_json(review_path, dict(review_receipt), preserve_previous=False)
            created_sidecars.append(review_path)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "package_type": "APPROVED_SHORTS_PACKAGE",
                "episode_id": episode_id,
                "short_id": f"{episode_id}-SHORT-{short_number:02d}",
                "internal_short_label": f"{episode_id}-SHORT-{short_number:02d}",
                "source_episode_sha256": source_episode_sha256,
                "render_plan_sha256": render_plan_sha256,
                "approved_render_sha256": approved_render_sha256,
                "exported_file_sha256": exported_hash,
                "human_review_receipt_sha256": human_review_receipt_sha256,
                "profile_sha256": profile_sha256,
                "constitution_bundle_sha256": constitution_bundle_sha256,
                "render": {"path": str(final_video), "sha256": exported_hash},
                "captions": exported_captions,
                "human_review_receipt": str(review_path),
                "public_title": None,
                "public_title_owner": "HUMAN",
                "thumbnail": None,
                "thumbnail_owner": "HUMAN",
                "automatic_publication": False,
                "upload": False,
                "youtube_api": False,
                "state": "EXPORT_READY",
                "export_status": "EXPORTED",
                "exported_at": utc_now(),
            }
            manifest_path = manifests_dir / f"{final_video.stem}.manifest.json"
            if manifest_path.exists():
                raise ShortsLibraryError("SHORTS_EXPORT_CONFLICT", str(manifest_path))
            atomic_write_json(manifest_path, manifest, preserve_previous=False)
            created_sidecars.append(manifest_path)
            return {**manifest, "manifest_path": str(manifest_path), "episode_directory": str(episode_dir)}
        except Exception:
            # Roll back the complete task-owned package, never an older export.
            final_video.unlink(missing_ok=True)
            for sidecar in reversed(created_sidecars):
                sidecar.unlink(missing_ok=True)
            raise


__all__ = [
    "SCHEMA_VERSION",
    "LIBRARY_NAME",
    "ShortsLibraryError",
    "ShortsLibraryBinding",
    "ShortsLibraryIndexEntry",
    "CanonicalShortsLibrary",
    "discover_desktop_location",
    "safe_episode_directory_name",
    "sha256_file",
]
