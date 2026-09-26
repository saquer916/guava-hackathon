"""Conversation state and provider-neutral call lifecycle values."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact, ClinicalState


class SessionPhase(StrEnum):
    START = "START"
    BOUNDARY_AND_CONSENT = "BOUNDARY_AND_CONSENT"
    COLLECT_FACT = "COLLECT_FACT"
    EVALUATE_POLICY = "EVALUATE_POLICY"
    ESCALATE = "ESCALATE"
    DISPOSITION = "DISPOSITION"
    SLOT_SEARCH = "SLOT_SEARCH"
    SLOT_OFFERED = "SLOT_OFFERED"
    EXPLICIT_CONFIRMATION = "EXPLICIT_CONFIRMATION"
    BOOKING_COMMIT = "BOOKING_COMMIT"
    CLOSE = "CLOSE"


class ConversationState(DomainModel):
    version: int = Field(default=0, ge=0)
    asked_question_ids: tuple[str, ...] = ()
    last_question_id: str | None = None
    pending_clarification_fact_id: str | None = None
    do_not_repeat_question_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_question_history(self) -> "ConversationState":
        if len(self.asked_question_ids) != len(set(self.asked_question_ids)):
            raise ValueError("asked_question_ids must not contain repeats")
        if self.last_question_id and self.last_question_id not in self.asked_question_ids:
            raise ValueError("last_question_id must be present in asked_question_ids")
        return self


class SessionState(DomainModel):
    call_id: str = Field(min_length=1)
    phase: SessionPhase = SessionPhase.START
    version: int = Field(default=0, ge=0)
    clinical: ClinicalState = ClinicalState()
    conversation: ConversationState = ConversationState()
    disposition: Disposition | None = None
    offered_slot_id: str | None = None
    terminal: bool = False

    @model_validator(mode="after")
    def terminal_phase_is_consistent(self) -> "SessionState":
        terminal_phases = {SessionPhase.ESCALATE, SessionPhase.CLOSE}
        if self.terminal != (self.phase in terminal_phases):
            raise ValueError("terminal must match ESCALATE or CLOSE phase")
        if self.disposition is Disposition.EMERGENCY and self.phase is not SessionPhase.ESCALATE:
            raise ValueError("EMERGENCY disposition requires ESCALATE phase")
        if self.phase is SessionPhase.ESCALATE and self.disposition is not Disposition.EMERGENCY:
            raise ValueError("ESCALATE phase requires EMERGENCY disposition")
        scheduling_phases = {
            SessionPhase.SLOT_SEARCH,
            SessionPhase.SLOT_OFFERED,
            SessionPhase.EXPLICIT_CONFIRMATION,
            SessionPhase.BOOKING_COMMIT,
        }
        schedulable_dispositions = {
            Disposition.URGENT_SAME_DAY,
            Disposition.SOON,
            Disposition.ROUTINE,
            Disposition.ADMINISTRATIVE,
        }
        if self.phase in scheduling_phases and self.disposition not in schedulable_dispositions:
            raise ValueError("scheduling requires an eligible non-emergency disposition")
        offer_phases = {
            SessionPhase.SLOT_OFFERED,
            SessionPhase.EXPLICIT_CONFIRMATION,
            SessionPhase.BOOKING_COMMIT,
        }
        if (self.phase in offer_phases) != (self.offered_slot_id is not None):
            raise ValueError("offered_slot_id must exist exactly during offer and booking phases")
        return self


class DomainEventKind(StrEnum):
    CALL_STARTED = "CALL_STARTED"
    CONSENT_RECORDED = "CONSENT_RECORDED"
    ANSWER_RECORDED = "ANSWER_RECORDED"
    ANSWER_CORRECTED = "ANSWER_CORRECTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"
    HUMAN_REVIEW_REQUESTED = "HUMAN_REVIEW_REQUESTED"
    SESSION_ENDED = "SESSION_ENDED"


class EventBase(DomainModel):
    event_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)
    expected_state_version: int = Field(ge=0)


class CallStarted(EventBase):
    kind: Literal[DomainEventKind.CALL_STARTED] = DomainEventKind.CALL_STARTED


class ConsentRecorded(EventBase):
    kind: Literal[DomainEventKind.CONSENT_RECORDED] = DomainEventKind.CONSENT_RECORDED
    consent_code: str = Field(min_length=1)


class AnswerRecorded(EventBase):
    kind: Literal[DomainEventKind.ANSWER_RECORDED] = DomainEventKind.ANSWER_RECORDED
    fact: ClinicalFact


class AnswerCorrected(EventBase):
    kind: Literal[DomainEventKind.ANSWER_CORRECTED] = DomainEventKind.ANSWER_CORRECTED
    fact: ClinicalFact
    replaces_event_id: str = Field(min_length=1)


class TaskCompleted(EventBase):
    kind: Literal[DomainEventKind.TASK_COMPLETED] = DomainEventKind.TASK_COMPLETED
    task_id: str = Field(min_length=1)


class AppointmentConfirmed(EventBase):
    kind: Literal[DomainEventKind.APPOINTMENT_CONFIRMED] = DomainEventKind.APPOINTMENT_CONFIRMED
    confirmation_id: str = Field(min_length=1)


class HumanReviewRequested(EventBase):
    kind: Literal[DomainEventKind.HUMAN_REVIEW_REQUESTED] = DomainEventKind.HUMAN_REVIEW_REQUESTED
    reason_code: str = Field(min_length=1)


class SessionEndedEvent(EventBase):
    kind: Literal[DomainEventKind.SESSION_ENDED] = DomainEventKind.SESSION_ENDED
    reason_code: str = Field(min_length=1)


DomainEvent = Annotated[
    CallStarted
    | ConsentRecorded
    | AnswerRecorded
    | AnswerCorrected
    | TaskCompleted
    | AppointmentConfirmed
    | HumanReviewRequested
    | SessionEndedEvent,
    Field(discriminator="kind"),
]


class AskQuestion(DomainModel):
    kind: Literal["ASK_QUESTION"] = "ASK_QUESTION"
    question_id: str = Field(min_length=1)


class Escalate(DomainModel):
    kind: Literal["ESCALATE"] = "ESCALATE"
    disposition: Literal[Disposition.EMERGENCY] = Disposition.EMERGENCY
    script_id: str = Field(min_length=1)
    trigger_rule_ids: tuple[str, ...] = Field(min_length=1)


class SearchAppointments(DomainModel):
    kind: Literal["SEARCH_APPOINTMENTS"] = "SEARCH_APPOINTMENTS"
    scheduling_window: str = Field(min_length=1)
    constraint_codes: tuple[str, ...] = ()


class RequestHumanReview(DomainModel):
    kind: Literal["REQUEST_HUMAN_REVIEW"] = "REQUEST_HUMAN_REVIEW"
    reason_code: str = Field(min_length=1)


class CloseCall(DomainModel):
    kind: Literal["CLOSE_CALL"] = "CLOSE_CALL"
    script_id: str = Field(min_length=1)


DomainCommand = AskQuestion | Escalate | SearchAppointments | RequestHumanReview | CloseCall
