from dataclasses import dataclass, field
@dataclass
class ConsistencyCheck:
    check_id: str
    check_type: str
    is_consistent: bool
    details: str
@dataclass
class ConsistencyReport:
    report_id: str
    checks: list[ConsistencyCheck] = field(default_factory=list)
@dataclass
class ConsistencyResult:
    result_id: str
    report: ConsistencyReport
    consistent: bool
    check_count: int
