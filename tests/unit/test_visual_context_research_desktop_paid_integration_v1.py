from __future__ import annotations

import json
from pathlib import Path

from src.application.siraj_luna_upstream_transport_v6_3 import PAID_LUNA_STAGES
import src.application.visual_context_research_desktop_paid_integration_v1 as mod


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _seed(tmp_path: Path) -> None:
    _write(
        tmp_path / "projects/_series/visual-context-research-policy-v1.json",
        {
            "schema_version": "siraj-visual-context-research-policy-v1",
            "scope": "SERIES_WIDE",
            "constitution_precedence": True,
            "source_classes": [
                {"id": "PRIMARY", "required_to_check": True},
            ],
            "face_policy": {
                "visible_face": "FORBIDDEN_WITHOUT_EXCEPTION",
                "head_required": False,
            },
        },
    )
    _write(
        tmp_path
        / "reports/pr01-production-readiness/"
        "EP002_R27_CANONICAL_REFERENCE_ASSET_INTAKE_V1.json",
        {
            "required_assets": [
                {
                    "reference_id": "ADAM_GARDEN",
                    "narration_text": "Adam is in the Garden.",
                    "brief": {
                        "purpose": "canonical recurring-character identity",
                    },
                }
            ]
        },
    )
    (
        tmp_path
        / "projects"
        / mod.EPISODE_ID
        / "research"
    ).mkdir(parents=True, exist_ok=True)


def test_stage_registered():
    assert mod.VISUAL_CONTEXT_RESEARCH_STAGE in PAID_LUNA_STAGES


def test_prepare_requires_desktop_only_when_paid(monkeypatch, tmp_path: Path):
    _seed(tmp_path)
    calls = {"desktop": 0, "auth": 0}

    def fake_desktop():
        calls["desktop"] += 1

    def fake_auth(repo, episode, stage, payload, phrase):
        calls["auth"] += 1
        assert stage == mod.VISUAL_CONTEXT_RESEARCH_STAGE
        assert payload["context_id"] == "ADAM_GARDEN"
        return tmp_path / "auth.json"

    monkeypatch.setattr(mod, "_assert_explicit_desktop_context", fake_desktop)
    monkeypatch.setattr(mod, "authorize_stage", fake_auth)

    plan = mod.prepare_visual_context_research_from_desktop(
        tmp_path,
        reference_id="ADAM_GARDEN",
    )
    assert plan.paid_call_required is True
    assert calls == {"desktop": 1, "auth": 1}


def test_execute_binds_exact_prepared_request(monkeypatch, tmp_path: Path):
    _seed(tmp_path)

    monkeypatch.setattr(mod, "_assert_explicit_desktop_context", lambda: None)
    monkeypatch.setattr(
        mod,
        "authorize_stage",
        lambda *args, **kwargs: tmp_path / "auth.json",
    )

    plan = mod.prepare_visual_context_research_from_desktop(
        tmp_path,
        reference_id="ADAM_GARDEN",
    )

    seen = {"n": 0}

    def fake_luna(repo, episode, *, input_payload):
        seen["n"] += 1
        assert input_payload["context_id"] == "ADAM_GARDEN"
        raise RuntimeError("stop-after-binding-proof")

    monkeypatch.setattr(
        mod,
        "execute_authorized_visual_context_research_stage",
        fake_luna,
    )

    try:
        mod.execute_prepared_visual_context_research(
            tmp_path,
            plan=plan,
        )
    except RuntimeError as exc:
        assert "stop-after-binding-proof" in str(exc)
    else:
        raise AssertionError("expected proof stop")

    assert seen["n"] == 1


def test_dock_source_contains_research_button():
    source = Path(
        "src/presentation/desktop/canonical_reference_generation_dock_v1.py"
    ).read_text(encoding="utf-8-sig")
    assert "Research selected" in source
    assert "research_selected" in source
