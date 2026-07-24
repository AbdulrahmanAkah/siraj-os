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
SERIES_ID = "siraj-islamic-history-chronology"
WORKING_TITLE = "آدم عليه السلام: الخلق والتكريم والسكن في الجنة"
CENTRAL_QUESTION = (
    "ماذا ثبت عن حال الكون قبيل خلق آدم، وكيف خلقه الله وكرمه بالعلم، "
    "وأمر الملائكة بالسجود له، ثم خلق زوجه وأسكنهما الجنة؟"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL_RECORD_NOT_OBJECT:{path}:{line_number}")
        records.append(value)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(canonical_json(item) for item in records) + "\n"
    path.write_text(payload, encoding="utf-8", newline="\n")


def authority_class(source_type: str) -> str:
    mapping = {
        "quran": "REVELATION_PRIMARY",
        "hadith": "HADITH_PENDING_AUTHORIZED_GRADING",
        "tafsir": "SUNNI_CLASSICAL_TAFSIR",
        "historical_work": "SUNNI_CLASSICAL_HISTORY",
        "prophetic_history": "SUNNI_PROPHETIC_HISTORY",
        "israiliyyat": "COMPARATIVE_RESTRICTED",
    }
    return mapping.get(source_type, "UNCLASSIFIED_PENDING_REVIEW")


def primary_or_secondary(source_type: str) -> str:
    if source_type in {"quran", "hadith"}:
        return "PRIMARY"
    if source_type == "israiliyyat":
        return "COMPARATIVE"
    return "SECONDARY"


def source_type_label(source_type: str) -> str:
    return {
        "quran": "QURAN",
        "hadith": "HADITH",
        "tafsir": "TAFSIR",
        "historical_work": "HISTORICAL_WORK",
        "prophetic_history": "PROPHETIC_HISTORY",
        "israiliyyat": "ISRAILIYYAT",
    }.get(source_type, source_type.upper() or "UNKNOWN")


def patch_relative_contract_paths(composition_path: Path) -> bool:
    if not composition_path.is_file():
        raise FileNotFoundError(composition_path)
    text = composition_path.read_text(encoding="utf-8-sig")
    helper = '''\n\ndef _resolve_project_path(project_root: Path, value: str) -> Path:\n    """Resolve a contract path relative to the episode project root."""\n    candidate = Path(value)\n    return candidate.resolve() if candidate.is_absolute() else (project_root / candidate).resolve()\n'''
    changed = False
    if "def _resolve_project_path(" not in text:
        anchor = "def _fingerprint(value: Any) -> str:\n    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\")).encode(\"utf-8\")).hexdigest()\n"
        if anchor not in text:
            raise ValueError("COMPOSITION_PATCH_ANCHOR_NOT_FOUND")
        text = text.replace(anchor, anchor + helper, 1)
        changed = True
    replacements = {
        'evidence_path = Path(str(self.definition.get("evidence_package", {}).get("path", "")))': 'evidence_path = _resolve_project_path(self.project_root, str(self.definition.get("evidence_package", {}).get("path", "")))',
        'source_package_path = Path(str(definition.get("source_package", {}).get("path", "")))': 'source_package_path = _resolve_project_path(self.project_root, str(definition.get("source_package", {}).get("path", "")))',
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
        elif new not in text:
            raise ValueError(f"COMPOSITION_PATCH_TARGET_NOT_FOUND:{old}")
    if changed:
        composition_path.write_text(text, encoding="utf-8", newline="\n")
    return changed


def install_relative_path_test(test_path: Path) -> None:
    content = '''from pathlib import Path\n\nfrom src.application.episode_production_v1.composition import _resolve_project_path\n\n\ndef test_episode_contract_relative_path_resolves_from_project_root(tmp_path: Path) -> None:\n    assert _resolve_project_path(tmp_path, "contracts/source-package-v1.draft.json") == (tmp_path / "contracts" / "source-package-v1.draft.json").resolve()\n\n\ndef test_episode_contract_absolute_path_is_preserved(tmp_path: Path) -> None:\n    absolute = (tmp_path / "absolute.json").resolve()\n    assert _resolve_project_path(tmp_path / "other", str(absolute)) == absolute\n'''
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--keep-legacy-editorial-root", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    legacy = repo / "episodes" / "adam-01"
    project = repo / "projects" / EPISODE_ID
    editorial = project / "editorial"
    contracts = project / "contracts"
    if legacy.is_dir():
        inputs = {
            "episode": legacy / "episode.yaml",
            "readme": legacy / "README.md",
            "events": legacy / "event_map.json",
            "decisions": legacy / "human_decisions.json",
            "questions": legacy / "research_questions.json",
            "sources": legacy / "sources" / "source_registry.jsonl",
        }
    else:
        inputs = {
            "episode": editorial / "episode-brief.yaml",
            "readme": editorial / "README.md",
            "events": editorial / "event-map.json",
            "decisions": editorial / "human-decisions.json",
            "questions": editorial / "research-questions.json",
            "sources": editorial / "source-acquisition-register.jsonl",
        }

    required = [
        repo / "config" / "editorial_policy.yaml",
        repo / "series" / "historical_era_backbone.yaml",
        repo / "series" / "provisional_story_units.yaml",
        *inputs.values(),
        project / "episode.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_FILES:\n" + "\n".join(missing))

    questions = read_json(inputs["questions"])
    events = read_json(inputs["events"])
    decisions = read_json(inputs["decisions"])
    sources = read_jsonl(inputs["sources"])
    if not all(isinstance(value, list) for value in (questions, events, decisions)):
        raise ValueError("EDITORIAL_COLLECTION_NOT_LIST")

    question_ids = {item["question_id"] for item in questions}
    event_ids = {item["event_id"] for item in events}
    if len(question_ids) != len(questions):
        raise ValueError("DUPLICATE_RESEARCH_QUESTION_ID")
    if len(event_ids) != len(events):
        raise ValueError("DUPLICATE_EVENT_ID")
    dangling_questions = sorted({qid for event in events for qid in event.get("question_ids", []) if qid not in question_ids})
    if dangling_questions:
        raise ValueError("DANGLING_RESEARCH_QUESTION_REFS:" + ",".join(dangling_questions))

    # Correct the single known dangling event reference in the seed acquisition register.
    for source in sources:
        if source.get("source_id") == "SRC-QURAN-KAHF-050":
            source["supports_event_ids"] = [item for item in source.get("supports_event_ids", []) if item != "EV-ADAM-018"]
    dangling_events = sorted({eid for source in sources for eid in source.get("supports_event_ids", []) if eid not in event_ids})
    if dangling_events:
        raise ValueError("DANGLING_SOURCE_EVENT_REFS:" + ",".join(dangling_events))

    editorial.mkdir(parents=True, exist_ok=True)
    contracts.mkdir(parents=True, exist_ok=True)
    for source, destination in ((inputs["episode"], editorial / "episode-brief.yaml"), (inputs["readme"], editorial / "README.md")):
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
    write_json(editorial / "research-questions.json", questions)
    write_json(editorial / "event-map.json", events)
    write_json(editorial / "human-decisions.json", decisions)
    write_jsonl(editorial / "source-acquisition-register.jsonl", sources)

    now = utc_now()
    source_items: list[dict[str, Any]] = []
    for record in sources:
        raw_type = str(record.get("source_type", ""))
        location = record.get("location") or record.get("page_or_hadith_location")
        notes = {
            "verification_status": record.get("verification_status", "pending"),
            "usage_restrictions": record.get("usage_restrictions", []),
            "supports_event_ids": record.get("supports_event_ids", []),
            "canonical_locator": location,
            "israiliyyat_indicator": record.get("israiliyyat_indicator"),
        }
        source_items.append({
            "source_id": str(record["source_id"]),
            "source_type": source_type_label(raw_type),
            "title": str(record.get("title") or record["source_id"]),
            "author": str(record.get("author") or ""),
            "publisher": "",
            "publication_date": "",
            "edition": str(record.get("edition") or ""),
            "language": "ar",
            "path": "",
            "checksum": "",
            "page/section availability": "PLANNED",
            "access_status": "PLANNED",
            "authority_class": authority_class(raw_type),
            "primary_or_secondary": primary_or_secondary(raw_type),
            "allowed_for_extraction": False,
            "allowed_for_quotation": False,
            "copyright_or_usage_notes": "Acquisition and rights review pending.",
            "notes": notes,
        })

    source_package = {
        "schema_version": "siraj-episode-source-package-v1",
        "episode_id": EPISODE_ID,
        "source_package_id": "adam-01-source-package-draft-v1",
        "package_status": "DRAFT_ACQUISITION_PENDING",
        "title": "حزمة مصادر الحلقة الأولى من قصة آدم — مسودة اقتناء",
        "central_question": CENTRAL_QUESTION,
        "historical_scope": {
            "status": "PROVISIONAL",
            "starts_with": "حال الكون والمخلوقات قبل خلق آدم",
            "ends_with": "النهي عن الشجرة قبل وقوع الوسوسة",
            "chronology_policy": "VERIFIED_CHRONOLOGY_ONLY; EDITORIAL_ORDER_MUST_BE_LABELED",
            "required_event_ids": [item["event_id"] for item in sorted(events, key=lambda item: item.get("order", 0))],
        },
        "geographical_scope": {
            "status": "TO_BE_APPROVED",
            "notes": "لا يجزم بتعيين مواقع أرضية أو غيبية لم يثبت تعيينها.",
        },
        "language": "ar",
        "source_items": source_items,
        "inclusion_policy": {
            "quran": "REQUIRED",
            "authenticated_hadith": "REQUIRED_AFTER_AUTHORIZED_GRADING",
            "sunni_tafsir": "PRINCIPAL_WITH_REPORT_LEVEL_CLASSIFICATION",
            "sunni_history_and_prophetic_histories": "PRINCIPAL_WITH_REPORT_LEVEL_CLASSIFICATION",
            "israiliyyat": "LABELED_COMPARATIVE_USE_ONLY",
        },
        "exclusion_policy": {
            "sectarian_sources": ["TWELVER_SHIA", "RAFIDI", "ISMAILI", "BATINI"],
            "unsupported_modern_storytelling": True,
            "creed_conflicting_reports": True,
            "automatic_hadith_grading": True,
            "dorar_hadith_grading": True,
        },
        "religious_sensitivity": {
            "status": "HUMAN_REVIEW_REQUIRED",
            "methodology": "SUNNI_SALAFI",
            "israiliyyat_policy": "LABEL_AND_DO_NOT_ASSERT_WHERE_REVELATION_IS_SILENT",
            "hadith_grading_authorities": "PENDING_HUMAN_DEFINITION",
            "prohibited_visuals": ["DEPICTION_OF_ALLAH", "DEPICTION_OF_PROPHETS", "EMBODIED_DEPICTION_OF_ANGELS", "UNREVIEWED_RECONSTRUCTION_OF_UNSEEN_EVENTS"],
        },
        "research_questions": questions,
        "created_at": now,
        "updated_at": now,
        "input_fingerprint": "",
    }
    source_package["input_fingerprint"] = fingerprint({key: value for key, value in source_package.items() if key != "input_fingerprint"})
    source_package_path = contracts / "source-package-v1.draft.json"
    write_json(source_package_path, source_package)

    episode_definition = {
        "schema_version": "siraj-episode-definition-v1",
        "episode_id": EPISODE_ID,
        "series_id": SERIES_ID,
        "title": WORKING_TITLE,
        "working_title": WORKING_TITLE,
        "language": "ar",
        "target_duration_minutes": 22,
        "minimum_duration_minutes": 18,
        "maximum_duration_minutes": 25,
        "subject": "خلق آدم عليه السلام وتكريمه وميثاق ذريته والسكن في الجنة",
        "central_question": CENTRAL_QUESTION,
        "intended_audience": "general_arabic_documentary",
        "historical_scope": source_package["historical_scope"],
        "geographical_scope": source_package["geographical_scope"],
        "religious_sensitivity": "HUMAN_REVIEW_REQUIRED",
        "source_package": {"path": "contracts/source-package-v1.draft.json", "approval_status": "NOT_REQUESTED"},
        "evidence_package": {"path": "", "input_fingerprint": ""},
        "requested_outputs": ["render_manifest", "subtitles", "video"],
        "production_profile": "DOCUMENTARY_STANDARD_V1",
        "human_approval_policy": {
            "required_gates": ["source_adjudication", "evidence_approval", "script_approval", "religious_safety_approval", "storyboard_approval", "master_visual_approval", "video_approval", "final_render_approval", "publication_approval"]
        },
        "external_provider_policy": {
            "default_allowed": False,
            "explicit_live_confirmation_required": True,
            "provider_configured": False,
            "credential_present": False,
            "disclosure_permitted": False,
            "request_limit_available": False,
            "quota_policy_valid": False,
            "stage_permissions": {},
        },
        "generated_video_policy": {
            "maximum_final_generated_video_seconds": 300,
            "allowed_models": ["VEO_3_1_LITE_1080P", "VEO_3_1_FAST_1080P"],
            "allocation_owner": "STORYBOARD_WRITER",
            "enforcement_owner": "VIDEO_POLICY_GUARD",
            "final_approval_required": True,
        },
        "editorial_inputs": {
            "episode_brief": "editorial/episode-brief.yaml",
            "event_map": "editorial/event-map.json",
            "research_questions": "editorial/research-questions.json",
            "human_decisions": "editorial/human-decisions.json",
            "source_acquisition_register": "editorial/source-acquisition-register.jsonl",
            "global_editorial_policy": "../../config/editorial_policy.yaml",
            "historical_backbone": "../../series/historical_era_backbone.yaml",
            "story_units": "../../series/provisional_story_units.yaml",
        },
        "created_at": now,
        "updated_at": now,
    }
    episode_definition_path = contracts / "episode-definition-v1.json"
    write_json(episode_definition_path, episode_definition)

    pipeline_config = {
        "schema_version": "siraj-episode-production-pipeline-config-v1",
        "episode_id": EPISODE_ID,
        "narrative_writer": {"enabled": False},
        "tts": {"enabled": False},
        "subtitles": {"enabled": True},
        "storyboard": {"enabled": True},
        "visuals": {"enabled": False, "live_validation_status": "IMPLEMENTATION_COMPLETED_LIVE_VALIDATION_DEFERRED"},
        "video": {"enabled": False, "live_validation_status": "VIDEO_PROVIDER_V1_IMPLEMENTED_LIVE_VALIDATION_DEFERRED"},
        "render": {"enabled": False},
        "research": {"enabled": True, "extractor_status": "IMPLEMENTED_EXTRACTOR_DISCONNECTED"},
        "qa": {"enabled": False},
        "publication": {"enabled": False},
        "external_provider_policy": episode_definition["external_provider_policy"],
        "approval_policy": {"human_approval_required": True},
        "runtime_paths": {"root": "working/episode-production-v1"},
        "request_limits": {},
        "disclosure_permissions": {},
    }
    write_json(contracts / "pipeline-config-v1.json", pipeline_config)

    # Validate with the runtime contracts in this checkout.
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from src.application.episode_orchestration_v1.runtime import validate_episode_definition
    from src.application.research_verification_episode_v1.runtime import validate_source_package

    def validate_pipeline_config(value: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        if value.get("schema_version") != "siraj-episode-production-pipeline-config-v1":
            errors.append("PIPELINE_CONFIGURATION_SCHEMA_INVALID")
        for name in ("narrative_writer", "tts", "subtitles", "storyboard", "visuals", "video", "render", "research", "qa", "publication", "external_provider_policy"):
            if not isinstance(value.get(name, {}), dict):
                errors.append(f"PIPELINE_CONFIGURATION_SECTION_INVALID:{name}")
        if not isinstance(value.get("episode_id"), str) or not value["episode_id"].strip():
            errors.append("PIPELINE_CONFIGURATION_EPISODE_ID_REQUIRED")
        narrative = value.get("narrative_writer", {})
        if narrative.get("enabled") is True and not isinstance(narrative.get("model_id"), str):
            errors.append("NARRATIVE_WRITER_MODEL_REQUIRED")
        for name in ("subtitles", "storyboard", "render"):
            if value.get(name, {}).get("enabled") not in {True, False, None}:
                errors.append(f"PIPELINE_CONFIGURATION_ENABLED_INVALID:{name}")
        policy = value.get("external_provider_policy", {})
        if policy and not isinstance(policy.get("stage_permissions", {}), dict):
            errors.append("PIPELINE_STAGE_PERMISSIONS_INVALID")
        return errors

    validation = {
        "episode_definition_errors": validate_episode_definition(episode_definition),
        "source_package_errors": validate_source_package(source_package, project_root=project, episode_id=EPISODE_ID),
        "pipeline_config_errors": validate_pipeline_config(pipeline_config),
        "dangling_question_refs": dangling_questions,
        "dangling_event_refs": dangling_events,
        "counts": {"research_questions": len(questions), "events": len(events), "human_decisions": len(decisions), "source_records": len(sources)},
    }
    validation["status"] = "PASS" if not any(validation[key] for key in ("episode_definition_errors", "source_package_errors", "pipeline_config_errors", "dangling_question_refs", "dangling_event_refs")) else "FAIL"
    write_json(contracts / "integration-validation-v1.json", validation)
    if validation["status"] != "PASS":
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))

    composition_changed = patch_relative_contract_paths(repo / "src" / "application" / "episode_production_v1" / "composition.py")
    install_relative_path_test(repo / "tests" / "integration" / "test_episode_contract_relative_paths_v1.py")

    integration_manifest = {
        "schema_version": "siraj-editorial-integration-manifest-v1",
        "episode_id": EPISODE_ID,
        "status": "INTEGRATED_DRAFT_SOURCE_ACQUISITION_PENDING",
        "legacy_bootstrap_manifest_preserved": "episode.json",
        "legacy_reviewed_source_pack_preserved": "source-pack.json",
        "canonical_episode_definition": "contracts/episode-definition-v1.json",
        "draft_source_package": "contracts/source-package-v1.draft.json",
        "pipeline_config": "contracts/pipeline-config-v1.json",
        "validation_report": "contracts/integration-validation-v1.json",
        "composition_relative_path_fix_applied": composition_changed,
        "created_at": now,
    }
    write_json(editorial / "integration-manifest-v1.json", integration_manifest)

    if legacy.is_dir() and not args.keep_legacy_editorial_root:
        shutil.rmtree(legacy)
        episodes_root = repo / "episodes"
        try:
            episodes_root.rmdir()
        except OSError:
            pass

    print(json.dumps({
        "status": "PASS",
        "episode_definition": str(episode_definition_path),
        "source_package": str(source_package_path),
        "editorial_root": str(editorial),
        "composition_relative_path_fix_applied": composition_changed,
        "counts": validation["counts"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
