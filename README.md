# Family Medicine Voice Triage Prototype

This repository is building a synthetic-only, AI-assisted inbound-call triage
prototype using Guava Voice AI and OpenEMR. It gathers structured history,
applies transparent safety policies, recommends a routing disposition, and
supports human-controlled scheduling decisions. It is not a diagnostic system
and is not approved for clinical use.

The existing Guava scaffold remains under `Hackathon/`. Engineering work is
coordinated through Fleet-backed GitHub Issues, branches, pull requests,
exact-SHA verification, remote CI, and Codex review.

See [the architecture](docs/architecture.md), [task graph](docs/task-graph.md),
and [Fleet field-test log](docs/fleet-field-test-guava.md).
