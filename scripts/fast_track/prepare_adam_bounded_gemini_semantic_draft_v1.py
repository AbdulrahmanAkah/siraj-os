from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EPISODE_ID = "episode-001-adam"
OUTPUT_DIR_NAME = "gemini-semantic-analysis-draft"
MANIFEST_SCHEMA = "siraj-adam-bounded-gemini-semantic-draft-manifest-v1"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{line_number}"
                )
            yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True)
                + "\n"
            )
            count += 1
    return count


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    material = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def compact(value: str) -> str:
    return " ".join(str(value or "").split())


def excerpt(value: str, maximum: int = 1400) -> str:
    value = compact(value)
    if len(value) <= maximum:
        return value
    return value[:maximum].rstrip() + "…"


def load_source_file(
    project: Path,
    manifest: dict[str, Any],
    output_key: str,
) -> Path:
    item = manifest["outputs"][output_key]
    path = project / item["project_path"]
    if not path.is_file():
        raise FileNotFoundError(f"SOURCE_OUTPUT_NOT_FOUND:{path}")
    if sha256_file(path) != item["sha256"]:
        raise ValueError(f"SOURCE_OUTPUT_CHECKSUM_MISMATCH:{output_key}")
    return path


def make_neighbour_map(
    records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    by_group: dict[tuple[str, Any, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for record in records:
        key = (
            str(record["work_source_id"]),
            record.get("book_id"),
            str(record.get("window_id") or ""),
        )
        by_group[key].append(record)

    neighbours: dict[str, dict[str, Any]] = {}
    for rows in by_group.values():
        rows.sort(
            key=lambda row: (
                int(row.get("sequence_num") or 0),
                int(row.get("segment_index") or 0),
                row["normalized_report_id"],
            )
        )
        for index, record in enumerate(rows):
            previous = rows[index - 1] if index > 0 else None
            following = (
                rows[index + 1]
                if index + 1 < len(rows)
                else None
            )
            neighbours[record["normalized_report_id"]] = {
                "previous": previous,
                "following": following,
            }
    return neighbours


def boundary_task_record(
    unresolved: dict[str, Any],
    normalized: dict[str, Any],
    neighbours: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    adjacent = neighbours.get(normalized["normalized_report_id"], {})
    previous = adjacent.get("previous")
    following = adjacent.get("following")

    return {
        "task_record_id": stable_id(
            "adam_gemini_boundary_task",
            normalized["normalized_report_id"],
        ),
        "normalized_report_id": normalized["normalized_report_id"],
        "work_source_id": normalized["work_source_id"],
        "book_id": normalized["book_id"],
        "window_id": normalized["window_id"],
        "canonical_locators": normalized["canonical_locators"],
        "warnings": unresolved["warnings"],
        "current_text": normalized["original_text"],
        "current_text_sha256": normalized["original_text_sha256"],
        "previous_context": (
            {
                "normalized_report_id": previous[
                    "normalized_report_id"
                ],
                "text_excerpt": excerpt(previous["original_text"]),
            }
            if previous
            else None
        ),
        "following_context": (
            {
                "normalized_report_id": following[
                    "normalized_report_id"
                ],
                "text_excerpt": excerpt(following["original_text"]),
            }
            if following
            else None
        ),
        "current_kind_candidate": normalized[
            "corrected_report_kind_candidate"
        ],
        "current_chain_nodes_candidate": normalized[
            "chain_nodes_candidate"
        ],
        "event_ids": normalized.get("event_ids") or [],
        "research_question_ids": normalized.get(
            "research_question_ids"
        )
        or [],
        "allowed_decisions": [
            "KEEP_AS_SINGLE",
            "SPLIT_CURRENT_TEXT",
            "MERGE_WITH_PREVIOUS",
            "MERGE_WITH_FOLLOWING",
            "DISCARD_AS_MID_REPORT_FRAGMENT",
            "REQUIRES_HUMAN_REVIEW",
        ],
        "permissions": {
            "candidate_only": True,
            "may_propose_boundaries": True,
            "may_not_grade_hadith": True,
            "may_not_judge_narrators": True,
            "may_not_approve_evidence": True,
            "may_not_approve_quotation": True,
            "may_not_approve_israiliyyat": True,
        },
    }


def semantic_task_record(
    normalized: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task_record_id": stable_id(
            "adam_gemini_semantic_task",
            normalized["normalized_report_id"],
        ),
        "normalized_report_id": normalized["normalized_report_id"],
        "work_source_id": normalized["work_source_id"],
        "book_id": normalized["book_id"],
        "book_title": normalized.get("book_title", ""),
        "window_id": normalized["window_id"],
        "canonical_locators": normalized["canonical_locators"],
        "original_text": normalized["original_text"],
        "original_text_sha256": normalized["original_text_sha256"],
        "footnote_context": normalized.get("footnote_context", ""),
        "kind_candidate": normalized[
            "corrected_report_kind_candidate"
        ],
        "report_form_candidate": normalized[
            "report_form_candidate"
        ],
        "chain_nodes_candidate": normalized[
            "chain_nodes_candidate"
        ],
        "terminal_speaker_surface_candidate": normalized.get(
            "terminal_speaker_surface_candidate"
        ),
        "event_ids": normalized.get("event_ids") or [],
        "research_question_ids": normalized.get(
            "research_question_ids"
        )
        or [],
        "attribution_profiles": normalized.get(
            "attribution_profiles"
        )
        or [],
        "requested_outputs": [
            "concise_claim_summary_ar",
            "speaker_type_candidate",
            "speaker_surface_candidate",
            "prophetic_or_non_prophetic_candidate",
            "event_mapping_proposal",
            "research_question_mapping_proposal",
            "text_variant_fingerprint",
            "source_dependence_observations",
            "possible_internal_report_count",
            "semantic_overlap_search_terms",
            "uncertainties",
        ],
        "permissions": {
            "candidate_only": True,
            "may_summarize_supplied_text": True,
            "may_propose_semantic_mappings": True,
            "may_compare_supplied_texts": True,
            "may_not_grade_hadith": True,
            "may_not_judge_narrators": True,
            "may_not_approve_isnad": True,
            "may_not_approve_evidence": True,
            "may_not_approve_quotation": True,
            "may_not_approve_israiliyyat": True,
            "may_not_add_external_facts": True,
        },
    }


def chain_task_record(
    chain: dict[str, Any],
    normalized: dict[str, Any],
    unresolved_ids: set[str],
) -> dict[str, Any]:
    return {
        "task_record_id": stable_id(
            "adam_gemini_chain_task",
            chain["chain_candidate_id"],
        ),
        "chain_candidate_id": chain["chain_candidate_id"],
        "normalized_report_id": chain["normalized_report_id"],
        "depends_on_boundary_resolution": (
            chain["normalized_report_id"] in unresolved_ids
        ),
        "work_source_id": chain["work_source_id"],
        "book_id": chain["book_id"],
        "canonical_locators": chain["canonical_locators"],
        "report_text": normalized["original_text"],
        "report_text_sha256": normalized["original_text_sha256"],
        "kind_candidate": chain[
            "corrected_report_kind_candidate"
        ],
        "report_form_candidate": chain["report_form_candidate"],
        "chain_nodes_candidate": chain["chain_nodes_candidate"],
        "terminal_speaker_surface_candidate": chain.get(
            "terminal_speaker_surface_candidate"
        ),
        "isnad_internal_text_candidate": chain[
            "isnad_internal_text_candidate"
        ],
        "script_attribution_candidate": chain[
            "script_attribution_candidate"
        ],
        "requested_outputs": [
            "ordered_chain_surface_proposal",
            "transmission_term_proposal",
            "terminal_speaker_surface_proposal",
            "prophet_reference_present",
            "companion_surface_candidate",
            "marfu_tabii_surface_candidate",
            "possible_chain_break_locations",
            "pronoun_or_alias_resolution_notes",
            "uncertainties",
        ],
        "permissions": {
            "candidate_only": True,
            "full_isnad_internal_retention": True,
            "full_isnad_in_script": False,
            "may_parse_chain_surfaces": True,
            "may_not_resolve_narrator_identity_final": True,
            "may_not_judge_narrator": True,
            "may_not_grade_hadith": True,
            "may_not_approve_chain_continuity": True,
            "may_not_approve_israiliyyat": True,
        },
    }


def batch_records(
    *,
    task_name: str,
    records: list[dict[str, Any]],
    output_dir: Path,
    contract_path: str,
    maximum_records: int,
    maximum_characters: int,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    for record in records:
        record_chars = len(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
        )
        if (
            current
            and (
                len(current) >= maximum_records
                or current_chars + record_chars
                > maximum_characters
            )
        ):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(record)
        current_chars += record_chars

    if current:
        batches.append(current)

    manifest_rows: list[dict[str, Any]] = []
    for index, batch in enumerate(batches, start=1):
        batch_id = f"{task_name}-batch-{index:04d}"
        payload = {
            "schema_version": (
                "siraj-adam-gemini-draft-batch-v1"
            ),
            "episode_id": EPISODE_ID,
            "provider_id": "GEMINI",
            "task_name": task_name,
            "batch_id": batch_id,
            "execution_status": "BLOCKED_NOT_AUTHORIZED",
            "execution_enabled": False,
            "model_id": None,
            "generation_config": {
                "temperature": 0,
                "response_mime_type": "application/json",
            },
            "task_contract_project_path": contract_path,
            "record_count": len(batch),
            "records": batch,
        }
        path = output_dir / f"{batch_id}.json"
        write_json(path, payload)
        manifest_rows.append(
            {
                "batch_id": batch_id,
                "task_name": task_name,
                "project_path": None,
                "record_count": len(batch),
                "character_count": len(
                    json.dumps(payload, ensure_ascii=False)
                ),
                "sha256": sha256_file(path),
                "local_path": str(path),
            }
        )
    return manifest_rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--maximum-records-per-batch", type=int, default=6)
    parser.add_argument(
        "--maximum-characters-per-batch",
        type=int,
        default=48000,
    )
    args = parser.parse_args()

    if not 1 <= args.maximum_records_per_batch <= 20:
        raise ValueError("MAXIMUM_RECORDS_PER_BATCH_OUT_OF_RANGE")
    if not 12000 <= args.maximum_characters_per_batch <= 100000:
        raise ValueError("MAXIMUM_CHARACTERS_PER_BATCH_OUT_OF_RANGE")

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    phase9_root = (
        secondary
        / "report-resegmentation-chain-normalization"
    )
    phase9_manifest_path = (
        phase9_root
        / "report-resegmentation-chain-normalization-manifest-v1.json"
    )
    phase9_manifest = read_json(phase9_manifest_path)

    if phase9_manifest.get("status") != (
        "PASS_NORMALIZED_REPORTS_READY_FOR_BOUNDED_SEMANTIC_REVIEW"
    ):
        raise ValueError("PHASE9_NOT_READY")
    if phase9_manifest.get("normalized_report_count") != 738:
        raise ValueError("EXPECTED_738_NORMALIZED_REPORTS")
    if (
        phase9_manifest.get("unresolved_boundary_record_count")
        != 446
    ):
        raise ValueError("EXPECTED_446_UNRESOLVED_BOUNDARIES")
    if (
        phase9_manifest.get("normalized_chain_candidate_count")
        != 448
    ):
        raise ValueError("EXPECTED_448_CHAIN_CANDIDATES")
    if (
        phase9_manifest.get("permissions", {}).get(
            "gemini_execution_enabled"
        )
        is not False
    ):
        raise ValueError("GEMINI_MUST_REMAIN_DISABLED")

    registry_path = load_source_file(
        project,
        phase9_manifest,
        "normalized_report_register",
    )
    unresolved_path = load_source_file(
        project,
        phase9_manifest,
        "unresolved_boundary_review_queue",
    )
    chain_path = load_source_file(
        project,
        phase9_manifest,
        "normalized_isnad_chain_candidates",
    )

    policy_path = (
        project
        / "editorial"
        / "narration-attribution-policy-v2.json"
    )
    if not policy_path.is_file():
        raise FileNotFoundError(
            f"NARRATION_POLICY_NOT_FOUND:{policy_path}"
        )
    policy = read_json(policy_path)
    if policy.get("status") != "USER_APPROVED_IN_CONVERSATION":
        raise ValueError("NARRATION_POLICY_NOT_APPROVED")

    normalized_records = list(iter_jsonl(registry_path))
    unresolved_records = list(iter_jsonl(unresolved_path))
    chain_records = list(iter_jsonl(chain_path))

    normalized_by_id = {
        record["normalized_report_id"]: record
        for record in normalized_records
    }
    unresolved_ids = {
        record["normalized_report_id"]
        for record in unresolved_records
    }

    if len(normalized_by_id) != 738:
        raise ValueError("NORMALIZED_ID_COUNT_MISMATCH")
    if len(unresolved_ids) != 446:
        raise ValueError("UNRESOLVED_ID_COUNT_MISMATCH")
    if not unresolved_ids <= set(normalized_by_id):
        raise ValueError("UNRESOLVED_REPORT_NOT_IN_REGISTRY")

    stable_ids = set(normalized_by_id) - unresolved_ids
    if len(stable_ids) != 292:
        raise ValueError("EXPECTED_292_STABLE_REPORTS")

    neighbours = make_neighbour_map(normalized_records)

    boundary_tasks = [
        boundary_task_record(
            unresolved,
            normalized_by_id[unresolved["normalized_report_id"]],
            neighbours,
        )
        for unresolved in unresolved_records
    ]
    boundary_tasks.sort(
        key=lambda row: (
            row["work_source_id"],
            int(row.get("book_id") or 0),
            row["normalized_report_id"],
        )
    )

    semantic_tasks = [
        semantic_task_record(normalized_by_id[report_id])
        for report_id in stable_ids
    ]
    semantic_tasks.sort(
        key=lambda row: (
            row["work_source_id"],
            int(row.get("book_id") or 0),
            row["normalized_report_id"],
        )
    )

    chain_tasks = []
    for chain in chain_records:
        report_id = chain["normalized_report_id"]
        if report_id not in normalized_by_id:
            raise ValueError(
                f"CHAIN_REPORT_NOT_FOUND:{report_id}"
            )
        chain_tasks.append(
            chain_task_record(
                chain,
                normalized_by_id[report_id],
                unresolved_ids,
            )
        )
    chain_tasks.sort(
        key=lambda row: (
            bool(row["depends_on_boundary_resolution"]),
            row["work_source_id"],
            int(row.get("book_id") or 0),
            row["normalized_report_id"],
        )
    )

    output_root = secondary / OUTPUT_DIR_NAME
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    contracts_root = output_root / "contracts"
    contracts_root.mkdir(parents=True)

    boundary_contract = {
        "schema_version": (
            "siraj-adam-gemini-boundary-resolution-contract-v1"
        ),
        "task_name": "BOUNDARY_RESOLUTION",
        "system_instruction_ar": (
            "أنت محلل حدود نصية فقط. استخدم النص والسياق المرفقين "
            "ولا تضف معرفة خارجية. اقترح إبقاء الوحدة أو تقسيمها عند "
            "إزاحات حرفية داخل current_text أو دمجها مع الجار المناسب. "
            "لا تحكم على صحة الرواية أو الرواة أو الإسناد."
        ),
        "required_response_fields": [
            "task_record_id",
            "normalized_report_id",
            "decision",
            "split_offsets",
            "merge_target_normalized_report_id",
            "reason_ar",
            "confidence",
            "uncertainties",
        ],
        "decision_enum": [
            "KEEP_AS_SINGLE",
            "SPLIT_CURRENT_TEXT",
            "MERGE_WITH_PREVIOUS",
            "MERGE_WITH_FOLLOWING",
            "DISCARD_AS_MID_REPORT_FRAGMENT",
            "REQUIRES_HUMAN_REVIEW",
        ],
        "prohibited_outputs": [
            "hadith_grade",
            "narrator_judgement",
            "isnad_approval",
            "israiliyyat_approval",
            "evidence_approval",
            "quotation_approval",
        ],
    }
    semantic_contract = {
        "schema_version": (
            "siraj-adam-gemini-semantic-mapping-contract-v1"
        ),
        "task_name": "SEMANTIC_MAPPING",
        "system_instruction_ar": (
            "حلل التقرير المرفق فقط. لخص ادعاءه، واقترح نوع القائل "
            "وربطه بأحداث وأسئلة الحلقة، وحدد التداخل النصي أو اعتماد "
            "المصادر بوصفه ملاحظة مرشحة. لا تضف معلومات خارج النص ولا "
            "تحكم على صحة الحديث أو الراوي أو الإسرائيلية."
        ),
        "required_response_fields": [
            "task_record_id",
            "normalized_report_id",
            "concise_claim_summary_ar",
            "speaker_type_candidate",
            "speaker_surface_candidate",
            "prophetic_or_non_prophetic_candidate",
            "event_mapping_proposal",
            "research_question_mapping_proposal",
            "text_variant_fingerprint",
            "source_dependence_observations",
            "possible_internal_report_count",
            "semantic_overlap_search_terms",
            "uncertainties",
        ],
        "prohibited_outputs": [
            "hadith_grade",
            "narrator_judgement",
            "isnad_approval",
            "israiliyyat_approval",
            "evidence_approval",
            "quotation_approval",
            "external_fact",
        ],
    }
    chain_contract = {
        "schema_version": (
            "siraj-adam-gemini-chain-interpretation-contract-v1"
        ),
        "task_name": "CHAIN_INTERPRETATION",
        "system_instruction_ar": (
            "حلل السند بوصفه بنية سطحية فقط. اقترح ترتيب الأسماء "
            "وألفاظ الأداء والقائل النهائي ووجود نسبة إلى النبي ﷺ. "
            "لا تثبت هوية راوٍ نهائيًا، ولا تحكم عليه، ولا تحكم باتصال "
            "السند أو صحة الحديث."
        ),
        "required_response_fields": [
            "task_record_id",
            "chain_candidate_id",
            "normalized_report_id",
            "ordered_chain_surface_proposal",
            "transmission_term_proposal",
            "terminal_speaker_surface_proposal",
            "prophet_reference_present",
            "companion_surface_candidate",
            "marfu_tabii_surface_candidate",
            "possible_chain_break_locations",
            "pronoun_or_alias_resolution_notes",
            "uncertainties",
        ],
        "prohibited_outputs": [
            "hadith_grade",
            "narrator_judgement",
            "chain_continuity_approval",
            "israiliyyat_approval",
        ],
    }

    boundary_contract_path = (
        contracts_root / "boundary-resolution-contract-v1.json"
    )
    semantic_contract_path = (
        contracts_root / "semantic-mapping-contract-v1.json"
    )
    chain_contract_path = (
        contracts_root / "chain-interpretation-contract-v1.json"
    )
    write_json(boundary_contract_path, boundary_contract)
    write_json(semantic_contract_path, semantic_contract)
    write_json(chain_contract_path, chain_contract)

    project_prefix = (
        "sources/secondary/"
        + OUTPUT_DIR_NAME
        + "/contracts/"
    )

    boundary_batches = batch_records(
        task_name="boundary-resolution",
        records=boundary_tasks,
        output_dir=output_root / "boundary-resolution" / "batches",
        contract_path=(
            project_prefix
            + boundary_contract_path.name
        ),
        maximum_records=args.maximum_records_per_batch,
        maximum_characters=args.maximum_characters_per_batch,
    )
    semantic_batches = batch_records(
        task_name="semantic-mapping",
        records=semantic_tasks,
        output_dir=output_root / "semantic-mapping" / "batches",
        contract_path=(
            project_prefix
            + semantic_contract_path.name
        ),
        maximum_records=args.maximum_records_per_batch,
        maximum_characters=args.maximum_characters_per_batch,
    )
    chain_batches = batch_records(
        task_name="chain-interpretation",
        records=chain_tasks,
        output_dir=output_root / "chain-interpretation" / "batches",
        contract_path=(
            project_prefix
            + chain_contract_path.name
        ),
        maximum_records=args.maximum_records_per_batch,
        maximum_characters=args.maximum_characters_per_batch,
    )

    all_batches = [
        *boundary_batches,
        *semantic_batches,
        *chain_batches,
    ]
    for batch in all_batches:
        local_path = Path(batch.pop("local_path"))
        batch["project_path"] = local_path.relative_to(
            project
        ).as_posix()

    execution_lock = {
        "schema_version": "siraj-gemini-execution-lock-v1",
        "episode_id": EPISODE_ID,
        "provider_id": "GEMINI",
        "execution_enabled": False,
        "execution_status": "BLOCKED_NOT_AUTHORIZED",
        "explicit_user_authorization_required": True,
        "model_id_required_before_execution": True,
        "api_key_required_at_execution_only": True,
        "network_call_present_in_this_phase": False,
        "allowed_task_names_after_authorization": [
            "boundary-resolution",
            "semantic-mapping",
            "chain-interpretation",
        ],
        "prohibited_authority_actions": [
            "hadith grading",
            "narrator judgement",
            "isnad approval",
            "Israiliyyat approval",
            "evidence approval",
            "quotation approval",
            "final narrative approval",
        ],
    }
    execution_lock_path = output_root / "execution-lock-v1.json"
    write_json(execution_lock_path, execution_lock)

    policy_snapshot_path = (
        output_root / "narration-attribution-policy-snapshot-v2.json"
    )
    write_json(policy_snapshot_path, policy)

    batch_index_path = output_root / "batch-index-v1.csv"
    with batch_index_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "task_name",
            "batch_id",
            "project_path",
            "record_count",
            "character_count",
            "sha256",
            "execution_status",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for batch in all_batches:
            writer.writerow(
                {
                    **batch,
                    "execution_status": "BLOCKED_NOT_AUTHORIZED",
                }
            )

    task_counts = {
        "boundary_resolution_records": len(boundary_tasks),
        "stable_semantic_mapping_records": len(semantic_tasks),
        "chain_interpretation_records": len(chain_tasks),
        "chain_records_depending_on_boundary_resolution": sum(
            1
            for row in chain_tasks
            if row["depends_on_boundary_resolution"]
        ),
    }
    batch_counts = {
        "boundary_resolution_batches": len(boundary_batches),
        "semantic_mapping_batches": len(semantic_batches),
        "chain_interpretation_batches": len(chain_batches),
        "total_batches": len(all_batches),
    }

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "PASS_GEMINI_DRAFTS_READY_EXECUTION_BLOCKED",
        "created_at": now_utc(),
        "source_phase9_manifest": phase9_manifest_path.relative_to(
            project
        ).as_posix(),
        "source_phase9_manifest_sha256": sha256_file(
            phase9_manifest_path
        ),
        "source_policy": policy_path.relative_to(project).as_posix(),
        "source_policy_sha256": sha256_file(policy_path),
        "normalized_report_count": len(normalized_records),
        "unresolved_boundary_count": len(unresolved_records),
        "stable_report_count": len(stable_ids),
        "normalized_chain_candidate_count": len(chain_records),
        "task_counts": task_counts,
        "batch_counts": batch_counts,
        "configuration": {
            "maximum_records_per_batch": (
                args.maximum_records_per_batch
            ),
            "maximum_characters_per_batch": (
                args.maximum_characters_per_batch
            ),
            "temperature": 0,
            "response_mime_type": "application/json",
        },
        "outputs": {
            "execution_lock": {
                "project_path": execution_lock_path.relative_to(
                    project
                ).as_posix(),
                "sha256": sha256_file(execution_lock_path),
            },
            "batch_index": {
                "project_path": batch_index_path.relative_to(
                    project
                ).as_posix(),
                "rows": len(all_batches),
                "sha256": sha256_file(batch_index_path),
            },
            "policy_snapshot": {
                "project_path": policy_snapshot_path.relative_to(
                    project
                ).as_posix(),
                "sha256": sha256_file(policy_snapshot_path),
            },
            "contracts": {
                "boundary_resolution": {
                    "project_path": (
                        boundary_contract_path.relative_to(
                            project
                        ).as_posix()
                    ),
                    "sha256": sha256_file(
                        boundary_contract_path
                    ),
                },
                "semantic_mapping": {
                    "project_path": (
                        semantic_contract_path.relative_to(
                            project
                        ).as_posix()
                    ),
                    "sha256": sha256_file(
                        semantic_contract_path
                    ),
                },
                "chain_interpretation": {
                    "project_path": (
                        chain_contract_path.relative_to(
                            project
                        ).as_posix()
                    ),
                    "sha256": sha256_file(
                        chain_contract_path
                    ),
                },
            },
            "batches": all_batches,
        },
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "network_call_made": False,
            "source_approval_changed": False,
            "evidence_approval_changed": False,
            "quotation_approval_changed": False,
            "hadith_grading_changed": False,
            "narrator_judgement_changed": False,
            "isnad_approval_changed": False,
            "israiliyyat_classification_changed": False,
            "final_narrative_approval_changed": False,
        },
        "next_gate": "EXPLICIT_GEMINI_EXECUTION_AUTHORIZATION",
    }
    manifest_path = (
        output_root / "gemini-semantic-analysis-draft-manifest-v1.json"
    )
    write_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": str(manifest_path),
                "task_counts": task_counts,
                "batch_counts": batch_counts,
                "execution_enabled": False,
                "network_call_made": False,
                "gemini_execution_enabled": False,
                "next_gate": manifest["next_gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
