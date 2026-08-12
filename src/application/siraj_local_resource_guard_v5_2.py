"""SIRAJ V5.2 local resource guard.

Goal: keep the Windows workstation responsive while Luna computes remotely.

This does NOT reduce Luna reasoning, context, output quality, or API capability.
It only changes the priority/power behavior of the local Python client.

Policy:
- Windows process priority: BELOW_NORMAL
- Windows EcoQoS / execution-speed throttling: requested when supported
- no CPU-affinity hard cap
- no artificial sleep/pacing
- no provider/API limit changes
- common native math thread pools limited to 1 if they are ever imported
"""
from __future__ import annotations

import ctypes
import os
from typing import Any

BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1
PROCESS_POWER_THROTTLING_EXECUTION_SPEED = 0x1
PROCESS_POWER_THROTTLING = 4

_STATE: dict[str, Any] | None = None


class PROCESS_POWER_THROTTLING_STATE(ctypes.Structure):
    _fields_ = [
        ("Version", ctypes.c_ulong),
        ("ControlMask", ctypes.c_ulong),
        ("StateMask", ctypes.c_ulong),
    ]


def _limit_native_thread_pools() -> None:
    # These do not affect the remote OpenAI model. They only prevent a local
    # numerical library from unexpectedly consuming all cores if imported.
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
    ):
        os.environ.setdefault(name, "1")


def activate_local_resource_guard() -> dict[str, Any]:
    global _STATE
    if _STATE is not None:
        return dict(_STATE)

    _limit_native_thread_pools()

    state: dict[str, Any] = {
        "active": True,
        "platform": os.name,
        "priority_policy": "BELOW_NORMAL_ON_WINDOWS",
        "ecoqos_policy": "REQUEST_ON_WINDOWS_WHEN_SUPPORTED",
        "cpu_affinity_cap": None,
        "fixed_sleep_seconds": None,
        "luna_reasoning_changed": False,
        "provider_limits_changed": False,
    }

    if os.name != "nt":
        state["windows_priority_applied"] = False
        state["windows_ecoqos_applied"] = False
        state["note"] = "NON_WINDOWS_NOOP"
        _STATE = state
        return dict(state)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_current_process = kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    handle = get_current_process()

    set_priority = kernel32.SetPriorityClass
    set_priority.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    set_priority.restype = ctypes.c_int

    priority_ok = bool(
        set_priority(handle, BELOW_NORMAL_PRIORITY_CLASS)
    )
    state["windows_priority_applied"] = priority_ok
    if not priority_ok:
        state["priority_last_error"] = ctypes.get_last_error()

    eco_ok = False
    try:
        set_process_information = kernel32.SetProcessInformation
        set_process_information.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_ulong,
        ]
        set_process_information.restype = ctypes.c_int

        throttling = PROCESS_POWER_THROTTLING_STATE(
            PROCESS_POWER_THROTTLING_CURRENT_VERSION,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
            PROCESS_POWER_THROTTLING_EXECUTION_SPEED,
        )
        eco_ok = bool(
            set_process_information(
                handle,
                PROCESS_POWER_THROTTLING,
                ctypes.byref(throttling),
                ctypes.sizeof(throttling),
            )
        )
        if not eco_ok:
            state["ecoqos_last_error"] = ctypes.get_last_error()
    except Exception as exc:
        state["ecoqos_error"] = type(exc).__name__

    state["windows_ecoqos_applied"] = eco_ok
    _STATE = state
    return dict(state)


def current_resource_guard_state() -> dict[str, Any]:
    return activate_local_resource_guard()
