import pytest

from src.application.siraj_luna_central_director_v4 import (
    PREPRODUCTION_OWNER_STAGES,
    SUPERVISED_EXECUTION_STAGES,
    LunaCentralDirectorError,
    assert_luna_cannot_authorize_spend,
    assert_stage_governance,
)

def test_all_preproduction_is_luna_owned():
    for stage in PREPRODUCTION_OWNER_STAGES:
        assert_stage_governance(stage, "LUNA")
        with pytest.raises(LunaCentralDirectorError):
            assert_stage_governance(stage, "DETERMINISTIC_RUNTIME")

def test_execution_is_luna_supervised_not_luna_executed():
    for stage in SUPERVISED_EXECUTION_STAGES:
        assert_stage_governance(stage, "LUNA_SUPERVISOR")
        assert_stage_governance(stage, "DETERMINISTIC_RUNTIME")
        with pytest.raises(LunaCentralDirectorError):
            assert_stage_governance(stage, "LUNA")

def test_luna_cannot_self_authorize_paid_work():
    with pytest.raises(LunaCentralDirectorError):
        assert_luna_cannot_authorize_spend("LUNA")
    with pytest.raises(LunaCentralDirectorError):
        assert_luna_cannot_authorize_spend("LUNA_SUPERVISOR")
