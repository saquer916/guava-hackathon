# Fleet task graph

Each node is a separate Fleet task and GitHub Issue. Dependencies are recorded
here and as GitHub Issue comments because Fleet Phase 2 has no first-class
dependency field.

```text
architecture-contracts
 |-- openemr-local ---- openemr-fhir-adapter -- synthetic-data --\
 |-- conversation-triage ----------------------------------------|
 |-- red-flag-policy --------------------------------------------|--> integration-orchestrator --> e2e-demo
 |-- scheduling-policy ------------------------------------------|
 `-- guava-adapter-mock -----------------------------------------/

e2e-demo --> documentation-readiness --> fleet-field-test-evaluation
```

## Tasks

1. `guava-architecture-contracts`: provider-neutral types, ports, configuration,
   audit schema, and ADRs. No clinical policy content.
2. `guava-openemr-local`: loopback-only OpenEMR Compose environment,
   CapabilityStatement probe, synthetic-only runbook, and health evidence.
3. `guava-openemr-fhir-adapter`: typed adapter, capability-driven behavior,
   least-privilege auth boundary, and clearly documented API gaps.
4. `guava-synthetic-data`: deterministic patients A-G and repeatable fixture
   loading without PHI.
5. `guava-conversation-triage`: separate clinical/conversation state, adaptive
   question selection, dispositions, and no-repeat behavior.
6. `guava-red-flag-policy`: example deterministic emergency rules, immediate
   scheduling interruption, auditable triggers, and clinician-review markers.
7. `guava-scheduling-policy`: ranked ordinary/alternative availability and
   human-approved overbook recommendations.
8. `guava-voice-adapter`: narrow Guava adapter plus deterministic mock; no
   invented endpoints or credentials.
9. `guava-integration-orchestrator`: high-level tools, call flow, audit effects,
   and adapter coordination.
10. `guava-e2e-demo`: CLI demonstration and six behavior-based scenarios,
    including emergency interruption and OpenEMR integration evidence.
11. `guava-documentation-readiness`: setup, Guava integration checkpoint,
    security/PHI gaps, clinical-policy TODOs, and operator runbooks.
12. `guava-fleet-evaluation`: candid Fleet metrics, collisions, failures,
    provenance, orchestration overhead, and recommended improvements.

After task 1, tasks 2, 5, 6, 7, and 8 may proceed in parallel. Tests belong to
each implementation task; task 10 proves the integrated path rather than
backfilling unit coverage at the end.
