"""Configurable appointment ranking without autonomous overbooking."""

from datetime import datetime, timedelta
from hashlib import sha256

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.disposition import Disposition
from clinical_triage.domain.scheduling import (
    AppointmentConfirmation,
    AppointmentOffer,
    AppointmentOptions,
    AppointmentSlot,
    AvailabilityKind,
    AvailabilitySnapshot,
    OverbookReviewRequest,
)


class SchedulingPolicyError(ValueError):
    """A fail-closed scheduling outcome with a stable machine-readable code."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


class SchedulingPolicy(DomainModel):
    policy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    normal_kind_order: tuple[AvailabilityKind, ...]
    alternative_kind_order: tuple[AvailabilityKind, ...] = ()
    maximum_offers: int = Field(default=3, ge=1, le=20)
    offer_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    overbook_review_dispositions: tuple[Disposition, ...] = ()

    @model_validator(mode="after")
    def policy_is_unambiguous(self) -> "SchedulingPolicy":
        ranked = self.normal_kind_order + self.alternative_kind_order
        if not ranked:
            raise ValueError("scheduling policy requires at least one availability kind")
        if len(ranked) != len(set(ranked)):
            raise ValueError("availability kinds must be unique across ranking groups")
        prohibited = {Disposition.EMERGENCY, Disposition.HUMAN_REVIEW}
        if prohibited.intersection(self.overbook_review_dispositions):
            raise ValueError("emergency and human-review dispositions cannot request overbooking")
        return self


def rank_appointment_options(
    *,
    snapshot: AvailabilitySnapshot,
    disposition: Disposition,
    policy: SchedulingPolicy,
    now: datetime,
) -> AppointmentOptions:
    """Rank fresh slots; never books, overbooks, or changes the disposition."""

    _validate_scheduling_context(snapshot=snapshot, disposition=disposition, now=now)
    normal = _rank_group(
        snapshot=snapshot,
        kinds=policy.normal_kind_order,
        now=now,
        ttl_seconds=policy.offer_ttl_seconds,
    )
    alternative = _rank_group(
        snapshot=snapshot,
        kinds=policy.alternative_kind_order,
        now=now,
        ttl_seconds=policy.offer_ttl_seconds,
    )

    remaining = policy.maximum_offers
    normal = normal[:remaining]
    remaining -= len(normal)
    alternative = alternative[:remaining]

    review = None
    if not normal and disposition in policy.overbook_review_dispositions:
        suggested = tuple(offer.slot.slot_id for offer in alternative)
        review = OverbookReviewRequest(
            reason_code="NO_NORMAL_SLOT_FOR_CONFIGURED_WINDOW",
            suggested_slot_ids=suggested,
        )

    return AppointmentOptions(
        normal_availability=tuple(normal),
        alternative_availability=tuple(alternative),
        possible_escalation=review,
    )


def build_confirmation(
    *,
    offer: AppointmentOffer,
    confirmation_id: str,
    confirmation_event_id: str,
    confirmed_at: datetime,
) -> AppointmentConfirmation:
    """Bind an explicit caller confirmation event to one previously ranked offer."""

    return AppointmentConfirmation(
        confirmation_id=confirmation_id,
        confirmation_event_id=confirmation_event_id,
        offer=offer,
        confirmed_at=confirmed_at,
    )


def _validate_scheduling_context(
    *, snapshot: AvailabilitySnapshot, disposition: Disposition, now: datetime
) -> None:
    if now.tzinfo is None:
        raise SchedulingPolicyError("CURRENT_TIME_NOT_TIMEZONE_AWARE")
    if disposition is Disposition.EMERGENCY:
        raise SchedulingPolicyError("EMERGENCY_PROHIBITS_SCHEDULING")
    if disposition is Disposition.HUMAN_REVIEW:
        raise SchedulingPolicyError("HUMAN_REVIEW_PROHIBITS_SCHEDULING")
    if now < snapshot.observed_at:
        raise SchedulingPolicyError("AVAILABILITY_NOT_YET_OBSERVED")
    if now > snapshot.expires_at:
        raise SchedulingPolicyError("AVAILABILITY_SNAPSHOT_EXPIRED")


def _rank_group(
    *,
    snapshot: AvailabilitySnapshot,
    kinds: tuple[AvailabilityKind, ...],
    now: datetime,
    ttl_seconds: int,
) -> list[AppointmentOffer]:
    kind_rank = {kind: index for index, kind in enumerate(kinds)}
    slots = [slot for slot in snapshot.slots if slot.kind in kind_rank and slot.starts_at > now]
    slots.sort(key=lambda slot: (kind_rank[slot.kind], slot.starts_at, slot.slot_id))
    return [
        _offer(snapshot=snapshot, slot=slot, now=now, ttl_seconds=ttl_seconds) for slot in slots
    ]


def _offer(
    *, snapshot: AvailabilitySnapshot, slot: AppointmentSlot, now: datetime, ttl_seconds: int
) -> AppointmentOffer:
    expires_at = min(snapshot.expires_at, slot.starts_at, now + timedelta(seconds=ttl_seconds))
    digest = sha256(f"{snapshot.snapshot_id}:{slot.slot_id}".encode()).hexdigest()[:20]
    return AppointmentOffer(
        offer_id=f"offer-{digest}",
        snapshot=snapshot,
        slot=slot,
        offered_at=now,
        expires_at=expires_at,
    )
