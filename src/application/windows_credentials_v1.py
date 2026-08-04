from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

TARGET_NAME = "SIRAJ/RUNWARE_API_KEY"
USERNAME = "SIRAJ"
CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class CredentialStoreError(RuntimeError):
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
        raise CredentialStoreError("WINDOWS_CREDENTIAL_MANAGER_REQUIRED")
    library = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    library.CredWriteW.argtypes = [
        ctypes.POINTER(CREDENTIALW),
        wintypes.DWORD,
    ]
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


def save_runware_api_key(api_key: str) -> None:
    value = api_key.strip()
    if not value:
        raise CredentialStoreError("RUNWARE_API_KEY_REQUIRED")
    if os.name != "nt":
        raise CredentialStoreError("WINDOWS_CREDENTIAL_MANAGER_REQUIRED")

    encoded = value.encode("utf-16-le")
    blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    credential = CREDENTIALW()
    credential.Flags = 0
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = TARGET_NAME
    credential.Comment = "Runware API key for SIRAJ desktop production"
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
        error = ctypes.get_last_error()
        raise CredentialStoreError(f"CRED_WRITE_FAILED:{error}")


def read_runware_api_key() -> str | None:
    environment = os.environ.get("RUNWARE_API_KEY", "").strip()
    if environment:
        return environment
    if os.name != "nt":
        return None

    library = _advapi32()
    pointer = PCREDENTIALW()
    if not library.CredReadW(
        TARGET_NAME,
        CRED_TYPE_GENERIC,
        0,
        ctypes.byref(pointer),
    ):
        error = ctypes.get_last_error()
        if error == ERROR_NOT_FOUND:
            return None
        raise CredentialStoreError(f"CRED_READ_FAILED:{error}")
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


def delete_runware_api_key() -> None:
    if os.name != "nt":
        return
    library = _advapi32()
    if not library.CredDeleteW(
        TARGET_NAME,
        CRED_TYPE_GENERIC,
        0,
    ):
        error = ctypes.get_last_error()
        if error != ERROR_NOT_FOUND:
            raise CredentialStoreError(f"CRED_DELETE_FAILED:{error}")
