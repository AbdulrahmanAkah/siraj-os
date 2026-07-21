"""Explicit authorization gate for external TTS providers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


EXTERNAL_TTS_CONFIRMATION_VARIABLE = (
    "SIRAJ_ALLOW_EXTERNAL_TTS"
)

EXTERNAL_TTS_CONFIRMATION_VALUE = "YES"


class ExternalTTSGuardError(RuntimeError):
    """External TTS execution was not explicitly authorized."""


@dataclass(frozen=True)
class ExternalTTSGuardStatus:
    provider_api_key_present: bool
    external_tts_authorized: bool
    ready: bool


def inspect_external_tts_guard(
    api_key_variable: str,
    environment: Mapping[str, str] | None = None,
) -> ExternalTTSGuardStatus:
    if not str(api_key_variable).strip():
        raise ValueError(
            "EXTERNAL_TTS_API_KEY_VARIABLE_REQUIRED"
        )

    values = (
        environment
        if environment is not None
        else os.environ
    )

    key_present = bool(
        values.get(
            api_key_variable,
            "",
        ).strip()
    )

    authorized = (
        values.get(
            EXTERNAL_TTS_CONFIRMATION_VARIABLE,
            "",
        ).strip()
        == EXTERNAL_TTS_CONFIRMATION_VALUE
    )

    return ExternalTTSGuardStatus(
        provider_api_key_present=(
            key_present
        ),
        external_tts_authorized=(
            authorized
        ),
        ready=(
            key_present
            and authorized
        ),
    )


def require_external_tts_authorization(
    api_key_variable: str,
    environment: Mapping[str, str] | None = None,
) -> ExternalTTSGuardStatus:
    status = inspect_external_tts_guard(
        api_key_variable,
        environment,
    )

    if not status.provider_api_key_present:
        raise ExternalTTSGuardError(
            f"{api_key_variable}_MISSING"
        )

    if not status.external_tts_authorized:
        raise ExternalTTSGuardError(
            "EXTERNAL_TTS_NOT_AUTHORIZED:"
            "SET_SIRAJ_ALLOW_EXTERNAL_TTS_TO_YES"
        )

    return status


def require_external_tts_execution_authorization(
    environment: Mapping[str, str] | None = None,
) -> None:
    """Require explicit approval without assuming an API-key credential flow.

    Google Cloud uses Application Default Credentials, which can be supplied by
    an account or workload identity rather than an environment API key.
    """
    values = environment if environment is not None else os.environ
    if values.get(EXTERNAL_TTS_CONFIRMATION_VARIABLE, "").strip() != EXTERNAL_TTS_CONFIRMATION_VALUE:
        raise ExternalTTSGuardError(
            "EXTERNAL_TTS_NOT_AUTHORIZED:SET_SIRAJ_ALLOW_EXTERNAL_TTS_TO_YES"
        )
