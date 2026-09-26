from datetime import UTC, date, datetime
from typing import Any

import pytest
from openemr_fakes import (
    BASE,
    OPENEMR_LIKE_CAPABILITIES,
    ScriptedTransport,
    bundle,
    capability_statement,
    ok,
    resource_capability,
    synthetic_patient,
    unreachable,
)

from clinical_triage.adapters.errors import AdapterOperationUnavailable
from clinical_triage.adapters.openemr import (
    READ_ONLY_SCOPES,
    FhirResponse,
    OpenEMRConfig,
    OpenEMRFhirAdapter,
    UnsafeOpenEMRConfig,
)
from clinical_triage.domain.ehr import PatientQuery
from clinical_triage.domain.scheduling import AvailabilityKind

PATIENT_A = synthetic_patient("syn-a", "Avery", "Synthetic", "1980-01-02", "555-0100")
PATIENT_B = synthetic_patient("syn-b", "Avery", "Syntheticson", "1980-01-02", "555-0101")


def adapter(
    routes: dict[str, Any], capabilities: dict[str, Any] | None = None
) -> OpenEMRFhirAdapter:
    table: dict[str, Any] = {f"{BASE}/metadata": ok(capabilities or OPENEMR_LIKE_CAPABILITIES)}
    table.update({f"{BASE}/{path}": response for path, response in routes.items()})
    return OpenEMRFhirAdapter.discover(config=OpenEMRConfig(), transport=ScriptedTransport(table))


def operations(target: OpenEMRFhirAdapter) -> dict[str, tuple[bool, str]]:
    return {
        op.operation_code: (op.supported, op.reason_code) for op in target.capabilities().operations
    }


# --- configuration boundary ------------------------------------------------


@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost:9300",
        "https://ehr.example.org",
        "https://10.1.2.3",
        "https://a:b@localhost",
    ],
)
def test_config_refuses_nonlocal_or_plaintext_targets(base_url: str) -> None:
    with pytest.raises(UnsafeOpenEMRConfig):
        OpenEMRConfig(base_url=base_url)


@pytest.mark.parametrize(
    "scope",
    [
        "system/Patient.rs",
        "patient/Patient.rs",
        "user/*.rs",
        "user/Patient.cruds",
        "user/Appointment.write",
        "user/Patient.read",
        "offline_access",
        "api:oemr",
    ],
)
def test_config_refuses_scopes_beyond_user_read_search(scope: str) -> None:
    with pytest.raises(UnsafeOpenEMRConfig):
        OpenEMRConfig(scopes=(*READ_ONLY_SCOPES, scope))


def test_default_scopes_are_read_only_user_context() -> None:
    resource_scopes = [scope for scope in READ_ONLY_SCOPES if "/" in scope]
    assert resource_scopes and all(
        scope.startswith("user/") and scope.endswith(".rs") for scope in resource_scopes
    )


def test_identity_verification_requires_two_factors() -> None:
    with pytest.raises(UnsafeOpenEMRConfig):
        OpenEMRConfig(minimum_verification_factors=1)


# --- capability discovery ----------------------------------------------------


def test_discovered_capabilities_gate_each_operation() -> None:
    report = adapter({}).capabilities()
    assert report.active and report.adapter_name == "openemr-fhir-r4"
    assert operations(adapter({})) == {
        "FIND_PATIENT": (True, "ADVERTISED_BY_CAPABILITY_STATEMENT"),
        "GET_PATIENT": (True, "ADVERTISED_BY_CAPABILITY_STATEMENT"),
        "VERIFY_PATIENT": (True, "ADVERTISED_BY_CAPABILITY_STATEMENT"),
        "GET_APPOINTMENTS": (True, "ADVERTISED_BY_CAPABILITY_STATEMENT"),
        "GET_AVAILABLE_APPOINTMENTS": (False, "NOT_ADVERTISED_SLOT_SEARCH_TYPE"),
        "GET_CLINICAL_CONTEXT": (True, "ADVERTISED_BY_CAPABILITY_STATEMENT"),
        "CREATE_APPOINTMENT": (False, "ADAPTER_READ_ONLY_BOUNDARY"),
        "UPDATE_APPOINTMENT": (False, "ADAPTER_READ_ONLY_BOUNDARY"),
        "RECORD_CALL_SUMMARY": (False, "ADAPTER_READ_ONLY_BOUNDARY"),
        "RECORD_TRIAGE_RESULT": (False, "ADAPTER_READ_ONLY_BOUNDARY"),
    }


def test_advertised_slot_still_reports_unmapped_availability_as_unsupported() -> None:
    with_slot = capability_statement(
        *OPENEMR_LIKE_CAPABILITIES["rest"][0]["resource"],
        resource_capability("Slot", ("search-type",), ("start", "status")),
    )
    target = adapter({}, with_slot)
    assert operations(target)["GET_AVAILABLE_APPOINTMENTS"] == (
        False,
        "SLOT_MAPPING_NOT_IMPLEMENTED",
    )


@pytest.mark.parametrize(
    ("metadata", "reason"),
    [
        (unreachable(), "EHR_UNREACHABLE"),
        (FhirResponse(status=503, body=None), "CAPABILITY_HTTP_503"),
        (ok({"resourceType": "OperationOutcome"}), "NOT_A_CAPABILITY_STATEMENT"),
        (ok(capability_statement(version="5.0.0")), "UNSUPPORTED_FHIR_VERSION"),
    ],
)
def test_failed_discovery_disables_every_operation(metadata: Any, reason: str) -> None:
    transport = ScriptedTransport({f"{BASE}/metadata": metadata})
    target = OpenEMRFhirAdapter.discover(config=OpenEMRConfig(), transport=transport)
    report = target.capabilities()
    assert not report.active
    assert not any(op.supported for op in report.operations)
    with pytest.raises(AdapterOperationUnavailable) as raised:
        target.get_patient("syn-a")
    assert raised.value.reason_code == reason
    assert transport.requests == [(f"{BASE}/metadata", {})]


def test_unadvertised_resource_fails_closed_without_request() -> None:
    patient_only = capability_statement(
        resource_capability("Patient", ("read", "search-type"), ("given", "family"))
    )
    target = adapter({}, patient_only)
    with pytest.raises(AdapterOperationUnavailable) as raised:
        target.get_clinical_context("syn-a")
    assert raised.value.reason_code == "NOT_ADVERTISED_CONDITION_SEARCH_TYPE"


def test_unadvertised_search_parameter_fails_closed() -> None:
    no_phone = capability_statement(
        resource_capability("Patient", ("read", "search-type"), ("given", "family"))
    )
    with pytest.raises(AdapterOperationUnavailable) as raised:
        adapter({}, no_phone).find_patient(PatientQuery(phone="555-0100"))
    assert raised.value.reason_code == "NOT_ADVERTISED_PATIENT_SEARCH_PARAM"


def test_availability_is_unavailable_over_documented_openemr_fhir() -> None:
    with pytest.raises(AdapterOperationUnavailable) as raised:
        adapter({}).get_available_appointments(
            earliest=datetime(2026, 1, 1, tzinfo=UTC),
            latest=datetime(2026, 1, 2, tzinfo=UTC),
            constraint_codes=(),
        )
    assert raised.value.operation_code == "GET_AVAILABLE_APPOINTMENTS"


# --- patient matching and identity ------------------------------------------


def test_find_patient_rechecks_prefix_matches_exactly() -> None:
    target = adapter({"Patient": ok(bundle(PATIENT_A, PATIENT_B))})
    candidates = target.find_patient(
        PatientQuery(given_name="avery", family_name="Synthetic", birth_date=date(1980, 1, 2))
    )
    assert [c.patient_id for c in candidates] == ["syn-a"]
    assert candidates[0].match_factor_codes == ("BIRTH_DATE", "FAMILY_NAME", "GIVEN_NAME")
    assert not candidates[0].ambiguous


def test_multiple_exact_matches_are_ambiguous() -> None:
    twin = synthetic_patient("syn-z", "Avery", "Synthetic", "1980-01-02", "555-0199")
    candidates = adapter({"Patient": ok(bundle(PATIENT_A, twin))}).find_patient(
        PatientQuery(given_name="Avery", family_name="Synthetic")
    )
    assert [c.patient_id for c in candidates] == ["syn-a", "syn-z"]
    assert all(c.ambiguous for c in candidates)


@pytest.mark.parametrize("paging", [{"next_link": True}, {"total": 7}])
def test_truncated_patient_search_is_ambiguous(paging: dict[str, Any]) -> None:
    candidates = adapter({"Patient": ok(bundle(PATIENT_A, **paging))}).find_patient(
        PatientQuery(phone="(555) 0100")
    )
    assert [c.patient_id for c in candidates] == ["syn-a"]
    assert candidates[0].ambiguous


def test_find_patient_sends_only_advertised_params() -> None:
    transport = ScriptedTransport(
        {f"{BASE}/metadata": ok(OPENEMR_LIKE_CAPABILITIES), f"{BASE}/Patient": ok(bundle())}
    )
    target = OpenEMRFhirAdapter.discover(config=OpenEMRConfig(), transport=transport)
    assert (
        target.find_patient(PatientQuery(family_name="Synthetic", birth_date=date(1980, 1, 2)))
        == ()
    )
    assert transport.requests[-1] == (
        f"{BASE}/Patient",
        {"family": "Synthetic", "birthdate": "1980-01-02"},
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "AUTHORIZATION_REJECTED"), (403, "AUTHORIZATION_REJECTED"), (500, "HTTP_500")],
)
def test_http_failures_raise_codes_without_bodies(status: int, reason: str) -> None:
    secretish = {"resourceType": "OperationOutcome", "issue": [{"diagnostics": "Avery Synthetic"}]}
    target = adapter({"Patient": FhirResponse(status=status, body=secretish)})
    with pytest.raises(AdapterOperationUnavailable) as raised:
        target.find_patient(PatientQuery(given_name="Avery"))
    assert raised.value.reason_code == reason
    assert "Avery" not in str(raised.value)


def test_network_failure_after_discovery_fails_closed() -> None:
    target = adapter({"Patient/syn-a": unreachable()})
    with pytest.raises(AdapterOperationUnavailable) as raised:
        target.get_patient("syn-a")
    assert raised.value.reason_code == "EHR_UNREACHABLE"


def test_get_patient_maps_missing_to_none_and_rejects_path_injection() -> None:
    target = adapter({"Patient/syn-a": ok(PATIENT_A)})
    assert target.get_patient("syn-a") is not None
    assert target.get_patient("syn-missing") is None
    with pytest.raises(AdapterOperationUnavailable) as raised:
        target.get_patient("../Patient?_id=1")
    assert raised.value.reason_code == "INVALID_RECORD_ID"


def test_get_patient_rejects_mismatched_resource() -> None:
    target = adapter({"Patient/syn-a": ok(PATIENT_B)})
    with pytest.raises(AdapterOperationUnavailable):
        target.get_patient("syn-a")


@pytest.mark.parametrize(
    ("factors", "verified"),
    [
        (("BIRTH_DATE", "FAMILY_NAME"), True),
        (("BIRTH_DATE", "BIRTH_DATE"), False),
        (("FAMILY_NAME", "GIVEN_NAME"), False),
        (("BIRTH_DATE", "UNKNOWN_FACTOR"), False),
    ],
)
def test_verification_requires_distinct_factors_including_birth_date(
    factors: tuple[str, ...], verified: bool
) -> None:
    result = adapter({"Patient/syn-a": ok(PATIENT_A)}).verify_patient("syn-a", factors)
    assert result.verified is verified
    assert result.requires_human_review is not verified


def test_verification_of_missing_patient_requires_review() -> None:
    result = adapter({}).verify_patient("syn-missing", ("BIRTH_DATE", "FAMILY_NAME"))
    assert not result.verified and result.requires_human_review


# --- appointments and clinical context --------------------------------------


def synthetic_appointment(
    appointment_id: str, start: str, end: str, overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Appointment",
        "id": appointment_id,
        "status": "booked",
        "start": start,
        "end": end,
        "participant": [
            {"actor": {"reference": "Patient/syn-a"}},
            {"actor": {"reference": "Practitioner/prov-1"}},
            {"actor": {"reference": "Location/loc-1"}},
        ],
    }
    resource.update(overrides or {})
    return resource


def test_existing_appointments_map_to_domain_values_in_order() -> None:
    later = synthetic_appointment(
        "appt-2", "2026-10-02T09:00:00+00:00", "2026-10-02T09:20:00+00:00"
    )
    earlier = synthetic_appointment("appt-1", "2026-10-01T09:00:00Z", "2026-10-01T09:20:00Z")
    result = adapter({"Appointment": ok(bundle(later, earlier))}).get_appointments("syn-a")
    assert [item.appointment_id for item in result] == ["appt-1", "appt-2"]
    first = result[0]
    assert first.status == "BOOKED"
    assert first.slot.provider_id == "prov-1" and first.slot.location_id == "loc-1"
    assert first.slot.kind is AvailabilityKind.OPEN
    assert first.slot.starts_at == datetime(2026, 10, 1, 9, tzinfo=UTC)


@pytest.mark.parametrize(
    "override",
    [
        {"start": "2026-10-01T09:00:00"},
        {"end": None},
        {"participant": [{"actor": {"reference": "Practitioner/prov-1"}}]},
    ],
)
def test_incomplete_appointments_fail_closed(override: dict[str, Any]) -> None:
    broken = synthetic_appointment(
        "appt-1", "2026-10-01T09:00:00Z", "2026-10-01T09:20:00Z", override
    )
    with pytest.raises(AdapterOperationUnavailable) as raised:
        adapter({"Appointment": ok(bundle(broken))}).get_appointments("syn-a")
    assert raised.value.reason_code == "APPOINTMENT_MAPPING_INCOMPLETE"


def coded(resource_type: str, element: str, code: str) -> dict[str, Any]:
    return {
        "resourceType": resource_type,
        "id": f"{resource_type}-{code}",
        element: {"coding": [{"system": "urn:synthetic", "code": code}]},
    }


def context_routes(**overrides: Any) -> dict[str, Any]:
    routes: dict[str, Any] = {
        "Condition": ok(bundle(coded("Condition", "code", "c2"), coded("Condition", "code", "c1"))),
        "MedicationRequest": ok(
            bundle(coded("MedicationRequest", "medicationCodeableConcept", "m1"))
        ),
        "AllergyIntolerance": ok(bundle()),
        "Observation": ok(bundle(coded("Observation", "code", "o1"))),
    }
    routes.update(overrides)
    return routes


def test_clinical_context_returns_sorted_system_qualified_codes() -> None:
    context = adapter(context_routes()).get_clinical_context("syn-a")
    assert context.condition_codes == ("urn:synthetic|c1", "urn:synthetic|c2")
    assert context.medication_codes == ("urn:synthetic|m1",)
    assert context.allergy_codes == ()
    assert context.observation_codes == ("urn:synthetic|o1",)


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"AllergyIntolerance": ok(bundle(next_link=True))}, "RESULTS_TRUNCATED"),
        ({"AllergyIntolerance": FhirResponse(status=403, body=None)}, "AUTHORIZATION_REJECTED"),
        ({"AllergyIntolerance": ok({"resourceType": "OperationOutcome"})}, "MALFORMED_RESPONSE"),
        (
            {"MedicationRequest": ok(bundle({"resourceType": "MedicationRequest", "id": "m"}))},
            "UNCODED_CLINICAL_ENTRY",
        ),
    ],
)
def test_partial_clinical_context_is_never_returned(override: dict[str, Any], reason: str) -> None:
    with pytest.raises(AdapterOperationUnavailable) as raised:
        adapter(context_routes(**override)).get_clinical_context("syn-a")
    assert raised.value.reason_code == reason


# --- writes stay outside the boundary ----------------------------------------


def test_writes_return_failed_results_and_never_touch_transport() -> None:
    from clinical_triage.domain.ehr import CallSummary

    transport = ScriptedTransport({f"{BASE}/metadata": ok(OPENEMR_LIKE_CAPABILITIES)})
    target = OpenEMRFhirAdapter.discover(config=OpenEMRConfig(), transport=transport)
    summary = CallSummary(
        call_id="call-1",
        synthetic_patient_id="SYN-PAT-A",
        disposition_code="ROUTINE",
        rationale_code="EXAMPLE",
        policy_id="p",
        policy_version="1",
    )
    result = target.record_call_summary(summary)
    assert not result.completed and result.failure_code == "ADAPTER_READ_ONLY_BOUNDARY"
    assert result.operation_id == target.record_call_summary(summary).operation_id
    assert transport.requests == [(f"{BASE}/metadata", {})]
    assert not hasattr(transport, "post") and not hasattr(transport, "put")
