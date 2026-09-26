import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.scheduling import (
    AppointmentSlot,
    AvailabilityKind,
    AvailabilitySnapshot,
)
from clinical_triage.scheduling import (
    SchedulingPolicy,
    SchedulingPolicyError,
    build_confirmation,
    rank_appointment_options,
)

NOW = datetime(2026, 9, 26, 9, tzinfo=UTC)


def slot(slot_id: str, kind: AvailabilityKind, hours: int) -> AppointmentSlot:
    starts_at = NOW + timedelta(hours=hours)
    return AppointmentSlot(
        slot_id=slot_id,
        provider_id=f"provider-{slot_id}",
        location_id="synthetic-clinic",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(minutes=30),
        kind=kind,
    )


def snapshot(*slots: AppointmentSlot) -> AvailabilitySnapshot:
    return AvailabilitySnapshot(
        snapshot_id="snapshot-1",
        observed_at=NOW - timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=10),
        slots=slots,
    )


def policy() -> SchedulingPolicy:
    return SchedulingPolicy(
        policy_id="synthetic-policy",
        version="1",
        normal_kind_order=(
            AvailabilityKind.OPEN,
            AvailabilityKind.CANCELLATION,
            AvailabilityKind.SHORT_VISIT,
        ),
        alternative_kind_order=(
            AvailabilityKind.ALTERNATIVE_PROVIDER,
            AvailabilityKind.NEXT_AVAILABLE,
        ),
        maximum_offers=3,
        overbook_review_dispositions=(Disposition.URGENT_SAME_DAY,),
    )


def test_ranking_is_configured_deterministic_and_bounded() -> None:
    options = rank_appointment_options(
        snapshot=snapshot(
            slot("next", AvailabilityKind.NEXT_AVAILABLE, 1),
            slot("cancel", AvailabilityKind.CANCELLATION, 3),
            slot("open", AvailabilityKind.OPEN, 5),
            slot("alternative", AvailabilityKind.ALTERNATIVE_PROVIDER, 2),
        ),
        disposition=Disposition.ROUTINE,
        policy=policy(),
        now=NOW,
    )

    assert [offer.slot.slot_id for offer in options.normal_availability] == ["open", "cancel"]
    assert [offer.slot.slot_id for offer in options.alternative_availability] == ["alternative"]
    assert options.possible_escalation is None


def test_no_normal_slot_only_requests_human_overbook_review() -> None:
    options = rank_appointment_options(
        snapshot=snapshot(slot("alternative", AvailabilityKind.ALTERNATIVE_PROVIDER, 2)),
        disposition=Disposition.URGENT_SAME_DAY,
        policy=policy(),
        now=NOW,
    )

    assert options.normal_availability == ()
    assert options.possible_escalation is not None
    assert options.possible_escalation.request_type == "REQUEST_OVERBOOK_REVIEW"
    assert options.possible_escalation.suggested_slot_ids == ("alternative",)


@pytest.mark.parametrize("disposition", [Disposition.EMERGENCY, Disposition.HUMAN_REVIEW])
def test_unsafe_dispositions_never_enter_scheduling(disposition: Disposition) -> None:
    with pytest.raises(SchedulingPolicyError, match="PROHIBITS_SCHEDULING"):
        rank_appointment_options(
            snapshot=snapshot(slot("open", AvailabilityKind.OPEN, 1)),
            disposition=disposition,
            policy=policy(),
            now=NOW,
        )


def test_stale_availability_fails_closed() -> None:
    stale = AvailabilitySnapshot(
        snapshot_id="stale",
        observed_at=NOW - timedelta(hours=1),
        expires_at=NOW - timedelta(seconds=1),
        slots=(slot("open", AvailabilityKind.OPEN, 1),),
    )
    with pytest.raises(SchedulingPolicyError, match="SNAPSHOT_EXPIRED"):
        rank_appointment_options(
            snapshot=stale,
            disposition=Disposition.ROUTINE,
            policy=policy(),
            now=NOW,
        )


def test_confirmation_is_bound_to_ranked_offer_and_expiry() -> None:
    offer = rank_appointment_options(
        snapshot=snapshot(slot("open", AvailabilityKind.OPEN, 1)),
        disposition=Disposition.ROUTINE,
        policy=policy(),
        now=NOW,
    ).normal_availability[0]
    confirmation = build_confirmation(
        offer=offer,
        confirmation_id="confirmation-1",
        confirmation_event_id="event-1",
        confirmed_at=NOW + timedelta(minutes=1),
    )
    assert confirmation.offer.offer_id == offer.offer_id

    with pytest.raises(ValidationError, match="expired offer"):
        build_confirmation(
            offer=offer,
            confirmation_id="confirmation-2",
            confirmation_event_id="event-2",
            confirmed_at=offer.expires_at + timedelta(seconds=1),
        )


def test_example_policy_file_is_valid_and_contains_no_provider_identifiers() -> None:
    path = Path(__file__).parents[2] / "config" / "scheduling" / "example.json"
    raw = path.read_text()
    loaded = SchedulingPolicy.model_validate(json.loads(raw))
    assert loaded.policy_id == "synthetic-family-medicine-scheduling"
    assert "guava" not in raw.lower()
    assert "openemr" not in raw.lower()


def test_policy_rejects_duplicate_ranking_kinds_and_unsafe_overbook_review() -> None:
    with pytest.raises(ValidationError, match="unique"):
        SchedulingPolicy(
            policy_id="invalid",
            version="1",
            normal_kind_order=(AvailabilityKind.OPEN,),
            alternative_kind_order=(AvailabilityKind.OPEN,),
        )

    with pytest.raises(ValidationError, match="cannot request overbooking"):
        SchedulingPolicy(
            policy_id="invalid",
            version="1",
            normal_kind_order=(AvailabilityKind.OPEN,),
            overbook_review_dispositions=(Disposition.EMERGENCY,),
        )
