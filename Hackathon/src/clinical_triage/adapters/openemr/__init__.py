"""Local-only, read-only OpenEMR FHIR R4 adapter."""

from clinical_triage.adapters.openemr.adapter import OpenEMRFhirAdapter
from clinical_triage.adapters.openemr.capabilities import FhirCapabilities
from clinical_triage.adapters.openemr.config import (
    READ_ONLY_SCOPES,
    OpenEMRConfig,
    UnsafeOpenEMRConfig,
)
from clinical_triage.adapters.openemr.transport import (
    FhirResponse,
    FhirTransport,
    HttpxFhirTransport,
    StaticAccessToken,
    TransportFailure,
)

__all__ = [
    "READ_ONLY_SCOPES",
    "FhirCapabilities",
    "FhirResponse",
    "FhirTransport",
    "HttpxFhirTransport",
    "OpenEMRConfig",
    "OpenEMRFhirAdapter",
    "StaticAccessToken",
    "TransportFailure",
    "UnsafeOpenEMRConfig",
]
