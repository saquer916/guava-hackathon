# Repository Instructions

This repository is managed with Engineering Fleet. These instructions extend
the global Fleet doctrine; they do not replace it.

## Architecture

- Codex is the architectural decision gate and final technical reviewer.
- Workers operate only within explicitly assigned scope.
- Record important decisions and their evidence in version control.

## Verification

- Run `fleet verify` before proposing or promoting changes.
- A worker claim is not proof. Treat only recorded deterministic verification
  or identified production evidence as proof.

## Repository-specific constraints

- This is a synthetic-only healthcare prototype. Never add real PHI, patient
  names, phone numbers, credentials, tokens, recordings, or transcripts.
- The system performs triage and routing. It must not diagnose, prescribe,
  independently declare a patient safe, or suppress escalation because of
  appointment capacity.
- Emergency rules must be explicit, deterministic, auditable, and marked for
  clinician review. An LLM statement or confidence score is never clinical
  proof.
- A triggered emergency rule terminates ordinary scheduling. Workers may not
  weaken this invariant or change clinical policy outside a scoped task.
- `Hackathon/main.py` and `Hackathon/guava.toml` are live-voice boundaries.
  Do not call, transfer, authenticate, deploy, or bind to Guava without explicit
  Codex and human approval.
- OpenEMR must remain local-only and synthetic. Do not expose it publicly,
  disable authentication, or write to a nonlocal EHR.
- Secrets belong in ignored environment files. Logs and audit records use
  stable synthetic IDs and must pass redaction tests.
- Guava and OpenEMR code implement adapters. Domain, triage, safety,
  conversation, scheduling, and audit modules must not import provider SDKs.
- Every meaningful unit of work uses a Fleet task/GitHub Issue, scoped worker
  claim, exact-SHA verification, PR, remote CI, and Codex review.
- Workers do not choose architecture, merge PRs, deploy, or edit outside their
  Fleet task boundary.

## Repository layout

- `Hackathon/src/clinical_triage/domain/` — provider-neutral models and ports.
- `Hackathon/src/clinical_triage/conversation/` — adaptive question state.
- `Hackathon/src/clinical_triage/safety/` — explicit red-flag policies.
- `Hackathon/src/clinical_triage/scheduling/` — appointment decision policy.
- `Hackathon/src/clinical_triage/adapters/` — Guava and EHR implementations.
- `Hackathon/src/clinical_triage/orchestration/` — call/tool coordination.
- `Hackathon/tests/` — deterministic unit, integration, and scenario tests.
- `Hackathon/infra/openemr/` — local-only OpenEMR configuration and fixtures.
- `docs/` — architecture, integration checkpoints, safety limits, and Fleet
  field-test evidence.

## Verification

- Use `uv` and the checked-in `Hackathon/uv.lock`; do not use ad-hoc global
  Python packages.
- Run `node /Users/sadius/engineering-fleet/dist/cli.js verify` from the
  repository root for the canonical lint, typecheck, test, and build sequence.
- Network, Guava, and OpenEMR tests must be opt-in and clearly separated from
  deterministic default verification.
