"""Structured synthetic-call audit contracts, separate from operational logs."""

from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact


class OperationOutcome(StrEnum):
    ATTEMPTED = "ATTEMPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AuditedOperation(DomainModel):
    operation_id: str = Field(min_length=1)
    operation_type: str = Field(min_length=1)
    target_system: str = Field(min_length=1)
    outcome: OperationOutcome
    error_code: str | None = None


class RuleEvaluationTrace(DomainModel):
    rule_id: str = Field(min_length=1)
    evaluated: bool
    triggered: bool
    evidence_fact_ids: tuple[str, ...] = ()


class AuditRecord(DomainModel):
    call_id: str = Field(min_length=1)
    synthetic_patient_id: str | None = None
    started_at: datetime
    ended_at: datetime | None = None
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question_ids_asked: tuple[str, ...] = ()
    facts_recorded: tuple[ClinicalFact, ...] = ()
    rule_evaluations: tuple[RuleEvaluationTrace, ...] = ()
    disposition: Disposition | None = None
    appointment_option_ids_considered: tuple[str, ...] = ()
    human_decision_codes: tuple[str, ...] = ()
    operations: tuple[AuditedOperation, ...] = ()
    error_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_time_range(self) -> "AuditRecord":
        if self.started_at.tzinfo is None:
            raise ValueError("audit timestamps must be timezone-aware")
        if self.ended_at is not None:
            if self.ended_at.tzinfo is None:
                raise ValueError("audit timestamps must be timezone-aware")
            if self.ended_at < self.started_at:
                raise ValueError("audit end must not precede start")
        return self


class OperationalEvent(DomainModel):
    """Sanitized telemetry; deliberately excludes facts and free text."""

    event_code: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    occurred_at: datetime
    outcome: OperationOutcome
    error_code: str | None = None
