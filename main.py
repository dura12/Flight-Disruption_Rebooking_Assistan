import argparse
import json

from langchain_core.messages import HumanMessage

from src.graph import build_graph, export_mermaid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--booking-ref", default="XK9L2P")
    parser.add_argument(
        "--message",
        default="My flight to Dubai was cancelled. I need to be there by tomorrow noon.",
    )
    parser.add_argument("--thread-id", default="demo")
    parser.add_argument("--diagram", action="store_true")
    args = parser.parse_args()

    app = build_graph()
    if args.diagram:
        print(export_mermaid(app))
        return

    result = app.invoke(
        {
            "request_id": "R-1",
            "booking_ref": args.booking_ref,
            "messages": [HumanMessage(content=args.message)],
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
        "supervisor_approved": None,
    },
        config={"configurable": {"thread_id": args.thread_id}},
    )
    print(json.dumps(
        {
            "intent": result.get("intent"),
            "policy_passed": result.get("policy_passed"),
            "proposed_solution": result.get("proposed_solution"),
            "final_response": result.get("final_response"),
        },
        indent=2,
        default=str,
    ))


if __name__ == "__main__":
    main()
