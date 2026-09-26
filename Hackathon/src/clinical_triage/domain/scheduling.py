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


class OverbookReviewRequest(DomainModel):
    request_type: Literal["REQUEST_OVERBOOK_REVIEW"] = "REQUEST_OVERBOOK_REVIEW"
    reason_code: str = Field(min_length=1)
    suggested_slot_ids: tuple[str, ...]


class AppointmentOptions(DomainModel):
    normal_availability: tuple[AppointmentSlot, ...] = ()
    alternative_availability: tuple[AppointmentSlot, ...] = ()
    possible_escalation: OverbookReviewRequest | None = None


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
