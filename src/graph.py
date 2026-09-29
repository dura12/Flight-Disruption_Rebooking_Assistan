"""LangGraph assembly: StateGraph, ToolNode, checkpointer, conditional edges."""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from src.nodes import (
    compensation_agent,
    escalation_agent,
    final_response_agent,
    policy_checker,
    rebooking_agent,
    refund_agent,
    request_classifier,
)
from src.routing import route_after_classifier, route_after_policy
from src.state import RebookingState
from src.tools import REBOOKING_TOOLS


def build_graph(checkpointer: MemorySaver | None = None):
    """Compile the disruption assistant graph.

    Nodes (8):
      request_classifier, rebooking_agent, tools, refund_agent,
      compensation_agent, policy_checker, escalation, final_response

    Conditional routing (3 custom + tools_condition):
      1. After classifier → specialist or escalation
      2. After rebooking → tools loop or policy (also via tools_condition)
      3. After policy → pass / retry same agent / escalate
    """
    graph = StateGraph(RebookingState)

    graph.add_node("request_classifier", request_classifier)
    graph.add_node("rebooking_agent", rebooking_agent)
    graph.add_node("tools", ToolNode(REBOOKING_TOOLS))
    graph.add_node("refund_agent", refund_agent)
    graph.add_node("compensation_agent", compensation_agent)
    graph.add_node("policy_checker", policy_checker)
    graph.add_node("escalation", escalation_agent)
    graph.add_node("final_response", final_response_agent)

    graph.add_edge(START, "request_classifier")

    graph.add_conditional_edges(
        "request_classifier",
        route_after_classifier,
        {
            "rebooking_agent": "rebooking_agent",
            "refund_agent": "refund_agent",
            "compensation_agent": "compensation_agent",
            "escalation": "escalation",
        },
    )

    # Rebooking ⇄ ToolNode loop via tools_condition; when done → policy_checker
    graph.add_conditional_edges(
        "rebooking_agent",
        tools_condition,
        {"tools": "tools", END: "policy_checker"},
    )
    # After tools, always return to rebooking agent (tool loop)
    graph.add_edge("tools", "rebooking_agent")

    graph.add_edge("refund_agent", "policy_checker")
    graph.add_edge("compensation_agent", "policy_checker")

    graph.add_conditional_edges(
        "policy_checker",
        route_after_policy,
        {
            "final_response": "final_response",
            "rebooking_agent": "rebooking_agent",
            "refund_agent": "refund_agent",
            "compensation_agent": "compensation_agent",
            "escalation": "escalation",
        },
    )

    graph.add_edge("escalation", "final_response")
    graph.add_edge("final_response", END)

    memory = checkpointer or MemorySaver()
    return graph.compile(checkpointer=memory)


def export_mermaid(compiled) -> str:
    """Return the Mermaid diagram source for the compiled graph."""
    return compiled.get_graph().draw_mermaid()
