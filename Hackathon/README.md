# Hackathon: synthetic family-medicine call triage

A provider-neutral inbound-call triage and routing prototype. It gathers a
small set of structured facts, applies explicit **EXAMPLE_UNREVIEWED** routing
rules, offers appointments, and escalates. It does **not** diagnose, prescribe,
or declare anyone safe. Every patient, slot, and answer here is synthetic.

## Setup

```bash
cd Hackathon
python -m uv sync --frozen          # uv 0.12.19; Python 3.12 matches CI
```

## Simulated calls (no Guava, no OpenEMR needed)

```bash
python -m uv run --frozen python -m clinical_triage.demo --list
python -m uv run --frozen python -m clinical_triage.demo                  # all scenarios
python -m uv run --frozen python -m clinical_triage.demo emergency-interruption
python -m uv run --frozen python -m clinical_triage.demo --json routine
python -m uv run --frozen python -m clinical_triage.demo --audit-dir audit
```

Each run prints the call transcript and a **developer-only** diagnostic panel:
patient match, facts recorded, deciding rules, disposition, appointment
action, EHR operations, human decisions, and errors. The panel exposes policy
internals and must never be shown to a caller.

What the demo is, and is not:

- Caller turns are **scripted**. Each turn supplies the structured field
  values a voice layer would have extracted, plus a display-only line. Nothing
  performs speech recognition or language understanding.
- The voice side is the SDK-free mock port (`adapters/voice_mock.py`), driven
  through the same `InboundHandlers` the Guava adapter binds.
- The EHR is `SyntheticEHR`, an **offline fixture EHR**. It is not OpenEMR.
  Booking and record writes are enabled only for this in-memory EHR.
- `--audit-dir` writes `operational.jsonl` (IDs and codes only) and
  `protected-decisions.jsonl` (structured facts) to separate files. Both are
  git-ignored when written directly under `Hackathon/audit/` (`.gitignore` matches `Hackathon/audit/*.jsonl` only).

| Scenario | What it shows |
| --- | --- |
| `routine` | Follow-up visit; no symptom questions; routine slot booked |
| `adaptive-clarification` | Mild symptom adds a temperature question; an implausible reading is clarified once |
| `urgent-same-day` | Severe symptom routes to same-day and books it |
| `emergency-interruption` | A red-flag correction during an active offer withdraws it and escalates; no booking or further EHR call |
| `emergency-at-screening` | A red flag during screening escalates before any EHR call |
| `human-review-fallback` | A critical fact can't be collected; not asked twice; handed to a nurse |
| `scheduling-failure` | Expired offer, one retry, slot taken after the snapshot; handed to staff |
| `schedule-squeeze` | No normal same-day slot; alternative offered; overbook review surfaced, never forced |
| `identity-uncertain` | Name shared by two synthetic patients, birth date matches neither; no record chosen |

## Verification

```bash
python -m uv run --frozen ruff check .
python -m uv run --frozen mypy src tests
python -m uv run --frozen pytest -q
python -m uv run --frozen hatchling build
```

Default tests are offline and deterministic. Live OpenEMR tests are opt-in
(see `docs/openemr-local.md` and `tests/e2e/test_openemr_live.py`).

## Live boundaries

`main.py` and `guava.toml` are the live Guava entry point and are unchanged.
Binding a phone number, transferring a call, or authenticating to Guava needs
explicit Codex and human approval (`docs/guava-integration.md`).
