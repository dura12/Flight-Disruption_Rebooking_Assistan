from __future__ import annotations

import json
import re
from typing import Any, Literal, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel, Field

from src.llm import get_llm
from src.policy import evaluate_policy
from src.prompts import (
    CLASSIFIER_SYSTEM,
    COMPENSATION_SYSTEM,
    ESCALATION_SYSTEM,
    FINAL_RESPONSE_SYSTEM,
    REBOOKING_SYSTEM,
    REFUND_SYSTEM,
)
from src.state import RebookingState
from src.tools import (
    COMPENSATION_TOOLS,
    REBOOKING_TOOLS,
    REFUND_TOOLS,
    get_booking,
)


class ClassifierOutput(BaseModel):
    intent: Literal["rebook", "refund", "compensation", "complaint"]
    latest_arrival: Optional[str] = Field(
        default=None,
        description="ISO datetime for latest acceptable arrival, if any",
    )
    preferred_cabin: Optional[str] = None
    notes: Optional[str] = None


def _extract_json_block(text: str) -> Optional[dict[str, Any]]:
    if not text:
        return None
    fenced = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    candidates = fenced or re.findall(r"(\{[^{}]*\"type\"[^{}]*\})", text, flags=re.DOTALL)
    if not candidates:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidates = [match.group(0)]
    for raw in reversed(candidates):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def _last_human_text(state: RebookingState) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


def _booking_from_tool_messages(messages: list) -> Optional[dict[str, Any]]:
    for msg in reversed(messages or []):
        if isinstance(msg, ToolMessage) or getattr(msg, "type", None) == "tool":
            try:
                data = json.loads(str(msg.content))
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(data, dict) and "booking_ref" in data and "error" not in data:
                return data
    return None


def request_classifier(state: RebookingState) -> dict[str, Any]:
    llm = get_llm().with_structured_output(ClassifierOutput)
    passenger_msg = _last_human_text(state)
    result: ClassifierOutput = llm.invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(
                content=(
                    f"Booking reference: {state.get('booking_ref')}\n"
                    f"Request id: {state.get('request_id')}\n"
                    f"Passenger message: {passenger_msg}"
                )
            ),
        ]
    )

    intent = result.intent
    constraints = {
        "latest_arrival": result.latest_arrival,
        "preferred_cabin": result.preferred_cabin,
        "notes": result.notes,
    }
    active_map = {
        "rebook": "rebooking",
        "refund": "refund",
        "compensation": "compensation",
    }
    return {
        "intent": intent,
        "constraints": constraints,
        "active_agent": active_map.get(intent),
        "policy_passed": None,
        "policy_failure_reason": None,
        "retry_count": 0,
        "escalated": False,
        "escalation_note": None,
        "proposed_solution": None,
        "final_response": None,
        "messages": [
            AIMessage(
                content=(
                    f"Classified intent={intent}; "
                    f"constraints={json.dumps(constraints)}"
                )
            )
        ],
    }


def rebooking_agent(state: RebookingState) -> dict[str, Any]:
    llm = get_llm().bind_tools(REBOOKING_TOOLS)
    failure = state.get("policy_failure_reason")
    context = (
        f"booking_ref={state.get('booking_ref')}\n"
        f"constraints={json.dumps(state.get('constraints') or {})}\n"
    )
    if failure:
        context += (
            f"POLICY FAILURE (retry {state.get('retry_count', 0)}): {failure}\n"
            "Choose a different compliant flight.\n"
        )

    messages = [
        SystemMessage(content=REBOOKING_SYSTEM),
        HumanMessage(content=context),
        *list(state.get("messages") or []),
    ]
    response = llm.invoke(messages)
    updates: dict[str, Any] = {"messages": [response], "active_agent": "rebooking"}

    booking = state.get("booking") or _booking_from_tool_messages(
        list(state.get("messages") or [])
    )
    if booking:
        updates["booking"] = booking

    if not getattr(response, "tool_calls", None):
        parsed = _extract_json_block(str(response.content))
        if parsed and parsed.get("type") == "rebook":
            updates["proposed_solution"] = parsed
    return updates


def _default_refund(booking: dict[str, Any]) -> dict[str, Any]:
    fare = float(booking.get("fare_amount") or 0)
    tax = float(booking.get("tax_amount") or 0)
    disruption = (booking.get("disruption_type") or "").lower()
    fare_type = (booking.get("fare_type") or "basic").lower()
    if disruption in {"cancelled", "delayed"}:
        amount, reason = fare, "airline disruption → full fare"
    elif fare_type == "flex":
        amount, reason = fare, "refundable fare → full fare"
    else:
        amount, reason = tax, "non-refundable fare → taxes only"
    return {
        "type": "refund",
        "summary": f"Refund of ${amount:.2f} ({reason})",
        "refund_amount": amount,
        "reason": reason,
    }


def _default_compensation(booking: dict[str, Any]) -> dict[str, Any]:
    disruption = (booking.get("disruption_type") or "").lower()
    delay_hours = float(booking.get("delay_hours") or 0)
    if disruption == "cancelled" or delay_hours > 6:
        amount, reason = 400.0, "cancelled or delay over 6 hours"
    elif delay_hours >= 3:
        amount, reason = 200.0, "delay 3 to 6 hours"
    else:
        amount, reason = 0.0, "delay under 3 hours"
    return {
        "type": "compensation",
        "summary": f"Compensation of ${amount:.0f} ({reason})",
        "compensation_amount": amount,
        "reason": reason,
    }


def refund_agent(state: RebookingState) -> dict[str, Any]:
    llm = get_llm().bind_tools(REFUND_TOOLS)
    failure = state.get("policy_failure_reason")
    context = f"booking_ref={state.get('booking_ref')}\n"
    if failure:
        context += f"POLICY FAILURE (retry {state.get('retry_count', 0)}): {failure}\n"

    messages = [
        SystemMessage(content=REFUND_SYSTEM),
        HumanMessage(content=context),
        *list(state.get("messages") or []),
    ]
    response = llm.invoke(messages)
    updates: dict[str, Any] = {"messages": [response], "active_agent": "refund"}
    booking = state.get("booking")

    if getattr(response, "tool_calls", None):
        tool_map = {t.name: t for t in REFUND_TOOLS}
        tool_messages = []
        for call in response.tool_calls:
            tool_fn = tool_map[call["name"]]
            result = tool_fn.invoke(call["args"])
            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=call["id"])
            )
            if call["name"] == "get_booking":
                try:
                    data = json.loads(result)
                    if "booking_ref" in data:
                        booking = data
                        updates["booking"] = data
                except json.JSONDecodeError:
                    pass
        follow = llm.bind_tools([]).invoke(
            messages
            + [response]
            + tool_messages
            + [
                HumanMessage(
                    content="Using the tool results, output the refund JSON now."
                )
            ]
        )
        updates["messages"] = [response, *tool_messages, follow]
        parsed = _extract_json_block(str(follow.content))
        if parsed and parsed.get("type") == "refund":
            updates["proposed_solution"] = parsed
    else:
        parsed = _extract_json_block(str(response.content))
        if parsed and parsed.get("type") == "refund":
            updates["proposed_solution"] = parsed

    if not updates.get("proposed_solution"):
        if not booking and state.get("booking_ref"):
            raw = get_booking.invoke({"booking_ref": state["booking_ref"]})
            try:
                booking = json.loads(raw)
                updates["booking"] = booking
            except json.JSONDecodeError:
                booking = None
        if booking and "error" not in booking:
            updates["proposed_solution"] = _default_refund(booking)
    return updates


def compensation_agent(state: RebookingState) -> dict[str, Any]:
    llm = get_llm().bind_tools(COMPENSATION_TOOLS)
    failure = state.get("policy_failure_reason")
    context = f"booking_ref={state.get('booking_ref')}\n"
    if failure:
        context += f"POLICY FAILURE (retry {state.get('retry_count', 0)}): {failure}\n"

    messages = [
        SystemMessage(content=COMPENSATION_SYSTEM),
        HumanMessage(content=context),
        *list(state.get("messages") or []),
    ]
    response = llm.invoke(messages)
    updates: dict[str, Any] = {
        "messages": [response],
        "active_agent": "compensation",
    }
    booking = state.get("booking")

    if getattr(response, "tool_calls", None):
        tool_map = {t.name: t for t in COMPENSATION_TOOLS}
        tool_messages = []
        for call in response.tool_calls:
            tool_fn = tool_map[call["name"]]
            result = tool_fn.invoke(call["args"])
            tool_messages.append(
                ToolMessage(content=str(result), tool_call_id=call["id"])
            )
            if call["name"] == "get_booking":
                try:
                    data = json.loads(result)
                    if "booking_ref" in data:
                        booking = data
                        updates["booking"] = data
                except json.JSONDecodeError:
                    pass
        follow = llm.bind_tools([]).invoke(
            messages
            + [response]
            + tool_messages
            + [
                HumanMessage(
                    content="Using the tool results, output the compensation JSON now."
                )
            ]
        )
        updates["messages"] = [response, *tool_messages, follow]
        parsed = _extract_json_block(str(follow.content))
        if parsed and parsed.get("type") == "compensation":
            updates["proposed_solution"] = parsed
    else:
        parsed = _extract_json_block(str(response.content))
        if parsed and parsed.get("type") == "compensation":
            updates["proposed_solution"] = parsed

    if not updates.get("proposed_solution"):
        if not booking and state.get("booking_ref"):
            raw = get_booking.invoke({"booking_ref": state["booking_ref"]})
            try:
                booking = json.loads(raw)
                updates["booking"] = booking
            except json.JSONDecodeError:
                booking = None
        if booking and "error" not in booking:
            updates["proposed_solution"] = _default_compensation(booking)
    return updates


def policy_checker(state: RebookingState) -> dict[str, Any]:
    booking = state.get("booking")
    if not booking and state.get("booking_ref"):
        raw = get_booking.invoke({"booking_ref": state["booking_ref"]})
        try:
            data = json.loads(raw)
            if "booking_ref" in data:
                booking = data
        except json.JSONDecodeError:
            booking = None

    passed, reason = evaluate_policy(booking, state.get("proposed_solution"))
    updates: dict[str, Any] = {
        "policy_passed": passed,
        "policy_failure_reason": None if passed else reason,
        "booking": booking,
    }
    if not passed:
        updates["retry_count"] = int(state.get("retry_count") or 0) + 1
    return updates


def escalation_agent(state: RebookingState) -> dict[str, Any]:
    llm = get_llm()
    payload = {
        "request_id": state.get("request_id"),
        "booking_ref": state.get("booking_ref"),
        "intent": state.get("intent"),
        "constraints": state.get("constraints"),
        "proposed_solution": state.get("proposed_solution"),
        "policy_failure_reason": state.get("policy_failure_reason"),
        "retry_count": state.get("retry_count"),
        "passenger_message": _last_human_text(state),
    }
    note = llm.invoke(
        [
            SystemMessage(content=ESCALATION_SYSTEM),
            HumanMessage(content=json.dumps(payload, default=str)),
        ]
    )
    text = str(note.content)
    return {
        "escalated": True,
        "escalation_note": text,
        "messages": [AIMessage(content=f"Escalation note:\n{text}")],
    }


def final_response_agent(state: RebookingState) -> dict[str, Any]:
    llm = get_llm()
    payload = {
        "intent": state.get("intent"),
        "booking": state.get("booking"),
        "proposed_solution": state.get("proposed_solution"),
        "policy_passed": state.get("policy_passed"),
        "escalated": state.get("escalated"),
        "escalation_note": state.get("escalation_note"),
        "constraints": state.get("constraints"),
        "passenger_message": _last_human_text(state),
    }
    reply = llm.invoke(
        [
            SystemMessage(content=FINAL_RESPONSE_SYSTEM),
            HumanMessage(content=json.dumps(payload, default=str)),
        ]
    )
    text = str(reply.content)
    return {
        "final_response": text,
        "messages": [AIMessage(content=text)],
    }
