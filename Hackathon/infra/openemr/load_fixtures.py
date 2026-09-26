"""Render, and optionally load, synthetic patients A-G into the LOCAL OpenEMR.

Default is a dry run that prints deterministic FHIR Patient documents. Writing
requires `--apply --i-approve-local-synthetic-write`, a loopback URL, a pinned
certificate, and a token in OPENEMR_ACCESS_TOKEN (never printed). Only Patient
resources are written; each is looked up by name and birth date first, so
repeated runs do not duplicate records. Conditions, medications, allergies,
and observations are not loaded: no documented OpenEMR FHIR create path.

  uv run --frozen python infra/openemr/load_fixtures.py render
  uv run --frozen python infra/openemr/load_fixtures.py apply --pin-sha256 <hex> \
      --apply --i-approve-local-synthetic-write
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import socket
import ssl
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).parent))

from probe import (  # noqa: E402
    DEFAULT_BASE_URL,
    ProbeRefused,
    pin_matches,
    require_loopback_https,
)

from clinical_triage.fixtures import SyntheticPatient, build_fixtures  # noqa: E402

IDENTIFIER_SYSTEM = "urn:synthetic:patient"
PATIENT_PATH = "/apis/default/fhir/Patient"


def patient_resource(patient: SyntheticPatient) -> dict[str, Any]:
    return {
        "resourceType": "Patient",
        "identifier": [{"system": IDENTIFIER_SYSTEM, "value": patient.synthetic_id}],
        "name": [{"use": "official", "family": patient.family_name, "given": [patient.given_name]}],
        "birthDate": patient.birth_date.isoformat(),
        "telecom": [{"system": "phone", "value": patient.phone, "use": "home"}],
        "gender": "unknown",
    }


def render_patients() -> list[dict[str, Any]]:
    return [patient_resource(patient) for patient in build_fixtures().patients]


def _pinned_request(
    host: str, port: int, pin: str, method: str, path: str, token: str, body: bytes | None
) -> tuple[int, Any]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=15) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            if not pin_matches(tls.getpeercert(binary_form=True), pin):
                raise ProbeRefused("server certificate does not match the pinned fingerprint")
            connection = http.client.HTTPConnection(host, port, timeout=15)
            connection.sock = tls
            headers = {
                "Accept": "application/fhir+json",
                "Authorization": f"Bearer {token}",
                "Host": host,
            }
            if body is not None:
                headers["Content-Type"] = "application/fhir+json"
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw_body = response.read()
            try:
                return response.status, json.loads(raw_body) if raw_body else None
            except ValueError:
                return response.status, None


def apply(base_url: str, pin: str) -> int:
    host, port = require_loopback_https(base_url)
    token = os.environ.get("OPENEMR_ACCESS_TOKEN", "")
    if not token.strip():
        print("REFUSED: OPENEMR_ACCESS_TOKEN is not set", file=sys.stderr)
        return 3
    for resource in render_patients():
        synthetic_id = resource["identifier"][0]["value"]
        # OpenEMR may not persist custom identifiers, so existence is checked by
        # the documented family/given/birthdate search parameters instead.
        query = urlencode(
            {
                "family": resource["name"][0]["family"],
                "given": resource["name"][0]["given"][0],
                "birthdate": resource["birthDate"],
            }
        )
        status, found = _pinned_request(
            host, port, pin, "GET", f"{PATIENT_PATH}?{query}", token, None
        )
        if status != 200 or not isinstance(found, dict):
            print(f"FAILED {synthetic_id}: lookup HTTP {status}", file=sys.stderr)
            return 2
        if found.get("entry"):
            print(f"SKIP {synthetic_id}: already present")
            continue
        status, _ = _pinned_request(
            host, port, pin, "POST", PATIENT_PATH, token, json.dumps(resource).encode()
        )
        if status not in {200, 201}:
            print(f"FAILED {synthetic_id}: create HTTP {status}", file=sys.stderr)
            return 2
        print(f"CREATED {synthetic_id}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("render", help="print deterministic FHIR Patient documents")
    writer = commands.add_parser("apply", help="write patients to the local OpenEMR")
    writer.add_argument("--pin-sha256", required=True)
    writer.add_argument("--apply", action="store_true")
    writer.add_argument("--i-approve-local-synthetic-write", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "render":
        print(json.dumps(render_patients(), indent=2, sort_keys=True))
        return 0
    if not (args.apply and args.i_approve_local_synthetic_write):
        print(
            "REFUSED: writing requires --apply and --i-approve-local-synthetic-write",
            file=sys.stderr,
        )
        return 3
    try:
        return apply(args.base_url, args.pin_sha256)
    except ProbeRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    except OSError as exc:
        print(f"FAILED: connection error ({type(exc).__name__})", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
