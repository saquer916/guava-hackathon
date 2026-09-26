"""Scripted FHIR transport and hand-authored synthetic payloads.

Payloads follow the shapes in OpenEMR rel-840 Documentation/api/FHIR_API.md.
They are not captures from a live server and contain only synthetic values.
"""

from collections.abc import Mapping
from typing import Any

from clinical_triage.adapters.openemr import FhirResponse, TransportFailure

BASE = "/apis/default/fhir"


def resource_capability(
    resource_type: str, interactions: tuple[str, ...], params: tuple[str, ...]
) -> dict[str, Any]:
    return {
        "type": resource_type,
        "interaction": [{"code": code} for code in interactions],
        "searchParam": [{"name": name, "type": "token"} for name in params],
    }


def capability_statement(*resources: dict[str, Any], version: str = "4.0.1") -> dict[str, Any]:
    return {
        "resourceType": "CapabilityStatement",
        "status": "active",
        "fhirVersion": version,
        "software": {"name": "OpenEMR", "version": "synthetic-test"},
        "rest": [{"mode": "server", "resource": list(resources)}],
    }


OPENEMR_LIKE_CAPABILITIES = capability_statement(
    resource_capability(
        "Patient",
        ("create", "update", "search-type", "read"),
        ("_id", "identifier", "name", "birthdate", "family", "given", "phone"),
    ),
    resource_capability("Appointment", ("read", "search-type"), ("_id", "patient", "date")),
    resource_capability("Condition", ("read", "search-type"), ("patient",)),
    resource_capability("MedicationRequest", ("read", "search-type"), ("patient",)),
    resource_capability("AllergyIntolerance", ("read", "search-type"), ("patient",)),
    resource_capability("Observation", ("read", "search-type"), ("patient", "category")),
)


def bundle(
    *resources: dict[str, Any], next_link: bool = False, total: int | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "resourceType": "Bundle",
        "type": "searchset",
        "entry": [{"resource": resource, "search": {"mode": "match"}} for resource in resources],
    }
    if total is not None:
        body["total"] = total
    if next_link:
        body["link"] = [{"relation": "next", "url": "https://localhost:9300/next"}]
    return body


def synthetic_patient(
    patient_id: str, given: str, family: str, birth_date: str, phone: str
) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "id": patient_id,
        "name": [{"family": family, "given": [given]}],
        "birthDate": birth_date,
        "telecom": [{"system": "phone", "value": phone}],
        "identifier": [{"system": "urn:synthetic", "value": f"SYN-{patient_id}"}],
    }


class ScriptedTransport:
    """Returns pre-registered responses; records every request; never writes."""

    def __init__(self, routes: Mapping[str, FhirResponse | Exception]) -> None:
        self._routes = dict(routes)
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, path: str, params: Mapping[str, str] | None = None) -> FhirResponse:
        self.requests.append((path, dict(params or {})))
        route = self._routes.get(path)
        if route is None:
            return FhirResponse(status=404, body={"resourceType": "OperationOutcome"})
        if isinstance(route, Exception):
            raise route
        return route


def ok(body: dict[str, Any]) -> FhirResponse:
    return FhirResponse(status=200, body=body)


def unreachable() -> TransportFailure:
    return TransportFailure("ConnectError")
