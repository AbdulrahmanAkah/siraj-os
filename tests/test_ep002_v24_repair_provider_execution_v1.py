from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil

import pytest

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file
from src.application.ep002_v24_repair_provider_execution_v1 import (
    APPROVAL_REL,
    DESKTOP_SOURCE,
    DOSSIERS_REL,
    EPISODE_ID,
    EXPECTED_COST_USD,
    EXPECTED_PLAN_SHA256,
    EXPECTED_PROVIDER_SECONDS,
    EXPECTED_STORYBOARD_SHA256,
    EXPECTED_UNIT_COUNT,
    FEMALE_REVIEW_REL,
    MAXIMUM_COST_USD,
    PRICING_REL,
    SOURCE_BINDING_REL,
    STORYBOARD_REL,
    CERTIFICATION_REL,
    CONSTITUTION_REL,
    EP002V24DesktopRepairExecutionService,
    EP002V24RepairExecutionError,
    build_approved_provider_plan,
)
from src.application.provider_model_contracts import (
    ProviderModelContractError,
    validate_runware_task,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_path,
)


REPO = Path(__file__).resolve().parents[1]


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _copy_release_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for rel in (
        STORYBOARD_REL,
        APPROVAL_REL,
        DOSSIERS_REL,
        FEMALE_REVIEW_REL,
        SOURCE_BINDING_REL,
        CERTIFICATION_REL,
        CONSTITUTION_REL,
        PRICING_REL,
    ):
        src = REPO / rel
        dst = repo / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    auth_path = master_authorization_path(repo, EPISODE_ID)
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    auth = {
        "schema_version": "siraj-episode-master-paid-authorization-v6.6",
        "status": "ACTIVE",
        "episode_id": EPISODE_ID,
        "authorized_from_stage": "PROVIDER_EXECUTION",
        "scope": "ALL_INITIAL_PAID_OPERATIONS_THROUGH_READY_FOR_FINAL_HUMAN_REVIEW",
        "providers": ["RUNWARE"],
        "future_episode_event_review_gate": True,
        "event_discussion_with_luna": True,
        "post_event_approval_continues_automatically": True,
        "completed_stage_rerun": "FORBIDDEN",
        "paid_retry_included": False,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "assistant_authored_cost_cap_usd": None,
        "assistant_authored_call_cap": None,
        "publishing": "HUMAN_ONLY",
        "authorization_source": "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION",
        "confirmation_phrase": "أوافق على الإنتاج الكامل للحلقة",
        "authorized_at_utc": "2026-08-01T00:00:00Z",
    }
    auth["authorization_sha256"] = canonical_sha256(auth)
    auth_path.write_text(
        json.dumps(auth, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return repo


class _FakeGateway:
    requires_uuid4 = True

    def __init__(
        self,
        fail_at: int | None = None,
        actual_cost_multiplier: float = 1.0,
    ):
        self.fail_at = fail_at
        self.actual_cost_multiplier = float(actual_cost_multiplier)
        self.calls = []

    def submit(self, *, request, unit, attempt_id):
        self.calls.append(
            {
                "request": request,
                "unit": dict(unit),
                "attempt_id": attempt_id,
            }
        )
        ordinal = len(self.calls)
        if self.fail_at == ordinal:
            return {
                "status": "UNKNOWN",
                "error": "FAKE_UNKNOWN_NO_RETRY",
            }
        root = (
            Path(request.repo_root)
            / "projects"
            / request.episode_id
            / "orchestration"
            / "provider-execution-assets-v1"
        )
        root.mkdir(parents=True, exist_ok=True)
        asset = root / (str(unit["unit_id"]) + ".mp4")
        asset.write_bytes(
            (f"fake-video-{unit['unit_id']}-".encode("utf-8")) * 200
        )
        return {
            "status": "COMPLETE",
            "asset_path": str(asset.relative_to(request.repo_root)).replace("\\", "/"),
            "asset_sha256": sha256_file(asset),
            "actual_cost_usd": self.actual_cost_multiplier
            * 0.05
            * int(request.payload["duration"]),
            "provider_operation_id": request.payload["taskUUID"],
        }


def _fake_technical(asset: Path, *, requested_seconds: int):
    assert asset.is_file()
    return {
        "width": 1280,
        "height": 720,
        "duration_seconds": float(requested_seconds),
        "size_bytes": asset.stat().st_size,
        "codec_name": "fake",
        "avg_frame_rate": "24/1",
    }


def _fake_reference(repo: Path, unit_id: str, asset: Path):
    assert asset.is_file()
    path = (
        repo
        / "projects"
        / EPISODE_ID
        / "orchestration"
        / "ep002-v2-4-repair-provider-execution-v1"
        / "reference-frames-v1"
        / f"{unit_id}__last-frame.jpg"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"fake-jpeg" * 100 + b"\xff\xd9")
    return path, sha256_file(path)


def _fake_review(repo: Path, units, completed):
    assert len(completed) == EXPECTED_UNIT_COUNT
    path = repo / "fake-review.zip"
    path.write_bytes(b"PK\x03\x04" + b"review" * 100)
    return path


def _service(repo: Path, gateway):
    return EP002V24DesktopRepairExecutionService(
        repo,
        gateway=gateway,
        technical_validator=_fake_technical,
        reference_extractor=_fake_reference,
        environment_validator=lambda: None,
        review_builder=_fake_review,
    )


def test_exact_v24_storyboard_and_plan_are_bound():
    storyboard_path = REPO / STORYBOARD_REL
    assert sha256_file(storyboard_path) == EXPECTED_STORYBOARD_SHA256
    units, plan_sha = build_approved_provider_plan(_read(storyboard_path))
    assert plan_sha == EXPECTED_PLAN_SHA256
    assert len(units) == EXPECTED_UNIT_COUNT
    assert sum(x.duration_seconds for x in units) == EXPECTED_PROVIDER_SECONDS
    assert sum(x.expected_cost_usd for x in units) == pytest.approx(EXPECTED_COST_USD)
    assert EXPECTED_COST_USD <= MAXIMUM_COST_USD


def test_v24_approval_receipt_binds_exact_plan():
    approval = _read(REPO / APPROVAL_REL)
    signature = approval.pop("approval_sha256")
    assert signature == canonical_sha256(approval)
    assert approval["storyboard_sha256"] == EXPECTED_STORYBOARD_SHA256
    assert approval["provider_plan_sha256"] == EXPECTED_PLAN_SHA256
    assert approval["scope"] == "V24_INITIAL_FIRST_ATTEMPTS_ONLY"
    assert approval["automatic_paid_retry"] is False
    assert approval["automatic_paid_resubmission"] is False
    assert approval["maximum_cost_usd"] == 12.0


def test_provider_contract_accepts_v24_seeded_text_to_video():
    value = validate_runware_task(
        {
            "taskType": "videoInference",
            "taskUUID": "90e8600d-9865-49f7-8fcb-36cbfbb856ef",
            "model": "google:veo@3.1-lite",
            "positivePrompt": "Literal cinematic event coverage.",
            "width": 1280,
            "height": 720,
            "duration": 8,
            "seed": 123456,
            "numberResults": 1,
            "deliveryMethod": "async",
            "includeCost": True,
            "providerSettings": {
                "google": {
                    "generateAudio": False,
                    "personGeneration": "allow_adult",
                }
            },
        },
        require_uuid_v4=True,
    )
    assert value.payload["seed"] == 123456


def test_provider_contract_accepts_v24_first_frame_continuity():
    value = validate_runware_task(
        {
            "taskType": "videoInference",
            "taskUUID": "eb4d4586-d3a5-4f41-93be-0013642c2332",
            "model": "google:veo@3.1-lite",
            "positivePrompt": "Continue exactly from the provided first frame.",
            "resolution": "720p",
            "duration": 8,
            "seed": 42,
            "inputs": {
                "frameImages": [
                    {
                        "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                        "frame": "first",
                    }
                ]
            },
            "numberResults": 1,
            "deliveryMethod": "async",
            "includeCost": True,
            "providerSettings": {
                "google": {
                    "generateAudio": False,
                    "personGeneration": "allow_adult",
                }
            },
        },
        require_uuid_v4=True,
    )
    assert value.payload["resolution"] == "720p"
    assert "width" not in value.payload


def test_provider_contract_rejects_dimensions_with_frame_images():
    with pytest.raises(ProviderModelContractError):
        validate_runware_task(
            {
                "taskType": "videoInference",
                "taskUUID": "b8e62ac3-0300-46a3-a71d-74c9b9476b86",
                "model": "google:veo@3.1-lite",
                "positivePrompt": "Invalid mixed sizing.",
                "width": 1280,
                "height": 720,
                "resolution": "720p",
                "duration": 8,
                "inputs": {
                    "frameImages": [
                        {
                            "image": "data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                            "frame": "first",
                        }
                    ]
                },
                "numberResults": 1,
                "deliveryMethod": "async",
                "includeCost": True,
                "providerSettings": {
                    "google": {
                        "generateAudio": False,
                        "personGeneration": "allow_adult",
                    }
                },
            },
            require_uuid_v4=True,
        )


def test_service_requires_one_shot_desktop_capability(tmp_path):
    repo = _copy_release_repo(tmp_path)
    gateway = _FakeGateway()
    service = _service(repo, gateway)
    with pytest.raises(
        EP002V24RepairExecutionError,
        match="V24_DESKTOP_EXECUTION_CONTEXT_REQUIRED",
    ):
        service.execute(object(), source=DESKTOP_SOURCE)
    assert gateway.calls == []


def test_service_executes_exact_27_first_attempts_and_chains_debate_frames(tmp_path):
    repo = _copy_release_repo(tmp_path)
    gateway = _FakeGateway()
    service = _service(repo, gateway)

    preview = service.inspect()
    assert preview.execution_allowed is True
    assert preview.remaining_units == 27

    capability = service.issue_desktop_capability(source=DESKTOP_SOURCE)
    outcome = service.execute(capability, source=DESKTOP_SOURCE)

    assert outcome.status == "AWAITING_HUMAN_RENDER_CONFORMANCE_REVIEW"
    assert outcome.completed_units == 27
    assert len(gateway.calls) == 27

    debate = [
        call
        for call in gateway.calls
        if call["unit"]["unit_id"]
        in {
            "V23-GEN-013-DEBATE-A",
            "V23-GEN-014-DEBATE-B",
            "V23-GEN-SUPPORT-01920-DEBATE",
            "V23-GEN-SUPPORT-02122-DEBATE",
            "V24-GEN-015-DEBATE-C",
            "V24-GEN-016-DEBATE-D",
            "V24-GEN-017-DEBATE-E",
            "V24-GEN-018-DEBATE-F",
        }
    ]
    assert len(debate) == 8
    assert debate[0]["request"].payload["width"] == 1280
    assert "inputs" not in debate[0]["request"].payload
    for call in debate[1:]:
        payload = call["request"].payload
        assert payload["resolution"] == "720p"
        assert "width" not in payload
        assert payload["inputs"]["frameImages"][0]["frame"] == "first"
        assert payload["inputs"]["frameImages"][0]["image"].startswith(
            "data:image/jpeg;base64,"
        )

    second_service = _service(repo, _FakeGateway())
    replay_preview = second_service.inspect()
    assert replay_preview.status == "ALREADY_COMPLETED"
    assert replay_preview.remaining_units == 0
    assert replay_preview.execution_allowed is False


def test_first_unknown_stops_without_submitting_next_unit_and_blocks_rerun(tmp_path):
    repo = _copy_release_repo(tmp_path)
    gateway = _FakeGateway(fail_at=2)
    service = _service(repo, gateway)
    capability = service.issue_desktop_capability(source=DESKTOP_SOURCE)

    with pytest.raises(
        EP002V24RepairExecutionError,
        match="NO_RETRY",
    ):
        service.execute(capability, source=DESKTOP_SOURCE)

    assert len(gateway.calls) == 2

    fresh = _service(repo, _FakeGateway())
    preview = fresh.inspect()
    assert preview.execution_allowed is False
    assert preview.status == "BLOCKED_RECONCILIATION_REQUIRED"
    assert len(preview.unresolved_unit_ids) == 1


def test_all_v24_provider_prompts_are_under_provider_limit_and_non_filler():
    units, _ = build_approved_provider_plan(_read(REPO / STORYBOARD_REL))
    assert units
    for unit in units:
        prompt = unit.positive_prompt.lower()
        assert len(unit.positive_prompt) <= 3000
        assert "no filler" in prompt
        assert "no generic scenery substitution" in prompt
        assert "no symbolic replacement" in prompt
        assert "no graphics" in prompt


def test_cost_drift_stops_after_current_completed_unit_and_blocks_future(tmp_path):
    repo = _copy_release_repo(tmp_path)
    gateway = _FakeGateway(actual_cost_multiplier=1.5)
    service = _service(repo, gateway)
    capability = service.issue_desktop_capability(source=DESKTOP_SOURCE)

    with pytest.raises(
        EP002V24RepairExecutionError,
        match="V24_COST_DRIFT_REQUIRES_HUMAN_REACK",
    ):
        service.execute(capability, source=DESKTOP_SOURCE)

    assert len(gateway.calls) == 1
    fresh = _service(repo, _FakeGateway())
    preview = fresh.inspect()
    assert preview.execution_allowed is False
    assert preview.status == "BLOCKED_RECONCILIATION_REQUIRED"
    assert preview.unresolved_unit_ids == ("COST_DRIFT_HUMAN_REACK_REQUIRED",)

def test_v24_review_package_requires_all_decoded_frames():
    source = (
        REPO / "src/application/ep002_v24_repair_provider_execution_v1.py"
    ).read_text(encoding="utf-8")
    assert "ALL_DECODED_FRAMES_CONTACT_SHEET_8X8" in source
    assert "total_decoded_frames_reviewable" in source
    assert "tile=8x8" in source
