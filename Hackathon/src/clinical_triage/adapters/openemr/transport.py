"""Read-only HTTP transport for the OpenEMR FHIR API.

The transport exposes GET only. It never logs requests, tokens, or response
bodies, and it refuses to disable TLS verification; a self-signed local
certificate must be supplied as a CA bundle file.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

from clinical_triage.adapters.openemr.config import validate_loopback_https


@dataclass(frozen=True)
class FhirResponse:
    status: int
    body: Mapping[str, Any] | None


class TransportFailure(RuntimeError):
    """The request did not produce an HTTP response (network, TLS, timeout)."""


class FhirTransport(Protocol):
    def get(self, path: str, params: Mapping[str, str] | None = None) -> FhirResponse: ...


class AccessTokenProvider(Protocol):
    def access_token(self) -> str: ...


class StaticAccessToken:
    """Holds an operator-supplied short-lived token without ever rendering it."""

    def __init__(self, token: str) -> None:
        if not token.strip():
            raise ValueError("access token must not be empty")
        self._token = token

    def access_token(self) -> str:
        return self._token

    def __repr__(self) -> str:
        return "StaticAccessToken(<redacted>)"


class HttpxFhirTransport:
    def __init__(
        self,
        *,
        base_url: str,
        ca_bundle: Path,
        tokens: AccessTokenProvider,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not isinstance(ca_bundle, Path) or not ca_bundle.is_file():
            raise ValueError("a CA bundle file is required; TLS verification cannot be disabled")
        self._tokens = tokens
        self._client = httpx.Client(
            base_url=validate_loopback_https(base_url),
            verify=str(ca_bundle),
            timeout=timeout_seconds,
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        return "HttpxFhirTransport(<local>)"

    def get(self, path: str, params: Mapping[str, str] | None = None) -> FhirResponse:
        headers = {"Accept": "application/fhir+json"}
        if not path.endswith("/metadata"):
            headers["Authorization"] = f"Bearer {self._tokens.access_token()}"
        try:
            response = self._client.get(path, params=dict(params or {}), headers=headers)
        except httpx.HTTPError as exc:
            raise TransportFailure(type(exc).__name__) from None
        try:
            body = response.json()
        except ValueError:
            body = None
        return FhirResponse(
            status=response.status_code, body=body if isinstance(body, dict) else None
        )

    def close(self) -> None:
        self._client.close()
