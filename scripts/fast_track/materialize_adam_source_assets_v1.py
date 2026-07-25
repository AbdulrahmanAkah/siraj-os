from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EPISODE_ID = "episode-001-adam"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_NOT_OBJECT:{path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--asset-map", required=True)
    parser.add_argument("--activate-exact-package", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    contracts = project / "contracts"
    sources_root = project / "sources"
    package_path = contracts / "source-package-v1.exact-draft.json"
    plan_path = sources_root / "acquisition-plan-v1.json"
    state_path = sources_root / "source-materialization-state-v1.json"
    episode_path = contracts / "episode-definition-v1.json"

    for path in (package_path, plan_path, state_path, episode_path, Path(args.asset_map)):
        if not path.is_file():
            raise SystemExit(f"FILE_NOT_FOUND:{path}")

    package = read_json(package_path)
    plan = read_json(plan_path)
    state = read_json(state_path)
    asset_map = read_json(Path(args.asset_map).resolve())
    assets = asset_map.get("assets")
    if not isinstance(assets, dict):
        raise ValueError("ASSET_MAP_ASSETS_INVALID")

    targets = {item["asset_key"]: item for item in plan["asset_targets"]}
    results: dict[str, dict[str, Any]] = {}

    for asset_key, config in assets.items():
        if asset_key not in targets:
            raise ValueError(f"UNKNOWN_ASSET_KEY:{asset_key}")
        if not isinstance(config, dict):
            raise ValueError(f"ASSET_CONFIG_INVALID:{asset_key}")
        raw_path = str(config.get("external_source_path", "")).strip()
        if not raw_path:
            results[asset_key] = {"status": "PENDING", "path": "", "checksum": ""}
            continue
        source = Path(raw_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"ASSET_SOURCE_NOT_FOUND:{asset_key}:{source}")
        target = project / targets[asset_key]["normalized_target_path"]
        target = target.resolve()
        try:
            target.relative_to(project.resolve())
        except ValueError as error:
            raise ValueError(f"TARGET_OUTSIDE_PROJECT:{asset_key}") from error
        target.parent.mkdir(parents=True, exist_ok=True)
        if config.get("copy_into_project", True):
            if source != target:
                shutil.copy2(source, target)
        elif source != target:
            raise ValueError(f"NONCOPY_ASSET_MUST_ALREADY_BE_TARGET_PATH:{asset_key}")
        checksum = sha256_file(target)
        rights_reviewed = config.get("rights_reviewed") is True
        enable_extraction = config.get("enable_extraction") is True and rights_reviewed
        enable_quotation = config.get("enable_quotation") is True and rights_reviewed
        results[asset_key] = {
            "status": "AVAILABLE",
            "path": target.relative_to(project).as_posix(),
            "checksum": checksum,
            "rights_reviewed": rights_reviewed,
            "enable_extraction": enable_extraction,
            "enable_quotation": enable_quotation,
        }

    for item in package["source_items"]:
        notes = item.get("notes") if isinstance(item.get("notes"), dict) else {}
        asset_key = notes.get("asset_key")
        if asset_key not in results:
            continue
        result = results[asset_key]
        if result["status"] != "AVAILABLE":
            continue
        item["path"] = result["path"]
        item["checksum"] = result["checksum"]
        item["access_status"] = "AVAILABLE"
        item["page/section availability"] = "EXACT_LOCATOR_RECORDED"
        item["allowed_for_extraction"] = result["enable_extraction"]
        item["allowed_for_quotation"] = result["enable_quotation"]
        item["copyright_or_usage_notes"] = "Rights reviewed." if result["rights_reviewed"] else "Rights review pending; extraction and quotation disabled."

    exact_items = [item for item in package["source_items"] if isinstance(item.get("notes"), dict) and item["notes"].get("asset_key")]
    available_count = sum(item["access_status"] == "AVAILABLE" for item in exact_items)
    extractable_count = sum(item["allowed_for_extraction"] is True for item in exact_items)
    quotable_count = sum(item["allowed_for_quotation"] is True for item in exact_items)
    package["package_status"] = "DRAFT_PARTIALLY_MATERIALIZED" if available_count else "DRAFT_EXACT_LOCATORS_ASSETS_PENDING"
    if available_count == len(exact_items):
        package["package_status"] = "DRAFT_PHASE1_ASSETS_MATERIALIZED_REVIEW_PENDING"
    package["updated_at"] = now_utc()
    package["input_fingerprint"] = ""
    package["input_fingerprint"] = fingerprint({key: value for key, value in package.items() if key != "input_fingerprint"})

    state.update({
        "status": "PHASE1_ASSETS_MATERIALIZED_REVIEW_PENDING" if available_count == len(exact_items) else ("PARTIALLY_MATERIALIZED" if available_count else "NO_ASSETS_MATERIALIZED"),
        "available_record_count": available_count,
        "extractable_record_count": extractable_count,
        "quotable_record_count": quotable_count,
        "asset_families": results,
        "updated_at": now_utc(),
    })

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from src.application.research_verification_episode_v1.runtime import validate_source_package
    errors = validate_source_package(package, project_root=project, episode_id=EPISODE_ID)
    if errors:
        raise SystemExit(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))

    write_json(package_path, package)
    write_json(state_path, state)

    activated = False
    if args.activate_exact_package:
        if available_count != len(exact_items):
            raise SystemExit("EXACT_PACKAGE_ACTIVATION_REQUIRES_ALL_PHASE1_ASSETS")
        episode = read_json(episode_path)
        episode["source_package"] = {"path": "contracts/source-package-v1.exact-draft.json", "approval_status": "NOT_REQUESTED"}
        episode["updated_at"] = now_utc()
        write_json(episode_path, episode)
        activated = True

    print(json.dumps({
        "status": "PASS",
        "available_exact_records": available_count,
        "extractable_exact_records": extractable_count,
        "quotable_exact_records": quotable_count,
        "exact_record_count": len(exact_items),
        "exact_package_activated": activated,
        "source_approval_changed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
