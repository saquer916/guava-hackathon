"""Translate provider-neutral voice specs into documented Guava SDK objects.

Only documented `guava.Field` parameters and `guava.Say` are used. `searchable`
fields are refused because they need an `on_search_query` handler, which the
provider-neutral voice port does not expose.
"""

from typing import Literal, cast

import guava

from clinical_triage.domain.voice import ChecklistItem, FieldSpec, SaySpec, SessionEnded, TaskSpec

TerminationReason = Literal["user-hangup", "bot-hangup", "bot-failure", "bot-transfer"]
_KNOWN_TERMINATIONS: frozenset[str] = frozenset(
    {"user-hangup", "bot-hangup", "bot-failure", "bot-transfer"}
)


class UnsupportedVoiceSpec(ValueError):
    """A spec asks for Guava behavior outside the documented, approved surface."""


def to_guava_field(spec: FieldSpec) -> guava.Field:
    if spec.searchable:
        raise UnsupportedVoiceSpec("searchable fields require on_search_query, not in the port")
    if spec.choices and spec.field_type not in {"multiple_choice", "calendar_slot"}:
        raise UnsupportedVoiceSpec("choices are only valid for multiple_choice or calendar_slot")
    return guava.Field(
        key=spec.key,
        description=spec.description,
        question=spec.question,
        field_type=spec.field_type,
        required=spec.required,
        choices=list(spec.choices),
        sensitive=spec.sensitive,
    )


def to_guava_item(item: ChecklistItem) -> guava.Field | guava.Say | str:
    if isinstance(item, FieldSpec):
        return to_guava_field(item)
    if isinstance(item, SaySpec):
        return guava.Say(item.text)  # type: ignore[no-untyped-call]
    return item


def to_guava_checklist(task: TaskSpec) -> list[guava.Field | guava.Say | str]:
    keys = [item.key for item in task.checklist if isinstance(item, FieldSpec)]
    if len(keys) != len(set(keys)):
        raise UnsupportedVoiceSpec("field keys must be unique within a task")
    if not task.objective and not task.checklist:
        raise UnsupportedVoiceSpec("a task requires an objective or checklist")
    return [to_guava_item(item) for item in task.checklist]


def to_session_ended(termination_reason: str) -> SessionEnded:
    """Map documented termination reasons; anything else (e.g. voicemail) is a failure."""

    if termination_reason in _KNOWN_TERMINATIONS:
        return SessionEnded(reason=cast(TerminationReason, termination_reason))
    return SessionEnded(reason="bot-failure")
