"""Behavioral tests for the call orchestrator against synthetic fixtures only."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from orchestration_harness import (
    PATIENT_A,
    PATIENT_B,
    PATIENT_C,
    PATIENT_F,
    Harness,
    Result,
    Stepper,
    build,
    consent,
    identity,
    leaves,
    offer,
    reason,
    red_flags,
    severity,
    telemetry_json,
    temperature,
    temperature_confirm,
)

from clinical_triage.adapters.voice_mock import MockEvent, MockScriptError
from clinical_triage.audit import JsonlAuditSink
from clinical_triage.domain.audit import OperationOutcome
from clinical_triage.domain.conversation import SessionPhase
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.ehr import PatientCandidate, PatientQuery
from clinical_triage.domain.facts import ClinicalFact, FactSource
from clinical_triage.fixtures import FIXTURE_CLOCK, FixedClock, SyntheticEHR, build_fixtures
from clinical_triage.orchestration import OrchestratorConfig
from clinical_triage.orchestration.example import (
    EMERGENCY_SCRIPT_ID,
    EMERGENCY_TARGET,
    HUMAN_REVIEW_TARGET,
    example_orchestrator_config,
)

ROUTINE_A = (*consent(), *red_flags(), *reason("FOLLOW_UP"), *PATIENT_A)
MILD_B = (*consent(), *red_flags(), *reason("SYMPTOM"), *severity("MILD"), *temperature("38.2"))
SEVERE_C = (*consent(), *red_flags(), *reason("SYMPTOM"), *severity("SEVERE"), *PATIENT_C)
CHEST_PAIN = ClinicalFact(
    fact_id="red_flag.chest_pain_now", value=True, source=FactSource.CALLER, confirmed=True
)


def phase(result: Result) -> SessionPhase:
    return result.ctx.state.phase


def disposition(result: Result) -> Disposition | None:
    return result.audit.disposition


def human_decisions(result: Result) -> tuple[str, ...]:
    return result.audit.human_decision_codes


def triggered(result: Result) -> set[str]:
    return {t.rule_id for t in result.audit.rule_evaluations if t.triggered}


def at_offer(harness: Harness, *, call_id: str = "call-1") -> Stepper:
    step = harness.stepper(call_id)
    step.answer("q.consent", {"consent.continue": "YES"})
    for task_id, key in (
        ("q.red_flag.chest_pain", "red_flag.chest_pain_now"),
        ("q.red_flag.breathing", "red_flag.trouble_breathing_now"),
        ("q.red_flag.neuro", "red_flag.new_confusion_or_one_sided_weakness"),
        ("q.red_flag.bleeding", "red_flag.heavy_bleeding_now"),
    ):
        step.answer(task_id, {key: "NO"})
    step.answer("q.call.reason", {"call.reason": "FOLLOW_UP"})
    step.answer(
        "identity",
        {
            "identity.given_name": "Avery",
            "identity.family_name": "Synthetic",
            "identity.birth_date": "1980-01-02",
        },
    )
    assert step.port.active_task is not None and step.port.active_task.task_id == "offer"
    return step


# --- configuration -----------------------------------------------------------------


def test_example_config_marks_every_script_unreviewed() -> None:
    config = example_orchestrator_config()
    texts = [
        *config.scripts.values(),
        config.consent_boundary_script,
        config.question_deflection,
        config.human_review_callback_script,
        config.offer_prompt_template,
        config.agent.purpose,
    ]
    assert all("EXAMPLE_UNREVIEWED" in text for text in texts)
    assert config.allow_booking_writes is False and config.allow_record_writes is False
    assert all(q.field.question for q in config.questions)


def test_config_rejects_reused_field_keys() -> None:
    config = example_orchestrator_config()
    clashing = config.questions[-1]
    duplicate = type(clashing)(
        clashing.question_id,
        clashing.fact_id,
        config.questions[-2].field,
        clashing.parse,
        clashing.unit_code,
    )
    with pytest.raises(ValueError, match="field keys must be unique"):
        OrchestratorConfig(
            **{
                **config.__dict__,
                "questions": (*config.questions[:-1], duplicate),
            }
        )


# --- adaptive questioning ------------------------------------------------------


def test_follow_up_skips_symptom_questions_and_red_flags_come_first() -> None:
    result = build(allow_booking_writes=True).run((*ROUTINE_A, *offer("YES")))
    asked = result.audit.question_ids_asked
    assert asked == (
        "q.consent",
        "q.red_flag.chest_pain",
        "q.red_flag.breathing",
        "q.red_flag.neuro",
        "q.red_flag.bleeding",
        "q.call.reason",
    )
    assert disposition(result) is Disposition.ROUTINE


def test_mild_symptom_adds_temperature_but_severe_does_not() -> None:
    mild = build().run((*MILD_B, *PATIENT_B, *offer("NO")))
    severe = build().run((*SEVERE_C, *offer("NO")))
    assert "q.symptom.temperature" in mild.audit.question_ids_asked
    assert "q.symptom.temperature" not in severe.audit.question_ids_asked
    assert disposition(mild) is Disposition.ROUTINE
    assert disposition(severe) is Disposition.URGENT_SAME_DAY


def test_implausible_number_is_clarified_once_and_the_correction_reroutes() -> None:
    script = (
        *consent(),
        *red_flags(),
        *reason("SYMPTOM"),
        *severity("MILD"),
        *temperature("103"),
        *temperature_confirm("38.1"),
        *PATIENT_B,
        *offer("NO"),
    )
    result = build().run(script)
    assert result.audit.question_ids_asked[-2:] == (
        "q.symptom.temperature",
        "q.symptom.temperature.confirm",
    )
    fact = next(
        f for f in result.decision.facts_recorded if f.fact_id == "symptom.measured_temperature"
    )
    assert fact.value == 38.1 and fact.confirmed is True
    assert disposition(result) is Disposition.ROUTINE


def test_implausible_number_twice_goes_to_human_review() -> None:
    script = (
        *consent(),
        *red_flags(),
        *reason("SYMPTOM"),
        *severity("MILD"),
        *temperature("103"),
        *temperature_confirm("104"),
    )
    result = build(allow_booking_writes=True).run(script)
    assert disposition(result) is Disposition.HUMAN_REVIEW
    assert "HUMAN_REVIEW:UNCONFIRMED_CRITICAL_FACT" in human_decisions(result)
    assert "CREATE_APPOINTMENT" not in result.harness.ehr.calls


def test_unparseable_answer_is_not_asked_again_and_routes_to_human_review() -> None:
    script = (*consent(), *red_flags(), *reason("SYMPTOM"), *severity("MILD"), *temperature("?"))
    result = build(allow_booking_writes=True).run(script)
    assert result.audit.question_ids_asked.count("q.symptom.temperature") == 1
    assert "UNPARSEABLE_ANSWER:q.symptom.temperature" in result.audit.error_codes
    assert "HUMAN_REVIEW:CRITICAL_FACT_UNRESOLVED" in human_decisions(result)
    assert result.harness.ehr.calls == []


# --- emergency ---------------------------------------------------------------------


def test_emergency_escalates_without_any_ehr_or_booking_call() -> None:
    harness = build(allow_booking_writes=True, allow_record_writes=True)
    result = harness.run((*consent(), *red_flags(breathing="YES")))
    assert harness.ehr.calls == []
    assert phase(result) is SessionPhase.ESCALATE
    assert disposition(result) is Disposition.EMERGENCY
    assert triggered(result) == {"EX-EMERG-002"}
    assert result.port.transfers == [EMERGENCY_TARGET]
    assert "q.call.reason" not in result.audit.question_ids_asked
    codes = [e.event_code for e in harness.audit.operational_events]
    assert "SAFETY.EMERGENCY_RULE:EX-EMERG-002" in codes
    assert not any(o.target_system == "ehr" for o in result.audit.operations)


def test_red_flag_correction_mid_offer_interrupts_scheduling() -> None:
    harness = build(allow_booking_writes=True, allow_record_writes=True)
    step = at_offer(harness)
    calls_before = list(harness.ehr.calls)
    assert step.ctx.state.offered_slot_id is not None

    transition = harness.orchestrator.submit_correction("call-1", CHEST_PAIN)

    assert transition is not None and transition.accepted
    assert step.ctx.state.phase is SessionPhase.ESCALATE
    assert step.ctx.state.offered_slot_id is None and step.ctx.offer is None
    assert step.port.transfers == [EMERGENCY_TARGET]
    # A late confirmation of the withdrawn offer must not book anything.
    step.handlers.on_task_complete["offer"](step.port)
    result = step.end()
    assert harness.ehr.calls == calls_before
    assert "CREATE_APPOINTMENT" not in harness.ehr.calls
    assert disposition(result) is Disposition.EMERGENCY
    assert "STALE_OFFER_TASK:offer" in result.audit.error_codes
    assert result.operations("EHR.RECORD_CALL_SUMMARY") == [OperationOutcome.SKIPPED]


def test_failed_emergency_transfer_hangs_up_with_the_emergency_script() -> None:
    harness = build(transfer_outcomes={EMERGENCY_TARGET.target_id: "TARGET_BUSY"})
    result = harness.run((*consent(), *red_flags(chest="YES")))
    script = example_orchestrator_config().scripts[EMERGENCY_SCRIPT_ID]
    assert result.port.hangups == [script]
    assert result.operations("VOICE.TRANSFER") == [OperationOutcome.FAILED]
    assert result.operations("VOICE.TRANSFER_COMPLETED") == []


def test_declined_consent_goes_to_human_review() -> None:
    result = build().run((*consent("NO"),))
    assert disposition(result) is Disposition.HUMAN_REVIEW
    assert "HUMAN_REVIEW:CONSENT_NOT_GIVEN" in human_decisions(result)
    assert result.port.transfers == [HUMAN_REVIEW_TARGET]


# --- booking gates -------------------------------------------------------------------


def test_booking_is_disabled_by_default_even_after_caller_yes() -> None:
    result = build().run((*ROUTINE_A, *offer("YES")))
    assert "CREATE_APPOINTMENT" not in result.harness.ehr.calls
    assert result.operations("EHR.CREATE_APPOINTMENT") == [OperationOutcome.SKIPPED]
    assert "HUMAN_REVIEW:BOOKING_REQUIRES_STAFF_APPROVAL" in human_decisions(result)
    assert disposition(result) is Disposition.ROUTINE


def test_caller_no_never_books() -> None:
    result = build(allow_booking_writes=True).run((*ROUTINE_A, *offer("NO")))
    assert "CREATE_APPOINTMENT" not in result.harness.ehr.calls
    assert "CALLER_DECLINED_OFFER" in human_decisions(result)


def test_caller_yes_with_writes_enabled_books_once_and_closes() -> None:
    harness = build(allow_booking_writes=True)
    result = harness.run((*ROUTINE_A, *offer("YES")))
    assert harness.ehr.calls.count("CREATE_APPOINTMENT") == 1
    assert harness.ehr.booked_slot_ids == {"SLOT-SYN-OPEN-1": "SYN-PAT-A"}
    assert result.ctx.appointment_id is not None
    assert phase(result) is SessionPhase.CLOSE
    assert result.port.hangups and "EXAMPLE_UNREVIEWED" in result.port.hangups[0]
    assert result.operations("EHR.CREATE_APPOINTMENT") == [OperationOutcome.COMPLETED]
    assert result.audit.synthetic_patient_id == "SYN-PAT-A"


def test_retry_offer_needs_a_fresh_yes_then_second_failure_goes_to_human_review() -> None:
    harness = build(
        allow_booking_writes=True, slots_taken_after_snapshot=frozenset({"SLOT-SYN-OPEN-1"})
    )
    with pytest.raises(MockScriptError, match="required fields not supplied"):
        harness.run((*ROUTINE_A, *offer("YES"), MockEvent.complete("offer_retry")), "stale")

    harness = build(
        allow_booking_writes=True, slots_taken_after_snapshot=frozenset({"SLOT-SYN-OPEN-1"})
    )
    result = harness.run((*ROUTINE_A, *offer("YES"), *offer("YES", "offer_retry")))
    assert harness.ehr.calls.count("CREATE_APPOINTMENT") == 2
    assert result.task_ids()[-2:] == ["offer", "offer_retry"]
    assert result.operations("EHR.CREATE_APPOINTMENT") == [OperationOutcome.FAILED] * 2
    assert "HUMAN_REVIEW:SLOT_NO_LONGER_AVAILABLE" in human_decisions(result)
    assert harness.ehr.booked_slot_ids == {}


def test_squeeze_offers_an_alternative_and_surfaces_overbook_review() -> None:
    booked = {"SLOT-SYN-SAME-DAY-1": "SYN-PAT-X", "SLOT-SYN-CANCEL-1": "SYN-PAT-X"}
    result = build(booked_slot_ids=booked).run((*SEVERE_C, *offer("NO")))
    offered = result.port.tasks[-1]
    assert offered.task_id == "offer" and "ALTERNATIVE_PROVIDER" in offered.objective
    assert "OVERBOOK_REVIEW_SUGGESTED:NO_NORMAL_SLOT_FOR_CONFIGURED_WINDOW" in human_decisions(
        result
    )


def test_no_slot_at_all_requests_overbook_review_from_staff_without_booking() -> None:
    booked = {
        slot: "SYN-PAT-X"
        for slot in (
            "SLOT-SYN-SAME-DAY-1",
            "SLOT-SYN-CANCEL-1",
            "SLOT-SYN-ALT-1",
            "SLOT-SYN-TELE-1",
        )
    }
    harness = build(allow_booking_writes=True, booked_slot_ids=booked)
    result = harness.run(SEVERE_C)
    assert "HUMAN_REVIEW:OVERBOOK_REVIEW_REQUESTED" in human_decisions(result)
    assert "CREATE_APPOINTMENT" not in harness.ehr.calls
    assert disposition(result) is Disposition.URGENT_SAME_DAY


# --- identity ------------------------------------------------------------------------


def test_same_name_wrong_birth_date_goes_to_human_review() -> None:
    harness = build(allow_booking_writes=True)
    script = (
        *consent(),
        *red_flags(),
        *reason("FOLLOW_UP"),
        *identity("Avery", "Synthetic", "1990-01-01"),
    )
    result = harness.run(script)
    assert disposition(result) is Disposition.HUMAN_REVIEW
    assert "IDENTITY_NO_MATCH" in result.audit.error_codes
    assert "HUMAN_REVIEW:IDENTITY_UNVERIFIED" in human_decisions(result)
    assert result.audit.synthetic_patient_id is None
    assert "CREATE_APPOINTMENT" not in harness.ehr.calls


def test_name_without_birth_date_never_searches() -> None:
    harness = build(allow_booking_writes=True)
    script = (
        *consent(),
        *red_flags(),
        *reason("FOLLOW_UP"),
        *identity("Avery", "Synthetic", "unsure"),
    )
    result = harness.run(script)
    assert "FIND_PATIENT" not in harness.ehr.calls
    assert "IDENTITY_INCOMPLETE" in result.audit.error_codes
    assert disposition(result) is Disposition.HUMAN_REVIEW


class NameOnlyEHR(SyntheticEHR):
    """An EHR whose search ignores birth date, so A and G collide."""

    def find_patient(self, query: PatientQuery) -> tuple[PatientCandidate, ...]:
        return super().find_patient(
            PatientQuery(given_name=query.given_name, family_name=query.family_name)
        )


def test_ambiguous_candidates_a_and_g_go_to_human_review() -> None:
    clock = FixedClock(FIXTURE_CLOCK)
    harness = build(allow_booking_writes=True, ehr=NameOnlyEHR(build_fixtures(), clock))
    result = harness.run((*ROUTINE_A,))
    assert "IDENTITY_NOT_UNIQUE" in result.audit.error_codes
    assert "VERIFY_PATIENT" not in harness.ehr.calls
    assert disposition(result) is Disposition.HUMAN_REVIEW


# --- transfers -----------------------------------------------------------------------


def test_accepted_transfer_is_attempted_until_session_end_reports_bot_transfer() -> None:
    harness = build()
    step = harness.stepper()
    step.answer("q.consent", {"consent.continue": "NO"})
    assert [o.outcome for o in step.ctx.operations] == [OperationOutcome.ATTEMPTED]
    result = step.end()
    assert result.operations("VOICE.TRANSFER") == [OperationOutcome.ATTEMPTED]
    assert result.operations("VOICE.TRANSFER_COMPLETED") == [OperationOutcome.COMPLETED]


def test_accepted_transfer_without_bot_transfer_end_is_recorded_failed() -> None:
    harness = build()
    step = harness.stepper()
    step.answer("q.consent", {"consent.continue": "NO"})
    result = step.end("user-hangup")
    assert result.operations("VOICE.TRANSFER_COMPLETED") == [OperationOutcome.FAILED]
    completed = [
        o for o in result.audit.operations if o.operation_type == "VOICE.TRANSFER_COMPLETED"
    ]
    assert completed[0].error_code == "TRANSFER_NOT_OBSERVED"


def test_rejected_human_review_transfer_hangs_up_with_callback_script() -> None:
    harness = build(transfer_outcomes={})
    result = harness.run((*consent("NO"),))
    assert result.port.hangups == [example_orchestrator_config().human_review_callback_script]
    assert result.operations("VOICE.TRANSFER") == [OperationOutcome.FAILED]


# --- EHR failure ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "expected_decision"),
    [
        ("FIND_PATIENT", "HUMAN_REVIEW:IDENTITY_UNVERIFIED"),
        ("VERIFY_PATIENT", "HUMAN_REVIEW:IDENTITY_UNVERIFIED"),
        ("GET_AVAILABLE_APPOINTMENTS", "HUMAN_REVIEW:AVAILABILITY_UNAVAILABLE"),
        ("CREATE_APPOINTMENT", "HUMAN_REVIEW:FAULT_INJECTED"),
    ],
)
def test_ehr_unavailability_fails_closed(operation: str, expected_decision: str) -> None:
    harness = build(allow_booking_writes=True, unavailable_operations=frozenset({operation}))
    result = harness.run((*ROUTINE_A, *offer("YES")))
    assert expected_decision in human_decisions(result)
    assert harness.ehr.booked_slot_ids == {}
    assert OperationOutcome.FAILED in result.operations(f"EHR.{operation}")
    assert not [c for c in result.audit.error_codes if c.startswith("UNHANDLED")]


class ExplodingEHR(SyntheticEHR):
    def get_available_appointments(self, **kwargs: object) -> object:  # type: ignore[override]
        raise RuntimeError("synthetic failure mentioning Avery Synthetic 1980-01-02")


def test_unexpected_adapter_exception_is_recorded_by_class_name_only() -> None:
    clock = FixedClock(FIXTURE_CLOCK)
    harness = build(ehr=ExplodingEHR(build_fixtures(), clock))
    result = harness.run(ROUTINE_A)
    failed = [
        o for o in result.audit.operations if o.operation_type == "EHR.GET_AVAILABLE_APPOINTMENTS"
    ]
    assert [o.error_code for o in failed] == ["RuntimeError"]
    assert "HUMAN_REVIEW:AVAILABILITY_UNAVAILABLE" in human_decisions(result)
    assert "Avery" not in json.dumps(telemetry_json(harness.audit))


def test_record_writes_happen_only_when_enabled_and_identified() -> None:
    off = build(allow_booking_writes=True).run((*ROUTINE_A, *offer("YES")))
    on = build(allow_booking_writes=True, allow_record_writes=True).run((*ROUTINE_A, *offer("YES")))
    assert "RECORD_TRIAGE_RESULT" not in off.harness.ehr.calls
    assert on.harness.ehr.calls[-2:] == ["RECORD_CALL_SUMMARY", "RECORD_TRIAGE_RESULT"]
    assert on.operations("EHR.RECORD_TRIAGE_RESULT") == [OperationOutcome.COMPLETED]


# --- privacy -------------------------------------------------------------------------


def test_question_text_is_never_stored() -> None:
    secret = "SYNTHETIC-QUESTION-TEXT-7f3a is this serious"
    harness = build()
    script = (*consent(), MockEvent.question(secret), *red_flags(chest="YES"))
    result = harness.run(script)
    assert result.port.answers == [example_orchestrator_config().question_deflection]
    everything = json.dumps(telemetry_json(harness.audit)) + json.dumps(
        [json.loads(r.model_dump_json()) for r in harness.audit.decision_records]
    )
    assert "7f3a" not in everything
    assert "CALL.QUESTION_DEFLECTED" in everything


def test_telemetry_has_no_fact_values_or_identity_while_decision_record_keeps_facts() -> None:
    harness = build(allow_booking_writes=True)
    result = harness.run((*MILD_B, *PATIENT_B, *offer("YES")))
    assert result.ctx.appointment_id is not None
    telemetry = telemetry_json(harness.audit)
    strings = [v for _, v in leaves(telemetry) if isinstance(v, str)]
    numbers = [v for _, v in leaves(telemetry) if isinstance(v, float)]
    forbidden = ["Blake", "Synthetic", "1975-03-04", "555-0102", "SYMPTOM", "MILD"]
    assert not [s for s in strings for f in forbidden if f in s]
    assert 38.2 not in numbers
    assert not any(key in {"value", "facts_recorded"} for key, _ in leaves(telemetry))
    decision_values = {f.fact_id: f.value for f in result.decision.facts_recorded}
    assert decision_values["call.reason"] == "SYMPTOM"
    assert decision_values["symptom.measured_temperature"] == 38.2
    assert result.audit.fact_ids_recorded == tuple(sorted(decision_values))


def test_jsonl_sink_keeps_protected_records_in_a_separate_file(tmp_path: Path) -> None:
    sink = JsonlAuditSink(
        operational_path=tmp_path / "ops.jsonl", protected_path=tmp_path / "protected.jsonl"
    )
    harness = build(allow_booking_writes=True)
    harness.run((*MILD_B, *PATIENT_B, *offer("YES")))
    for record in harness.audit.audit_records:
        sink.append_audit_record(record)
    for event in harness.audit.operational_events:
        sink.emit_operational_event(event)
    for decision in harness.audit.decision_records:
        sink.append_decision_record(decision)
    ops = (tmp_path / "ops.jsonl").read_text(encoding="utf-8")
    protected = (tmp_path / "protected.jsonl").read_text(encoding="utf-8")
    assert '"SYMPTOM"' in protected and '"SYMPTOM"' not in ops
    assert {json.loads(line)["type"] for line in ops.splitlines()} == {"audit", "event"}
    with pytest.raises(ValueError, match="separate destination"):
        JsonlAuditSink(operational_path=tmp_path / "x", protected_path=tmp_path / "x")


def test_audit_timestamps_follow_the_injected_clock() -> None:
    result = build().run((*consent(), *red_flags(chest="YES")))
    assert result.audit.started_at == datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    assert result.audit.ended_at == result.audit.started_at


def test_scheduling_failure_scenario_patient_f() -> None:
    harness = build(
        allow_booking_writes=True, slots_taken_after_snapshot=frozenset({"SLOT-SYN-SAME-DAY-1"})
    )
    script = (
        *consent(),
        *red_flags(),
        *reason("SYMPTOM"),
        *severity("SEVERE"),
        *PATIENT_F,
        *offer("YES"),
        *offer("YES", "offer_retry"),
    )
    result = harness.run(script)
    assert result.operations("EHR.CREATE_APPOINTMENT") == [OperationOutcome.FAILED] * 2
    assert "HUMAN_REVIEW:SLOT_NO_LONGER_AVAILABLE" in human_decisions(result)
    assert disposition(result) is Disposition.URGENT_SAME_DAY
