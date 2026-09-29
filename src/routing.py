"""Conditional routing helpers for the disruption graph."""

from __future__ import annotations

from typing import Literal

from src.state import RebookingState

MAX_POLICY_RETRIES = 2


def route_after_classifier(
    state: RebookingState,
) -> Literal["rebooking_agent", "refund_agent", "compensation_agent", "escalation"]:
    intent = state.get("intent")
    if intent == "complaint":
        return "escalation"
    if intent == "refund":
        return "refund_agent"
    if intent == "compensation":
        return "compensation_agent"
    return "rebooking_agent"


def route_after_policy(
    state: RebookingState,
) -> Literal[
    "final_response",
    "rebooking_agent",
    "refund_agent",
    "compensation_agent",
    "escalation",
]:
    if state.get("policy_passed"):
        return "final_response"

    # retry_count is incremented on each failure inside policy_checker
    if int(state.get("retry_count") or 0) > MAX_POLICY_RETRIES:
        return "escalation"

    agent = state.get("active_agent") or "rebooking"
    if agent == "refund":
        return "refund_agent"
    if agent == "compensation":
        return "compensation_agent"
    return "rebooking_agent"


def route_after_rebooking(
    state: RebookingState,
) -> Literal["tools", "policy_checker"]:
    """If the last AI message still has tool calls, go to ToolNode; else policy."""
    messages = state.get("messages") or []
    if not messages:
        return "policy_checker"
    last = messages[-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return "policy_checker"
