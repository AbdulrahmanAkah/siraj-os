from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _bootstrap_repo_root() -> Path:
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / "src").is_dir() and (parent / "projects").is_dir():
            root = parent
            break
    else:
        raise RuntimeError("Unable to locate the Siraj repository root.")
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)
    return root


BOOTSTRAPPED_REPO_ROOT = _bootstrap_repo_root()

from src.application.storyboard_runtime.evidence_binding import (  # noqa: E402
    ApprovedEvidenceBinder,
    ApprovedEvidencePackage,
    ApprovedEventEvidenceAdjudication,
    CinematicSeriesError,
    event_evidence_adjudication_template,
    approved_evidence_package_template,
    validate_non_executable_templates,
    write_evidence_bound_blueprint,
)


EPISODE_RELATIVE = Path("projects/episode-001-adam")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Bind human-approved evidence to the Adam cinematic blueprint. "
            "No research, approval, provider call, or paid execution occurs."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=BOOTSTRAPPED_REPO_ROOT)
    parser.add_argument(
        "--approved-source-package",
        type=Path,
        default=Path("contracts/source-package-v1.approved.json"),
    )
    parser.add_argument(
        "--approved-evidence-package",
        type=Path,
        default=Path("evidence/approved-evidence-package-v1.json"),
    )
    parser.add_argument(
        "--approved-adjudication",
        type=Path,
        default=Path("evidence/event-evidence-adjudication-v1.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("cinematic/evidence-bound-cinematic-blueprint-v1.json"),
    )
    parser.add_argument(
        "--template-check",
        action="store_true",
        help="Validate that shipped templates are intentionally non-executable.",
    )
    return parser.parse_args()


def _resolve(episode_root: Path, value: Path) -> Path:
    return value if value.is_absolute() else episode_root / value


def _template_check(episode_root: Path) -> int:
    evidence_path = episode_root / "evidence/approved-evidence-package-v1.template.json"
    adjudication_path = (
        episode_root / "evidence/event-evidence-adjudication-v1.template.json"
    )
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    adjudication = json.loads(adjudication_path.read_text(encoding="utf-8"))
    if not validate_non_executable_templates(evidence, adjudication):
        raise CinematicSeriesError("Evidence templates are unexpectedly executable.")
    try:
        ApprovedEvidencePackage.from_mapping(evidence)
    except CinematicSeriesError:
        pass
    else:
        raise CinematicSeriesError("Evidence template passed as an approved package.")
    try:
        ApprovedEventEvidenceAdjudication.from_mapping(adjudication)
    except CinematicSeriesError:
        pass
    else:
        raise CinematicSeriesError("Adjudication template passed as approved.")
    print("STATUS=PASS_EVIDENCE_TEMPLATES_NON_EXECUTABLE")
    print("EVIDENCE_APPROVAL_AUTOMATION=FORBIDDEN")
    print("CURRENT_ADAM_EVIDENCE_GATE=WITHHELD")
    print("LIVE_PROVIDER_EXECUTION=BLOCKED")
    return 0


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()
    episode_root = repo_root / EPISODE_RELATIVE
    if args.template_check:
        return _template_check(episode_root)

    editorial_blueprint = (
        episode_root / "cinematic/editorial-cinematic-blueprint-v1.json"
    )
    binder = ApprovedEvidenceBinder()
    result = binder.bind_from_project(
        episode_root=episode_root,
        editorial_blueprint_path=editorial_blueprint,
        approved_source_package_path=_resolve(
            episode_root, args.approved_source_package
        ),
        approved_evidence_package_path=_resolve(
            episode_root, args.approved_evidence_package
        ),
        approved_adjudication_path=_resolve(
            episode_root, args.approved_adjudication
        ),
    )
    output = _resolve(episode_root, args.output)
    write_evidence_bound_blueprint(output, result)
    manifest = result.to_manifest()
    resolution = manifest["event_resolution"]
    print("STATUS=PASS_APPROVED_EVIDENCE_BOUND_OFFLINE")
    print(f"OUTPUT={output}")
    print(f"BINDING_ID={manifest['binding_id']}")
    print(f"EVIDENCE_GATE_STATUS={manifest['evidence_gate_status']}")
    print(f"INCLUDED_EVENTS={len(resolution['included_event_ids'])}")
    print(f"QUALIFIED_EVENTS={len(resolution['qualified_event_ids'])}")
    print(f"OMITTED_EVENTS={len(resolution['omitted_event_ids'])}")
    print(f"EDITORIAL_EVENTS={len(resolution['editorial_event_ids'])}")
    print("GENERATED_VIDEO_PREALLOCATION_SECONDS=0")
    print("RUNWARE_LIVE_EXECUTION=BLOCKED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        CinematicSeriesError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        RuntimeError,
    ) as error:
        print(f"STATUS=FAIL {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
