"""CLI: `uv run --frozen python -m clinical_triage.demo [SCENARIO ...] [--json]`."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from clinical_triage.audit import InMemoryAuditSink, JsonlAuditSink
from clinical_triage.demo.panel import BANNER, render, summarize
from clinical_triage.demo.scenarios import SCENARIOS, run_scenario, scenario


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m clinical_triage.demo", description=BANNER)
    parser.add_argument(
        "scenarios", nargs="*", help="scenario IDs (default: all)", metavar="SCENARIO"
    )
    parser.add_argument("--list", action="store_true", help="list scenario IDs and exit")
    parser.add_argument("--json", action="store_true", help="print structured summaries")
    parser.add_argument(
        "--audit-dir",
        type=Path,
        help="also write operational.jsonl and protected-decisions.jsonl here",
    )
    args = parser.parse_args(argv)
    if args.list:
        for item in SCENARIOS:
            print(f"{item.scenario_id:<24} {item.title}")
        return 0
    try:
        selected = [scenario(s) for s in args.scenarios] if args.scenarios else list(SCENARIOS)
    except KeyError as exc:
        parser.error(f"unknown scenario {exc.args[0]!r}; use --list")
    summaries = []
    if not args.json:
        print(BANNER)
    for item in selected:
        sink = InMemoryAuditSink()
        run = run_scenario(item, audit=sink)
        if args.audit_dir is not None:
            _write_audit(sink, args.audit_dir)
        if args.json:
            summaries.append(summarize(run))
        else:
            print(render(run))
    if args.json:
        json.dump(summaries, sys.stdout, indent=2)
        print()
    return 0


def _write_audit(sink: InMemoryAuditSink, directory: Path) -> None:
    jsonl = JsonlAuditSink(
        operational_path=directory / "operational.jsonl",
        protected_path=directory / "protected-decisions.jsonl",
    )
    for event in sink.operational_events:
        jsonl.emit_operational_event(event)
    for record in sink.audit_records:
        jsonl.append_audit_record(record)
    for decision in sink.decision_records:
        jsonl.append_decision_record(decision)


if __name__ == "__main__":
    raise SystemExit(main())
