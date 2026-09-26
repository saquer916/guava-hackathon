"""Structured facts kept separate from conversational phrasing."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel

FactValue = str | int | float | bool | date | datetime


class FactSource(StrEnum):
    CALLER = "CALLER"
    EHR = "EHR"
    DERIVED = "DERIVED"
    OPERATOR = "OPERATOR"


class ClinicalFact(DomainModel):
    fact_id: str = Field(min_length=1)
    value: FactValue
    source: FactSource
    confirmed: bool = False
    unit_code: str | None = None


class ClinicalState(DomainModel):
    facts: tuple[ClinicalFact, ...] = ()
    important_missing_fact_ids: tuple[str, ...] = ()
    possible_red_flag_ids: tuple[str, ...] = ()
    relevant_follow_up_domains: tuple[str, ...] = ()

    @model_validator(mode="after")
    def unique_fact_ids(self) -> "ClinicalState":
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("clinical facts must have unique fact_id values")
        return self

    def fact(self, fact_id: str) -> ClinicalFact | None:
        return next((fact for fact in self.facts if fact.fact_id == fact_id), None)
