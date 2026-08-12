"""SIRAJ V5.1 — Iconic Cinematic Review of Story Architecture.

This is a creative/editorial review inside the already-authorized
STORY_ARCHITECTURE stage.

It preserves the evidence-approved architecture, subjects it to Luna MAX+PRO
with the Iconic Cinematic Brain, iterates only when Luna deliberately returns
CONTINUE_ARCHITECTURE, and promotes the reviewed architecture only after PASS.

No automatic provider retries.
No assistant-authored call/cost/output/pacing caps.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_luna_adaptive_transport_v5 import post_luna_once
from src.application.siraj_luna_story_architecture_v5 import (
    _base_text_cost_usd,
    _extract_output_text,
    _schema,
    _usage,
    _validate_result,
    _validate_strict_schema,
)

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
STAGE = "STORY_ARCHITECTURE"
SUBSTAGE = "STORY_ARCHITECTURE_ICONIC_CREATIVE_REVIEW"
MODEL = "gpt-5.6-luna"


class IconicArchitectureReviewError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise IconicArchitectureReviewError(
            f"JSON_READ_FAILED:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise IconicArchitectureReviewError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _exclusive_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(dict(value), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise IconicArchitectureReviewError(
            f"EXCLUSIVE_FILE_ALREADY_EXISTS:{path}"
        ) from exc
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        0o600,
    )
    try:
        os.write(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)


def _last_ledger_event(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last = None
    for raw in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        raw = raw.strip()
        if not raw:
            continue
        value = json.loads(raw)
        if isinstance(value, dict):
            last = value
    return last


def _system_prompt() -> str:
    return """
المرحلة: STORY_ARCHITECTURE.
المهمة الفرعية: STORY_ARCHITECTURE_ICONIC_CREATIVE_REVIEW.

أمامك Story Architecture اجتازت بالفعل بوابة الأدلة ومصفوفة الادعاءات.
لا تعد البحث، ولا تغيّر قوة الادعاءات، ولا تخترع حدثاً أو حقيقة.

مهمتك الآن هي مراجعة هذه البنية كـShowrunner ومخرج سينمائي أيقوني بأقصى
معيار إبداعي متاح، ثم إعادة نفس مخطط Story Architecture بعد تحسينه.

اختبر البنية بقسوة:

- هل الـHook لا يمكن استبداله بهوك عام لأي فيديو آخر؟
- هل كل Beat يسبب ما بعده، أم أن بعضه مجرد معلومات متجاورة؟
- هل منحنى التوتر يتصاعد ويتنفس بصورة مقصودة؟
- هل يوجد لكل Beat محوري "فكرة بصرية قابلة للتذكر" حتى قبل storyboard؟
- هل توجد motifs قابلة للتطور عبر الحلقة من غير افتعال؟
- هل التحولات النفسية: وسوسة/اقتراب/زلة/انكشاف/عاقبة/توبة أو ما تسمح به
  الأدلة، محسوسة سردياً لا مجرد عناوين؟
- هل توجد لحظات متوقعة أو generic AI يمكن استبدالها بحلول أجرأ وأدق؟
- هل الغيب يُعامل بالرهبة والحجب والتجريد والمقياس دون ادعاء وصف غير ثابت؟
- هل هناك Beat يمكن حذفه بلا خسارة؟ إذا نعم فإما احذفه أو اجعله ضرورياً.
- هل الانتقالات نابعة من السبب والمعنى، لا من جمل وصل؟
- هل النهاية Resolution حقيقي وليست مجرد توقف؟
- هل البنية تمهد لكتابة Final Script قوي دون أن تقيده بمدة أو عدد كلمات؟
- هل أي إبداع اصطدم بالدليل؟ إن حدث، الدليل ينتصر.

لا تكتب السكربت النهائي.
لا تحدد مدة.
لا تحدد عدد لقطات.
لا تضف تفاصيل واقعية غير موجودة في Claim Matrix.

إذا وجدت أن البنية تحتاج جولة تحريرية أخرى، أعد CONTINUE_ARCHITECTURE مع
revision_needed=true وحدد revision targets دقيقة. ستصلك البنية الجديدة في
الجولة التالية للمراجعة الذاتية.

إذا كانت Claim Matrix نفسها تمنع الحل، أعد NEEDS_CLAIM_MATRIX_REOPEN.

لا تعد PASS إلا عندما تعتبر البنية صالحة فعلاً لتكون أساس حلقة ذات هوية
سينمائية مميزة، مترابطة، دقيقة، وقابلة للتذكر.
""".strip()


def _request(
    source_package: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
    candidate: Mapping[str, Any],
    review_iteration: int,
) -> dict[str, Any]:
    schema = _schema()
    _validate_strict_schema(schema)
    context = {
        "stage": STAGE,
        "substage": SUBSTAGE,
        "episode_id": EPISODE_ID,
        "review_iteration": review_iteration,
        "canonical_source_package": source_package,
        "source_claim_matrix": claim_matrix,
        "architecture_candidate": candidate,
        "review_mandate": (
            "Preserve evidence correctness; maximize originality, cinematic "
            "causality, memorable structure, visual potential, rhythm, "
            "emotional precision, continuity, and anti-generic quality."
        ),
    }
    return {
        "model": MODEL,
        "store": False,
        "reasoning": {
            "effort": "max",
            "mode": "pro",
        },
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": _system_prompt(),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            context,
                            ensure_ascii=False,
                            indent=2,
                        ),
                    }
                ],
            },
        ],
        "text": {
            "verbosity": "high",
            "format": {
                "type": "json_schema",
                "name": "siraj_luna_story_architecture_v5",
                "strict": True,
                "schema": schema,
            },
        },
    }


def _safe_validate(
    result: Mapping[str, Any],
    claim_matrix: Mapping[str, Any],
) -> None:
    try:
        _validate_result(result, claim_matrix)
    except Exception as exc:
        raise IconicArchitectureReviewError(
            f"REVIEWED_ARCHITECTURE_VALIDATION_FAILED:{exc}"
        ) from exc


def run(repo: Path) -> None:
    repo = repo.resolve()
    episode = repo / "projects" / EPISODE_ID

    source_package_path = (
        episode / "research/canonical-source-package-v5.json"
    )
    claim_matrix_path = (
        episode / "research/source-claim-matrix-v5.json"
    )
    canonical_architecture_path = (
        episode / "preproduction/luna-story-architecture-v5.json"
    )
    pre_iconic_archive_path = (
        episode
        / "preproduction/luna-story-architecture-pre-iconic-v5.json"
    )
    reviewed_output_path = (
        episode
        / "preproduction/luna-story-architecture-iconic-reviewed-v5-1.json"
    )
    auth_path = (
        episode
        / "orchestration/"
        "luna-story-architecture-iconic-review-authorization-v5-1.json"
    )
    state_path = (
        episode
        / "orchestration/"
        "story-architecture-iconic-review-v5-1-state.json"
    )
    marker_path = (
        episode / "orchestration/luna-runtime-v5-active.json"
    )

    root = (
        episode
        / "orchestration/luna-v5-1/story-architecture-iconic-review"
    )
    ledger = root / "attempt-ledger.jsonl"
    locks = root / "locks"
    raw_responses = root / "raw-responses"
    rounds = root / "rounds"
    receipts = root / "receipts"

    for path in (
        source_package_path,
        claim_matrix_path,
        canonical_architecture_path,
        auth_path,
        marker_path,
    ):
        if not path.is_file():
            raise IconicArchitectureReviewError(
                f"REQUIRED_FILE_MISSING:{path}"
            )

    source_package = _read_json(source_package_path)
    claim_matrix = _read_json(claim_matrix_path)
    current_architecture = _read_json(canonical_architecture_path)

    if source_package.get("status") != "PASS":
        raise IconicArchitectureReviewError(
            "CANONICAL_SOURCE_PACKAGE_NOT_PASS"
        )
    if claim_matrix.get("status") != "PASS":
        raise IconicArchitectureReviewError(
            "CLAIM_MATRIX_NOT_PASS"
        )
    _safe_validate(current_architecture, claim_matrix)
    if current_architecture.get("status") != "PASS":
        raise IconicArchitectureReviewError(
            "INPUT_ARCHITECTURE_NOT_PASS"
        )

    auth = _read_json(auth_path)
    if auth.get("status") != "ACTIVE":
        raise IconicArchitectureReviewError(
            f"REVIEW_AUTHORIZATION_NOT_ACTIVE:{auth.get('status')}"
        )
    if auth.get("automatic_retry") is not False:
        raise IconicArchitectureReviewError(
            "AUTOMATIC_RETRY_MUST_BE_FALSE"
        )

    marker = _read_json(marker_path)
    if marker.get("iconic_cinematic_brain") != "ACTIVE":
        raise IconicArchitectureReviewError(
            "ICONIC_CINEMATIC_BRAIN_NOT_ACTIVE"
        )
    if marker.get("luna_reasoning_effort") != "max":
        raise IconicArchitectureReviewError(
            "LUNA_MAX_REASONING_NOT_ACTIVE"
        )
    if marker.get("luna_reasoning_mode") != "pro":
        raise IconicArchitectureReviewError(
            "LUNA_PRO_MODE_NOT_ACTIVE"
        )

    if reviewed_output_path.is_file():
        reviewed = _read_json(reviewed_output_path)
        _safe_validate(reviewed, claim_matrix)
        if reviewed.get("status") == "PASS":
            print(
                "SIRAJ_LUNA_STORY_ARCHITECTURE_ICONIC_REVIEW_V5_1_"
                "ALREADY_COMPLETE"
            )
            print(f"OUTPUT={reviewed_output_path}")
            print("NEXT_STAGE=FINAL_SCRIPT")
            return

    # Preserve the evidence-approved pre-iconic architecture once.
    if not pre_iconic_archive_path.exists():
        shutil.copy2(
            canonical_architecture_path,
            pre_iconic_archive_path,
        )

    last = _last_ledger_event(ledger)
    if last and last.get("event") in {
        "PREPARED",
        "FAILED_NO_AUTO_RETRY",
        "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
        "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
        "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
    }:
        raise IconicArchitectureReviewError(
            "PREVIOUS_NON_SUCCESSFUL_PROVIDER_ATTEMPT_REQUIRES_MANUAL_REVIEW:"
            + str(last.get("event"))
        )

    completed_rounds = sorted(
        rounds.glob("review-iteration-*.json")
    )
    review_iteration = 1
    candidate = current_architecture

    if completed_rounds:
        candidate = _read_json(completed_rounds[-1])
        _safe_validate(candidate, claim_matrix)
        review_iteration = (
            int(candidate.get("_siraj_review_iteration", 0) or 0)
            + 1
        )
        if candidate.get("status") == "PASS":
            _atomic_write(reviewed_output_path, candidate)
            _atomic_write(canonical_architecture_path, candidate)
            print(
                "SIRAJ_LUNA_STORY_ARCHITECTURE_ICONIC_REVIEW_V5_1_"
                "ALREADY_COMPLETE"
            )
            print(f"OUTPUT={reviewed_output_path}")
            print("NEXT_STAGE=FINAL_SCRIPT")
            return

    total_input_tokens = 0
    total_output_tokens = 0
    cumulative_base_cost = 0.0
    for receipt_path in receipts.glob("*.json"):
        receipt = _read_json(receipt_path)
        total_input_tokens += int(
            receipt.get("input_tokens", 0) or 0
        )
        total_output_tokens += int(
            receipt.get("output_tokens", 0) or 0
        )
        cumulative_base_cost += float(
            receipt.get("base_text_cost_usd", 0) or 0
        )

    while True:
        request_payload = _request(
            source_package,
            claim_matrix,
            candidate,
            review_iteration,
        )
        request_uuid = str(uuid.uuid4())

        lock_path = locks / f"{request_uuid}.json"
        _exclusive_write(
            lock_path,
            {
                "schema_version": (
                    "siraj-luna-iconic-architecture-review-lock-v5.1"
                ),
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "substage": SUBSTAGE,
                "review_iteration": review_iteration,
                "request_uuid": request_uuid,
                "authorization_id": auth.get("authorization_id"),
                "reasoning_effort": "max",
                "reasoning_mode": "pro",
                "iconic_cinematic_brain_required": True,
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
                "created_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "PREPARED",
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "substage": SUBSTAGE,
                "review_iteration": review_iteration,
                "request_uuid": request_uuid,
                "timestamp_utc": _now(),
            },
        )

        _atomic_write(
            state_path,
            {
                "schema_version": (
                    "siraj-story-architecture-iconic-review-state-v5.1"
                ),
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "substage": SUBSTAGE,
                "status": "SUBMITTING",
                "review_iteration": review_iteration,
                "request_uuid": request_uuid,
                "reasoning_effort": "max",
                "reasoning_mode": "pro",
                "automatic_retry": False,
                "updated_at_utc": _now(),
            },
        )

        try:
            response = post_luna_once(
                repo,
                request_payload,
                client_request_id=request_uuid,
            )
        except Exception as exc:
            _append_jsonl(
                ledger,
                {
                    "event": "FAILED_NO_AUTO_RETRY",
                    "review_iteration": review_iteration,
                    "request_uuid": request_uuid,
                    "error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "FAILED_NO_AUTO_RETRY"
            state["error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise

        raw_path = raw_responses / f"{request_uuid}.json"
        _exclusive_write(raw_path, response)

        response_status = str(response.get("status") or "")
        if response_status and response_status != "completed":
            input_tokens, output_tokens, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_UNUSABLE_NO_AUTO_RETRY",
                    "review_iteration": review_iteration,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "response_status": response_status,
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "output_tokens": output_tokens,
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "UNUSABLE_RESPONSE_NO_AUTO_RETRY"
            state["response_status"] = response_status
            state["raw_response_path"] = str(raw_path)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise IconicArchitectureReviewError(
                f"LUNA_RESPONSE_NOT_COMPLETED:{response_status}"
            )

        text = _extract_output_text(response)
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            input_tokens, output_tokens, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_INVALID_JSON_NO_AUTO_RETRY",
                    "review_iteration": review_iteration,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "output_tokens": output_tokens,
                    "json_error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "INVALID_JSON_NO_AUTO_RETRY"
            state["raw_response_path"] = str(raw_path)
            state["json_error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise IconicArchitectureReviewError(
                "ICONIC_REVIEW_JSON_INVALID"
            ) from exc

        if not isinstance(result, dict):
            raise IconicArchitectureReviewError(
                "ICONIC_REVIEW_RESULT_OBJECT_REQUIRED"
            )

        try:
            _safe_validate(result, claim_matrix)
        except Exception as exc:
            input_tokens, output_tokens, cached = _usage(response)
            _append_jsonl(
                ledger,
                {
                    "event": "CONSUMED_SCHEMA_INVALID_NO_AUTO_RETRY",
                    "review_iteration": review_iteration,
                    "request_uuid": request_uuid,
                    "response_id": response.get("id"),
                    "input_tokens": input_tokens,
                    "cached_input_tokens": cached,
                    "output_tokens": output_tokens,
                    "validation_error": str(exc),
                    "timestamp_utc": _now(),
                },
            )
            state = _read_json(state_path)
            state["status"] = "SCHEMA_INVALID_NO_AUTO_RETRY"
            state["raw_response_path"] = str(raw_path)
            state["validation_error"] = str(exc)
            state["updated_at_utc"] = _now()
            _atomic_write(state_path, state)
            raise

        input_tokens, output_tokens, cached = _usage(response)
        base_cost = _base_text_cost_usd(
            input_tokens,
            output_tokens,
        )
        total_input_tokens += input_tokens
        total_output_tokens += output_tokens
        cumulative_base_cost += base_cost

        reviewed_round = dict(result)
        reviewed_round["_siraj_review_iteration"] = review_iteration
        reviewed_round["_siraj_iconic_review"] = {
            "substage": SUBSTAGE,
            "runtime": "V5.1_MAX_PRO_ICONIC_CINEMATIC",
            "reasoning_effort": "max",
            "reasoning_mode": "pro",
            "iconic_cinematic_brain": True,
            "request_uuid": request_uuid,
            "response_id": response.get("id"),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached,
            "output_tokens": output_tokens,
            "base_text_cost_usd": base_cost,
            "automatic_retry": False,
            "reviewed_at_utc": _now(),
        }

        round_path = (
            rounds
            / f"review-iteration-{review_iteration:03d}.json"
        )
        _exclusive_write(round_path, reviewed_round)

        _exclusive_write(
            receipts / f"{request_uuid}.json",
            {
                "schema_version": (
                    "siraj-luna-iconic-architecture-review-receipt-v5.1"
                ),
                "episode_id": EPISODE_ID,
                "stage": STAGE,
                "substage": SUBSTAGE,
                "review_iteration": review_iteration,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": input_tokens,
                "cached_input_tokens": cached,
                "output_tokens": output_tokens,
                "base_text_cost_usd": base_cost,
                "result_status": result.get("status"),
                "automatic_retry": False,
                "completed_at_utc": _now(),
            },
        )
        _append_jsonl(
            ledger,
            {
                "event": "COMPLETE",
                "review_iteration": review_iteration,
                "request_uuid": request_uuid,
                "response_id": response.get("id"),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "base_text_cost_usd": base_cost,
                "result_status": result.get("status"),
                "timestamp_utc": _now(),
            },
        )

        state = _read_json(state_path)
        state["status"] = result.get("status")
        state["response_id"] = response.get("id")
        state["round_path"] = str(round_path)
        state["updated_at_utc"] = _now()
        _atomic_write(state_path, state)

        status = result.get("status")
        if status == "PASS":
            final = dict(reviewed_round)
            final["_siraj_iconic_review_summary"] = {
                "status": "PASS",
                "review_iterations_completed": review_iteration,
                "total_input_tokens": total_input_tokens,
                "total_output_tokens": total_output_tokens,
                "cumulative_base_text_cost_usd": round(
                    cumulative_base_cost,
                    8,
                ),
                "pre_iconic_architecture_archive": str(
                    pre_iconic_archive_path
                ),
                "assistant_authored_call_limit": None,
                "assistant_authored_cost_cap_usd": None,
                "assistant_authored_max_output_tokens": None,
                "assistant_authored_fixed_pacing_seconds": None,
                "automatic_retry": False,
            }

            _atomic_write(reviewed_output_path, final)
            # Promote only after PASS; the pre-iconic version remains archived.
            _atomic_write(canonical_architecture_path, final)

            marker = _read_json(marker_path)
            marker[
                "story_architecture_creative_review_status"
            ] = "PASS"
            marker[
                "story_architecture_iconic_review_output"
            ] = str(reviewed_output_path)
            marker["next_stage"] = "FINAL_SCRIPT"
            marker["updated_at_utc"] = _now()
            _atomic_write(marker_path, marker)

            auth["status"] = "COMPLETED"
            auth["completed_review_iterations"] = review_iteration
            auth["completed_at_utc"] = _now()
            _atomic_write(auth_path, auth)

            print(
                "SIRAJ_LUNA_STORY_ARCHITECTURE_ICONIC_REVIEW_V5_1_COMPLETE"
            )
            print("STATUS=PASS")
            print(
                "REVIEW_ITERATIONS_COMPLETED="
                + str(review_iteration)
            )
            print("LUNA_REASONING_EFFORT=MAX")
            print("LUNA_REASONING_MODE=PRO")
            print("ICONIC_CINEMATIC_CREATIVE_BRAIN=ACTIVE")
            print(
                "ACTS="
                + str(len(result.get("acts", [])))
            )
            print(
                "BEATS="
                + str(len(result.get("beats", [])))
            )
            print(
                "TOTAL_INPUT_TOKENS="
                + str(total_input_tokens)
            )
            print(
                "TOTAL_OUTPUT_TOKENS="
                + str(total_output_tokens)
            )
            print(
                "CUMULATIVE_BASE_TEXT_COST_USD="
                + f"{cumulative_base_cost:.8f}"
            )
            print("ASSISTANT_AUTHORED_CALL_LIMIT=NONE")
            print("ASSISTANT_AUTHORED_COST_CAP_USD=NONE")
            print("ASSISTANT_AUTHORED_MAX_OUTPUT_TOKENS=NONE")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print(
                "PRE_ICONIC_ARCHITECTURE_ARCHIVE="
                + str(pre_iconic_archive_path)
            )
            print("OUTPUT=" + str(reviewed_output_path))
            print("CANONICAL_ARCHITECTURE=PROMOTED_AFTER_PASS")
            print("NEXT_STAGE=FINAL_SCRIPT")
            return

        if status == "NEEDS_CLAIM_MATRIX_REOPEN":
            marker = _read_json(marker_path)
            marker[
                "story_architecture_creative_review_status"
            ] = "NEEDS_CLAIM_MATRIX_REOPEN"
            marker["next_stage"] = "SOURCE_CLAIM_MATRIX_REOPEN"
            marker["updated_at_utc"] = _now()
            _atomic_write(marker_path, marker)

            print(
                "SIRAJ_LUNA_STORY_ARCHITECTURE_ICONIC_REVIEW_V5_1_STOPPED"
            )
            print("STATUS=NEEDS_CLAIM_MATRIX_REOPEN")
            print("AUTOMATIC_PROVIDER_RETRIES=0")
            print("NEXT_STAGE=SOURCE_CLAIM_MATRIX_REOPEN")
            return

        if status != "CONTINUE_ARCHITECTURE":
            raise IconicArchitectureReviewError(
                f"UNEXPECTED_REVIEW_STATUS:{status}"
            )

        candidate = reviewed_round
        review_iteration += 1
        print(
            "LUNA_ICONIC_ARCHITECTURE_REVIEW_CONTINUE:"
            f"NEXT_ITERATION={review_iteration}"
        )


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        fn = getattr(stream, "reconfigure", None)
        if callable(fn):
            fn(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-authorized", action="store_true")
    args = parser.parse_args()

    if not args.run_authorized:
        raise SystemExit(
            "EXPLICIT_FLAG_REQUIRED:--run-authorized"
        )
    run(Path(args.repo))


if __name__ == "__main__":
    main()
