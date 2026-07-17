"""Provider-neutral contracts for the v4 documentary quality gate.

The script, timeline and renderer consume these manifests, not an Azure or
image-generation implementation.  Adapters are selected outside this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Protocol

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id
from src.application.project_runtime import load_project, project_paths


V4_VOICE_SELECTION_SCHEMA = "siraj-quality-gate-voice-selection-v4"
V4_VISUAL_AUDITION_SCHEMA = "siraj-quality-gate-visual-auditions-v4"


@dataclass(frozen=True)
class VoiceProviderSelection:
    provider_identifier: str
    voice_identifier: str
    locale: str
    quality_gate_only: bool = True
    production_final: bool = False


class VoiceProviderFactory(Protocol):
    def __call__(self, selection: VoiceProviderSelection) -> Any: ...


class VoiceProviderRegistry:
    """Configuration-driven provider selection; it contains no Azure logic."""

    def __init__(self) -> None:
        self._factories: dict[str, VoiceProviderFactory] = {}

    def register(self, provider_identifier: str, factory: VoiceProviderFactory) -> None:
        if not provider_identifier or provider_identifier in self._factories:
            raise ValueError("DUPLICATE_OR_INVALID_VOICE_PROVIDER_IDENTIFIER")
        self._factories[provider_identifier] = factory

    def resolve(self, selection: VoiceProviderSelection) -> Any:
        try:
            factory = self._factories[selection.provider_identifier]
        except KeyError as error:
            raise ValueError("VOICE_PROVIDER_NOT_REGISTERED") from error
        return factory(selection)


@dataclass(frozen=True)
class VisualAssetSpec:
    asset_key: str
    asset_type: str
    source_path: str
    prompt: str
    layout_intent: str


class VisualAssetProvider(Protocol):
    provider_identifier: str
    model_identifier: str

    def materialize(self, spec: VisualAssetSpec, output_path: Path, ffmpeg: str) -> dict[str, Any]: ...


def _write_json(path: Path, payload: dict[str, Any], *, replace: bool) -> None:
    if path.exists() and not replace:
        raise FileExistsError(f"ARTIFACT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, suffix=".tmp", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _run(command: list[str]) -> None:
    process = subprocess.run(command, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=False)
    if process.returncode:
        raise RuntimeError("VISUAL_AUDITION_MEDIA_NORMALIZATION_FAILED")


class CuratedGeneratedVisualProvider:
    """Copies curated local generation outputs without tying consumers to a model."""

    provider_identifier = "OPENAI_IMAGE_GENERATION_BUILT_IN"
    model_identifier = "OPENAI_IMAGE_GENERATION_BUILT_IN_MODEL_UNSPECIFIED"

    def materialize(self, spec: VisualAssetSpec, output_path: Path, ffmpeg: str) -> dict[str, Any]:
        source = Path(spec.source_path)
        if not source.is_file():
            raise FileNotFoundError(f"VISUAL_AUDITION_SOURCE_MISSING:{spec.asset_key}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Every delivered audition is 16:9 at the declared production raster.
        _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source), "-vf", "scale=1920:1080:flags=lanczos", "-frames:v", "1", str(output_path)])
        return {
            "asset_id": deterministic_id("visual_audition_v4", [spec.asset_key, sha256(output_path.read_bytes()).hexdigest()]),
            "asset_type": spec.asset_type,
            "origin": "AI_GENERATED_RECONSTRUCTION",
            "source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",
            "creator": "SIRAJ curated generation workflow",
            "license": "INTERNAL_EVALUATION_ONLY",
            "authenticity_classification": "AI_GENERATED_RECONSTRUCTION",
            "provider_identifier": self.provider_identifier,
            "model_identifier": self.model_identifier,
            "prompt": spec.prompt,
            "layout_intent": spec.layout_intent,
            "resolution": {"width": 1920, "height": 1080},
            "sha256": sha256(output_path.read_bytes()).hexdigest(),
            "path": output_path.name,
        }


def create_quality_gate_voice_selection(project_root: str | Path, selection: VoiceProviderSelection, *, replace: bool = False) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=False)
    load_project(root)
    paths = project_paths(root)
    target = Path(paths.working_root) / "production-v4" / "voice-provider-selection.json"
    payload = {
        "schema_version": V4_VOICE_SELECTION_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "selection_id": deterministic_id("quality_gate_voice_selection", [selection.provider_identifier, selection.voice_identifier, selection.locale]),
        "selection": asdict(selection),
        "future_provider_contract": "VoiceProvider protocol; adapters may register without changing script, timeline, or renderer.",
    }
    _write_json(target, payload, replace=replace)
    return payload


def build_visual_auditions(
    project_root: str | Path,
    specs: list[VisualAssetSpec],
    provider: VisualAssetProvider,
    *,
    ffmpeg: str,
    replace: bool = False,
) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=False)
    load_project(root)
    if len(specs) != 8 or len({item.asset_key for item in specs}) != 8:
        raise ValueError("QUALITY_GATE_REQUIRES_EIGHT_UNIQUE_VISUAL_AUDITIONS")
    paths = project_paths(root)
    output_root = Path(paths.working_root) / "production-v4" / "visual-auditions"
    assets = []
    for position, spec in enumerate(specs, 1):
        target = output_root / f"{position:02d}-{spec.asset_key}.png"
        if target.exists() and not replace:
            raise FileExistsError(f"ARTIFACT_EXISTS:{target}")
        asset = provider.materialize(spec, target, ffmpeg)
        asset["position"] = position
        asset["path"] = str(target.relative_to(root).as_posix())
        assets.append(asset)
    manifest = {
        "schema_version": V4_VISUAL_AUDITION_SCHEMA,
        "created_at": CANONICAL_TIMESTAMP,
        "asset_provider_identifier": provider.provider_identifier,
        "assets": assets,
        "status": "READY_FOR_HUMAN_VISUAL_REVIEW",
    }
    manifest_path = output_root / "visual-audition-manifest.json"
    _write_json(manifest_path, manifest, replace=replace)
    contact_sheet = output_root / "contact-sheet-v4.png"
    inputs = []
    for asset in assets:
        inputs.extend(["-i", str(root / asset["path"])])
    contact_filters = ";".join(
        [f"[{index}:v]scale=480:270:flags=lanczos[v{index}]" for index in range(8)]
        + ["".join(f"[v{index}]" for index in range(8)) + "xstack=inputs=8:layout=0_0|480_0|960_0|1440_0|0_270|480_270|960_270|1440_270:fill=black[contact]"]
    )
    _run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *inputs,
        "-filter_complex", contact_filters, "-map", "[contact]",
        "-frames:v", "1", str(contact_sheet),
    ])
    manifest["contact_sheet"] = str(contact_sheet.relative_to(root).as_posix())
    _write_json(manifest_path, manifest, replace=True)
    return manifest
