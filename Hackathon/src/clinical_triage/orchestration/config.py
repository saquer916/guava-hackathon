"""Orchestrator configuration: voice questions, targets, scripts, and approval flags.

Every approval flag defaults to the conservative value. Script texts are
operator-facing instructions; entries marked EXAMPLE_UNREVIEWED have not been
reviewed and must not be used with real callers.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from clinical_triage.conversation.config import ConversationConfig
from clinical_triage.domain.facts import FactValue
from clinical_triage.domain.voice import AgentSpec, FieldSpec, TransferTarget


class ParseKind(StrEnum):
    YES_NO = "YES_NO"
    CHOICE = "CHOICE"
    NUMBER = "NUMBER"


@dataclass(frozen=True)
class VoiceQuestion:
    question_id: str
    fact_id: str
    field: FieldSpec
    parse: ParseKind
    unit_code: str | None = None

    def parse_value(self, raw: object) -> FactValue | None:
        """Deterministically parse a voice field; anything unparseable is None."""

        if raw is None:
            return None
        text = str(raw).strip()
        if self.parse is ParseKind.YES_NO:
            return {"YES": True, "NO": False}.get(text.upper())
        if self.parse is ParseKind.CHOICE:
            return text if text in self.field.choices else None
        try:
            number = float(text)
        except ValueError:
            return None
        return number if number == number and abs(number) != float("inf") else None


@dataclass(frozen=True)
class SchedulingWindow:
    earliest_offset_minutes: int
    latest_offset_minutes: int

    def __post_init__(self) -> None:
        if not 0 <= self.earliest_offset_minutes < self.latest_offset_minutes:
            raise ValueError("scheduling window offsets must be increasing and non-negative")


def parse_birth_date(raw: object) -> date | None:
    try:
        return date.fromisoformat(str(raw).strip()) if raw is not None else None
    except ValueError:
        return None


@dataclass(frozen=True)
class OrchestratorConfig:
    agent: AgentSpec
    conversation: ConversationConfig
    questions: tuple[VoiceQuestion, ...]
    consent_field: FieldSpec
    consent_boundary_script: str
    windows: Mapping[str, SchedulingWindow]
    emergency_target: TransferTarget
    human_review_target: TransferTarget
    scripts: Mapping[str, str]
    question_deflection: str
    human_review_callback_script: str
    offer_prompt_template: str
    allow_booking_writes: bool = False
    allow_record_writes: bool = False
    retryable_booking_failures: frozenset[str] = field(
        default=frozenset({"SLOT_NO_LONGER_AVAILABLE", "OFFER_EXPIRED"})
    )

    def __post_init__(self) -> None:
        ids = [q.question_id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("voice question IDs must be unique")
        reserved = {"identity", "offer", self.conversation.consent_question_id}
        if reserved & set(ids):
            raise ValueError("voice question IDs collide with orchestrator task IDs")
        for question in self.questions:
            if question.field.key != question.fact_id:
                raise ValueError("voice field key must equal its fact ID")
        missing_windows = set(self.conversation.scheduling_windows.values()) - set(self.windows)
        if missing_windows:
            raise ValueError(f"no time range for scheduling windows: {sorted(missing_windows)}")
        if self.conversation.fallback_emergency_script_id not in self.scripts:
            raise ValueError("the fallback emergency script must have text")

    def question(self, question_id: str) -> VoiceQuestion | None:
        return next((q for q in self.questions if q.question_id == question_id), None)
