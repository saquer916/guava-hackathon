"""EHR request and response values shared by every provider adapter."""

from datetime import date

from pydantic import Field, model_validator

from clinical_triage.domain._model import DomainModel
from clinical_triage.domain.scheduling import AppointmentSlot


class PatientQuery(DomainModel):
    given_name: str | None = None
    family_name: str | None = None
    birth_date: date | None = None
    phone: str | None = None
    external_identifier: str | None = None

    @model_validator(mode="after")
    def requires_a_search_factor(self) -> "PatientQuery":
        if not any(
            (
                self.given_name,
                self.family_name,
                self.birth_date,
                self.phone,
                self.external_identifier,
            )
        ):
            raise ValueError("patient query requires at least one search factor")
        return self


class PatientCandidate(DomainModel):
    patient_id: str = Field(min_length=1)
    match_factor_codes: tuple[str, ...]
    ambiguous: bool = False


class IdentityVerification(DomainModel):
    patient_id: str = Field(min_length=1)
    verified: bool
    verified_factor_codes: tuple[str, ...]
    requires_human_review: bool

    @model_validator(mode="after")
    def unresolved_identity_requires_review(self) -> "IdentityVerification":
        if self.verified == self.requires_human_review:
            raise ValueError("verified and requires_human_review must be opposites")
        return self


class ExistingAppointment(DomainModel):
    appointment_id: str = Field(min_length=1)
    slot: AppointmentSlot
    status: str = Field(min_length=1)


class ClinicalContext(DomainModel):
    patient_id: str = Field(min_length=1)
    condition_codes: tuple[str, ...] = ()
    medication_codes: tuple[str, ...] = ()
    allergy_codes: tuple[str, ...] = ()
    observation_codes: tuple[str, ...] = ()


class RecordResult(DomainModel):
    operation_id: str = Field(min_length=1)
    completed: bool
    record_reference: str | None = None
    failure_code: str | None = None

    @model_validator(mode="after")
    def result_is_unambiguous(self) -> "RecordResult":
        if self.completed and not self.record_reference:
            raise ValueError("completed record result requires record_reference")
        if not self.completed and not self.failure_code:
            raise ValueError("failed record result requires failure_code")
        if self.completed and self.failure_code:
            raise ValueError("completed record result must not contain failure_code")
        if not self.completed and self.record_reference:
            raise ValueError("failed record result must not contain record_reference")
        return self


class CapabilityOperation(DomainModel):
    resource_type: str = Field(min_length=1)
    interaction: str = Field(min_length=1)
    search_parameters: tuple[str, ...] = ()
    required_scope: str = Field(min_length=1)
    supported: bool
    reason: str = Field(min_length=1)


class EHRCapabilityReport(DomainModel):
    fhir_version: str = Field(min_length=1)
    software_name: str = Field(min_length=1)
    software_version: str = Field(min_length=1)
    active: bool
    operations: tuple[CapabilityOperation, ...]
