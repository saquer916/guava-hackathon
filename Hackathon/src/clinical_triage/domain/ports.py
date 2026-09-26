"""Provider-neutral integration ports."""

from datetime import datetime
from typing import Protocol

from clinical_triage.domain.audit import AuditRecord, DecisionRecord, OperationalEvent
from clinical_triage.domain.ehr import (
    CallSummary,
    ClinicalContext,
    EHRCapabilityReport,
    ExistingAppointment,
    IdentityVerification,
    PatientCandidate,
    PatientQuery,
    RecordResult,
)
from clinical_triage.domain.scheduling import (
    AppointmentConfirmation,
    AppointmentMutationResult,
    AvailabilitySnapshot,
)
from clinical_triage.domain.triage import TriageResult


class EHRAdapter(Protocol):
    def capabilities(self) -> EHRCapabilityReport: ...

    def find_patient(self, query: PatientQuery) -> tuple[PatientCandidate, ...]: ...

    def get_patient(self, patient_id: str) -> PatientCandidate | None: ...

    def verify_patient(
        self, patient_id: str, factor_codes: tuple[str, ...]
    ) -> IdentityVerification: ...

    def get_appointments(self, patient_id: str) -> tuple[ExistingAppointment, ...]: ...

    def get_available_appointments(
        self, *, earliest: datetime, latest: datetime, constraint_codes: tuple[str, ...]
    ) -> AvailabilitySnapshot: ...

    def get_clinical_context(self, patient_id: str) -> ClinicalContext: ...

    def create_appointment(
        self,
        *,
        patient_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult: ...

    def update_appointment(
        self,
        *,
        appointment_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult: ...

    def record_call_summary(self, record: CallSummary) -> RecordResult: ...

    def record_triage_result(
        self, *, patient_id: str, result: TriageResult, idempotency_key: str
    ) -> RecordResult: ...


class AuditSink(Protocol):
    def append_audit_record(self, record: AuditRecord) -> None: ...

    def append_decision_record(self, record: DecisionRecord) -> None: ...

    def emit_operational_event(self, event: OperationalEvent) -> None: ...
