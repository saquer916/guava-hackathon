"""Local-only, read-only OpenEMR FHIR connection settings."""

import ipaddress
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

LOOPBACK_HOSTNAMES = frozenset({"localhost"})

# SMART v2 scope: context/Resource.permissions, e.g. user/Patient.rs
_RESOURCE_SCOPE = re.compile(r"^(patient|user|system)/([A-Za-z*]+)\.([cruds]+|read|write|\*)$")
_NON_RESOURCE_SCOPES = frozenset({"openid", "fhirUser", "api:fhir"})

# The only resources and permissions this adapter reads. Nothing else is requested.
READ_ONLY_SCOPES: tuple[str, ...] = (
    "openid",
    "api:fhir",
    "user/Patient.rs",
    "user/Appointment.rs",
    "user/Condition.rs",
    "user/MedicationRequest.rs",
    "user/AllergyIntolerance.rs",
    "user/Observation.rs",
)


class UnsafeOpenEMRConfig(ValueError):
    """Configuration would leave the local, least-privilege boundary."""


def validate_loopback_https(base_url: str) -> str:
    parts = urlsplit(base_url)
    if parts.scheme != "https":
        raise UnsafeOpenEMRConfig("OpenEMR base URL must use https")
    if parts.username or parts.password:
        raise UnsafeOpenEMRConfig("credentials must not be embedded in the base URL")
    host = parts.hostname or ""
    if host not in LOOPBACK_HOSTNAMES:
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise UnsafeOpenEMRConfig("OpenEMR adapter only connects to loopback hosts")
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise UnsafeOpenEMRConfig("base URL must not contain a path, query, or fragment")
    return base_url.rstrip("/")


def validate_read_only_scopes(scopes: tuple[str, ...]) -> tuple[str, ...]:
    if len(scopes) != len(set(scopes)):
        raise UnsafeOpenEMRConfig("scopes must be unique")
    for scope in scopes:
        if scope in _NON_RESOURCE_SCOPES:
            continue
        match = _RESOURCE_SCOPE.match(scope)
        if match is None:
            raise UnsafeOpenEMRConfig(f"unsupported scope: {scope}")
        context, resource, permissions = match.groups()
        if context != "user":
            raise UnsafeOpenEMRConfig("only user-context scopes are permitted")
        if resource == "*":
            raise UnsafeOpenEMRConfig("wildcard resource scopes are not permitted")
        if permissions != "rs":
            raise UnsafeOpenEMRConfig("only read/search (.rs) permissions are permitted")
    return scopes


@dataclass(frozen=True)
class OpenEMRConfig:
    base_url: str = "https://localhost:9300"
    site: str = "default"
    scopes: tuple[str, ...] = READ_ONLY_SCOPES
    minimum_verification_factors: int = 2
    required_verification_factor_codes: tuple[str, ...] = ("BIRTH_DATE",)
    adapter_version: str = field(default="0.1.0")

    def __post_init__(self) -> None:
        validate_loopback_https(self.base_url)
        validate_read_only_scopes(self.scopes)
        if not re.fullmatch(r"[a-z0-9_-]+", self.site):
            raise UnsafeOpenEMRConfig("site must be a simple OpenEMR site identifier")
        if self.minimum_verification_factors < 2:
            raise UnsafeOpenEMRConfig("identity verification requires at least two factors")

    @property
    def fhir_base_path(self) -> str:
        return f"/apis/{self.site}/fhir"
