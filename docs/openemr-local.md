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

- Offline invariants (loopback binds, digest pins, no credential defaults,
  password grant off, confirmation-gated reset, probe URL refusal, pinning,
  capability summarization) are covered by `tests/integration/test_openemr_local.py`.
- **Not yet observed live.** The machine that produced this task had no
  Docker runtime, so the stack has not been started, the image healthcheck has
  not been observed, and no live CapabilityStatement has been captured. The
  first operator with Docker should run the reset and probe above and attach
  the probe summary to Issue #3.

## Known risks

- The self-signed certificate may be regenerated whenever the container is
  recreated; re-pin after every reset. The in-container `openssl` cross-check
  above assumes the image ships `openssl`; this has not been observed yet.
- `site_addr_oath` assumes the host port in `.env`; changing the port requires
  a reset so OAuth2 audience values match.
- Image digests are multi-architecture index digests (amd64, arm64).
