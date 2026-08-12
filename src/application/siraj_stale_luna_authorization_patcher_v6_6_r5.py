from __future__ import annotations

from pathlib import Path

from src.application.artifact_provenance_v1 import record_invalidation

MARKER = "SIRAJ_STALE_LUNA_AUTH_AUTOREFRESH_V6_6_R5"


class StaleLunaAuthorizationPatcherV66R5Error(RuntimeError):
    pass


def patch_wrapper(path: Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if MARKER in text:
        return "ALREADY_PATCHED"

    import_anchor = (
        "from src.application.siraj_episode_master_authorization_v6_6 import (\n"
    )
    pos = text.find(import_anchor)
    if pos < 0:
        raise StaleLunaAuthorizationPatcherV66R5Error(
            "V66_MASTER_IMPORT_ANCHOR_NOT_FOUND"
        )

    import_block = (
        "# SIRAJ_STALE_LUNA_AUTH_AUTOREFRESH_V6_6_R5\n"
        "from src.application.siraj_luna_upstream_transport_v6_3 import (\n"
        "    authorization_path as luna_authorization_path,\n"
        ")\n"
    )
    text = text[:pos] + import_block + text[pos:]

    exec_anchor = "def execute_current_stage(\n"
    exec_pos = text.find(exec_anchor)
    if exec_pos < 0:
        raise StaleLunaAuthorizationPatcherV66R5Error(
            "V66_EXECUTE_CURRENT_STAGE_NOT_FOUND"
        )

    helper = r'''
def _is_pre_network_luna_authorization_invalid(
    exc: Exception,
    stage: str,
) -> bool:
    return (
        "LUNA_STAGE_AUTHORIZATION_INVALID:" + stage
    ) in str(exc)


def _archive_stale_luna_authorization(
    repo: Path,
    episode_id: str,
    stage: str,
) -> str:
    target_id = (
        v64.BOOTSTRAP_ID
        if stage == "TOPIC_SELECTION"
        else episode_id
    )
    path = luna_authorization_path(
        repo,
        target_id,
        stage,
    )
    if not path.is_file():
        return "NOT_PRESENT"

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    root = (
        repo
        / "projects"
        / (
            "_series"
            if episode_id == NEXT_EPISODE_ID
            else episode_id
        )
        / "orchestration/"
        "derived-luna-authorization-refresh-v6-6-r5"
    )
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination = (
        root
        / (
            stage.lower()
            + "-"
            + digest[:16]
            + ".stale-authorization.json"
        )
    )
    if not destination.is_file():
        destination.write_bytes(payload)
    record_invalidation(
        repo,
        episode_id,
        path,
        reason="STALE_DERIVED_LUNA_AUTHORIZATION",
        classification="SUPERSEDED",
    )
    return "ARCHIVED_AND_PRESERVED"


def _execute_paid_stage_with_master_auth_refresh(
    repo: Path,
    base: AutopilotInspection,
) -> str:
    try:
        return v64.execute_current_stage(repo)
    except Exception as exc:
        if (
            base.stage not in LUNA_STAGES
            or not _is_pre_network_luna_authorization_invalid(
                exc,
                base.stage,
            )
        ):
            raise

        if not master_authorization_active(
            repo,
            base.episode_id,
        ):
            raise

        _archive_stale_luna_authorization(
            repo,
            base.episode_id,
            base.stage,
        )

        fresh = v64.inspect_autopilot(repo)
        if fresh.stage != base.stage:
            raise AutopilotV66Error(
                "LUNA_AUTH_REFRESH_STAGE_CHANGED:"
                + base.stage
                + "->"
                + fresh.stage
            ) from exc

        _ensure_legacy_stage_authorized(
            repo,
            fresh,
        )

        return v64.execute_current_stage(repo)


'''
    text = text[:exec_pos] + helper + text[exec_pos:]

    paid_try = (
        "        try:\n"
        "            result = v64.execute_current_stage(\n"
        "                repo\n"
        "            )\n"
        "        except Exception as exc:\n"
    )
    replacement = (
        "        try:\n"
        "            result = _execute_paid_stage_with_master_auth_refresh(\n"
        "                repo,\n"
        "                base,\n"
        "            )\n"
        "        except Exception as exc:\n"
    )

    anchor_pos = text.find(paid_try, text.find(exec_anchor))
    if anchor_pos < 0:
        raise StaleLunaAuthorizationPatcherV66R5Error(
            "V66_PAID_EXECUTION_TRY_ANCHOR_NOT_FOUND"
        )

    text = (
        text[:anchor_pos]
        + replacement
        + text[anchor_pos + len(paid_try):]
    )

    path.write_text(text, encoding="utf-8")
    return "PATCHED"
