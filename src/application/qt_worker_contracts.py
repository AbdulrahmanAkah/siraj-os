"""Typed contracts shared by Qt launchers, workers and live monitors."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LiveProductionMonitorContract(Protocol):
    def set_worker_active(self, active: bool) -> None: ...
    def set_runtime_action(
        self, stage: str, action: str, done: int | None = None,
        total: int | None = None,
    ) -> None: ...
    def set_runtime_error(self, error: str) -> None: ...


@runtime_checkable
class AutopilotWorkerContract(Protocol):
    def start(self) -> None: ...
    def isRunning(self) -> bool: ...
    def isFinished(self) -> bool: ...
    def deleteLater(self) -> None: ...


def validate_monitor_contract(value: object) -> LiveProductionMonitorContract:
    if not isinstance(value, LiveProductionMonitorContract):
        missing = [
            name for name in ("set_worker_active", "set_runtime_action", "set_runtime_error")
            if not callable(getattr(value, name, None))
        ]
        raise TypeError("LIVE_MONITOR_CONTRACT_INVALID:" + ",".join(missing))
    return value
