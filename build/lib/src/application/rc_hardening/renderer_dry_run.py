"""Render-manifest validation and neutral operation planning only."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.application.operations_common import deterministic_id

from .security import SecurityBoundaryError, path_within_root


@dataclass(frozen=True)
class RenderArgument:
    name: str
    value: str
    position: int


@dataclass(frozen=True)
class RenderOperation:
    operation_id: str
    operation_type: str
    arguments: list[RenderArgument]
    position: int


@dataclass(frozen=True)
class RenderDependencyCheck:
    dependency_id: str
    status: str
    code: str = ""


@dataclass(frozen=True)
class RenderExecutionPlan:
    plan_id: str
    operations: list[RenderOperation] = field(default_factory=list)
    status: str = "VALID"


@dataclass(frozen=True)
class RenderDryRunReport:
    report_id: str
    status: str
    checks: list[RenderDependencyCheck] = field(default_factory=list)
    execution_plan: RenderExecutionPlan | None = None


class RendererDryRunAdapter:
    """Creates a stable render plan and never creates a subprocess."""

    def __init__(self, allowed_asset_root: str):
        self.allowed_asset_root = allowed_asset_root

    def dry_run(self, manifest: Any) -> RenderDryRunReport:
        values = manifest if isinstance(manifest, dict) else manifest.__dict__
        checks: list[RenderDependencyCheck] = []
        if values.get("validation_state", "VALID") != "VALID":
            checks.append(RenderDependencyCheck("manifest", "INVALID", "INVALID_MANIFEST"))
        missing = sorted(values.get("missing_assets", []))
        checks.extend(RenderDependencyCheck(asset, "BLOCKED", "MISSING_ASSET") for asset in missing)
        assets = values.get("assets", [])
        for asset in sorted(assets, key=lambda item: str(item.get("asset_id", ""))):
            asset_id = str(asset.get("asset_id", ""))
            if asset.get("rights_status", "RIGHTS_UNVERIFIED") != "RIGHTS_VERIFIED":
                checks.append(RenderDependencyCheck(asset_id, "BLOCKED", "RIGHTS_UNVERIFIED"))
            try:
                asset_path = path_within_root(self.allowed_asset_root, asset.get("path", ""))
                if not asset_path.is_file():
                    checks.append(RenderDependencyCheck(asset_id, "BLOCKED", "MISSING_ASSET"))
            except (SecurityBoundaryError, TypeError):
                checks.append(RenderDependencyCheck(asset_id, "INVALID", "INVALID_ASSET_PATH"))
        output_path = values.get("output_path")
        if output_path:
            try:
                path_within_root(self.allowed_asset_root, output_path)
            except (SecurityBoundaryError, TypeError):
                checks.append(RenderDependencyCheck("output", "INVALID", "INVALID_OUTPUT_PATH"))
        tracks = values.get("tracks", {})
        for track_id, segments in sorted(tracks.items()):
            previous_end = 0
            for segment in sorted(segments, key=lambda item: (item.get("start_ms", -1), item.get("position", 0))):
                start, end = segment.get("start_ms", -1), segment.get("end_ms", -1)
                if start < 0 or end <= start or start < previous_end:
                    checks.append(RenderDependencyCheck(str(track_id), "INVALID", "INVALID_TIMELINE_RANGE"))
                previous_end = max(previous_end, end)
        dependencies = values.get("dependencies", [])
        if len(dependencies) != len(set(dependencies)):
            checks.append(RenderDependencyCheck("dependencies", "INVALID", "INVALID_DEPENDENCY"))
        status = "INVALID" if any(check.status == "INVALID" for check in checks) else "BLOCKED" if any(check.status == "BLOCKED" for check in checks) else "VALID"
        operations: list[RenderOperation] = []
        if status == "VALID":
            for position, asset in enumerate(sorted(assets, key=lambda item: str(item.get("asset_id", "")))):
                arguments = [RenderArgument("asset", str(asset["path"]), 0), RenderArgument("asset_id", str(asset.get("asset_id", "")), 1)]
                operations.append(RenderOperation(deterministic_id("render_operation", [asset.get("asset_id", ""), asset.get("path", "")]), "PLACE_ASSET", arguments, position))
        plan = RenderExecutionPlan(deterministic_id("render_execution_plan", [[item.operation_id for item in operations], status]), operations, status)
        return RenderDryRunReport(deterministic_id("render_dry_run", [[check.__dict__ for check in checks], plan.plan_id]), status, checks, plan)
