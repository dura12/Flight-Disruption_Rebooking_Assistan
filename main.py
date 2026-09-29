"""CLI entrypoint: run a single request or export the Mermaid diagram."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage

from src.graph import build_graph, export_mermaid


def initial_state(request_id: str, booking_ref: str, message: str) -> dict:
    return {
        "request_id": request_id,
        "booking_ref": booking_ref,
        "messages": [HumanMessage(content=message)],
        "intent": None,
        "constraints": {},
        "active_agent": None,
        "booking": None,
        "proposed_solution": None,
        "policy_passed": None,
        "policy_failure_reason": None,
        "retry_count": 0,
        "escalated": False,
        "escalation_note": None,
        "final_response": None,
    }


def run_once(
    request_id: str,
    booking_ref: str,
    message: str,
    thread_id: str,
    graph=None,
) -> dict:
    app = graph or build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke(
        initial_state(request_id, booking_ref, message),
        config=config,
    )
    return result


def follow_up(message: str, thread_id: str, graph=None) -> dict:
    """Continue an existing conversation — reuses checkpointed state."""
    app = graph or build_graph()
    config = {"configurable": {"thread_id": thread_id}}
    result = app.invoke(
        {"messages": [HumanMessage(content=message)]},
        config=config,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flight Disruption Rebooking Assistant")
    parser.add_argument("--request-id", default="R-7702")
    parser.add_argument("--booking-ref", default="XK9L2P")
    parser.add_argument("--message", default="My flight to Dubai was cancelled. I need to be there by tomorrow noon.")
    parser.add_argument("--thread-id", default="passenger-XK9L2P")
    parser.add_argument("--diagram", action="store_true", help="Write Mermaid diagram and exit")
    parser.add_argument("--diagram-out", default="docs/graph.mmd")
    args = parser.parse_args(argv)

    app = build_graph()

    if args.diagram:
        mermaid = export_mermaid(app)
        out = Path(args.diagram_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(mermaid, encoding="utf-8")
        print(mermaid)
        print(f"\nSaved to {out}", file=sys.stderr)
        return 0

    result = run_once(
        args.request_id,
        args.booking_ref,
        args.message,
        args.thread_id,
        graph=app,
    )
    summary = {
        "intent": result.get("intent"),
        "active_agent": result.get("active_agent"),
        "policy_passed": result.get("policy_passed"),
        "retry_count": result.get("retry_count"),
        "escalated": result.get("escalated"),
        "proposed_solution": result.get("proposed_solution"),
        "final_response": result.get("final_response"),
    }
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
