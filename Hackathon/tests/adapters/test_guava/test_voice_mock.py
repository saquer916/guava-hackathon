import ast
from pathlib import Path

import pytest

from clinical_triage.adapters.voice_mock import (
    DeterministicInboundMock,
    MockCallPort,
    MockEvent,
    MockScriptError,
)
from clinical_triage.domain.voice import (
    AgentSpec,
    CallPort,
    EscalationRequest,
    FieldSpec,
    InboundHandlers,
    SessionEnded,
    TaskSpec,
    TransferResult,
    TransferTarget,
)

SPEC = AgentSpec(name=None, organization="Synthetic Clinic", purpose="synthetic")
TASK = TaskSpec(
    task_id="t1",
    objective="collect",
    checklist=(FieldSpec(key="a"), FieldSpec(key="b", required=False)),
)
NURSE = TransferTarget("nurse", "Nurse")


def handlers(log: list[str], *, escalate_on_complete: bool = False) -> InboundHandlers:
    def on_start(port: CallPort) -> None:
        log.append("start")
        port.set_task(TASK)

    def on_complete(port: CallPort) -> None:
        log.append(f"complete a={port.get_field('a')} b={port.get_field('b')}")
        if escalate_on_complete:
            request = EscalationRequest(
                call_id=port.id, script_id="S", trigger_rule_ids=("R",), target=NURSE
            )
            result = on_escalate(port, request)
            log.append(f"transfer accepted={result.accepted} code={result.failure_code}")
            if not result.accepted:
                port.hangup("FALLBACK")
        else:
            port.hangup("CLOSE")

    def on_escalate(port: CallPort, request: EscalationRequest) -> TransferResult:
        return port.transfer(request.target)

    def on_end(port: CallPort, ended: SessionEnded) -> None:
        log.append(f"end {ended.reason}")

    return InboundHandlers(
        on_call_start=on_start,
        on_question=lambda port, q: "FIXED_DEFLECTION",
        on_task_complete={"t1": on_complete},
        on_escalate=on_escalate,
        on_session_end=on_end,
    )


def run(script: tuple[MockEvent, ...], **kwargs: object) -> tuple[MockCallPort, list[str]]:
    log: list[str] = []
    mock = DeterministicInboundMock(**kwargs)  # type: ignore[arg-type]
    mock.bind(SPEC, handlers(log, escalate_on_complete="transfer_outcomes" in kwargs))
    return mock.run("call-1", script), log


def test_script_replays_explicit_values_only() -> None:
    port, log = run((MockEvent.start(), MockEvent.field("a", "X"), MockEvent.complete("t1")))
    assert log == ["start", "complete a=X b=None", "end bot-hangup"]
    assert port.hangups == ["CLOSE"]


def test_events_after_session_end_are_not_delivered() -> None:
    port, log = run(
        (MockEvent.start(), MockEvent.field("a", "X"), MockEvent.complete("t1"), MockEvent.start())
    )
    assert log.count("start") == 1


def test_caller_hangup_ends_session() -> None:
    _, log = run((MockEvent.start(), MockEvent.hangup()))
    assert log == ["start", "end user-hangup"]


def test_question_handler_answer_is_recorded_verbatim() -> None:
    port, _ = run((MockEvent.start(), MockEvent.question("is this a diagnosis?")))
    assert port.answers == ["FIXED_DEFLECTION"]


@pytest.mark.parametrize(
    "script",
    [
        (MockEvent.start(), MockEvent.field("not-in-task", 1)),
        (MockEvent.start(), MockEvent.complete("t1")),
        (MockEvent.start(), MockEvent.field("a", 1), MockEvent.complete("other")),
        (MockEvent.field("a", 1),),
    ],
)
def test_inconsistent_scripts_fail_loudly(script: tuple[MockEvent, ...]) -> None:
    with pytest.raises(MockScriptError):
        run(script)


def test_configured_transfer_ends_session_as_transfer() -> None:
    port, log = run(
        (MockEvent.start(), MockEvent.field("a", "X"), MockEvent.complete("t1")),
        transfer_outcomes={"nurse": None},
    )
    assert "transfer accepted=True code=None" in log
    assert log[-1] == "end bot-transfer"
    assert port.transfers == [NURSE]


def test_failed_transfer_is_reported_and_handler_can_fall_back() -> None:
    port, log = run(
        (MockEvent.start(), MockEvent.field("a", "X"), MockEvent.complete("t1")),
        transfer_outcomes={"nurse": "NO_ANSWER"},
    )
    assert "transfer accepted=False code=NO_ANSWER" in log
    assert port.hangups == ["FALLBACK"] and log[-1] == "end bot-hangup"


def test_mock_refuses_to_listen_on_a_phone_number() -> None:
    with pytest.raises(RuntimeError):
        DeterministicInboundMock().listen_phone("+15550100000")


def test_mock_imports_no_provider_sdk() -> None:
    source = Path(__file__).parents[3] / "src" / "clinical_triage" / "adapters" / "voice_mock.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    modules = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not any(m.split(".")[0] in {"guava", "httpx"} for m in modules)
