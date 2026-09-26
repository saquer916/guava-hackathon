"""CapabilityStatement discovery and per-operation gates.

Operations are enabled only when the live server advertises every FHIR
interaction and search parameter they use. Anything not advertised, and every
write, is reported unsupported with a stable reason code.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from clinical_triage.domain.ehr import AdapterOperationCapability


@dataclass(frozen=True)
class ResourceCapability:
    interactions: frozenset[str]
    search_params: frozenset[str]


@dataclass(frozen=True)
class FhirCapabilities:
    fhir_version: str
    resources: Mapping[str, ResourceCapability]

    @classmethod
    def from_statement(cls, document: Mapping[str, Any]) -> "FhirCapabilities":
        if document.get("resourceType") != "CapabilityStatement":
            raise ValueError("NOT_A_CAPABILITY_STATEMENT")
        version = document.get("fhirVersion")
        if not isinstance(version, str) or not version.startswith("4.0."):
            raise ValueError("UNSUPPORTED_FHIR_VERSION")
        resources: dict[str, ResourceCapability] = {}
        for rest in document.get("rest") or ():
            if not isinstance(rest, Mapping) or rest.get("mode") != "server":
                continue
            for resource in rest.get("resource") or ():
                if not isinstance(resource, Mapping):
                    continue
                name = resource.get("type")
                if not isinstance(name, str):
                    continue
                resources[name] = ResourceCapability(
                    interactions=frozenset(
                        str(item["code"])
                        for item in resource.get("interaction") or ()
                        if isinstance(item, Mapping) and isinstance(item.get("code"), str)
                    ),
                    search_params=frozenset(
                        str(item["name"])
                        for item in resource.get("searchParam") or ()
                        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
                    ),
                )
        return cls(fhir_version=version, resources=resources)

    def supports(self, resource: str, interaction: str, params: tuple[str, ...] = ()) -> bool:
        capability = self.resources.get(resource)
        if capability is None or interaction not in capability.interactions:
            return False
        return set(params) <= capability.search_params


@dataclass(frozen=True)
class ReadRequirement:
    resource: str
    interaction: str
    search_params: tuple[str, ...] = ()


# Operation codes are provider-neutral names for EHRAdapter methods.
FIND_PATIENT = "FIND_PATIENT"
GET_PATIENT = "GET_PATIENT"
VERIFY_PATIENT = "VERIFY_PATIENT"
GET_APPOINTMENTS = "GET_APPOINTMENTS"
GET_AVAILABLE_APPOINTMENTS = "GET_AVAILABLE_APPOINTMENTS"
GET_CLINICAL_CONTEXT = "GET_CLINICAL_CONTEXT"
CREATE_APPOINTMENT = "CREATE_APPOINTMENT"
UPDATE_APPOINTMENT = "UPDATE_APPOINTMENT"
RECORD_CALL_SUMMARY = "RECORD_CALL_SUMMARY"
RECORD_TRIAGE_RESULT = "RECORD_TRIAGE_RESULT"

CLINICAL_CONTEXT_RESOURCES = ("Condition", "MedicationRequest", "AllergyIntolerance", "Observation")

READ_REQUIREMENTS: Mapping[str, tuple[ReadRequirement, ...]] = {
    # Patient search parameters are checked per query factor at call time.
    FIND_PATIENT: (ReadRequirement("Patient", "search-type"),),
    GET_PATIENT: (ReadRequirement("Patient", "read"),),
    VERIFY_PATIENT: (ReadRequirement("Patient", "read"),),
    GET_APPOINTMENTS: (ReadRequirement("Appointment", "search-type", ("patient",)),),
    # OpenEMR documents no Slot/Schedule resource; this stays unsupported unless advertised.
    GET_AVAILABLE_APPOINTMENTS: (ReadRequirement("Slot", "search-type", ("start", "status")),),
    GET_CLINICAL_CONTEXT: tuple(
        ReadRequirement(resource, "search-type", ("patient",))
        for resource in CLINICAL_CONTEXT_RESOURCES
    ),
}

# Advertised-but-unmapped reads stay unsupported rather than guessing a mapping.
NOT_IMPLEMENTED: Mapping[str, str] = {GET_AVAILABLE_APPOINTMENTS: "SLOT_MAPPING_NOT_IMPLEMENTED"}

# Writes are outside this adapter's least-privilege boundary regardless of what
# the server advertises. Enabling any of them requires a Codex-approved task.
READ_ONLY_BOUNDARY = "ADAPTER_READ_ONLY_BOUNDARY"
WRITE_OPERATIONS = (
    CREATE_APPOINTMENT,
    UPDATE_APPOINTMENT,
    RECORD_CALL_SUMMARY,
    RECORD_TRIAGE_RESULT,
)


def evaluate_operations(
    capabilities: FhirCapabilities | None, discovery_failure: str | None
) -> tuple[AdapterOperationCapability, ...]:
    results: list[AdapterOperationCapability] = []
    for operation, requirements in READ_REQUIREMENTS.items():
        if capabilities is None:
            reason = discovery_failure or "CAPABILITIES_NOT_DISCOVERED"
            supported = False
        else:
            missing = [
                requirement
                for requirement in requirements
                if not capabilities.supports(
                    requirement.resource, requirement.interaction, requirement.search_params
                )
            ]
            if missing:
                supported = False
                reason = (
                    f"NOT_ADVERTISED_{missing[0].resource.upper()}_{_code(missing[0].interaction)}"
                )
            elif operation in NOT_IMPLEMENTED:
                supported = False
                reason = NOT_IMPLEMENTED[operation]
            else:
                supported = True
                reason = "ADVERTISED_BY_CAPABILITY_STATEMENT"
        results.append(
            AdapterOperationCapability(
                operation_code=operation, supported=supported, reason_code=reason
            )
        )
    for operation in WRITE_OPERATIONS:
        results.append(
            AdapterOperationCapability(
                operation_code=operation, supported=False, reason_code=READ_ONLY_BOUNDARY
            )
        )
    return tuple(results)


def _code(interaction: str) -> str:
    return interaction.upper().replace("-", "_")
