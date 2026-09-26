"""Structured triage output for routing and review."""

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.disposition import Disposition


class TriageResult(DomainModel):
    disposition: Disposition
    confidence: float | None = Field(default=None, ge=0, le=1)
    trigger_rule_ids: tuple[str, ...] = ()
    symptom_fact_ids: tuple[str, ...] = ()
    red_flag_ids: tuple[str, ...] = ()
    unanswered_critical_question_ids: tuple[str, ...] = ()
    recommended_scheduling_window: str | None = None
    requires_human_review: bool
    rationale_code: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def enforce_safety_invariants(self) -> "TriageResult":
        if self.unanswered_critical_question_ids and not self.requires_human_review:
            raise ValueError("unanswered critical questions require human review")
        if self.unanswered_critical_question_ids and self.disposition not in {
            Disposition.EMERGENCY,
            Disposition.HUMAN_REVIEW,
        }:
            raise ValueError("unanswered critical questions prohibit a nonurgent disposition")
        if self.disposition is Disposition.EMERGENCY:
            if not self.trigger_rule_ids or not self.red_flag_ids:
                raise ValueError("EMERGENCY requires rule and red-flag evidence")
            if not self.requires_human_review:
                raise ValueError("EMERGENCY requires human review")
            if self.recommended_scheduling_window is not None:
                raise ValueError("EMERGENCY must not recommend ordinary scheduling")
        return self
