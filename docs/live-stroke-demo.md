# Focused live Guava stroke-emergency demo

This is the only live path in the current hackathon milestone. It uses one
existing synthetic OpenEMR patient and one deterministic emergency rule. It is
not a general triage system and must not be used with real patient data.

## Flow

1. Guava receives an inbound call on `GUAVA_AGENT_NUMBER`.
2. The caller supplies date of birth and phone number.
3. The read-only OpenEMR FHIR adapter verifies both factors and fetches small
   condition, medication, and observation summaries.
4. Guava asks when the vague symptoms began, whether the right arm is weak, and
   whether speech sounds unusual.
5. The local deterministic rule emits `EMERGENCY` only when both focal facts are
   affirmative. It never schedules.
6. The caller is told to call 911, have someone call for them, and not drive.
7. A JSONL audit record is written to `Hackathon/audit/stroke-emergency.jsonl`.

The structured audit contains `disposition`, `trigger`,
`scheduling_allowed`, synthetic patient ID, symptom fact IDs, call ID, and an
ISO timestamp. No transcript or raw caller statement is logged.

## Local run

1. Start the existing synthetic-only OpenEMR instance and ensure the patient ID
   is known.
2. Authenticate Guava with `guava login`, or export `GUAVA_API_KEY`.
3. Copy `.env.example` to an ignored `.env` and fill only synthetic/local values.
4. Set `GUAVA_AGENT_NUMBER` to the Guava inbound number you own.
5. Run from `Hackathon/`:

```sh
set -a
. .env
set +a
uv run python main.py
```

6. Call the number and use synthetic identity details. Say that you have felt
   weird for about 20 minutes. Answer yes to right-arm weakness and unusual
   speech. Confirm the caller hears the 911 instruction and inspect the last
   JSONL audit line.

There is intentionally no OpenEMR writeback in this milestone: a safe,
documented write capability has not been proven. The local audit is the
permanent demo artifact. Do not deploy or expose OpenEMR publicly.
