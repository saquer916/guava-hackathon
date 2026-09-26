"""End-to-end synthetic scenarios: mock voice port -> orchestrator -> policy -> scheduling
-> SyntheticEHR -> audit. Offline and deterministic; OpenEMR is not involved here."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from clinical_triage.demo import (
    SCENARIOS,
    ScenarioError,
    ScenarioRun,
    run_scenario,
    scenario,
)
from clinical_triage.demo.__main__ import main
from clinical_triage.demo.panel import summarize
from clinical_triage.domain.audit import AuditRecord, OperationOutcome
from clinical_triage.domain.conversation import SessionPhase
from clinical_triage.domain.disposition import Disposition
from clinical_triage.orchestration.example import (
    CLOSE_SCRIPT_ID,
    EMERGENCY_TARGET,
    HUMAN_REVIEW_TARGET,
    example_orchestrator_config,
)

SCREENING = [
    "q.consent",
    "q.red_flag.chest_pain",
    "q.red_flag.breathing",
    "q.red_flag.neuro",
    "q.red_flag.bleeding",
]
CLOSE_TEXT = example_orchestrator_config().scripts[CLOSE_SCRIPT_ID]
BOOKING_CALLS = [
    "FIND_PATIENT",
    "VERIFY_PATIENT",
    "GET_AVAILABLE_APPOINTMENTS",
    "CREATE_APPOINTMENT",
    "RECORD_CALL_SUMMARY",
    "RECORD_TRIAGE_RESULT",
]


def run(scenario_id: str) -> ScenarioRun:
    return run_scenario(scenario(scenario_id))


def audit_of(result: ScenarioRun) -> AuditRecord:
    (record,) = result.audit.audit_records
    return record


def tasks(result: ScenarioRun) -> list[str]:
    return [t.task_id for t in result.drive.port.tasks]


def final_phase(result: ScenarioRun) -> SessionPhase:
    return result.ctx.state.phase


def outcomes(result: ScenarioRun, operation_type: str) -> list[OperationOutcome]:
    return [o.outcome for o in audit_of(result).operations if o.operation_type == operation_type]


def booked_slot(result: ScenarioRun) -> list[str]:
    return list(result.ehr.booked_slot_ids)


def test_scenario_catalog_covers_the_required_six_plus_extras() -> None:
    ids = [s.scenario_id for s in SCENARIOS]
    assert ids[:4] == [
        "routine",
        "adaptive-clarification",
        "urgent-same-day",
        "emergency-interruption",
    ]
    assert {"human-review-fallback", "scheduling-failure"} <= set(ids)
    assert len(ids) == len(set(ids))


def test_routine_request_books_a_routine_slot() -> None:
    result = run("routine")
    assert tasks(result) == [*SCREENING, "q.call.reason", "identity", "offer"]
    assert result.drive.port.transfers == []
    assert result.drive.port.hangups == [CLOSE_TEXT]
    assert final_phase(result) is SessionPhase.CLOSE
    assert audit_of(result).disposition is Disposition.ROUTINE
    assert result.ehr.calls == BOOKING_CALLS
    assert booked_slot(result) == ["SLOT-SYN-OPEN-1"]
    assert result.ctx.triage is not None and result.ctx.triage.confidence is None
    assert result.ctx.triage.trigger_rule_ids == ("EX-ROUTINE-002",)


def test_adaptive_clarification_asks_follow_ups_only_when_needed() -> None:
    result = run("adaptive-clarification")
    assert tasks(result) == [
        *SCREENING,
        "q.call.reason",
        "q.symptom.severity",
        "q.symptom.temperature",
        "q.symptom.temperature.confirm",
        "identity",
        "offer",
    ]
    (decision,) = result.audit.decision_records
    temperature = next(
        f for f in decision.facts_recorded if f.fact_id == "symptom.measured_temperature"
    )
    assert (temperature.value, temperature.confirmed, temperature.unit_code) == (38.4, True, "Cel")
    assert audit_of(result).disposition is Disposition.ROUTINE
    assert result.ctx.triage is not None
    assert result.ctx.triage.trigger_rule_ids == ("EX-ROUTINE-001",)
    assert result.ehr.calls == BOOKING_CALLS


def test_urgent_same_day_books_the_same_day_slot_without_extra_questions() -> None:
    result = run("urgent-same-day")
    assert "q.symptom.temperature" not in tasks(result)
    assert audit_of(result).disposition is Disposition.URGENT_SAME_DAY
    assert booked_slot(result) == ["SLOT-SYN-SAME-DAY-1"]
    assert result.ehr.calls == BOOKING_CALLS
    assert result.drive.port.hangups == [CLOSE_TEXT]


def test_emergency_interrupts_an_active_offer_and_escalates() -> None:
    result = run("emergency-interruption")
    audit = audit_of(result)
    # Ordinary workflow really was in progress: an offer had been made.
    assert tasks(result)[-1] == "offer" and audit.appointment_option_ids_considered
    assert final_phase(result) is SessionPhase.ESCALATE
    assert audit.disposition is Disposition.EMERGENCY
    assert result.ctx.state.offered_slot_id is None and result.ctx.offer is None
    assert result.ctx.triage is not None
    assert result.ctx.triage.trigger_rule_ids == ("EX-EMERG-001",)
    assert result.ctx.triage.recommended_scheduling_window is None
    assert result.drive.port.transfers == [EMERGENCY_TARGET]
    assert result.ehr.calls == ["FIND_PATIENT", "VERIFY_PATIENT", "GET_AVAILABLE_APPOINTMENTS"]
    assert booked_slot(result) == []
    assert outcomes(result, "VOICE.TRANSFER") == [OperationOutcome.ATTEMPTED]
    assert outcomes(result, "VOICE.TRANSFER_COMPLETED") == [OperationOutcome.COMPLETED]
    assert outcomes(result, "EHR.RECORD_CALL_SUMMARY") == [OperationOutcome.SKIPPED]
    events = [e.event_code for e in result.audit.operational_events]
    assert "SAFETY.EMERGENCY_RULE:EX-EMERG-001" in events
    assert any(t.speaker == "Tool" for t in result.drive.transcript)


def test_emergency_during_screening_never_touches_the_ehr() -> None:
    result = run("emergency-at-screening")
    assert tasks(result) == SCREENING[:3]
    assert result.ehr.calls == []
    assert audit_of(result).disposition is Disposition.EMERGENCY
    assert result.drive.port.transfers == [EMERGENCY_TARGET]


def test_human_review_fallback_does_not_repeat_the_question() -> None:
    result = run("human-review-fallback")
    audit = audit_of(result)
    assert tasks(result).count("q.symptom.temperature") == 1
    assert audit.disposition is Disposition.HUMAN_REVIEW
    assert "HUMAN_REVIEW:CRITICAL_FACT_UNRESOLVED" in audit.human_decision_codes
    assert result.ctx.triage is not None
    assert result.ctx.triage.unanswered_critical_question_ids == ("q.symptom.temperature",)
    assert result.drive.port.transfers == [HUMAN_REVIEW_TARGET]
    assert result.ehr.calls == []


def test_scheduling_failure_retries_once_then_hands_booking_to_staff() -> None:
    result = run("scheduling-failure")
    audit = audit_of(result)
    assert tasks(result)[-2:] == ["offer", "offer_retry"]
    assert [c for c in audit.error_codes if c.startswith("BOOKING_ATTEMPT_FAILED")] == [
        "BOOKING_ATTEMPT_FAILED:OFFER_EXPIRED",
        "BOOKING_ATTEMPT_FAILED:SLOT_NO_LONGER_AVAILABLE",
    ]
    assert outcomes(result, "EHR.CREATE_APPOINTMENT") == [OperationOutcome.FAILED]
    assert result.ehr.calls.count("GET_AVAILABLE_APPOINTMENTS") == 2
    assert "HUMAN_REVIEW:SLOT_NO_LONGER_AVAILABLE" in audit.human_decision_codes
    assert audit.disposition is Disposition.URGENT_SAME_DAY
    assert result.drive.port.transfers == [HUMAN_REVIEW_TARGET]
    assert booked_slot(result) == []


def test_schedule_squeeze_offers_alternative_and_surfaces_overbook_review() -> None:
    result = run("schedule-squeeze")
    audit = audit_of(result)
    assert "OVERBOOK_REVIEW_SUGGESTED:NO_NORMAL_SLOT_FOR_CONFIGURED_WINDOW" in (
        audit.human_decision_codes
    )
    assert booked_slot(result) == ["SLOT-SYN-SAME-DAY-1", "SLOT-SYN-CANCEL-1", "SLOT-SYN-ALT-1"]
    assert result.ctx.appointment_id is not None


def test_uncertain_identity_never_picks_a_record() -> None:
    result = run("identity-uncertain")
    audit = audit_of(result)
    assert result.ehr.calls == ["FIND_PATIENT"]
    assert audit.synthetic_patient_id is None
    assert audit.disposition is Disposition.HUMAN_REVIEW
    assert "HUMAN_REVIEW:IDENTITY_UNVERIFIED" in audit.human_decision_codes


@pytest.mark.parametrize("scenario_id", [s.scenario_id for s in SCENARIOS])
def test_every_scenario_is_deterministic_and_clean(scenario_id: str) -> None:
    first = run(scenario_id)
    second = run(scenario_id)
    assert summarize(first) == summarize(second)
    assert not [c for c in audit_of(first).error_codes if c.startswith(("UNHANDLED", "REJECTED"))]
    telemetry = json.dumps(
        [json.loads(r.model_dump_json()) for r in first.audit.audit_records]
        + [json.loads(e.model_dump_json()) for e in first.audit.operational_events]
    )
    assert "Synthetic" not in telemetry and "1980-" not in telemetry


def test_driver_rejects_scripts_that_disagree_with_the_call() -> None:
    routine = scenario("routine")
    with pytest.raises(ScenarioError, match="still active"):
        run_scenario(replace(routine, steps=routine.steps[:-1]))
    emergency = scenario("emergency-at-screening")
    with pytest.raises(ScenarioError, match="after the call ended"):
        run_scenario(replace(emergency, steps=(*emergency.steps, routine.steps[-1])))
    with pytest.raises(ScenarioError, match="is not active"):
        run_scenario(replace(routine, steps=routine.steps[1:]))


def test_cli_prints_panel_and_writes_separated_audit_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["emergency-interruption", "--audit-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "never patient-facing" in out and "Deciding rules" in out and "EX-EMERG-001" in out
    operational = (tmp_path / "operational.jsonl").read_text(encoding="utf-8")
    protected = (tmp_path / "protected-decisions.jsonl").read_text(encoding="utf-8")
    assert '"red_flag.chest_pain_now"' in protected and '"value": true' in protected
    assert '"value"' not in operational
    assert main(["--json", "routine"]) == 0
    (summary,) = json.loads(capsys.readouterr().out)
    assert summary["disposition"] == "ROUTINE" and summary["confidence"] is None
    assert summary["ehr_backend"].startswith("SyntheticEHR")
