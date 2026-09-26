"""Routing outcomes; these are not diagnoses."""

from enum import StrEnum


class Disposition(StrEnum):
    EMERGENCY = "EMERGENCY"
    URGENT_SAME_DAY = "URGENT_SAME_DAY"
    SOON = "SOON"
    ROUTINE = "ROUTINE"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    HUMAN_REVIEW = "HUMAN_REVIEW"
