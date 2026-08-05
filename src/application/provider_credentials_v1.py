from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from src.application.elevenlabs_key_validation_recovery_v1 import (
    ElevenLabsKeyValidationError,
    normalize_and_validate_elevenlabs_api_key,
)

OPENAI_TARGET = "SIRAJ/OPENAI_API_KEY"
ELEVENLABS_TARGET = "SIRAJ/ELEVENLABS_API_KEY"
USERNAME = "SIRAJ"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class ProviderCredentialError(RuntimeError):
    pass


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


def _advapi32():
    if os.name != "nt":
        raise ProviderCredentialError("WINDOWS_CREDENTIAL_MANAGER_REQUIRED")
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    library.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIALW), wintypes.DWORD]
    library.CredWriteW.restype = wintypes.BOOL
    library.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(PCREDENTIALW),
    ]
    library.CredReadW.restype = wintypes.BOOL
    library.CredDeleteW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    library.CredDeleteW.restype = wintypes.BOOL
    library.CredFree.argtypes = [ctypes.c_void_p]
    library.CredFree.restype = None
    return library


def _save(target: str, value: str, comment: str) -> None:
    secret = value.strip()
    if not secret:
        raise ProviderCredentialError("API_KEY_REQUIRED")
    if os.name != "nt":
        raise ProviderCredentialError("WINDOWS_CREDENTIAL_MANAGER_REQUIRED")
    encoded = secret.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = CREDENTIALW()
    credential.Flags = 0
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.Comment = comment
    credential.CredentialBlobSize = len(encoded)
    credential.CredentialBlob = ctypes.cast(
        blob,
        ctypes.POINTER(ctypes.c_ubyte),
    )
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.AttributeCount = 0
    credential.Attributes = None
    credential.TargetAlias = None
    credential.UserName = USERNAME
    library = _advapi32()
    if not library.CredWriteW(ctypes.byref(credential), 0):
        raise ProviderCredentialError(
            f"CRED_WRITE_FAILED:{ctypes.get_last_error()}"
        )


def _read(target: str, environment_name: str | None) -> str | None:
    environment = (
        os.environ.get(environment_name, "").strip()
        if environment_name
        else ""
    )
    if environment:
        return environment
    if os.name != "nt":
        return None
    library = _advapi32()
    pointer = PCREDENTIALW()
    if not library.CredReadW(
        target,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(pointer),
    ):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise ProviderCredentialError(f"CRED_READ_FAILED:{error}")
    try:
        credential = pointer.contents
        if not credential.CredentialBlob or not credential.CredentialBlobSize:
            return None
        raw = ctypes.string_at(
            credential.CredentialBlob,
            credential.CredentialBlobSize,
        )
        return raw.decode("utf-16-le").strip() or None
    finally:
        library.CredFree(pointer)


def _delete(target: str) -> None:
    if os.name != "nt":
        return
    library = _advapi32()
    if not library.CredDeleteW(target, CRED_TYPE_GENERIC, 0):
        error = ctypes.get_last_error()
        if error != ERROR_NOT_FOUND:
            raise ProviderCredentialError(f"CRED_DELETE_FAILED:{error}")


def save_openai_api_key(api_key: str) -> None:
    _save(
        OPENAI_TARGET,
        api_key,
        "OpenAI API key for SIRAJ autonomous episode orchestration",
    )


def read_openai_api_key() -> str | None:
    return _read(OPENAI_TARGET, "OPENAI_API_KEY")


def delete_openai_api_key() -> None:
    _delete(OPENAI_TARGET)


def save_elevenlabs_api_key(api_key: str) -> None:
    try:
        secret = normalize_and_validate_elevenlabs_api_key(
            api_key,
            source="WINDOWS_CREDENTIAL_SAVE",
        )
    except ElevenLabsKeyValidationError as exc:
        raise ProviderCredentialError(str(exc)) from exc
    _save(
        ELEVENLABS_TARGET,
        secret,
        "ElevenLabs API key for SIRAJ narration production",
    )


def read_elevenlabs_api_key() -> str | None:
    environment = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if environment:
        try:
            return normalize_and_validate_elevenlabs_api_key(
                environment,
                source="ELEVENLABS_API_KEY_ENVIRONMENT",
            )
        except ElevenLabsKeyValidationError as exc:
            raise ProviderCredentialError(str(exc)) from exc
    value = _read(ELEVENLABS_TARGET, None)
    if value is None:
        return None
    try:
        return normalize_and_validate_elevenlabs_api_key(
            value,
            source="WINDOWS_CREDENTIAL_MANAGER",
        )
    except ElevenLabsKeyValidationError as exc:
        raise ProviderCredentialError(str(exc)) from exc


def delete_elevenlabs_api_key() -> None:
    _delete(ELEVENLABS_TARGET)
