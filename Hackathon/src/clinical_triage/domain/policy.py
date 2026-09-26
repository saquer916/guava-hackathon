"""Content-neutral policy contracts. Clinical content requires external approval."""

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import FactValue


class PolicyReviewStatus(StrEnum):
    EXAMPLE_UNREVIEWED = "EXAMPLE_UNREVIEWED"
    CLINICIAN_REVIEWED = "CLINICIAN_REVIEWED"


class PredicateOperator(StrEnum):
    PRESENT = "PRESENT"
    EQUALS = "EQUALS"
    IN = "IN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"


class FactPredicate(DomainModel):
    fact_id: str = Field(min_length=1)
    operator: PredicateOperator
    value: FactValue | tuple[FactValue, ...] | None = None

    @model_validator(mode="after")
    def operator_value_shape(self) -> "FactPredicate":
        if self.operator is PredicateOperator.PRESENT and self.value is not None:
            raise ValueError("PRESENT predicates must not supply a value")
        if self.operator is not PredicateOperator.PRESENT and self.value is None:
            raise ValueError(f"{self.operator} predicates require a value")
        if self.operator is PredicateOperator.IN and not isinstance(self.value, tuple):
            raise ValueError("IN predicates require a tuple value")
        return self


class RuleSpec(DomainModel):
    rule_id: str = Field(min_length=1)
    priority: int = Field(ge=0)
    disposition: Disposition
    all_of: tuple[FactPredicate, ...] = ()
    any_of: tuple[FactPredicate, ...] = ()
    required_fact_ids: tuple[str, ...] = ()
    approved_script_id: str | None = None

    @model_validator(mode="after")
    def rule_has_predicates(self) -> "RuleSpec":
        if not self.all_of and not self.any_of:
            raise ValueError("a rule requires at least one predicate")
        return self


class PolicyBundle(DomainModel):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_date: date
    review_status: PolicyReviewStatus
    approved_by: str | None = None
    rules: tuple[RuleSpec, ...]

    @model_validator(mode="after")
    def review_metadata_and_rules_are_consistent(self) -> "PolicyBundle":
        if self.review_status is PolicyReviewStatus.CLINICIAN_REVIEWED and not self.approved_by:
            raise ValueError("clinician-reviewed policy requires approved_by")
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("policy rule_id values must be unique")
        return self


class PolicyEvaluation(DomainModel):
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    policy_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    considered_fact_ids: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]
    suppressed_rule_ids: tuple[str, ...] = ()
    unresolved_rule_ids: tuple[str, ...] = ()
    next_required_fact_ids: tuple[str, ...] = ()
    disposition: Disposition | None = None
    fail_closed_reason: str | None = None

    @model_validator(mode="after")
    def outcome_is_explicit(self) -> "PolicyEvaluation":
        if (self.disposition is None) == (self.fail_closed_reason is None):
            raise ValueError("evaluation requires exactly one disposition or fail_closed_reason")
        return self
