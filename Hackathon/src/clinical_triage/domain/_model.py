"""Shared validation behavior for immutable domain values."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Reject unknown fields and prevent mutation after validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
