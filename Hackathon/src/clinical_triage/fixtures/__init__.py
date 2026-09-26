"""Synthetic-only fixtures. Nothing in this package may hold real patient data."""

from clinical_triage.fixtures.ehr import FixedClock, SyntheticEHR
from clinical_triage.fixtures.synthetic import (
    FIXTURE_CLOCK,
    SyntheticFixtures,
    SyntheticPatient,
    build_fixtures,
    load_fixture_json,
    render_fixture_json,
)

__all__ = [
    "FIXTURE_CLOCK",
    "FixedClock",
    "SyntheticEHR",
    "SyntheticFixtures",
    "SyntheticPatient",
    "build_fixtures",
    "load_fixture_json",
    "render_fixture_json",
]
