"""Content-neutral conversation configuration and the policy evaluation seam.

Question IDs, consent codes, and scheduling-window codes are identifiers only;
the wording that a voice layer speaks for them lives outside this package.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalState
from clinical_triage.domain.policy import PolicyEvaluation


class QuestionKind(StrEnum):
    PRIMARY = "PRIMARY"
    CLARIFICATION = "CLARIFICATION"


@dataclass(frozen=True)
class QuestionSpec:
    question_id: str
    fact_id: str
    kind: QuestionKind = QuestionKind.PRIMARY


@dataclass(frozen=True)
class PolicyOutcome:
    """A policy evaluation plus the reviewed script to use if it escalates."""

    evaluation: PolicyEvaluation
    escalation_script_id: str | None = None


class PolicyEvaluator(Protocol):
    def __call__(self, clinical: ClinicalState) -> PolicyOutcome: ...


ORDINARY_DISPOSITIONS = frozenset(
    {
        Disposition.URGENT_SAME_DAY,
        Disposition.SOON,
        Disposition.ROUTINE,
        Disposition.ADMINISTRATIVE,
    }
)


@dataclass(frozen=True)
class ConversationConfig:
    questions: tuple[QuestionSpec, ...]
    consent_question_id: str
    accepted_consent_codes: frozenset[str]
    scheduling_windows: Mapping[Disposition, str]
    fallback_emergency_script_id: str
    close_script_id: str = "CLOSE_BOOKED"
    constraint_codes: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        ids = [q.question_id for q in self.questions] + [self.consent_question_id]
        if len(ids) != len(set(ids)):
            raise ValueError("question IDs must be unique")
        keys = [(q.fact_id, q.kind) for q in self.questions]
        if len(keys) != len(set(keys)):
            raise ValueError("each fact has at most one question per kind")
        if set(self.scheduling_windows) != ORDINARY_DISPOSITIONS:
            raise ValueError(
                "scheduling windows are required for exactly the ordinary dispositions"
            )
        if not self.accepted_consent_codes:
            raise ValueError("at least one consent code is required")

    def question_for(self, fact_id: str, kind: QuestionKind) -> QuestionSpec | None:
        return next((q for q in self.questions if q.fact_id == fact_id and q.kind is kind), None)
