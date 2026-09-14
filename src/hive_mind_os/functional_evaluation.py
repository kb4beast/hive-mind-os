"""Observable behavior evaluation contracts (N24)."""
from dataclasses import dataclass
from enum import StrEnum
class CheckOutcome(StrEnum): PASS="PASS"; FAIL="FAIL"; UNAVAILABLE="UNAVAILABLE"; INCONCLUSIVE="INCONCLUSIVE"
class EvaluationVerdict(StrEnum): PASS="PASS"; FAIL="FAIL"; BLOCKED_ENVIRONMENT="BLOCKED_ENVIRONMENT"; CONTAMINATED="CONTAMINATED"; INCONCLUSIVE="INCONCLUSIVE"
@dataclass(frozen=True, slots=True)
class FunctionalEvaluation:
 episode_id:str; candidate_digest:str; rubric_digest:str; environment_digest:str; reference_health:CheckOutcome; required_checks:tuple[str,...]; capability_results:dict[str,CheckOutcome]; quality_metrics:dict[str,float]; security_results:dict[str,CheckOutcome]; resource_use:dict[str,float]; contamination_status:str; evaluator_id:str; verdict:EvaluationVerdict; evidence_refs:tuple[str,...]=()
 def __post_init__(self):
  if self.contamination_status!="CLEAR" and self.verdict is not EvaluationVerdict.CONTAMINATED: raise ValueError("contamination must quarantine evaluation")
def verdict_for(checks, *, contaminated=False):
 if contaminated:return EvaluationVerdict.CONTAMINATED
 vals=list(checks.values())
 if any(v is CheckOutcome.FAIL for v in vals):return EvaluationVerdict.FAIL
 if any(v is CheckOutcome.UNAVAILABLE for v in vals):return EvaluationVerdict.BLOCKED_ENVIRONMENT
 if any(v is CheckOutcome.INCONCLUSIVE for v in vals):return EvaluationVerdict.INCONCLUSIVE
 return EvaluationVerdict.PASS
