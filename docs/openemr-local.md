# Local synthetic OpenEMR runbook

Scope: Fleet task `guava-openemr-local` (Issue #3). This environment exists
only to exercise the EHR adapter against synthetic data on one developer
machine. It is not a deployment and must never hold real patient data.

## Boundaries

- **Loopback only.** The single published port binds `127.0.0.1:9300` →
  container `443`. Port 80 is not published. `reset.sh` stops the stack if
  Compose reports any other bind address.
- **Pinned images.** `openemr/openemr:8.4.1-2026-09-26` and `mariadb:11.8.9`,
  each pinned by content digest. OpenEMR rebuilds `8.4.1` daily; the dated tag
  and digest keep the environment reproducible. Update pins only in a reviewed
  Fleet task.
- **No committed secrets.** Every credential is `${VAR:?}` in
  `compose.yaml`; Compose refuses to start until the ignored
  `infra/openemr/.env` supplies it. `.env.example` has empty secret values.
- **Authentication stays on.** Only the FHIR API is enabled
  (`OPENEMR_SETTING_rest_fhir_api=1`). The standard REST API, portal API,
  system scopes, and OAuth2 password grant are explicitly off
  (`OPENEMR_SETTING_oauth_password_grant=0`).
- **Synthetic only.** Load nothing except the repository's synthetic fixtures.

Setting names come from OpenEMR `rel-840`
`src/Services/Globals/GlobalConnectorsEnum.php` and the Docker Hub image
documentation (`OPENEMR_SETTING_*`, `MYSQL_*`, `OE_USER`, `OE_PASS`).

## Prerequisites

- Docker Engine or Docker Desktop with Compose v2 (`docker compose`).
- Python 3.11+ for the probe (standard library only).

## Start or reset (deterministic)

```bash
cd Hackathon
cp infra/openemr/.env.example infra/openemr/.env   # then fill every blank value locally
infra/openemr/reset.sh --yes-destroy-local-synthetic-data
```

`reset.sh` validates the Compose file, deletes **only** this project's
volumes (`guava-openemr-local_openemr-db`, `guava-openemr-local_openemr-sites`),
recreates the stack, waits for container health (`--wait`, 600 s), and
verifies the loopback-only bind. Every reset starts from an empty database,
so repeated runs produce the same state before fixtures are loaded.

To stop without deleting data: `docker compose -f infra/openemr/compose.yaml down`.

## Health and CapabilityStatement probe

OpenEMR serves a self-signed certificate. The probe does not disable TLS
verification; it pins the exact certificate by SHA-256 fingerprint.

```bash
python infra/openemr/probe.py fingerprint
# Compare the fingerprint with the certificate inside the container before trusting it, e.g.
#   docker compose -f infra/openemr/compose.yaml exec openemr \
#     sh -c 'echo | openssl s_client -connect 127.0.0.1:443 2>/dev/null | openssl x509 -noout -fingerprint -sha256'
python infra/openemr/probe.py probe --pin-sha256 <fingerprint> --output infra/openemr/data/capabilities.json
```

The probe calls only `GET /apis/default/fhir/metadata`, which OpenEMR
documents as unauthenticated, and prints a sorted summary of FHIR version,
software version, and each resource's interactions and search parameters.
Exit codes: `0` healthy, `2` unhealthy/unreachable, `3` refused (non-loopback
URL, embedded credentials, or certificate pin mismatch).

`infra/openemr/data/` is git-ignored; capability reports are local evidence
and are summarized, not committed, in PRs.

Opt-in live test (skipped by default verification):

```bash
OPENEMR_LIVE_PIN_SHA256=<fingerprint> uv run --frozen pytest tests/integration -q
```

## Documented API surface relevant to the adapter

From OpenEMR `rel-840` `Documentation/api/FHIR_API.md` and `AUTHENTICATION.md`:

- FHIR base: `https://localhost:9300/apis/default/fhir`; CapabilityStatement at `/metadata`.
- OAuth2 base: `https://localhost:9300/oauth2/default/` (`registration`,
  `authorize`, `token`, `.well-known/openid-configuration`).
- Scopes use SMART v2 `.cruds` syntax, e.g. `user/Patient.rs`.
- `system/*` scopes require client-credentials with an asymmetric JWKS;
  this project does not request them.
- The documented resource list includes `Patient` and `Appointment` but **no
  `Slot` or `Schedule`**. Appointment availability is therefore not assumed to
  exist over FHIR; the adapter must gate it on the live CapabilityStatement.

## Evidence status

Offline invariants (loopback binds, digest pins, no credential defaults,
password grant off, confirmation-gated reset, probe URL refusal, pinning,
capability summarization) are covered by `tests/integration/test_openemr_local.py`.

### Observed live (2026-09-26, Windows 11 + Docker Desktop 29.8.0)

- Both pinned images pulled; Docker verified the pinned content digests
  (`openemr/openemr@sha256:1ebfa4ab…`, `mariadb@sha256:79d59758…`).
- `reset.sh` completed with `OPENEMR_HTTPS_PORT=9301` (9300 was already taken on
  that host). Compose `--wait` reported healthy after about 14 s; OpenEMR's own
  first-run auto-configuration log reported 41 s.
- Published binding: `127.0.0.1:9301->443/tcp` only; MariaDB is not published.
- The certificate fingerprint read from the host matched the in-container
  `openssl` fingerprint (the image does ship `openssl`). The certificate is
  self-signed with `CN=localhost` and `CA:TRUE`, so the exported PEM works as the
  CA bundle `HttpxFhirTransport` requires.
- `probe.py --base-url https://localhost:9301 probe --pin-sha256 <pin>` returned
  healthy. Summary of the live CapabilityStatement:
  - `fhirVersion` 4.0.1, status `active`, software version not reported.
  - 34 resource types. **No `Slot`, no `Schedule`.**
  - `Patient`: create, read, search-type, update; search params include `given`,
    `family`, `birthdate`, `phone`, `identifier`.
  - `Appointment`: read, search-type only (`_id`, `_lastUpdated`, `date`, `patient`).
  - `Encounter`, `Observation`: read, search-type. `DocumentReference`: create,
    read, search-type.
- The real `OpenEMRFhirAdapter.discover()` ran against it
  (`tests/e2e/test_openemr_live.py`, opt-in): active; `FIND_PATIENT` and
  `VERIFY_PATIENT` supported; availability, create, and update appointment
  unsupported.
- OAuth2 discovery advertises only `authorization_code` and `refresh_token`
  grants. Dynamic client registration succeeded; the new client was
  **disabled by default** (`oauth_clients.is_enabled = 0`) and had to be enabled
  by an administrator action (performed directly on the synthetic database).

### Not observed live

- **No access token was obtained.** A scripted authorization-code login with
  the `OE_USER`/`OE_PASS` administrator credential was rejected by the OAuth2
  login page ("verify the information you have entered is correct"). The
  cause is unresolved (candidates: OAuth2 login requiring a separately
  provisioned API user, or the credential not being applied to the OAuth2
  user store). Therefore no FHIR Patient search, no fixture loading
  (`load_fixtures.py apply`), and no orchestrated call through live OpenEMR
  has run.
- The opt-in test in `tests/integration/test_openemr_local.py` calls the probe
  without `--base-url`, so it always targets port 9300; on a host where 9300 is
  another stack it probes the wrong server. Use the probe CLI with
  `--base-url` instead until the test accepts the port.

## Known risks

- The self-signed certificate may be regenerated whenever the container is
  recreated; re-pin after every reset.
- `site_addr_oath` assumes the host port in `.env`; changing the port requires
  a reset so OAuth2 audience values match.
- Image digests are multi-architecture index digests (amd64, arm64).
