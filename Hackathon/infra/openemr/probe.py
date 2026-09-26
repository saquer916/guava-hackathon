"""Health and CapabilityStatement probe for the local synthetic OpenEMR.

Standard library only so it runs before `uv sync`. It refuses non-loopback
targets and pins the server's self-signed certificate by SHA-256 fingerprint
instead of disabling TLS verification. The CapabilityStatement endpoint
(`/apis/{site}/fhir/metadata`) is documented as unauthenticated, so the probe
never handles credentials.

Usage:
  python infra/openemr/probe.py fingerprint
  python infra/openemr/probe.py probe --pin-sha256 <hex> [--output report.json]
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import socket
import ssl
import sys
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "https://localhost:9300"
FHIR_METADATA_PATH = "/apis/default/fhir/metadata"
LOOPBACK_HOSTNAMES = frozenset({"localhost"})
EXIT_OK = 0
EXIT_UNHEALTHY = 2
EXIT_REFUSED = 3


class ProbeRefused(ValueError):
    """The probe was asked to do something outside the local-only boundary."""


def require_loopback_https(base_url: str) -> tuple[str, int]:
    parts = urlsplit(base_url)
    if parts.scheme != "https":
        raise ProbeRefused("OpenEMR probe requires https")
    if parts.username or parts.password:
        raise ProbeRefused("credentials must not appear in the probe URL")
    host = parts.hostname
    if host is None:
        raise ProbeRefused("probe URL requires a host")
    if host not in LOOPBACK_HOSTNAMES:
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ProbeRefused("OpenEMR probe only targets loopback addresses")
        except ValueError as exc:
            raise ProbeRefused("OpenEMR probe only targets loopback addresses") from exc
    if parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ProbeRefused("probe base URL must not contain a path, query, or fragment")
    return host, parts.port or 443


def normalize_fingerprint(value: str) -> str:
    cleaned = value.replace(":", "").strip().lower()
    if len(cleaned) != 64 or any(ch not in "0123456789abcdef" for ch in cleaned):
        raise ProbeRefused("certificate pin must be a 64-character SHA-256 hex digest")
    return cleaned


def certificate_fingerprint(der_certificate: bytes) -> str:
    return hashlib.sha256(der_certificate).hexdigest()


def pin_matches(der_certificate: bytes | None, expected_pin: str) -> bool:
    if not der_certificate:
        return False
    return certificate_fingerprint(der_certificate) == normalize_fingerprint(expected_pin)


def summarize_capability_statement(document: Mapping[str, Any]) -> dict[str, Any]:
    """Reduce a CapabilityStatement to the facts the adapter depends on."""

    if document.get("resourceType") != "CapabilityStatement":
        raise ValueError("response is not a FHIR CapabilityStatement")
    software = document.get("software") or {}
    resources: dict[str, dict[str, list[str]]] = {}
    for rest in document.get("rest") or ():
        if rest.get("mode") != "server":
            continue
        for resource in rest.get("resource") or ():
            resource_type = resource.get("type")
            if not isinstance(resource_type, str):
                continue
            interactions = sorted(
                {
                    str(item["code"])
                    for item in resource.get("interaction") or ()
                    if isinstance(item, Mapping) and "code" in item
                }
            )
            search_params = sorted(
                {
                    str(item["name"])
                    for item in resource.get("searchParam") or ()
                    if isinstance(item, Mapping) and "name" in item
                }
            )
            resources[resource_type] = {
                "interactions": interactions,
                "search_params": search_params,
            }
    return {
        "fhir_version": document.get("fhirVersion"),
        "status": document.get("status"),
        "software_name": software.get("name"),
        "software_version": software.get("version"),
        "resources": dict(sorted(resources.items())),
    }


def _pinned_https_get(
    host: str, port: int, path: str, expected_pin: str, timeout: float
) -> tuple[int, bytes]:
    # Hostname/CA validation is replaced by an exact certificate pin: the
    # request is only sent after the peer certificate matches the operator pin.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            if not pin_matches(tls.getpeercert(binary_form=True), expected_pin):
                raise ProbeRefused("server certificate does not match the pinned fingerprint")
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connection.sock = tls
            connection.request(
                "GET", path, headers={"Accept": "application/fhir+json", "Host": host}
            )
            response = connection.getresponse()
            return response.status, response.read()


def _fetch_fingerprint(host: str, port: int) -> str:
    pem = ssl.get_server_certificate((host, port))
    return certificate_fingerprint(ssl.PEM_cert_to_DER_cert(pem))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fingerprint", help="print the server certificate SHA-256 pin")
    probe = commands.add_parser("probe", help="check health and summarize capabilities")
    probe.add_argument("--pin-sha256", required=True)
    probe.add_argument("--timeout", type=float, default=10.0)
    probe.add_argument("--output")
    args = parser.parse_args(argv)

    try:
        host, port = require_loopback_https(args.base_url)
        if args.command == "fingerprint":
            print(_fetch_fingerprint(host, port))
            return EXIT_OK
        status, body = _pinned_https_get(
            host, port, FHIR_METADATA_PATH, args.pin_sha256, args.timeout
        )
    except ProbeRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except OSError as exc:
        print(f"UNHEALTHY: connection failed ({type(exc).__name__})", file=sys.stderr)
        return EXIT_UNHEALTHY

    if status != 200:
        print(f"UNHEALTHY: metadata returned HTTP {status}", file=sys.stderr)
        return EXIT_UNHEALTHY
    try:
        report = summarize_capability_statement(json.loads(body))
    except ValueError as exc:
        print(f"UNHEALTHY: {exc}", file=sys.stderr)
        return EXIT_UNHEALTHY
    rendered = json.dumps({"healthy": True, "capabilities": report}, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    print(rendered)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
