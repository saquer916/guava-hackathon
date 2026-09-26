# Engineering Fleet field test: Guava triage

## Baseline

- Repository baseline: `2b9aba8c336a780f5cb8153c18993b911e028c12`.
- Default branch: `master`; clean at inspection; one initial scaffold commit.
- GitHub state: no issues, pull requests, or workflows.
- Project: Python Guava SDK scaffold in `Hackathon/`, `guava-sdk==0.45.0`
  resolved by the existing lock, no tests or package source tree.
- Host at inspection: Docker Desktop and Compose available; Python 3.9 was too
  old for the declared `>=3.11`; `uv` and Guava CLI were absent.
- Baseline validation: locked dependencies resolved under uv-managed Python
  3.14 and `main.py` compiled. No behavioral test existed.
- Guava API credentials are unavailable and are not required for mock work.

## Tracking conventions

For each task record worker assignment and claim revisions, publish or sync
failures, stale evidence, CI attempts, review loops, collisions, merge
conflicts, manual interventions, and exact-SHA provenance. Time spent will be
classified as implementation, verification, or Fleet orchestration. Estimates
will be labeled and kept separate from exact timestamps/counts.

## Initial Fleet friction

- Fleet did not discover the nested `Hackathon/pyproject.toml`; verification
  checks required manual configuration.
- Fleet's generated CI does not install Python or uv. The workflow needs a
  repository-specific setup step after generation, which can be lost if the
  managed workflow is regenerated.
- Fleet tasks have no first-class dependency field. Dependencies are therefore
  duplicated in this document and GitHub Issue comments.
- The initial repository had no root `.gitignore`; running Python directly
  created a cache directory that had to be moved out before bootstrap.

## Event log

| Timestamp (UTC) | Event | Evidence / effect |
| --- | --- | --- |
| 2026-09-26 | Read-only baseline | Clean `master` at `2b9aba8`; no Issues/PRs/CI |
| 2026-09-26 | Tool setup | Installed uv 0.12.19 and Guava CLI 0.45.0; no login or deploy |
| 2026-09-26 | Fleet bootstrap started | Dedicated `fleet/bootstrap-guava-triage` branch |
