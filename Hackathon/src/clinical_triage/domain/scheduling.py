"""Provider-neutral appointment options and human-review requests."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel


class AvailabilityKind(StrEnum):
    OPEN = "OPEN"
    SAME_DAY = "SAME_DAY"
    CANCELLATION = "CANCELLATION"
    SHORT_VISIT = "SHORT_VISIT"
    ALTERNATIVE_PROVIDER = "ALTERNATIVE_PROVIDER"
    NEXT_AVAILABLE = "NEXT_AVAILABLE"
    TELEHEALTH = "TELEHEALTH"


class AppointmentSlot(DomainModel):
    slot_id: str = Field(min_length=1)
    provider_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    kind: AvailabilityKind

    @model_validator(mode="after")
    def valid_interval(self) -> "AppointmentSlot":
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("appointment times must be timezone-aware")
        if self.ends_at <= self.starts_at:
            raise ValueError("appointment end must be after start")
        return self


class AvailabilitySnapshot(DomainModel):
    snapshot_id: str = Field(min_length=1)
    observed_at: datetime
    expires_at: datetime
    slots: tuple[AppointmentSlot, ...] = ()

    @model_validator(mode="after")
    def valid_freshness_window(self) -> "AvailabilitySnapshot":
        if self.observed_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("availability timestamps must be timezone-aware")
        if self.expires_at <= self.observed_at:
            raise ValueError("availability expiry must be after observation")
        slot_ids = [slot.slot_id for slot in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("availability slot IDs must be unique")
        return self


class AppointmentOffer(DomainModel):
    offer_id: str = Field(min_length=1)
    snapshot: AvailabilitySnapshot
    slot: AppointmentSlot
    offered_at: datetime
    expires_at: datetime
    hold_token: str | None = None

    @model_validator(mode="after")
    def valid_offer_window(self) -> "AppointmentOffer":
        if self.offered_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("offer timestamps must be timezone-aware")
        if self.offered_at < self.snapshot.observed_at:
            raise ValueError("offer must not predate its availability snapshot")
        if self.expires_at <= self.offered_at:
            raise ValueError("offer expiry must be after offer time")
        if self.expires_at > self.snapshot.expires_at:
            raise ValueError("offer must not outlive its availability snapshot")
        if self.slot not in self.snapshot.slots:
            raise ValueError("offered slot must come from the availability snapshot")
        return self


class AppointmentConfirmation(DomainModel):
    confirmation_id: str = Field(min_length=1)
    confirmation_event_id: str = Field(min_length=1)
    offer: AppointmentOffer
    confirmed_at: datetime

    @model_validator(mode="after")
    def confirmation_is_fresh(self) -> "AppointmentConfirmation":
        if self.confirmed_at.tzinfo is None:
            raise ValueError("confirmation timestamps must be timezone-aware")
        if self.confirmed_at < self.offer.offered_at:
            raise ValueError("appointment confirmation must not predate its offer")
        if self.confirmed_at > self.offer.expires_at:
            raise ValueError("appointment confirmation must not use an expired offer")
        return self


class OverbookReviewRequest(DomainModel):
    request_type: Literal["REQUEST_OVERBOOK_REVIEW"] = "REQUEST_OVERBOOK_REVIEW"
    reason_code: str = Field(min_length=1)
    suggested_slot_ids: tuple[str, ...]


class AppointmentOptions(DomainModel):
    normal_availability: tuple[AppointmentOffer, ...] = ()
    alternative_availability: tuple[AppointmentOffer, ...] = ()
    possible_escalation: OverbookReviewRequest | None = None

    @model_validator(mode="after")
    def offers_are_unique(self) -> "AppointmentOptions":
        offers = self.normal_availability + self.alternative_availability
        offer_ids = [offer.offer_id for offer in offers]
        if len(offer_ids) != len(set(offer_ids)):
            raise ValueError("appointment offer IDs must be unique")
        return self


class AppointmentMutationResult(DomainModel):
    operation_id: str = Field(min_length=1)
    completed: bool
    appointment_id: str | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def result_is_unambiguous(self) -> "AppointmentMutationResult":
        if self.completed and not self.appointment_id:
            raise ValueError("completed appointment mutation requires appointment_id")
        if not self.completed and not self.failure_code:
            raise ValueError("failed appointment mutation requires failure_code")
        if self.completed and self.failure_code:
            raise ValueError("completed appointment mutation must not contain failure_code")
        if not self.completed and self.appointment_id:
            raise ValueError("failed appointment mutation must not contain appointment_id")
        return self
