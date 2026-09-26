from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from clinical_triage.domain.audit import AuditRecord
from clinical_triage.domain.conversation import ConversationState, SessionPhase, SessionState
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.ehr import PatientQuery
from clinical_triage.domain.facts import ClinicalFact, FactSource
from clinical_triage.domain.policy import (
    FactPredicate,
    PolicyBundle,
    PolicyReviewStatus,
    PredicateOperator,
    RuleSpec,
)
from clinical_triage.domain.scheduling import AppointmentSlot, AvailabilityKind
from clinical_triage.domain.triage import TriageResult

CHECKSUM = "a" * 64


def test_triage_result_serializes_explicit_policy_and_routing_evidence() -> None:
    result = TriageResult(
        disposition=Disposition.URGENT_SAME_DAY,
        confidence=0.6,
        trigger_rule_ids=("example-rule",),
        symptom_fact_ids=("abdominal-pain",),
        red_flag_ids=(),
        unanswered_critical_question_ids=("pregnancy-status",),
        recommended_scheduling_window="same-day",
        requires_human_review=True,
        rationale_code="EXAMPLE_POLICY_MATCH",
        policy_id="example-family-medicine",
        policy_version="0.1.0",
        policy_checksum_sha256=CHECKSUM,
    )

    payload = result.model_dump(mode="json")
    assert payload["disposition"] == "URGENT_SAME_DAY"
    assert payload["requires_human_review"] is True
    assert payload["policy_checksum_sha256"] == CHECKSUM


def test_conversation_state_rejects_repeated_question_ids() -> None:
    with pytest.raises(ValidationError, match="must not contain repeats"):
        ConversationState(asked_question_ids=("onset", "onset"), last_question_id="onset")


def test_emergency_session_is_terminal_and_in_escalation_phase() -> None:
    state = SessionState(
        call_id="call-synthetic-1",
        phase=SessionPhase.ESCALATE,
        disposition=Disposition.EMERGENCY,
        terminal=True,
    )
    assert state.terminal is True

    with pytest.raises(ValidationError, match="EMERGENCY disposition requires ESCALATE"):
        SessionState(
            call_id="call-synthetic-1",
            phase=SessionPhase.DISPOSITION,
            disposition=Disposition.EMERGENCY,
            terminal=False,
        )


def test_policy_contract_requires_review_identity_and_unique_rules() -> None:
    predicate = FactPredicate(fact_id="example", operator=PredicateOperator.PRESENT)
    rule = RuleSpec(
        rule_id="example-rule",
        priority=1,
        disposition=Disposition.HUMAN_REVIEW,
        all_of=(predicate,),
    )

    with pytest.raises(ValidationError, match="requires approved_by"):
        PolicyBundle(
            policy_id="policy",
            version="1",
            checksum_sha256=CHECKSUM,
            effective_date=date(2026, 9, 26),
            review_status=PolicyReviewStatus.CLINICIAN_REVIEWED,
            rules=(rule,),
        )


def test_appointment_slots_require_timezone_aware_valid_intervals() -> None:
    starts_at = datetime(2026, 9, 26, 9, tzinfo=UTC)
    slot = AppointmentSlot(
        slot_id="slot-1",
        provider_id="provider-1",
        location_id="location-1",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        kind=AvailabilityKind.OPEN,
    )
    assert slot.starts_at.tzinfo is UTC

    with pytest.raises(ValidationError, match="timezone-aware"):
        AppointmentSlot(
            slot_id="slot-2",
            provider_id="provider-1",
            location_id="location-1",
            starts_at=datetime(2026, 9, 26, 9),
            ends_at=datetime(2026, 9, 26, 9, 30),
            kind=AvailabilityKind.OPEN,
        )


def test_patient_query_rejects_unbounded_search() -> None:
    with pytest.raises(ValidationError, match="at least one search factor"):
        PatientQuery()


def test_audit_schema_uses_stable_ids_and_excludes_raw_conversation_fields() -> None:
    record = AuditRecord(
        call_id="call-synthetic-1",
        synthetic_patient_id="patient-a",
        started_at=datetime(2026, 9, 26, 9, tzinfo=UTC),
        policy_id="example-policy",
        policy_version="0.1.0",
        policy_checksum_sha256=CHECKSUM,
        question_ids_asked=("reason-for-call",),
        facts_recorded=(
            ClinicalFact(
                fact_id="reason-for-call",
                value="synthetic annual physical request",
                source=FactSource.CALLER,
                confirmed=True,
            ),
        ),
    )
    payload = record.model_dump(mode="json")
    assert "transcript" not in payload
    assert "patient_name" not in payload
    assert payload["synthetic_patient_id"] == "patient-a"
    assert payload["facts_recorded"][0]["fact_id"] == "reason-for-call"
