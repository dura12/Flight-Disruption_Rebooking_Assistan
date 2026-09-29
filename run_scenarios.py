"""Run the four evaluation scenarios plus the Scenario 1 follow-up."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# Ensure project root is on sys.path when run as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.graph import build_graph, export_mermaid


def _base(request_id: str, booking_ref: str, message: str) -> dict:
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


def _path_summary(result: dict) -> list[str]:
    """Infer a human-readable path from final state fields."""
    intent = result.get("intent")
    steps = ["Classifier"]
    if intent == "complaint":
        steps += ["Escalation", "Final response"]
        return steps
    agent = {
        "rebook": "Rebooking ⇄ Tools",
        "refund": "Refund",
        "compensation": "Compensation",
    }.get(intent or "", "Specialist")
    steps.append(agent)
    retries = int(result.get("retry_count") or 0)
    if result.get("escalated") and intent != "complaint":
        if retries > 0:
            steps.append(f"Policy checker (fail ×{retries})")
        steps += ["Escalation", "Final response"]
    else:
        steps.append("Policy checker (pass)")
        steps.append("Final response")
    return steps


def _print_result(title: str, result: dict) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)
    print("Path:", " → ".join(_path_summary(result)))
    print(f"intent={result.get('intent')}  retries={result.get('retry_count')}  "
          f"policy_passed={result.get('policy_passed')}  escalated={result.get('escalated')}")
    if result.get("proposed_solution"):
        print("Proposed:", json.dumps(result["proposed_solution"], default=str)[:500])
    if result.get("policy_failure_reason"):
        print("Last policy reason:", result["policy_failure_reason"])
    print("\nFinal response:\n", result.get("final_response"))


def run_all() -> dict:
    checkpointer = MemorySaver()
    app = build_graph(checkpointer=checkpointer)

    # Persist diagram next to outputs
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    (docs / "graph.mmd").write_text(export_mermaid(app), encoding="utf-8")

    outputs: dict = {"ran_at": datetime.now(timezone.utc).isoformat(), "scenarios": {}}

    # --- Scenario 1 ---
    s1_thread = "scenario-1-XK9L2P"
    s1 = app.invoke(
        _base(
            "R-7702",
            "XK9L2P",
            "My flight to Dubai was cancelled. I need to be there by tomorrow noon.",
        ),
        config={"configurable": {"thread_id": s1_thread}},
    )
    _print_result("Scenario 1 — Cancelled flight, arrive by noon", s1)
    outputs["scenarios"]["1"] = {
        "input": {
            "request_id": "R-7702",
            "booking_ref": "XK9L2P",
            "message": "My flight to Dubai was cancelled. I need to be there by tomorrow noon.",
            "thread_id": s1_thread,
        },
        "path": _path_summary(s1),
        "intent": s1.get("intent"),
        "policy_passed": s1.get("policy_passed"),
        "escalated": s1.get("escalated"),
        "proposed_solution": s1.get("proposed_solution"),
        "final_response": s1.get("final_response"),
        "booking_ref_in_state": (s1.get("booking") or {}).get("booking_ref"),
    }

    # --- Scenario 1 follow-up (same thread_id) ---
    s1b = app.invoke(
        {"messages": [HumanMessage(content="Actually, can I get a refund instead?")]},
        config={"configurable": {"thread_id": s1_thread}},
    )
    _print_result("Scenario 1 follow-up — refund instead (same thread)", s1b)
    outputs["scenarios"]["1_followup"] = {
        "input": {
            "message": "Actually, can I get a refund instead?",
            "thread_id": s1_thread,
        },
        "path": _path_summary(s1b),
        "intent": s1b.get("intent"),
        "policy_passed": s1b.get("policy_passed"),
        "booking_reused": (s1b.get("booking") or {}).get("booking_ref") == "XK9L2P",
        "proposed_solution": s1b.get("proposed_solution"),
        "final_response": s1b.get("final_response"),
    }

    # --- Scenario 2 ---
    s2 = app.invoke(
        _base(
            "R-8801",
            "DL6H01",
            "My flight is delayed 6 hours. Am I entitled to anything?",
        ),
        config={"configurable": {"thread_id": "scenario-2-DL6H01"}},
    )
    _print_result("Scenario 2 — 6-hour delay, compensation", s2)
    outputs["scenarios"]["2"] = {
        "input": {
            "booking_ref": "DL6H01",
            "message": "My flight is delayed 6 hours. Am I entitled to anything?",
        },
        "path": _path_summary(s2),
        "intent": s2.get("intent"),
        "policy_passed": s2.get("policy_passed"),
        "proposed_solution": s2.get("proposed_solution"),
        "final_response": s2.get("final_response"),
    }

    # --- Scenario 3 ---
    s3 = app.invoke(
        _base(
            "R-9903",
            "BZONLY1",
            "My flight from Paris to New York was cancelled. Please rebook me in economy.",
        ),
        config={"configurable": {"thread_id": "scenario-3-BZONLY1"}},
    )
    _print_result("Scenario 3 — Only business seats (retry → escalate)", s3)
    outputs["scenarios"]["3"] = {
        "input": {
            "booking_ref": "BZONLY1",
            "message": "My flight from Paris to New York was cancelled. Please rebook me in economy.",
        },
        "path": _path_summary(s3),
        "intent": s3.get("intent"),
        "retry_count": s3.get("retry_count"),
        "escalated": s3.get("escalated"),
        "policy_failure_reason": s3.get("policy_failure_reason"),
        "final_response": s3.get("final_response"),
    }

    # --- Scenario 4 ---
    s4 = app.invoke(
        _base(
            "R-1104",
            "CMPL01",
            "This is the third time you've cancelled on me. I want to speak to a manager.",
        ),
        config={"configurable": {"thread_id": "scenario-4-CMPL01"}},
    )
    _print_result("Scenario 4 — Complaint → manager", s4)
    outputs["scenarios"]["4"] = {
        "input": {
            "booking_ref": "CMPL01",
            "message": "This is the third time you've cancelled on me. I want to speak to a manager.",
        },
        "path": _path_summary(s4),
        "intent": s4.get("intent"),
        "escalated": s4.get("escalated"),
        "escalation_note": s4.get("escalation_note"),
        "final_response": s4.get("final_response"),
    }

    out_dir = ROOT / "scenario_outputs"
    out_dir.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"results_{stamp}.json"
    out_path.write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved results to {out_path}")
    return outputs


if __name__ == "__main__":
    run_all()
