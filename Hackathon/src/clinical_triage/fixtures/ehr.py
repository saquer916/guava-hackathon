"""In-memory EHR backed only by synthetic fixtures, for offline deterministic runs.

Implements the provider-neutral EHR port so orchestration and scenarios can run
without OpenEMR. It supports deterministic fault injection (unavailable
operations, slots taken after a snapshot) to exercise fail-closed paths.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from hashlib import sha256

from clinical_triage.adapters.errors import AdapterOperationUnavailable
from clinical_triage.domain.ehr import (
    AdapterOperationCapability,
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
from clinical_triage.fixtures.synthetic import SyntheticFixtures, SyntheticPatient

OPERATIONS = (
    "FIND_PATIENT",
    "GET_PATIENT",
    "VERIFY_PATIENT",
    "GET_APPOINTMENTS",
    "GET_AVAILABLE_APPOINTMENTS",
    "GET_CLINICAL_CONTEXT",
    "CREATE_APPOINTMENT",
    "UPDATE_APPOINTMENT",
    "RECORD_CALL_SUMMARY",
    "RECORD_TRIAGE_RESULT",
)


class FixedClock:
    """Deterministic clock; time only moves when a test or scenario advances it."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("clock must be timezone-aware")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, *, seconds: int) -> None:
        self._now += timedelta(seconds=seconds)


@dataclass
class SyntheticEHR:
    fixtures: SyntheticFixtures
    clock: FixedClock
    snapshot_ttl_seconds: int = 600
    unavailable_operations: frozenset[str] = frozenset()
    slots_taken_after_snapshot: frozenset[str] = frozenset()
    bookings: dict[str, AppointmentMutationResult] = field(default_factory=dict)
    booked_slot_ids: dict[str, str] = field(default_factory=dict)
    records: dict[str, RecordResult] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def capabilities(self) -> EHRCapabilityReport:
        return EHRCapabilityReport(
            adapter_name="synthetic-fixture-ehr",
            adapter_version=self.fixtures.fixture_version,
            active=True,
            operations=tuple(
                AdapterOperationCapability(
                    operation_code=code,
                    supported=code not in self.unavailable_operations,
                    reason_code=(
                        "FAULT_INJECTED"
                        if code in self.unavailable_operations
                        else "SYNTHETIC_FIXTURE"
                    ),
                )
                for code in OPERATIONS
            ),
        )

    def find_patient(self, query: PatientQuery) -> tuple[PatientCandidate, ...]:
        self._enter("FIND_PATIENT")
        wanted = {
            "GIVEN_NAME": query.given_name.casefold() if query.given_name else None,
            "FAMILY_NAME": query.family_name.casefold() if query.family_name else None,
            "BIRTH_DATE": query.birth_date,
            "PHONE": _digits(query.phone) if query.phone else None,
            "EXTERNAL_IDENTIFIER": query.external_identifier,
        }
        requested = {code: value for code, value in wanted.items() if value}
        matches = [
            patient
            for patient in self.fixtures.patients
            if all(_patient_value(patient, code) == value for code, value in requested.items())
        ]
        return tuple(
            PatientCandidate(
                patient_id=patient.synthetic_id,
                match_factor_codes=tuple(sorted(requested)),
                ambiguous=len(matches) > 1,
            )
            for patient in matches
        )

    def get_patient(self, patient_id: str) -> PatientCandidate | None:
        self._enter("GET_PATIENT")
        if self._patient(patient_id) is None:
            return None
        return PatientCandidate(patient_id=patient_id, match_factor_codes=("RECORD_ID",))

    def verify_patient(
        self, patient_id: str, factor_codes: tuple[str, ...]
    ) -> IdentityVerification:
        self._enter("VERIFY_PATIENT")
        factors = tuple(
            sorted(
                set(factor_codes)
                & {"GIVEN_NAME", "FAMILY_NAME", "BIRTH_DATE", "PHONE", "EXTERNAL_IDENTIFIER"}
            )
        )
        verified = (
            self._patient(patient_id) is not None and len(factors) >= 2 and "BIRTH_DATE" in factors
        )
        return IdentityVerification(
            patient_id=patient_id,
            verified=verified,
            verified_factor_codes=factors if verified else (),
            requires_human_review=not verified,
        )

    def get_appointments(self, patient_id: str) -> tuple[ExistingAppointment, ...]:
        self._enter("GET_APPOINTMENTS")
        return ()

    def get_available_appointments(
        self, *, earliest: datetime, latest: datetime, constraint_codes: tuple[str, ...]
    ) -> AvailabilitySnapshot:
        self._enter("GET_AVAILABLE_APPOINTMENTS")
        now = self.clock.now()
        slots = tuple(
            slot
            for slot in (template.at(self.fixtures.clock) for template in self.fixtures.slots)
            if earliest <= slot.starts_at <= latest and slot.slot_id not in self.booked_slot_ids
        )
        digest = sha256(
            f"{now.isoformat()}|{earliest.isoformat()}|{latest.isoformat()}|"
            f"{','.join(s.slot_id for s in slots)}".encode()
        ).hexdigest()[:16]
        return AvailabilitySnapshot(
            snapshot_id=f"snapshot-{digest}",
            observed_at=now,
            expires_at=now + timedelta(seconds=self.snapshot_ttl_seconds),
            slots=slots,
        )

    def get_clinical_context(self, patient_id: str) -> ClinicalContext:
        self._enter("GET_CLINICAL_CONTEXT")
        patient = self._patient(patient_id)
        if patient is None:
            raise AdapterOperationUnavailable("GET_CLINICAL_CONTEXT", "PATIENT_NOT_FOUND")
        return ClinicalContext(
            patient_id=patient_id,
            condition_codes=patient.condition_codes,
            medication_codes=patient.medication_codes,
            allergy_codes=patient.allergy_codes,
            observation_codes=patient.observation_codes,
        )

    def create_appointment(
        self,
        *,
        patient_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult:
        operation_id = _operation_id("create", idempotency_key)
        if idempotency_key in self.bookings:
            return self.bookings[idempotency_key]
        self.calls.append("CREATE_APPOINTMENT")
        failure = self._booking_failure("CREATE_APPOINTMENT", patient_id, confirmation)
        if failure:
            return AppointmentMutationResult(
                operation_id=operation_id, completed=False, failure_code=failure
            )
        slot_id = confirmation.offer.slot.slot_id
        result = AppointmentMutationResult(
            operation_id=operation_id,
            completed=True,
            appointment_id=f"APPT-SYN-{sha256(idempotency_key.encode()).hexdigest()[:12]}",
        )
        self.bookings[idempotency_key] = result
        self.booked_slot_ids[slot_id] = patient_id
        return result

    def update_appointment(
        self,
        *,
        appointment_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult:
        self.calls.append("UPDATE_APPOINTMENT")
        return AppointmentMutationResult(
            operation_id=_operation_id("update", idempotency_key),
            completed=False,
            failure_code="UPDATE_NOT_SUPPORTED_BY_SYNTHETIC_EHR",
        )

    def record_call_summary(self, record: CallSummary) -> RecordResult:
        return self._record("RECORD_CALL_SUMMARY", f"summary:{record.call_id}")

    def record_triage_result(
        self, *, patient_id: str, result: TriageResult, idempotency_key: str
    ) -> RecordResult:
        return self._record("RECORD_TRIAGE_RESULT", f"triage:{idempotency_key}")

    # --- internals ---------------------------------------------------------

    def _enter(self, operation: str) -> None:
        self.calls.append(operation)
        if operation in self.unavailable_operations:
            raise AdapterOperationUnavailable(operation, "FAULT_INJECTED")

    def _patient(self, patient_id: str) -> SyntheticPatient | None:
        return next((p for p in self.fixtures.patients if p.synthetic_id == patient_id), None)

    def _booking_failure(
        self, operation: str, patient_id: str, confirmation: AppointmentConfirmation
    ) -> str | None:
        slot_id = confirmation.offer.slot.slot_id
        if operation in self.unavailable_operations:
            return "FAULT_INJECTED"
        if self._patient(patient_id) is None:
            return "PATIENT_NOT_FOUND"
        if self.clock.now() > confirmation.offer.expires_at:
            return "OFFER_EXPIRED"
        if slot_id in self.slots_taken_after_snapshot or slot_id in self.booked_slot_ids:
            return "SLOT_NO_LONGER_AVAILABLE"
        return None

    def _record(self, operation: str, key: str) -> RecordResult:
        self.calls.append(operation)
        if key in self.records:
            return self.records[key]
        operation_id = _operation_id(operation.lower(), key)
        if operation in self.unavailable_operations:
            return RecordResult(
                operation_id=operation_id, completed=False, failure_code="FAULT_INJECTED"
            )
        result = RecordResult(
            operation_id=operation_id,
            completed=True,
            record_reference=f"REC-SYN-{operation_id[-12:]}",
        )
        self.records[key] = result
        return result


def _patient_value(patient: SyntheticPatient, code: str) -> object:
    return {
        "GIVEN_NAME": patient.given_name.casefold(),
        "FAMILY_NAME": patient.family_name.casefold(),
        "BIRTH_DATE": patient.birth_date,
        "PHONE": _digits(patient.phone),
        "EXTERNAL_IDENTIFIER": patient.synthetic_id,
    }[code]


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _operation_id(operation: str, key: str) -> str:
    return f"{operation}-{sha256(key.encode()).hexdigest()[:16]}"
