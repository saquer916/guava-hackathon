from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from clinical_triage.domain.audit import AuditRecord, DecisionRecord
from clinical_triage.domain.conversation import (
    AnswerRecorded,
    ConversationState,
    SessionPhase,
    SessionState,
)
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.ehr import PatientQuery
from clinical_triage.domain.facts import ClinicalFact, FactSource
from clinical_triage.domain.policy import (
    FactDataType,
    FactDefinition,
    FactPredicate,
    PolicyBundle,
    PolicyEvaluation,
    PolicyReviewStatus,
    PredicateOperator,
    RuleSpec,
)
from clinical_triage.domain.scheduling import (
    AppointmentConfirmation,
    AppointmentOffer,
    AppointmentSlot,
    AvailabilityKind,
    AvailabilitySnapshot,
)
from clinical_triage.domain.triage import TriageResult

CHECKSUM = "a" * 64


def test_triage_result_serializes_explicit_policy_and_routing_evidence() -> None:
    result = TriageResult(
        disposition=Disposition.URGENT_SAME_DAY,
        confidence=0.6,
        trigger_rule_ids=("example-rule",),
        symptom_fact_ids=("abdominal-pain",),
        red_flag_ids=(),
        unanswered_critical_question_ids=(),
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

    with pytest.raises(ValidationError, match="ESCALATE phase requires EMERGENCY"):
        SessionState(
            call_id="call-synthetic-1",
            phase=SessionPhase.ESCALATE,
            disposition=Disposition.HUMAN_REVIEW,
            terminal=True,
        )


def test_scheduling_phases_require_an_offer_and_eligible_disposition() -> None:
    with pytest.raises(ValidationError, match="offered_slot_id"):
        SessionState(
            call_id="call-synthetic-1",
            phase=SessionPhase.EXPLICIT_CONFIRMATION,
            disposition=Disposition.ROUTINE,
        )

    with pytest.raises(ValidationError, match="eligible non-emergency"):
        SessionState(
            call_id="call-synthetic-1",
            phase=SessionPhase.SLOT_OFFERED,
            disposition=Disposition.HUMAN_REVIEW,
            offered_slot_id="slot-1",
        )

    with pytest.raises(ValidationError, match="eligible non-emergency"):
        SessionState(call_id="call-synthetic-1", phase=SessionPhase.SLOT_SEARCH)


def test_events_require_kind_specific_payloads() -> None:
    fact = ClinicalFact(fact_id="onset", value="today", source=FactSource.CALLER)
    event = AnswerRecorded(
        event_id="event-1",
        call_id="call-synthetic-1",
        expected_state_version=0,
        fact=fact,
    )
    assert event.kind == "ANSWER_RECORDED"

    with pytest.raises(ValidationError, match="fact"):
        AnswerRecorded.model_validate(
            {
                "event_id": "event-2",
                "call_id": "call-synthetic-1",
                "expected_state_version": 0,
            }
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
            fact_definitions=(FactDefinition(fact_id="example", data_type=FactDataType.BOOLEAN),),
            rules=(rule,),
        )


def test_policy_rejects_type_or_unit_mismatches() -> None:
    rule = RuleSpec(
        rule_id="example-rule",
        priority=1,
        disposition=Disposition.HUMAN_REVIEW,
        all_of=(
            FactPredicate(
                fact_id="temperature",
                operator=PredicateOperator.GREATER_THAN_OR_EQUAL,
                value="high",
                unit_code="Cel",
            ),
        ),
    )
    with pytest.raises(ValidationError, match="does not match"):
        PolicyBundle(
            policy_id="policy",
            version="1",
            checksum_sha256=CHECKSUM,
            effective_date=date(2026, 9, 26),
            review_status=PolicyReviewStatus.EXAMPLE_UNREVIEWED,
            fact_definitions=(
                FactDefinition(
                    fact_id="temperature",
                    data_type=FactDataType.NUMBER,
                    allowed_unit_codes=("Cel",),
                ),
            ),
            rules=(rule,),
        )


def test_policy_missing_facts_cannot_emit_ordinary_disposition() -> None:
    with pytest.raises(ValidationError, match="missing required facts"):
        PolicyEvaluation(
            policy_id="policy",
            policy_version="1",
            policy_checksum_sha256=CHECKSUM,
            considered_fact_ids=(),
            matched_rule_ids=(),
            next_required_fact_ids=("onset",),
            disposition=Disposition.ROUTINE,
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


def test_availability_and_confirmation_have_explicit_freshness() -> None:
    observed = datetime(2026, 9, 26, 8, tzinfo=UTC)
    slot = AppointmentSlot(
        slot_id="slot-1",
        provider_id="provider-1",
        location_id="location-1",
        starts_at=observed + timedelta(hours=1),
        ends_at=observed + timedelta(hours=1, minutes=30),
        kind=AvailabilityKind.OPEN,
    )
    snapshot = AvailabilitySnapshot(
        snapshot_id="snapshot-1",
        observed_at=observed,
        expires_at=observed + timedelta(minutes=10),
        slots=(slot,),
    )
    offer = AppointmentOffer(
        offer_id="offer-1",
        snapshot=snapshot,
        slot=slot,
        offered_at=observed,
        expires_at=snapshot.expires_at,
    )
    confirmation = AppointmentConfirmation(
        confirmation_id="confirmation-1",
        confirmation_event_id="event-1",
        offer=offer,
        confirmed_at=observed + timedelta(minutes=5),
    )
    assert confirmation.offer.slot.slot_id == "slot-1"

    with pytest.raises(ValidationError, match="expired offer"):
        AppointmentConfirmation(
            confirmation_id="confirmation-2",
            confirmation_event_id="event-2",
            offer=offer,
            confirmed_at=observed + timedelta(minutes=11),
        )


def test_offer_must_be_bound_to_its_snapshot() -> None:
    observed = datetime(2026, 9, 26, 8, tzinfo=UTC)
    slot = AppointmentSlot(
        slot_id="slot-1",
        provider_id="provider-1",
        location_id="location-1",
        starts_at=observed + timedelta(hours=1),
        ends_at=observed + timedelta(hours=1, minutes=30),
        kind=AvailabilityKind.OPEN,
    )
    snapshot = AvailabilitySnapshot(
        snapshot_id="snapshot-1",
        observed_at=observed,
        expires_at=observed + timedelta(minutes=10),
        slots=(),
    )
    with pytest.raises(ValidationError, match="must come from"):
        AppointmentOffer(
            offer_id="offer-1",
            snapshot=snapshot,
            slot=slot,
            offered_at=observed,
            expires_at=snapshot.expires_at,
        )

    with pytest.raises(ValidationError, match="must not predate"):
        AppointmentOffer(
            offer_id="offer-2",
            snapshot=AvailabilitySnapshot(
                snapshot_id="snapshot-2",
                observed_at=observed,
                expires_at=observed + timedelta(minutes=10),
                slots=(slot,),
            ),
            slot=slot,
            offered_at=observed - timedelta(minutes=1),
            expires_at=observed + timedelta(minutes=5),
        )


def test_confirmation_must_not_predate_offer() -> None:
    observed = datetime(2026, 9, 26, 8, tzinfo=UTC)
    slot = AppointmentSlot(
        slot_id="slot-1",
        provider_id="provider-1",
        location_id="location-1",
        starts_at=observed + timedelta(hours=1),
        ends_at=observed + timedelta(hours=1, minutes=30),
        kind=AvailabilityKind.OPEN,
    )
    offer = AppointmentOffer(
        offer_id="offer-1",
        snapshot=AvailabilitySnapshot(
            snapshot_id="snapshot-1",
            observed_at=observed,
            expires_at=observed + timedelta(minutes=10),
            slots=(slot,),
        ),
        slot=slot,
        offered_at=observed + timedelta(minutes=1),
        expires_at=observed + timedelta(minutes=10),
    )
    with pytest.raises(ValidationError, match="must not predate"):
        AppointmentConfirmation(
            confirmation_id="confirmation-1",
            confirmation_event_id="event-1",
            offer=offer,
            confirmed_at=observed,
        )


def test_patient_query_rejects_unbounded_search() -> None:
    with pytest.raises(ValidationError, match="at least one search factor"):
        PatientQuery()


def test_operational_audit_uses_stable_ids_and_excludes_fact_values() -> None:
    record = AuditRecord(
        call_id="call-synthetic-1",
        synthetic_patient_id="patient-a",
        started_at=datetime(2026, 9, 26, 9, tzinfo=UTC),
        policy_id="example-policy",
        policy_version="0.1.0",
        policy_checksum_sha256=CHECKSUM,
        question_ids_asked=("reason-for-call",),
        fact_ids_recorded=("reason-for-call",),
    )
    payload = record.model_dump(mode="json")
    assert "transcript" not in payload
    assert "patient_name" not in payload
    assert payload["synthetic_patient_id"] == "patient-a"
    assert payload["fact_ids_recorded"] == ["reason-for-call"]
    assert "synthetic annual physical request" not in record.model_dump_json()


def test_protected_decision_record_retains_structured_evidence_separately() -> None:
    record = DecisionRecord(
        call_id="call-synthetic-1",
        synthetic_patient_id="patient-a",
        recorded_at=datetime(2026, 9, 26, 9, tzinfo=UTC),
        policy_id="example-policy",
        policy_version="0.1.0",
        policy_checksum_sha256=CHECKSUM,
        facts_recorded=(
            ClinicalFact(
                fact_id="reason-for-call",
                value="synthetic annual physical request",
                source=FactSource.CALLER,
                confirmed=True,
            ),
        ),
    )
    assert record.facts_recorded[0].fact_id == "reason-for-call"


def test_emergency_result_requires_evidence_and_human_review() -> None:
    with pytest.raises(ValidationError, match="rule and red-flag evidence"):
        TriageResult(
            disposition=Disposition.EMERGENCY,
            requires_human_review=True,
            rationale_code="EXAMPLE_EMERGENCY",
            policy_id="example-policy",
            policy_version="0.1.0",
            policy_checksum_sha256=CHECKSUM,
        )


def test_missing_critical_facts_force_emergency_or_human_review() -> None:
    with pytest.raises(ValidationError, match="prohibit"):
        TriageResult(
            disposition=Disposition.URGENT_SAME_DAY,
            unanswered_critical_question_ids=("pregnancy-status",),
            recommended_scheduling_window="same-day",
            requires_human_review=True,
            rationale_code="EXAMPLE_POLICY_MATCH",
            policy_id="example-policy",
            policy_version="0.1.0",
            policy_checksum_sha256=CHECKSUM,
        )
