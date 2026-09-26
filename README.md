# Family Medicine Voice Triage Prototype

A synthetic-only, AI-assisted inbound-call triage prototype for a family
medicine practice, built to integrate Guava Voice AI and OpenEMR. It gathers a
small set of structured facts adaptively, applies explicit and auditable
**EXAMPLE_UNREVIEWED** routing rules, recommends a disposition, offers
appointments with a caller's explicit confirmation, and escalates to humans.

It is **not** a diagnostic system, does not prescribe, never declares a caller
safe, and is **not approved for clinical use**. Every patient, slot, and
answer in this repository is invented.

## Status (what actually runs)

| Path | Status | Evidence |
| --- | --- | --- |
| Synthetic call → voice mock → orchestrator → adaptive questions → facts → red-flag policy → disposition → scheduling → EHR port → audit | **Runs**, offline, deterministic | `tests/e2e`, `tests/orchestration`; `python -m clinical_triage.demo` |
| Emergency interrupts ordinary scheduling (including mid-offer) | **Runs** | `emergency-interruption` scenario; no booking, no EHR call after escalation |
| EHR = `SyntheticEHR` fixtures (booking + record writes in memory) | **Runs** | every scenario |
| Local OpenEMR (Docker, loopback-only, pinned digests) | **Observed live** once: healthy, CapabilityStatement captured | `docs/openemr-local.md` |
| Real OpenEMR adapter discovery against live OpenEMR | **Observed live** (opt-in test) | `tests/e2e/test_openemr_live.py` |
| Patient search / orchestrated call through live OpenEMR | **Not observed** (no OAuth token obtained) | `docs/openemr-local.md` |
| Booking or chart writes in OpenEMR | **Not possible** via FHIR (Appointment is read-only; no Slot/Schedule) | live CapabilityStatement |
| Guava voice | **Not connected**; adapter + mock only | `docs/guava-integration.md` |

## Quick start

```bash
cd Hackathon
python -m uv sync --frozen
python -m uv run --frozen python -m clinical_triage.demo --list
python -m uv run --frozen python -m clinical_triage.demo emergency-interruption
python -m uv run --frozen pytest -q
```

See `Hackathon/README.md` for all scenarios and the developer panel.

## Architecture

```text
Guava voice (not connected) / deterministic mock port
        │  InboundHandlers (provider-neutral)
CallOrchestrator ── Conversation reducer (pure, versioned; asks each question once)
        │        ── SafetyPolicyEngine (explicit rules; emergency first; fail closed)
        │        ── Triage result builder (confidence always None)
        │        ── Scheduling policy (ranking; overbook only suggested to staff)
        │        ── Audit sinks (operational telemetry ≠ protected decision records)
EHRAdapter port ── SyntheticEHR (offline) | OpenEMRFhirAdapter (read-only, capability-gated)
```

Provider SDKs stop at adapters: domain, conversation, safety, scheduling,
triage, and orchestration never import Guava or FHIR code. See
[architecture](docs/architecture.md) and the ADRs in `docs/adr/`.

## Operator runbook

| Task | Command / action |
| --- | --- |
| Run all checks (stand-in for `fleet verify`) | from `Hackathon/`: `ruff check .`, `mypy src tests`, `pytest -q`, `hatchling build` via `python -m uv run --frozen` |
| Run a simulated call | `python -m uv run --frozen python -m clinical_triage.demo <scenario>` |
| Keep audit output | add `--audit-dir audit` (writes `operational.jsonl` and `protected-decisions.jsonl`; git-ignored) |
| Start local OpenEMR | `docs/openemr-local.md`: fill the ignored `infra/openemr/.env`, then `infra/openemr/reset.sh --yes-destroy-local-synthetic-data` |
| Stop local OpenEMR | `docker compose -f Hackathon/infra/openemr/compose.yaml down` (add `--volumes` to delete synthetic data) |
| Probe OpenEMR | `python infra/openemr/probe.py --base-url https://localhost:<port> probe --pin-sha256 <pin>` |
| Live Guava | **Do not** run `main.py` against Guava without the checkpoint in `docs/guava-integration.md` |

If a scenario, test, or live observation ever shows scheduling continuing
after an emergency rule fired, stop and treat it as a safety defect.

## Documents

- [Security and PHI gaps](docs/security.md)
- [Clinical policy (EXAMPLE_UNREVIEWED) and clinician TODOs](docs/clinical-policy.md)
- [Guava integration checkpoint](docs/guava-integration.md)
- [Local OpenEMR runbook](docs/openemr-local.md) and [capabilities/gaps](docs/openemr-capabilities.md)
- [Task graph](docs/task-graph.md) and [Fleet field-test log](docs/fleet-field-test-guava.md)

Engineering work is coordinated through Fleet tasks (GitHub Issues #2–#13),
stacked pull requests, exact-SHA verification, remote CI, and Codex review.
Nothing is merged or deployed by workers; production deployment is prohibited
(`.fleet/config.json`).
