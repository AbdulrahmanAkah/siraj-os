from src.application.siraj_local_resource_guard_v5_2 import (
    activate_local_resource_guard,
)


def test_local_guard_does_not_change_luna_or_provider_limits():
    state = activate_local_resource_guard()
    assert state["active"] is True
    assert state["luna_reasoning_changed"] is False
    assert state["provider_limits_changed"] is False
    assert state["cpu_affinity_cap"] is None
    assert state["fixed_sleep_seconds"] is None


def test_local_guard_uses_below_normal_policy_on_windows():
    state = activate_local_resource_guard()
    assert state["priority_policy"] == "BELOW_NORMAL_ON_WINDOWS"
    assert state["ecoqos_policy"] == "REQUEST_ON_WINDOWS_WHEN_SUPPORTED"
