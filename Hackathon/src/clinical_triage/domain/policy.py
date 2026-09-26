"""Content-neutral policy contracts. Clinical content requires external approval."""

from datetime import date, datetime
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


class FactDataType(StrEnum):
    TEXT = "TEXT"
    CODE = "CODE"
    INTEGER = "INTEGER"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"


class FactDefinition(DomainModel):
    fact_id: str = Field(min_length=1)
    data_type: FactDataType
    allowed_unit_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def units_are_normalized(self) -> "FactDefinition":
        if len(self.allowed_unit_codes) != len(set(self.allowed_unit_codes)):
            raise ValueError("allowed unit codes must be unique")
        if self.allowed_unit_codes and self.data_type not in {
            FactDataType.INTEGER,
            FactDataType.NUMBER,
        }:
            raise ValueError("units are only valid for numeric facts")
        return self


class FactPredicate(DomainModel):
    fact_id: str = Field(min_length=1)
    operator: PredicateOperator
    value: FactValue | tuple[FactValue, ...] | None = None
    unit_code: str | None = None

    @model_validator(mode="after")
    def operator_value_shape(self) -> "FactPredicate":
        if self.operator is PredicateOperator.PRESENT and self.value is not None:
            raise ValueError("PRESENT predicates must not supply a value")
        if self.operator is not PredicateOperator.PRESENT and self.value is None:
            raise ValueError(f"{self.operator} predicates require a value")
        if self.operator is PredicateOperator.IN and not isinstance(self.value, tuple):
            raise ValueError("IN predicates require a tuple value")
        if self.operator is not PredicateOperator.IN and isinstance(self.value, tuple):
            raise ValueError("only IN predicates accept tuple values")
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
    fact_definitions: tuple[FactDefinition, ...]
    rules: tuple[RuleSpec, ...]

    @model_validator(mode="after")
    def review_metadata_and_rules_are_consistent(self) -> "PolicyBundle":
        if self.review_status is PolicyReviewStatus.CLINICIAN_REVIEWED and not self.approved_by:
            raise ValueError("clinician-reviewed policy requires approved_by")
        rule_ids = [rule.rule_id for rule in self.rules]
        if len(rule_ids) != len(set(rule_ids)):
            raise ValueError("policy rule_id values must be unique")
        definitions = {definition.fact_id: definition for definition in self.fact_definitions}
        if len(definitions) != len(self.fact_definitions):
            raise ValueError("policy fact definitions must be unique")
        for rule in self.rules:
            referenced = set(rule.required_fact_ids)
            referenced.update(predicate.fact_id for predicate in rule.all_of + rule.any_of)
            unknown = referenced - definitions.keys()
            if unknown:
                raise ValueError(f"rule references undefined facts: {sorted(unknown)}")
            for predicate in rule.all_of + rule.any_of:
                self._validate_predicate(predicate, definitions[predicate.fact_id])
        return self

    @staticmethod
    def _validate_predicate(predicate: FactPredicate, definition: FactDefinition) -> None:
        comparable = {
            FactDataType.INTEGER,
            FactDataType.NUMBER,
            FactDataType.DATE,
            FactDataType.DATETIME,
        }
        if (
            predicate.operator
            in {
                PredicateOperator.GREATER_THAN_OR_EQUAL,
                PredicateOperator.LESS_THAN_OR_EQUAL,
            }
            and definition.data_type not in comparable
        ):
            raise ValueError("ordered comparison requires a numeric or temporal fact")
        if predicate.unit_code is not None:
            if predicate.unit_code not in definition.allowed_unit_codes:
                raise ValueError("predicate unit is not allowed by the fact definition")
        elif definition.allowed_unit_codes and predicate.operator is not PredicateOperator.PRESENT:
            raise ValueError("numeric predicate requires an explicit normalized unit")
        values = predicate.value if isinstance(predicate.value, tuple) else (predicate.value,)
        for value in values:
            if value is None:
                continue
            if not PolicyBundle._value_matches_type(value, definition.data_type):
                raise ValueError("predicate value does not match the fact definition type")

    @staticmethod
    def _value_matches_type(value: FactValue, data_type: FactDataType) -> bool:
        if data_type in {FactDataType.TEXT, FactDataType.CODE}:
            return isinstance(value, str)
        if data_type is FactDataType.INTEGER:
            return isinstance(value, int) and not isinstance(value, bool)
        if data_type is FactDataType.NUMBER:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if data_type is FactDataType.BOOLEAN:
            return isinstance(value, bool)
        if data_type is FactDataType.DATE:
            return isinstance(value, date) and not isinstance(value, datetime)
        return isinstance(value, datetime)


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
        if self.next_required_fact_ids and self.disposition not in {
            None,
            Disposition.EMERGENCY,
            Disposition.HUMAN_REVIEW,
        }:
            raise ValueError("missing required facts prohibit an ordinary disposition")
        return self
