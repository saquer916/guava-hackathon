"""Structured triage output for routing and review."""

from pydantic import Field

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
