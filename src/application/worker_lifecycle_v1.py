"""Deterministic UI worker lifecycle and local stall watchdog policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import time


class WorkerState(str, Enum):
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    FINISHED = "FINISHED"
    STALLED = "STALLED"


class WorkerLifecycleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkerLifecycle:
    state: WorkerState = WorkerState.IDLE
    started_monotonic: float | None = None
    heartbeat_monotonic: float | None = None
    error: str | None = None

    def start_requested(self, now: float | None = None) -> "WorkerLifecycle":
        if self.state not in {WorkerState.IDLE, WorkerState.FINISHED}:
            raise WorkerLifecycleError("DUPLICATE_WORKER_START_BLOCKED")
        stamp = time.monotonic() if now is None else now
        return replace(self, state=WorkerState.STARTING, started_monotonic=stamp,
                       heartbeat_monotonic=stamp, error=None)

    def entered(self, now: float | None = None) -> "WorkerLifecycle":
        if self.state != WorkerState.STARTING:
            raise WorkerLifecycleError("WORKER_ENTERED_FROM_INVALID_STATE")
        stamp = time.monotonic() if now is None else now
        return replace(self, state=WorkerState.RUNNING, heartbeat_monotonic=stamp)

    def heartbeat(self, now: float | None = None) -> "WorkerLifecycle":
        if self.state != WorkerState.RUNNING:
            raise WorkerLifecycleError("WORKER_HEARTBEAT_FROM_INVALID_STATE")
        return replace(self, heartbeat_monotonic=time.monotonic() if now is None else now)

    def terminal(self, *, error: str | None = None) -> "WorkerLifecycle":
        if self.state not in {WorkerState.STARTING, WorkerState.RUNNING}:
            raise WorkerLifecycleError("WORKER_TERMINAL_FROM_INVALID_STATE")
        return replace(self, state=WorkerState.FAILED if error else WorkerState.SUCCEEDED,
                       error=error)

    def finished(self) -> "WorkerLifecycle":
        if self.state not in {WorkerState.SUCCEEDED, WorkerState.FAILED, WorkerState.STALLED}:
            raise WorkerLifecycleError("WORKER_FINISHED_BEFORE_TERMINAL_SIGNAL")
        return replace(self, state=WorkerState.FINISHED)

    def watchdog(self, *, now: float | None = None, timeout_seconds: float = 30.0) -> "WorkerLifecycle":
        stamp = time.monotonic() if now is None else now
        if self.state in {WorkerState.STARTING, WorkerState.RUNNING} and self.heartbeat_monotonic is not None:
            if stamp - self.heartbeat_monotonic > timeout_seconds:
                return replace(self, state=WorkerState.STALLED, error="LOCAL_WORKER_HEARTBEAT_TIMEOUT")
        return self

    @property
    def may_close(self) -> bool:
        return self.state not in {WorkerState.STARTING, WorkerState.RUNNING}
