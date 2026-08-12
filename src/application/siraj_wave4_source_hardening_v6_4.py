from __future__ import annotations

from pathlib import Path
import re


class Wave4PatchError(RuntimeError):
    pass


UPSTREAM_STAGES = (
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
)

DOWNSTREAM_LUNA_STAGES = (
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
)


def _set_literal(name: str, stages: tuple[str, ...]) -> str:
    lines = [f"{name} = {{"]
    lines.extend(f'    "{stage}",' for stage in stages)
    lines.append("}")
    return "\n".join(lines)


def _extract_set_members(text: str, name: str) -> set[str] | None:
    match = re.search(
        rf"{re.escape(name)}\s*=\s*\{{(.*?)\}}",
        text,
        re.DOTALL,
    )
    if not match:
        return None
    return set(
        re.findall(r'"([^"]+)"', match.group(1))
    )


def _already_normalized(text: str) -> bool:
    upstream = _extract_set_members(
        text,
        "PAID_UPSTREAM_STAGES",
    )
    downstream = _extract_set_members(
        text,
        "PAID_LUNA_DOWNSTREAM_STAGES",
    )
    return (
        upstream == set(UPSTREAM_STAGES)
        and downstream == set(DOWNSTREAM_LUNA_STAGES)
        and "PAID_LUNA_STAGES = (" in text
        and (
            "PAID_UPSTREAM_STAGES | PAID_LUNA_DOWNSTREAM_STAGES"
            in text
        )
        and text.count(
            "if stage not in PAID_LUNA_STAGES:"
        ) >= 2
        and (
            "if stage not in PAID_UPSTREAM_STAGES:"
            not in text
        )
    )


def _replace_required_set(
    text: str,
    name: str,
    stages: tuple[str, ...],
) -> str:
    pattern = re.compile(
        rf"{re.escape(name)}\s*=\s*\{{.*?\}}",
        re.DOTALL,
    )
    if not pattern.search(text):
        raise Wave4PatchError(
            name + "_BLOCK_NOT_FOUND"
        )
    return pattern.sub(
        _set_literal(name, stages),
        text,
        count=1,
    )


def _replace_or_insert_downstream(
    text: str,
) -> str:
    canonical = _set_literal(
        "PAID_LUNA_DOWNSTREAM_STAGES",
        DOWNSTREAM_LUNA_STAGES,
    )
    pattern = re.compile(
        r"PAID_LUNA_DOWNSTREAM_STAGES\s*=\s*\{.*?\}",
        re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(
            canonical,
            text,
            count=1,
        )

    upstream_pattern = re.compile(
        r"PAID_UPSTREAM_STAGES\s*=\s*\{.*?\}",
        re.DOTALL,
    )
    match = upstream_pattern.search(text)
    if not match:
        raise Wave4PatchError(
            "PAID_UPSTREAM_STAGES_BLOCK_NOT_FOUND"
        )
    return (
        text[: match.end()]
        + "\n\n"
        + canonical
        + text[match.end() :]
    )


def _replace_or_insert_union(
    text: str,
) -> str:
    canonical = (
        "PAID_LUNA_STAGES = (\n"
        "    PAID_UPSTREAM_STAGES | PAID_LUNA_DOWNSTREAM_STAGES\n"
        ")"
    )
    pattern = re.compile(
        r"PAID_LUNA_STAGES\s*=\s*\(.*?\)",
        re.DOTALL,
    )
    if pattern.search(text):
        return pattern.sub(
            canonical,
            text,
            count=1,
        )

    downstream_pattern = re.compile(
        r"PAID_LUNA_DOWNSTREAM_STAGES\s*=\s*\{.*?\}",
        re.DOTALL,
    )
    match = downstream_pattern.search(text)
    if not match:
        raise Wave4PatchError(
            "PAID_LUNA_DOWNSTREAM_STAGES_BLOCK_NOT_FOUND"
        )
    return (
        text[: match.end()]
        + "\n\n"
        + canonical
        + text[match.end() :]
    )


def expand_luna_paid_stage_set(path: Path) -> str:
    """
    Idempotently preserve the Wave-3 public seven-stage contract while
    maintaining a broader Wave-4 Luna transport allow-list.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    was_normalized = _already_normalized(text)

    text = _replace_required_set(
        text,
        "PAID_UPSTREAM_STAGES",
        UPSTREAM_STAGES,
    )
    text = _replace_or_insert_downstream(text)
    text = _replace_or_insert_union(text)

    text = text.replace(
        "if stage not in PAID_UPSTREAM_STAGES:",
        "if stage not in PAID_LUNA_STAGES:",
    )

    if text.count(
        "if stage not in PAID_LUNA_STAGES:"
    ) < 2:
        raise Wave4PatchError(
            "PAID_LUNA_STAGE_GUARDS_INCOMPLETE"
        )

    path.write_text(
        text,
        encoding="utf-8",
    )

    if not _already_normalized(text):
        raise Wave4PatchError(
            "PAID_LUNA_STAGE_CONTRACT_NORMALIZATION_FAILED"
        )

    return (
        "ALREADY_SEPARATED_CONTRACT_NORMALIZED"
        if was_normalized
        else "SEPARATED_CONTRACT_INSTALLED"
    )


def patch_runware_credential_fallback(path: Path) -> str:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    if "read_runware_api_key" in text:
        return "ALREADY_PATCHED"

    pattern = re.compile(
        r"def _runware_key\(\):\n"
        r"(?:(?:    ).*\n)+?"
        r"    return value\n",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if not match:
        raise Wave4PatchError(
            "RUNWARE_KEY_FUNCTION_ANCHOR_NOT_FOUND"
        )

    replacement = (
        "def _runware_key():\n"
        "    value = (\n"
        "        os.environ.get(\"RUNWARE_API_KEY\", \"\").strip()\n"
        "        or os.environ.get(\"SIRAJ_RUNWARE_API_KEY\", \"\").strip()\n"
        "    )\n"
        "    if value:\n"
        "        return value\n"
        "\n"
        "    try:\n"
        "        from src.application.windows_credentials_v1 import (\n"
        "            read_runware_api_key,\n"
        "        )\n"
        "        value = str(read_runware_api_key() or \"\").strip()\n"
        "    except Exception as exc:\n"
        "        raise ProviderExecutionV621Error(\n"
        "            \"RUNWARE_CREDENTIAL_MANAGER_READ_FAILED:\" + str(exc)\n"
        "        ) from exc\n"
        "\n"
        "    if not value:\n"
        "        raise ProviderExecutionV621Error(\n"
        "            \"RUNWARE_API_KEY_REQUIRED:\"\n"
        "            \"STORE_SECURELY_IN_SIRAJ_RUNWARE_API_KEY_CREDENTIAL\"\n"
        "        )\n"
        "    return value\n"
    )
    text = (
        text[: match.start()]
        + replacement
        + text[match.end() :]
    )
    path.write_text(
        text,
        encoding="utf-8",
    )
    return "PATCHED"
