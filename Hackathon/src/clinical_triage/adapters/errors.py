"""Provider-neutral adapter failure signal.

The EHR port returns values for reads, and an empty value (no candidates, no
allergies) must never stand in for "the provider could not answer". Adapters
raise this instead so callers fail toward human review.
"""


class AdapterOperationUnavailable(RuntimeError):
    """An adapter operation is unsupported, unauthorized, or failed; carries codes only."""

    def __init__(self, operation_code: str, reason_code: str) -> None:
        self.operation_code = operation_code
        self.reason_code = reason_code
        super().__init__(f"{operation_code}:{reason_code}")
