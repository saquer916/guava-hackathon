"""Offline invariants for the local-only OpenEMR environment, plus an opt-in live probe."""

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

HACKATHON = Path(__file__).parents[2]
INFRA = HACKATHON / "infra" / "openemr"
COMPOSE = (INFRA / "compose.yaml").read_text(encoding="utf-8")


def _load_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("openemr_probe", INFRA / "probe.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

# Excerpt of the example response in OpenEMR rel-840 Documentation/api/FHIR_API.md.
# Hand-copied documentation shape, not a capture from a live server.
DOCUMENTED_CAPABILITY_EXCERPT: dict[str, Any] = {
    "resourceType": "CapabilityStatement",
    "status": "active",
    "fhirVersion": "4.0.1",
    "software": {"name": "OpenEMR", "version": "7.0.4"},
    "rest": [
        {
            "mode": "server",
            "resource": [
                {
                    "type": "Patient",
                    "interaction": [
                        {"code": "create"},
                        {"code": "update"},
                        {"code": "search-type"},
                        {"code": "read"},
                    ],
                    "searchParam": [
                        {"name": "birthdate", "type": "date"},
                        {"name": "family", "type": "string"},
                        {"name": "given", "type": "string"},
                        {"name": "identifier", "type": "token"},
                        {"name": "phone", "type": "token"},
                    ],
                }
            ],
        }
    ],
}


def test_every_published_port_is_loopback_only() -> None:
    quoted_list_items = re.compile(r"\s+- \"[\d$]")
    published = [
        line.strip()
        for line in COMPOSE.splitlines()
        if quoted_list_items.match(line) and ":" in line
    ]
    assert published, "OpenEMR must publish its HTTPS port for the local probe"
    for line in published:
        assert line.startswith('- "127.0.0.1:'), line
    assert "network_mode: host" not in COMPOSE
    assert ":80\"" not in COMPOSE


def test_images_are_pinned_by_dated_tag_and_digest() -> None:
    images = re.findall(r"^\s+image:\s*(\S+)$", COMPOSE, flags=re.MULTILINE)
    assert len(images) == 2
    for image in images:
        name, _, digest = image.partition("@")
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", digest), image
        assert not name.endswith(":latest") and ":" in name, image
    assert any(image.startswith("openemr/openemr:8.4.1-2026-09-26@") for image in images)


def test_credentials_have_no_committed_defaults() -> None:
    secret_keys = ("MARIADB_ROOT_PASSWORD", "MYSQL_ROOT_PASS", "MYSQL_PASS", "OE_PASS", "OE_USER")
    for key in secret_keys:
        match = re.search(rf"^\s+{key}:\s*(.+)$", COMPOSE, flags=re.MULTILINE)
        assert match, key
        assert re.fullmatch(r"\$\{[A-Z_]+:\?[^}]+\}", match.group(1).strip()), key

    example = (INFRA / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if "PASSWORD=" in line and not line.lstrip().startswith("#"):
            assert line.split("=", 1)[1] == "", line


def test_env_file_is_ignored_by_git() -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(INFRA / ".env")],
        cwd=HACKATHON,
        check=False,
    )
    assert result.returncode == 0


def test_only_the_fhir_api_is_enabled_and_password_grant_is_off() -> None:
    settings = dict(re.findall(r"OPENEMR_SETTING_(\w+):\s*\"([^\"]*)\"", COMPOSE))
    assert settings["rest_fhir_api"] == "1"
    assert settings["oauth_password_grant"] == "0"
    assert settings["rest_api"] == "0"
    assert settings["rest_portal_api"] == "0"
    assert settings["rest_system_scopes_api"] == "0"
    assert settings["site_addr_oath"].startswith("https://localhost:")


def test_reset_requires_explicit_destruction_flag_and_checks_loopback() -> None:
    script = (INFRA / "reset.sh").read_text(encoding="utf-8")
    assert "--yes-destroy-local-synthetic-data" in script
    assert "127.0.0.1:*" in script
    assert "down --volumes" in script


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:9300",
        "https://10.0.0.5:9300",
        "https://openemr.example.com",
        "https://user:pw@localhost:9300",
        "https://localhost:9300/apis/default/fhir",
        "https://0.0.0.0:9300",
    ],
)
def test_probe_refuses_non_loopback_or_unsafe_urls(url: str) -> None:
    with pytest.raises(probe.ProbeRefused):
        probe.require_loopback_https(url)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://localhost:9300", ("localhost", 9300)),
        ("https://127.0.0.1:9300/", ("127.0.0.1", 9300)),
        ("https://[::1]", ("::1", 443)),
    ],
)
def test_probe_accepts_loopback_https(url: str, expected: tuple[str, int]) -> None:
    assert probe.require_loopback_https(url) == expected


def test_certificate_pin_requires_exact_match() -> None:
    der = b"synthetic-certificate-bytes"
    pin = probe.certificate_fingerprint(der)
    colon_pin = ":".join(pin[i : i + 2] for i in range(0, 64, 2)).upper()
    assert probe.pin_matches(der, pin)
    assert probe.pin_matches(der, colon_pin)
    assert not probe.pin_matches(b"other", pin)
    assert not probe.pin_matches(None, pin)
    with pytest.raises(probe.ProbeRefused):
        probe.normalize_fingerprint("abc")


def test_capability_summary_is_deterministic() -> None:
    summary = probe.summarize_capability_statement(DOCUMENTED_CAPABILITY_EXCERPT)
    assert summary == {
        "fhir_version": "4.0.1",
        "status": "active",
        "software_name": "OpenEMR",
        "software_version": "7.0.4",
        "resources": {
            "Patient": {
                "interactions": ["create", "read", "search-type", "update"],
                "search_params": ["birthdate", "family", "given", "identifier", "phone"],
            }
        },
    }


def test_capability_summary_rejects_other_resources() -> None:
    with pytest.raises(ValueError, match="CapabilityStatement"):
        probe.summarize_capability_statement({"resourceType": "OperationOutcome"})


def test_probe_cli_refuses_remote_target_without_network() -> None:
    assert probe.main(["--base-url", "https://example.com", "fingerprint"]) == probe.EXIT_REFUSED


@pytest.mark.skipif(
    not os.environ.get("OPENEMR_LIVE_PIN_SHA256"),
    reason="opt-in: set OPENEMR_LIVE_PIN_SHA256 after starting local OpenEMR",
)
def test_live_local_capability_statement() -> None:  # pragma: no cover - opt-in only
    result = subprocess.run(
        [
            sys.executable,
            str(INFRA / "probe.py"),
            "probe",
            "--pin-sha256",
            os.environ["OPENEMR_LIVE_PIN_SHA256"],
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert '"Patient"' in result.stdout
