from dataclasses import dataclass, field


@dataclass
class ReasoningValidationPlan:
    plan_id: str
    required_checks: list[str] = field(default_factory=list)


@dataclass
class ValidationCheck:
    check_id: str
    check_type: str
    passed: bool
    error_codes: list[str] = field(default_factory=list)
    reference_ids: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class ValidatedReasoningResult:
    result_id: str
    plan_id: str
    reasoning_result_id: str
    interpretation_result_id: str
    is_valid: bool
    checks: list[ValidationCheck] = field(default_factory=list)
    check_count: int = 0
    validation_state: str = "VALID"


__all__ = [
    "ReasoningValidationPlan",
    "ValidatedReasoningResult",
    "ValidationCheck",
]
