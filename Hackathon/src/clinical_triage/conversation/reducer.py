"""Pure, versioned conversation reducer.

`reduce` applies one provider-neutral event to an immutable SessionState and
returns the next state plus typed commands. It never calls providers, never
reads free text, and never makes a clinical judgement itself: every new or
corrected fact is handed to the injected PolicyEvaluator, and the result is
routed with these invariants:

- An EMERGENCY evaluation escalates immediately from any non-terminal phase,
  including before consent and during booking. Nothing downgrades it.
- HUMAN_REVIEW is sticky: later facts may escalate it to EMERGENCY but never
  route it back to ordinary scheduling.
- A question is asked at most once. A critical fact still missing after its
  question was asked, a fact that stays unconfirmed after clarification, a
  policy fail-closed result, and any evaluator error all route to HUMAN_REVIEW.
- Stale, cross-call, and post-terminal events are rejected without effect.
"""

from dataclasses import dataclass

from clinical_triage.conversation.config import (
    ORDINARY_DISPOSITIONS,
    ConversationConfig,
    PolicyEvaluator,
    PolicyOutcome,
    QuestionKind,
)
from clinical_triage.domain.conversation import (
    AnswerCorrected,
    AnswerRecorded,
    AppointmentConfirmed,
    AskQuestion,
    CallStarted,
    CloseCall,
    ConsentRecorded,
    DomainCommand,
    DomainEvent,
    Escalate,
    HumanReviewRequested,
    RequestHumanReview,
    SearchAppointments,
    SessionEndedEvent,
    SessionPhase,
    SessionState,
    TaskCompleted,
)
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.facts import ClinicalFact

SCHEDULING_PHASES = frozenset(
    {
        SessionPhase.SLOT_SEARCH,
        SessionPhase.SLOT_OFFERED,
        SessionPhase.EXPLICIT_CONFIRMATION,
        SessionPhase.BOOKING_COMMIT,
    }
)
PRE_CONSENT_PHASES = frozenset({SessionPhase.START, SessionPhase.BOUNDARY_AND_CONSENT})


@dataclass(frozen=True)
class Transition:
    state: SessionState
    commands: tuple[DomainCommand, ...] = ()
    rejected_reason: str | None = None
    outcome: PolicyOutcome | None = None

    @property
    def accepted(self) -> bool:
        return self.rejected_reason is None


def new_session(call_id: str) -> SessionState:
    return SessionState(call_id=call_id)


def reduce(
    state: SessionState,
    event: DomainEvent,
    *,
    config: ConversationConfig,
    evaluate: PolicyEvaluator,
) -> Transition:
    rejection = _guard(state, event.call_id, event.expected_state_version)
    if rejection:
        return Transition(state=state, rejected_reason=rejection)

    if isinstance(event, CallStarted):
        if state.phase is not SessionPhase.START:
            return _reject(state, "CALL_ALREADY_STARTED")
        asked = _mark_asked(state, config.consent_question_id)
        return _accept(
            asked.model_copy(update={"phase": SessionPhase.BOUNDARY_AND_CONSENT}),
            (AskQuestion(question_id=config.consent_question_id),),
        )

    if isinstance(event, ConsentRecorded):
        if state.phase is not SessionPhase.BOUNDARY_AND_CONSENT:
            return _reject(state, "CONSENT_NOT_EXPECTED")
        if event.consent_code not in config.accepted_consent_codes:
            return _accept(*_human_review(state, "CONSENT_NOT_GIVEN"))
        collecting = state.model_copy(update={"phase": SessionPhase.COLLECT_FACT})
        return _evaluate_and_route(collecting, config, evaluate)

    if isinstance(event, AnswerRecorded):
        if state.clinical.fact(event.fact.fact_id) is not None:
            return _reject(state, "FACT_ALREADY_RECORDED_USE_CORRECTION")
        return _evaluate_and_route(_with_fact(state, event.fact), config, evaluate)

    if isinstance(event, AnswerCorrected):
        if state.clinical.fact(event.fact.fact_id) is None:
            return _reject(state, "NO_FACT_TO_CORRECT")
        return _evaluate_and_route(_with_fact(state, event.fact), config, evaluate)

    if isinstance(event, TaskCompleted):
        if event.task_id != state.conversation.last_question_id:
            return _accept(state, ())
        # The outstanding question's turn is over; anything it did not resolve
        # can no longer be asked again.
        closed = state.model_copy(
            update={
                "conversation": state.conversation.model_copy(update={"last_question_id": None})
            }
        )
        if state.phase in PRE_CONSENT_PHASES:
            return _accept(closed, ())
        return _evaluate_and_route(closed, config, evaluate)

    if isinstance(event, AppointmentConfirmed):
        if state.phase is not SessionPhase.SLOT_OFFERED:
            return _reject(state, "NO_OFFER_TO_CONFIRM")
        return _accept(state.model_copy(update={"phase": SessionPhase.EXPLICIT_CONFIRMATION}), ())

    if isinstance(event, HumanReviewRequested):
        return _accept(*_human_review(state, event.reason_code))

    if isinstance(event, SessionEndedEvent):
        return _accept(
            state.model_copy(
                update={"phase": SessionPhase.CLOSE, "terminal": True, "offered_slot_id": None}
            ),
            (),
        )

    return _reject(state, "UNSUPPORTED_EVENT")  # pragma: no cover - union is exhaustive


# --- scheduling sub-flow transitions (orchestrator-driven, same guards) ------


def offer_slot(state: SessionState, *, slot_id: str, expected_version: int) -> Transition:
    rejection = _guard(state, state.call_id, expected_version)
    if rejection:
        return _reject(state, rejection)
    if state.phase is not SessionPhase.SLOT_SEARCH:
        return _reject(state, "NOT_SEARCHING")
    return _accept(
        state.model_copy(update={"phase": SessionPhase.SLOT_OFFERED, "offered_slot_id": slot_id}),
        (),
    )


def begin_booking_commit(state: SessionState, *, expected_version: int) -> Transition:
    rejection = _guard(state, state.call_id, expected_version)
    if rejection:
        return _reject(state, rejection)
    if state.phase is not SessionPhase.EXPLICIT_CONFIRMATION:
        return _reject(state, "CONFIRMATION_REQUIRED")
    return _accept(state.model_copy(update={"phase": SessionPhase.BOOKING_COMMIT}), ())


def booking_completed(
    state: SessionState, *, expected_version: int, config: ConversationConfig
) -> Transition:
    rejection = _guard(state, state.call_id, expected_version)
    if rejection:
        return _reject(state, rejection)
    if state.phase is not SessionPhase.BOOKING_COMMIT:
        return _reject(state, "NO_BOOKING_IN_PROGRESS")
    return _accept(
        state.model_copy(
            update={"phase": SessionPhase.CLOSE, "terminal": True, "offered_slot_id": None}
        ),
        (CloseCall(script_id=config.close_script_id),),
    )


def scheduling_failed(
    state: SessionState,
    *,
    expected_version: int,
    reason_code: str,
    retry: bool,
    config: ConversationConfig,
) -> Transition:
    """Retry the search once (caller-controlled) or hand the booking to a human."""

    rejection = _guard(state, state.call_id, expected_version)
    if rejection:
        return _reject(state, rejection)
    if state.phase not in SCHEDULING_PHASES:
        return _reject(state, "NOT_SCHEDULING")
    if retry and state.disposition in ORDINARY_DISPOSITIONS:
        searching = state.model_copy(
            update={"phase": SessionPhase.SLOT_SEARCH, "offered_slot_id": None}
        )
        return _accept(searching, (_search_command(searching.disposition, config),))
    return _accept(
        state.model_copy(update={"phase": SessionPhase.DISPOSITION, "offered_slot_id": None}),
        (RequestHumanReview(reason_code=reason_code),),
    )


# --- internals ---------------------------------------------------------------


def _guard(state: SessionState, call_id: str, expected_version: int) -> str | None:
    if call_id != state.call_id:
        return "CALL_ID_MISMATCH"
    if state.terminal:
        return "SESSION_TERMINAL"
    if expected_version != state.version:
        return "STALE_EVENT"
    return None


def _reject(state: SessionState, reason: str) -> Transition:
    return Transition(state=state, rejected_reason=reason)


def _accept(
    state: SessionState,
    commands: tuple[DomainCommand, ...],
    outcome: PolicyOutcome | None = None,
) -> Transition:
    bumped = state.model_copy(
        update={
            "version": state.version + 1,
            "conversation": state.conversation.model_copy(
                update={"version": state.conversation.version + 1}
            ),
        }
    )
    return Transition(
        state=SessionState.model_validate(bumped.model_dump()), commands=commands, outcome=outcome
    )


def _with_fact(state: SessionState, fact: ClinicalFact) -> SessionState:
    others = tuple(f for f in state.clinical.facts if f.fact_id != fact.fact_id)
    facts = tuple(sorted((*others, fact), key=lambda f: f.fact_id))
    pending = state.conversation.pending_clarification_fact_id
    conversation = state.conversation
    if pending == fact.fact_id:
        # A new value for the fact under clarification answers the clarification.
        conversation = conversation.model_copy(
            update={
                "pending_clarification_fact_id": None if fact.confirmed else pending,
                "last_question_id": None,
            }
        )
    return state.model_copy(
        update={
            "clinical": state.clinical.model_copy(update={"facts": facts}),
            "conversation": conversation,
        }
    )


def _mark_asked(state: SessionState, question_id: str) -> SessionState:
    asked = (*state.conversation.asked_question_ids, question_id)
    return state.model_copy(
        update={
            "conversation": state.conversation.model_copy(
                update={
                    "asked_question_ids": asked,
                    "last_question_id": question_id,
                    "do_not_repeat_question_ids": asked,
                }
            )
        }
    )


def _human_review(
    state: SessionState, reason: str
) -> tuple[SessionState, tuple[DomainCommand, ...]]:
    if state.disposition is Disposition.HUMAN_REVIEW and state.phase is SessionPhase.DISPOSITION:
        return state, ()
    routed = state.model_copy(
        update={
            "phase": SessionPhase.DISPOSITION,
            "disposition": Disposition.HUMAN_REVIEW,
            "offered_slot_id": None,
        }
    )
    return routed, (RequestHumanReview(reason_code=reason),)


def _escalate(
    state: SessionState, outcome: PolicyOutcome, config: ConversationConfig
) -> Transition:
    evaluation = outcome.evaluation
    triggers = evaluation.matched_rule_ids or ("EMERGENCY_WITHOUT_RULE_EVIDENCE",)
    escalated = state.model_copy(
        update={
            "phase": SessionPhase.ESCALATE,
            "terminal": True,
            "disposition": Disposition.EMERGENCY,
            "offered_slot_id": None,
            "clinical": state.clinical.model_copy(
                update={"possible_red_flag_ids": evaluation.matched_rule_ids}
            ),
        }
    )
    command = Escalate(
        script_id=outcome.escalation_script_id or config.fallback_emergency_script_id,
        trigger_rule_ids=triggers,
    )
    return _accept(escalated, (command,), outcome)


def _search_command(
    disposition: Disposition | None, config: ConversationConfig
) -> SearchAppointments:
    assert disposition in ORDINARY_DISPOSITIONS
    return SearchAppointments(
        scheduling_window=config.scheduling_windows[disposition],
        constraint_codes=config.constraint_codes,
    )


def _evaluate_and_route(
    state: SessionState, config: ConversationConfig, evaluate: PolicyEvaluator
) -> Transition:
    try:
        outcome = evaluate(state.clinical)
    except Exception:  # noqa: BLE001 - any evaluator failure must fail closed
        return _accept(*_human_review(state, "POLICY_EVALUATION_ERROR"))
    evaluation = outcome.evaluation
    state = state.model_copy(
        update={
            "clinical": state.clinical.model_copy(
                update={"important_missing_fact_ids": evaluation.next_required_fact_ids}
            )
        }
    )

    if evaluation.disposition is Disposition.EMERGENCY:
        return _escalate(state, outcome, config)
    if state.phase in PRE_CONSENT_PHASES:
        return _accept(state, (), outcome)
    if state.disposition is Disposition.HUMAN_REVIEW:
        return _accept(state, (), outcome)
    if evaluation.disposition is Disposition.HUMAN_REVIEW:
        return _accept(*_human_review(state, "POLICY_REQUIRES_HUMAN_REVIEW"), outcome)

    if evaluation.disposition is None:
        return _ask_or_review(
            state, evaluation.next_required_fact_ids, evaluation.fail_closed_reason, config, outcome
        )

    unconfirmed = [
        fact.fact_id
        for fact in state.clinical.facts
        if not fact.confirmed and fact.fact_id in evaluation.considered_fact_ids
    ]
    if unconfirmed:
        return _clarify_or_review(state, unconfirmed[0], config, outcome)

    if state.phase in SCHEDULING_PHASES and state.disposition is evaluation.disposition:
        return _accept(state, (), outcome)
    routed = state.model_copy(
        update={
            "phase": SessionPhase.SLOT_SEARCH,
            "disposition": evaluation.disposition,
            "offered_slot_id": None,
        }
    )
    return _accept(routed, (_search_command(evaluation.disposition, config),), outcome)


def _ask_or_review(
    state: SessionState,
    missing: tuple[str, ...],
    fail_closed_reason: str | None,
    config: ConversationConfig,
    outcome: PolicyOutcome,
) -> Transition:
    if not missing:
        return _accept(*_human_review(state, fail_closed_reason or "POLICY_FAIL_CLOSED"), outcome)
    asked = set(state.conversation.asked_question_ids)
    for fact_id in missing:
        question = config.question_for(fact_id, QuestionKind.PRIMARY)
        if question is None:
            return _accept(*_human_review(state, "NO_QUESTION_FOR_REQUIRED_FACT"), outcome)
        if question.question_id == state.conversation.last_question_id:
            waiting = state.model_copy(update={"phase": SessionPhase.COLLECT_FACT})
            return _accept(waiting, (), outcome)
        if question.question_id in asked:
            return _accept(*_human_review(state, "CRITICAL_FACT_UNRESOLVED"), outcome)
        collecting = _mark_asked(state, question.question_id).model_copy(
            update={"phase": SessionPhase.COLLECT_FACT}
        )
        return _accept(collecting, (AskQuestion(question_id=question.question_id),), outcome)
    return _accept(*_human_review(state, "POLICY_FAIL_CLOSED"), outcome)  # pragma: no cover


def _clarify_or_review(
    state: SessionState, fact_id: str, config: ConversationConfig, outcome: PolicyOutcome
) -> Transition:
    question = config.question_for(fact_id, QuestionKind.CLARIFICATION)
    if question is not None and question.question_id == state.conversation.last_question_id:
        waiting = state.model_copy(
            update={
                "phase": SessionPhase.COLLECT_FACT,
                "disposition": None,
                "offered_slot_id": None,
            }
        )
        return _accept(waiting, (), outcome)
    if question is None or question.question_id in state.conversation.asked_question_ids:
        return _accept(*_human_review(state, "UNCONFIRMED_CRITICAL_FACT"), outcome)
    clarifying = _mark_asked(state, question.question_id)
    clarifying = clarifying.model_copy(
        update={
            "phase": SessionPhase.COLLECT_FACT,
            "disposition": None,
            "offered_slot_id": None,
            "conversation": clarifying.conversation.model_copy(
                update={"pending_clarification_fact_id": fact_id}
            ),
        }
    )
    return _accept(clarifying, (AskQuestion(question_id=question.question_id),), outcome)
