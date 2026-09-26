"""Read-only, capability-gated OpenEMR FHIR R4 implementation of the EHR port.

FHIR payloads are translated here and never returned to callers. Every read
that cannot be answered completely raises AdapterOperationUnavailable; every
write returns an explicit failed result because writes are outside this
adapter's least-privilege boundary.
"""

import re
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from hashlib import sha256
from typing import Any

from clinical_triage.adapters.errors import AdapterOperationUnavailable
from clinical_triage.adapters.openemr import capabilities as ops
from clinical_triage.adapters.openemr.capabilities import FhirCapabilities, evaluate_operations
from clinical_triage.adapters.openemr.config import OpenEMRConfig
from clinical_triage.adapters.openemr.transport import (
    FhirResponse,
    FhirTransport,
    TransportFailure,
)
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
    AppointmentSlot,
    AvailabilityKind,
    AvailabilitySnapshot,
)
from clinical_triage.domain.triage import TriageResult

ADAPTER_NAME = "openemr-fhir-r4"
_FHIR_ID = re.compile(r"^[A-Za-z0-9\-.]{1,64}$")

# Provider-neutral identity factor codes produced by patient matching.
GIVEN_NAME = "GIVEN_NAME"
FAMILY_NAME = "FAMILY_NAME"
BIRTH_DATE = "BIRTH_DATE"
PHONE = "PHONE"
EXTERNAL_IDENTIFIER = "EXTERNAL_IDENTIFIER"
KNOWN_FACTORS = frozenset({GIVEN_NAME, FAMILY_NAME, BIRTH_DATE, PHONE, EXTERNAL_IDENTIFIER})

_PATIENT_SEARCH_PARAMS = {
    GIVEN_NAME: "given",
    FAMILY_NAME: "family",
    BIRTH_DATE: "birthdate",
    PHONE: "phone",
    EXTERNAL_IDENTIFIER: "identifier",
}

_CONTEXT_CODE_ELEMENT = {
    "Condition": "code",
    "MedicationRequest": "medicationCodeableConcept",
    "AllergyIntolerance": "code",
    "Observation": "code",
}


class OpenEMRFhirAdapter:
    def __init__(
        self,
        *,
        config: OpenEMRConfig,
        transport: FhirTransport,
        capabilities: FhirCapabilities | None,
        discovery_failure: str | None = None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._capabilities = capabilities
        self._operations = {
            item.operation_code: item
            for item in evaluate_operations(capabilities, discovery_failure)
        }

    @classmethod
    def discover(cls, *, config: OpenEMRConfig, transport: FhirTransport) -> "OpenEMRFhirAdapter":
        """Read the CapabilityStatement once; any failure leaves every operation disabled."""

        failure: str | None = None
        discovered: FhirCapabilities | None = None
        try:
            response = transport.get(f"{config.fhir_base_path}/metadata")
        except TransportFailure:
            failure = "EHR_UNREACHABLE"
        else:
            if response.status != 200 or response.body is None:
                failure = f"CAPABILITY_HTTP_{response.status}"
            else:
                try:
                    discovered = FhirCapabilities.from_statement(response.body)
                except ValueError as exc:
                    failure = str(exc)
        return cls(
            config=config, transport=transport, capabilities=discovered, discovery_failure=failure
        )

    # --- EHRAdapter port -------------------------------------------------

    def capabilities(self) -> EHRCapabilityReport:
        return EHRCapabilityReport(
            adapter_name=ADAPTER_NAME,
            adapter_version=self._config.adapter_version,
            active=self._capabilities is not None,
            operations=tuple(self._operations.values()),
        )

    def find_patient(self, query: PatientQuery) -> tuple[PatientCandidate, ...]:
        self._require(ops.FIND_PATIENT)
        requested = _query_factors(query)
        params = {_PATIENT_SEARCH_PARAMS[code]: value for code, value in requested.items()}
        assert self._capabilities is not None
        if not self._capabilities.supports("Patient", "search-type", tuple(params)):
            raise AdapterOperationUnavailable(
                ops.FIND_PATIENT, "NOT_ADVERTISED_PATIENT_SEARCH_PARAM"
            )
        bundle = self._read(ops.FIND_PATIENT, "Patient", params)
        patients, truncated = _bundle_resources(bundle, "Patient")
        candidates: list[PatientCandidate] = []
        for patient in patients:
            patient_id = patient.get("id")
            if not isinstance(patient_id, str):
                raise AdapterOperationUnavailable(ops.FIND_PATIENT, "MALFORMED_RESPONSE")
            matched = _exact_factor_matches(patient, requested)
            if set(matched) == set(requested):
                candidates.append(
                    PatientCandidate(
                        patient_id=patient_id, match_factor_codes=tuple(sorted(matched))
                    )
                )
        ambiguous = truncated or len(candidates) > 1
        return tuple(
            candidate.model_copy(update={"ambiguous": ambiguous})
            for candidate in sorted(candidates, key=lambda item: item.patient_id)
        )

    def get_patient(self, patient_id: str) -> PatientCandidate | None:
        self._require(ops.GET_PATIENT)
        response = self._get(ops.GET_PATIENT, f"Patient/{_safe_id(ops.GET_PATIENT, patient_id)}")
        if response.status == 404:
            return None
        body = self._ok_body(ops.GET_PATIENT, response)
        if body.get("resourceType") != "Patient" or body.get("id") != patient_id:
            raise AdapterOperationUnavailable(ops.GET_PATIENT, "MALFORMED_RESPONSE")
        return PatientCandidate(patient_id=patient_id, match_factor_codes=("RECORD_ID",))

    def verify_patient(
        self, patient_id: str, factor_codes: tuple[str, ...]
    ) -> IdentityVerification:
        self._require(ops.VERIFY_PATIENT)
        factors = tuple(sorted(set(factor_codes) & KNOWN_FACTORS))
        exists = self.get_patient(patient_id) is not None
        verified = (
            exists
            and len(factors) >= self._config.minimum_verification_factors
            and set(self._config.required_verification_factor_codes) <= set(factors)
        )
        return IdentityVerification(
            patient_id=patient_id,
            verified=verified,
            verified_factor_codes=factors if verified else (),
            requires_human_review=not verified,
        )

    def get_appointments(self, patient_id: str) -> tuple[ExistingAppointment, ...]:
        self._require(ops.GET_APPOINTMENTS)
        bundle = self._read(
            ops.GET_APPOINTMENTS,
            "Appointment",
            {"patient": _safe_id(ops.GET_APPOINTMENTS, patient_id)},
        )
        resources, truncated = _bundle_resources(bundle, "Appointment")
        if truncated:
            raise AdapterOperationUnavailable(ops.GET_APPOINTMENTS, "RESULTS_TRUNCATED")
        appointments = [_appointment(resource) for resource in resources]
        return tuple(
            sorted(appointments, key=lambda item: (item.slot.starts_at, item.appointment_id))
        )

    def get_available_appointments(
        self, *, earliest: datetime, latest: datetime, constraint_codes: tuple[str, ...]
    ) -> AvailabilitySnapshot:
        self._require(ops.GET_AVAILABLE_APPOINTMENTS)
        raise AssertionError("availability is never enabled without a mapping")

    def get_clinical_context(self, patient_id: str) -> ClinicalContext:
        self._require(ops.GET_CLINICAL_CONTEXT)
        safe_id = _safe_id(ops.GET_CLINICAL_CONTEXT, patient_id)
        codes: dict[str, tuple[str, ...]] = {}
        for resource_type, element in _CONTEXT_CODE_ELEMENT.items():
            bundle = self._read(ops.GET_CLINICAL_CONTEXT, resource_type, {"patient": safe_id})
            resources, truncated = _bundle_resources(bundle, resource_type)
            if truncated:
                raise AdapterOperationUnavailable(ops.GET_CLINICAL_CONTEXT, "RESULTS_TRUNCATED")
            codes[resource_type] = tuple(
                sorted({_coded(resource.get(element)) for resource in resources})
            )
        return ClinicalContext(
            patient_id=patient_id,
            condition_codes=codes["Condition"],
            medication_codes=codes["MedicationRequest"],
            allergy_codes=codes["AllergyIntolerance"],
            observation_codes=codes["Observation"],
        )

    def create_appointment(
        self,
        *,
        patient_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult:
        return AppointmentMutationResult(
            operation_id=_operation_id(ops.CREATE_APPOINTMENT, idempotency_key),
            completed=False,
            failure_code=ops.READ_ONLY_BOUNDARY,
        )

    def update_appointment(
        self,
        *,
        appointment_id: str,
        confirmation: AppointmentConfirmation,
        idempotency_key: str,
    ) -> AppointmentMutationResult:
        return AppointmentMutationResult(
            operation_id=_operation_id(ops.UPDATE_APPOINTMENT, idempotency_key),
            completed=False,
            failure_code=ops.READ_ONLY_BOUNDARY,
        )

    def record_call_summary(self, record: CallSummary) -> RecordResult:
        return RecordResult(
            operation_id=_operation_id(ops.RECORD_CALL_SUMMARY, record.call_id),
            completed=False,
            failure_code=ops.READ_ONLY_BOUNDARY,
        )

    def record_triage_result(
        self, *, patient_id: str, result: TriageResult, idempotency_key: str
    ) -> RecordResult:
        return RecordResult(
            operation_id=_operation_id(ops.RECORD_TRIAGE_RESULT, idempotency_key),
            completed=False,
            failure_code=ops.READ_ONLY_BOUNDARY,
        )

    # --- internals ---------------------------------------------------------

    def _require(self, operation: str) -> None:
        capability = self._operations[operation]
        if not capability.supported:
            raise AdapterOperationUnavailable(operation, capability.reason_code)

    def _get(
        self, operation: str, relative: str, params: Mapping[str, str] | None = None
    ) -> FhirResponse:
        try:
            return self._transport.get(f"{self._config.fhir_base_path}/{relative}", params)
        except TransportFailure:
            raise AdapterOperationUnavailable(operation, "EHR_UNREACHABLE") from None

    def _ok_body(self, operation: str, response: FhirResponse) -> Mapping[str, Any]:
        if response.status in {401, 403}:
            raise AdapterOperationUnavailable(operation, "AUTHORIZATION_REJECTED")
        if response.status != 200:
            raise AdapterOperationUnavailable(operation, f"HTTP_{response.status}")
        if response.body is None:
            raise AdapterOperationUnavailable(operation, "MALFORMED_RESPONSE")
        return response.body

    def _read(self, operation: str, resource: str, params: Mapping[str, str]) -> Mapping[str, Any]:
        body = self._ok_body(operation, self._get(operation, resource, params))
        if body.get("resourceType") != "Bundle":
            raise AdapterOperationUnavailable(operation, "MALFORMED_RESPONSE")
        return body


def _query_factors(query: PatientQuery) -> dict[str, str]:
    raw: dict[str, str | date | None] = {
        GIVEN_NAME: query.given_name,
        FAMILY_NAME: query.family_name,
        BIRTH_DATE: query.birth_date,
        PHONE: query.phone,
        EXTERNAL_IDENTIFIER: query.external_identifier,
    }
    return {
        code: value.isoformat() if isinstance(value, date) else value.strip()
        for code, value in raw.items()
        if value is not None and (isinstance(value, date) or value.strip())
    }


def _exact_factor_matches(patient: Mapping[str, Any], requested: Mapping[str, str]) -> list[str]:
    """Re-check server-side matches exactly; FHIR string search is prefix-based."""

    matched: list[str] = []
    names = [name for name in patient.get("name") or () if isinstance(name, Mapping)]
    for code, value in requested.items():
        wanted = value.casefold()
        if code == GIVEN_NAME:
            hit = any(
                isinstance(given, str) and given.casefold() == wanted
                for name in names
                for given in name.get("given") or ()
            )
        elif code == FAMILY_NAME:
            hit = any(
                isinstance(name.get("family"), str) and name["family"].casefold() == wanted
                for name in names
            )
        elif code == BIRTH_DATE:
            hit = patient.get("birthDate") == value
        elif code == PHONE:
            hit = any(
                isinstance(item, Mapping)
                and item.get("system") == "phone"
                and _digits(str(item.get("value", ""))) == _digits(value)
                for item in patient.get("telecom") or ()
            )
        else:
            hit = any(
                isinstance(item, Mapping) and item.get("value") == value
                for item in patient.get("identifier") or ()
            )
        if hit:
            matched.append(code)
    return matched


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _bundle_resources(
    bundle: Mapping[str, Any], resource_type: str
) -> tuple[list[Mapping[str, Any]], bool]:
    resources = list(_entries(bundle, resource_type))
    has_next = any(
        isinstance(link, Mapping) and link.get("relation") == "next"
        for link in bundle.get("link") or ()
    )
    total = bundle.get("total")
    truncated = has_next or (isinstance(total, int) and total > len(resources))
    return resources, truncated


def _entries(bundle: Mapping[str, Any], resource_type: str) -> Iterator[Mapping[str, Any]]:
    for entry in bundle.get("entry") or ():
        resource = entry.get("resource") if isinstance(entry, Mapping) else None
        if not isinstance(resource, Mapping):
            continue
        # Included resources (e.g. OperationOutcome, Provenance) are not results.
        search = entry.get("search")
        if isinstance(search, Mapping) and search.get("mode") not in {None, "match"}:
            continue
        if resource.get("resourceType") == resource_type:
            yield resource


def _appointment(resource: Mapping[str, Any]) -> ExistingAppointment:
    operation = ops.GET_APPOINTMENTS
    appointment_id = resource.get("id")
    status = resource.get("status")
    practitioner = _participant_id(resource, "Practitioner")
    location = _participant_id(resource, "Location")
    starts_at = _instant(resource.get("start"))
    ends_at = _instant(resource.get("end"))
    if not (
        isinstance(appointment_id, str)
        and isinstance(status, str)
        and practitioner
        and location
        and starts_at
        and ends_at
    ):
        raise AdapterOperationUnavailable(operation, "APPOINTMENT_MAPPING_INCOMPLETE")
    try:
        slot = AppointmentSlot(
            slot_id=f"appointment-{appointment_id}",
            provider_id=practitioner,
            location_id=location,
            starts_at=starts_at,
            ends_at=ends_at,
            kind=AvailabilityKind.OPEN,
        )
    except ValueError:
        raise AdapterOperationUnavailable(operation, "APPOINTMENT_MAPPING_INCOMPLETE") from None
    return ExistingAppointment(appointment_id=appointment_id, slot=slot, status=status.upper())


def _participant_id(resource: Mapping[str, Any], resource_type: str) -> str | None:
    prefix = f"{resource_type}/"
    for participant in resource.get("participant") or ():
        actor = participant.get("actor") if isinstance(participant, Mapping) else None
        reference = actor.get("reference") if isinstance(actor, Mapping) else None
        if isinstance(reference, str) and reference.startswith(prefix):
            return reference.removeprefix(prefix)
    return None


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _coded(concept: object) -> str:
    codings = concept.get("coding") if isinstance(concept, Mapping) else None
    for coding in codings or ():
        if isinstance(coding, Mapping):
            system, code = coding.get("system"), coding.get("code")
            if isinstance(system, str) and isinstance(code, str) and system and code:
                return f"{system}|{code}"
    raise AdapterOperationUnavailable(ops.GET_CLINICAL_CONTEXT, "UNCODED_CLINICAL_ENTRY")


def _safe_id(operation: str, value: str) -> str:
    if not _FHIR_ID.fullmatch(value):
        raise AdapterOperationUnavailable(operation, "INVALID_RECORD_ID")
    return value


def _operation_id(operation: str, key: str) -> str:
    return f"{operation.lower()}-{sha256(key.encode()).hexdigest()[:16]}"
