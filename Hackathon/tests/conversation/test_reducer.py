import pytest
from conversation_harness import CONFIG, FakePolicy, Session, fact

from clinical_triage.conversation import (
    begin_booking_commit,
    booking_completed,
    offer_slot,
    reduce,
    scheduling_failed,
)
from clinical_triage.domain.conversation import (
    AnswerRecorded,
    AppointmentConfirmed,
    AskQuestion,
    CloseCall,
    Escalate,
    HumanReviewRequested,
    RequestHumanReview,
    SearchAppointments,
    SessionEndedEvent,
    SessionPhase,
    TaskCompleted,
)
from clinical_triage.domain.disposition import Disposition


def phase(session: Session) -> SessionPhase:
    return session.state.phase


def disposition(session: Session) -> Disposition | None:
    return session.state.disposition


def kinds(session: Session) -> list[str]:
    return [c.kind for c in session.transitions[-1].commands]


# --- lifecycle and adaptive questioning --------------------------------------


def test_start_asks_consent_and_consent_asks_first_missing_fact() -> None:
    session = Session()
    started = session.start()
    assert started.commands == (AskQuestion(question_id="q.consent"),)
    assert phase(session) is SessionPhase.BOUNDARY_AND_CONSENT
    consented = session.consent()
    assert consented.commands == (AskQuestion(question_id="q.a"),)
    assert phase(session) is SessionPhase.COLLECT_FACT
    assert session.state.version == 2
    assert session.state.clinical.important_missing_fact_ids == ("fact.a", "fact.b")


def test_routine_path_routes_to_search_with_configured_window() -> None:
    session = Session().ready()
    assert session.answer("fact.a", "routine").commands == (AskQuestion(question_id="q.b"),)
    assert session.answer("fact.b", "x").commands == (
        SearchAppointments(scheduling_window="WINDOW_ROUTINE"),
    )
    assert session.state.phase is SessionPhase.SLOT_SEARCH
    assert session.state.disposition is Disposition.ROUTINE


def test_questions_adapt_to_which_facts_are_already_known() -> None:
    session = Session().ready()
    session.answer("fact.b", "volunteered-early")
    assert session.state.conversation.asked_question_ids == ("q.consent", "q.a")
    assert session.answer("fact.a", "urgent").commands == (
        SearchAppointments(scheduling_window="WINDOW_SAME_DAY"),
    )
    assert "q.b" not in session.state.conversation.asked_question_ids


def test_outstanding_question_waits_instead_of_repeating_or_escalating() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    assert session.state.conversation.last_question_id == "q.b"
    assert session.answer("fact.unrelated", "noise").commands == ()
    assert session.state.phase is SessionPhase.COLLECT_FACT


def test_question_closed_without_answer_goes_to_review_and_is_never_repeated() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.unrelated", "noise")
    transition = session.complete("q.b")
    assert transition.commands == (RequestHumanReview(reason_code="CRITICAL_FACT_UNRESOLVED"),)
    assert session.state.disposition is Disposition.HUMAN_REVIEW
    asked = session.state.conversation.asked_question_ids
    assert asked.count("q.b") == 1 and len(asked) == len(set(asked))
    assert session.state.conversation.do_not_repeat_question_ids == asked


def test_completing_an_unrelated_task_is_a_no_op() -> None:
    session = Session().ready()
    version = session.state.version
    assert session.complete("some-other-task").commands == ()
    assert session.state.version == version + 1
    assert session.state.conversation.last_question_id == "q.a"


def test_required_fact_without_a_question_goes_to_review() -> None:
    session = Session(FakePolicy(required=("fact.unaskable",))).ready()
    assert session.transitions[-1].commands == (
        RequestHumanReview(reason_code="NO_QUESTION_FOR_REQUIRED_FACT"),
    )


def test_policy_fail_closed_without_missing_facts_goes_to_review() -> None:
    session = Session().ready()
    session.answer("fact.b", "x")
    assert session.answer("fact.a", "conflict").commands == (
        RequestHumanReview(reason_code="CONFLICTING_RULES"),
    )


def test_every_new_fact_reevaluates_policy() -> None:
    session = Session().ready()
    before = len(session.policy.calls)
    session.answer("fact.a", "routine")
    session.correct("fact.a", "urgent")
    assert len(session.policy.calls) == before + 2


# --- stale and invalid events --------------------------------------------------


def test_stale_version_is_rejected_without_effect() -> None:
    session = Session().ready()
    state = session.state
    stale = AnswerRecorded(
        event_id="late",
        call_id="call-1",
        expected_state_version=state.version - 1,
        fact=fact("fact.a", "routine"),
    )
    transition = reduce(state, stale, config=CONFIG, evaluate=session.policy)
    assert transition.rejected_reason == "STALE_EVENT"
    assert transition.state is state and transition.commands == ()


def test_cross_call_event_is_rejected() -> None:
    session = Session().ready()
    foreign = TaskCompleted(
        event_id="x", call_id="call-2", expected_state_version=session.state.version, task_id="t"
    )
    assert session.apply(foreign).rejected_reason == "CALL_ID_MISMATCH"


def test_duplicate_answer_requires_correction() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    version = session.state.version
    assert (
        session.answer("fact.a", "urgent").rejected_reason == "FACT_ALREADY_RECORDED_USE_CORRECTION"
    )
    assert session.state.version == version


def test_correcting_unknown_fact_is_rejected() -> None:
    assert Session().ready().correct("fact.a", "x").rejected_reason == "NO_FACT_TO_CORRECT"


def test_events_after_terminal_are_rejected() -> None:
    session = Session().ready()
    session.answer("fact.flag", True)
    assert session.state.terminal
    assert session.answer("fact.a", "routine").rejected_reason == "SESSION_TERMINAL"


def test_second_call_start_is_rejected() -> None:
    session = Session()
    session.start()
    assert session.start().rejected_reason == "CALL_ALREADY_STARTED"


# --- corrections ----------------------------------------------------------------


def test_correction_during_search_reroutes_to_new_window() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    transition = session.correct("fact.a", "urgent")
    assert transition.commands == (SearchAppointments(scheduling_window="WINDOW_SAME_DAY"),)
    assert session.state.disposition is Disposition.URGENT_SAME_DAY
    assert session.state.clinical.fact("fact.a") == fact("fact.a", "urgent")


def test_correction_with_same_route_does_not_restart_search() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    assert session.correct("fact.b", "y").commands == ()
    assert session.state.phase is SessionPhase.SLOT_SEARCH


def test_unconfirmed_fact_gets_one_clarification() -> None:
    session = Session().ready()
    session.answer("fact.b", "x")
    assert session.answer("fact.a", "routine", confirmed=False).commands == (
        AskQuestion(question_id="q.a.clarify"),
    )
    assert session.state.conversation.pending_clarification_fact_id == "fact.a"
    assert session.correct("fact.a", "routine", confirmed=True).commands == (
        SearchAppointments(scheduling_window="WINDOW_ROUTINE"),
    )
    assert session.state.conversation.pending_clarification_fact_id is None


def test_still_unconfirmed_after_clarification_goes_to_review() -> None:
    session = Session().ready()
    session.answer("fact.b", "x")
    session.answer("fact.a", "routine", confirmed=False)
    assert session.correct("fact.a", "routine", confirmed=False).commands == (
        RequestHumanReview(reason_code="UNCONFIRMED_CRITICAL_FACT"),
    )


# --- emergency, human review, fail closed -------------------------------------------


def test_emergency_escalates_before_consent() -> None:
    session = Session()
    session.start()
    transition = session.answer("fact.flag", True)
    assert transition.commands == (
        Escalate(script_id="SCRIPT_TEST_EMERGENCY", trigger_rule_ids=("TEST-EMERGENCY",)),
    )
    assert session.state.phase is SessionPhase.ESCALATE and session.state.terminal
    assert session.state.clinical.possible_red_flag_ids == ("TEST-EMERGENCY",)


def test_emergency_correction_interrupts_an_offer() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    session.answer("fact.flag", False)
    offered = offer_slot(session.state, slot_id="SLOT-1", expected_version=session.state.version)
    session.state = offered.state
    transition = session.correct("fact.flag", True)
    assert [c.kind for c in transition.commands] == ["ESCALATE"]
    assert session.state.offered_slot_id is None
    assert session.state.disposition is Disposition.EMERGENCY


def test_human_review_is_sticky_but_can_still_escalate() -> None:
    session = Session().ready()
    session.answer("fact.b", "x")
    session.answer("fact.a", "review")
    assert session.state.disposition is Disposition.HUMAN_REVIEW
    assert session.correct("fact.a", "routine").commands == ()
    assert session.state.disposition is Disposition.HUMAN_REVIEW
    assert session.state.phase is SessionPhase.DISPOSITION
    assert kinds(session) == []
    session.answer("fact.flag", True)
    assert disposition(session) is Disposition.EMERGENCY


def test_evaluator_error_fails_closed() -> None:
    session = Session(FakePolicy(raise_error=True)).ready()
    assert session.transitions[-1].commands == (
        RequestHumanReview(reason_code="POLICY_EVALUATION_ERROR"),
    )


def test_declined_consent_goes_to_review() -> None:
    session = Session()
    session.start()
    assert session.consent("DECLINED").commands == (
        RequestHumanReview(reason_code="CONSENT_NOT_GIVEN"),
    )


def test_explicit_human_review_request_clears_offer() -> None:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    session.state = offer_slot(
        session.state, slot_id="S", expected_version=session.state.version
    ).state
    session.apply(
        HumanReviewRequested(
            event_id="h",
            call_id="call-1",
            expected_state_version=session.state.version,
            reason_code="CALLER_ASKED",
        )
    )
    assert session.state.offered_slot_id is None
    assert session.state.disposition is Disposition.HUMAN_REVIEW


# --- scheduling sub-flow -------------------------------------------------------------


def searching() -> Session:
    session = Session().ready()
    session.answer("fact.a", "routine")
    session.answer("fact.b", "x")
    return session


def test_booking_requires_offer_then_explicit_confirmation_then_commit() -> None:
    session = searching()
    confirm = AppointmentConfirmed(
        event_id="c",
        call_id="call-1",
        expected_state_version=session.state.version,
        confirmation_id="k",
    )
    assert session.apply(confirm).rejected_reason == "NO_OFFER_TO_CONFIRM"
    assert (
        begin_booking_commit(session.state, expected_version=session.state.version).rejected_reason
        == "CONFIRMATION_REQUIRED"
    )
    session.state = offer_slot(
        session.state, slot_id="S", expected_version=session.state.version
    ).state
    session.apply(confirm.model_copy(update={"expected_state_version": session.state.version}))
    assert session.state.phase is SessionPhase.EXPLICIT_CONFIRMATION
    session.state = begin_booking_commit(
        session.state, expected_version=session.state.version
    ).state
    done = booking_completed(session.state, expected_version=session.state.version, config=CONFIG)
    assert done.commands == (CloseCall(script_id="CLOSE_BOOKED"),)
    assert done.state.phase is SessionPhase.CLOSE and done.state.terminal


def test_scheduling_failure_retries_then_hands_to_human_without_downgrade() -> None:
    session = searching()
    session.state = offer_slot(
        session.state, slot_id="S", expected_version=session.state.version
    ).state
    retried = scheduling_failed(
        session.state,
        expected_version=session.state.version,
        reason_code="STALE",
        retry=True,
        config=CONFIG,
    )
    assert retried.commands == (SearchAppointments(scheduling_window="WINDOW_ROUTINE"),)
    assert retried.state.offered_slot_id is None
    failed = scheduling_failed(
        retried.state,
        expected_version=retried.state.version,
        reason_code="STALE",
        retry=False,
        config=CONFIG,
    )
    assert failed.commands == (RequestHumanReview(reason_code="STALE"),)
    assert failed.state.disposition is Disposition.ROUTINE
    assert failed.state.phase is SessionPhase.DISPOSITION


def test_subflow_transitions_reject_stale_versions() -> None:
    session = searching()
    assert (
        offer_slot(
            session.state, slot_id="S", expected_version=session.state.version - 1
        ).rejected_reason
        == "STALE_EVENT"
    )


def test_session_end_closes() -> None:
    session = searching()
    session.apply(
        SessionEndedEvent(
            event_id="end",
            call_id="call-1",
            expected_state_version=session.state.version,
            reason_code="HANGUP",
        )
    )
    assert session.state.phase is SessionPhase.CLOSE and session.state.terminal


# --- determinism ---------------------------------------------------------------------


@pytest.mark.parametrize("run", range(3))
def test_identical_event_sequences_produce_identical_state(run: int) -> None:
    def drive() -> Session:
        session = Session().ready()
        session.answer("fact.a", "routine", confirmed=False)
        session.correct("fact.a", "urgent")
        session.answer("fact.b", "x")
        return session

    first, second = drive(), drive()
    assert first.state == second.state
    assert [t.commands for t in first.transitions] == [t.commands for t in second.transitions]
