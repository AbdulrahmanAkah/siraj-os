"""Explicit safety gate for paid external TTS execution."""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping


PAID_TTS_CONFIRMATION_VARIABLE = (
    "SIRAJ_ALLOW_PAID_TTS"
)

PAID_TTS_CONFIRMATION_VALUE = "YES"


class PaidTTSGuardError(RuntimeError):
    """Paid synthesis was not explicitly authorized."""


@dataclass(frozen=True)
class PaidTTSGuardStatus:
    api_key_present: bool
    paid_tts_authorized: bool
    ready: bool


def inspect_paid_tts_guard(
    environment: Mapping[str, str] | None = None,
) -> PaidTTSGuardStatus:
    values = (
        environment
        if environment is not None
        else os.environ
    )

    api_key_present = bool(
        values.get(
            "OPENAI_API_KEY",
            "",
        ).strip()
    )

    paid_tts_authorized = (
        values.get(
            PAID_TTS_CONFIRMATION_VARIABLE,
            "",
        ).strip()
        == PAID_TTS_CONFIRMATION_VALUE
    )

    return PaidTTSGuardStatus(
        api_key_present=api_key_present,
        paid_tts_authorized=(
            paid_tts_authorized
        ),
        ready=(
            api_key_present
            and paid_tts_authorized
        ),
    )


def require_paid_tts_authorization(
    environment: Mapping[str, str] | None = None,
) -> PaidTTSGuardStatus:
    status = inspect_paid_tts_guard(
        environment
    )

    if not status.api_key_present:
        raise PaidTTSGuardError(
            "OPENAI_API_KEY_MISSING"
        )

    if not status.paid_tts_authorized:
        raise PaidTTSGuardError(
            "PAID_TTS_NOT_AUTHORIZED:"
            "SET_SIRAJ_ALLOW_PAID_TTS_TO_YES"
        )

    return status