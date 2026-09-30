import json
import re

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
from src.tools import (
    FLIGHT_SEARCH,
    COMPENSATION_TOOLS,
    REBOOKING_TOOLS,
    REFUND_TOOLS,
    get_booking,
)


class ClassifierOutput(BaseModel):
    intent: str = Field(description="rebook, refund, compensation, or complaint")
    latest_arrival: str | None = None


def _json_from_text(text: str):
    if not text:
        return None
    blocks = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if not blocks:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        blocks = [match.group(0)] if match else []
    for raw in reversed(blocks):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None


def _passenger_text(state) -> str:
    for msg in reversed(state.get("messages") or []):
        if isinstance(msg, HumanMessage) or getattr(msg, "type", None) == "human":
            return str(msg.content)
    return ""


def _run_tools(response, tools):
    tool_map = {t.name: t for t in tools}
    tool_messages = []
    booking = None
    for call in response.tool_calls:
        result = tool_map[call["name"]].invoke(call["args"])
        tool_messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
        if call["name"] == "get_booking":
            try:
                data = json.loads(result)
                if "booking_ref" in data:
                    booking = data
            except json.JSONDecodeError:
                pass
    return tool_messages, booking


def _load_booking(state):
    booking = state.get("booking")
    if booking:
        return booking
    ref = state.get("booking_ref")
    if not ref:
        return None
    data = json.loads(get_booking.invoke({"booking_ref": ref}))
    return data if "booking_ref" in data else None


def _default_rebook(booking, failed_reason=None):
    key = (booking["origin"], booking["destination"])
    booked_cabin = (booking.get("cabin_class") or "economy").lower()
    for flight in FLIGHT_SEARCH.get(key, []):
        cabin = (flight.get("cabin_class") or "").lower()
        if CABIN_OK(booked_cabin, cabin) and (flight.get("connection_minutes") or 99) >= 60:
            if failed_reason and flight.get("flight_number", "") in (failed_reason or ""):
                continue
            return {
                "type": "rebook",
                "summary": f"Rebook on {flight['flight_number']}",
                "flight": flight,
                "reason": "Same cabin, within policy window",
            }
    flights = FLIGHT_SEARCH.get(key, [])
    if flights:
        return {
            "type": "rebook",
            "summary": f"Rebook on {flights[0]['flight_number']}",
            "flight": flights[0],
            "reason": "Only available option",
        }
    return None


def CABIN_OK(booked, proposed):
    rank = {"economy": 0, "premium_economy": 1, "business": 2, "first": 3}
    return rank.get(proposed, 99) <= rank.get(booked, 0)


def _default_refund(booking):
    fare = float(booking.get("fare_amount") or 0)
    tax = float(booking.get("tax_amount") or 0)
    disruption = (booking.get("disruption_type") or "").lower()
    if disruption in {"cancelled", "delayed"} or (booking.get("fare_type") or "") == "flex":
        amount = fare
    else:
        amount = tax
    return {
        "type": "refund",
        "summary": f"Refund ${amount:.2f}",
        "refund_amount": amount,
        "reason": "Policy default",
    }


def _default_compensation(booking):
    disruption = (booking.get("disruption_type") or "").lower()
    delay = float(booking.get("delay_hours") or 0)
    if disruption == "cancelled" or delay > 6:
        amount = 400.0
    elif delay >= 3:
        amount = 200.0
    else:
        amount = 0.0
    return {
        "type": "compensation",
        "summary": f"Compensation ${amount:.0f}",
        "compensation_amount": amount,
        "reason": "Policy default",
    }


def request_classifier(state):
    result = get_llm().with_structured_output(ClassifierOutput).invoke(
        [
            SystemMessage(content=CLASSIFIER_SYSTEM),
            HumanMessage(
                content=(
                    f"booking_ref={state.get('booking_ref')}\n"
                    f"message={_passenger_text(state)}"
                )
            ),
        ]
    )
    intent = result.intent
    active = {"rebook": "rebooking", "refund": "refund", "compensation": "compensation"}.get(
        intent
    )
    return {
        "intent": intent,
        "constraints": {"latest_arrival": result.latest_arrival},
        "active_agent": active,
        "policy_passed": None,
        "policy_failure_reason": None,
        "retry_count": 0,
        "escalated": False,
        "escalation_note": None,
        "proposed_solution": None,
        "final_response": None,
        "supervisor_approved": None,
    }


def rebooking_agent(state):
    llm = get_llm().bind_tools(REBOOKING_TOOLS)
    context = (
        f"booking_ref={state.get('booking_ref')}\n"
        f"constraints={json.dumps(state.get('constraints') or {})}\n"
    )
    if state.get("policy_failure_reason"):
        context += f"POLICY FAILURE: {state['policy_failure_reason']}\nPick another flight.\n"

    history = list(state.get("messages") or [])
    messages = [SystemMessage(content=REBOOKING_SYSTEM), *history, HumanMessage(content=context)]
    response = llm.invoke(messages)
    updates = {"messages": [response], "active_agent": "rebooking"}

    booking = _load_booking(state)
    if booking:
        updates["booking"] = booking

    if getattr(response, "tool_calls", None):
        return updates

    parsed = _json_from_text(str(response.content))
    if parsed and parsed.get("type") == "rebook":
        updates["proposed_solution"] = parsed
    elif booking:
        updates["proposed_solution"] = _default_rebook(
            booking, state.get("policy_failure_reason")
        )
    return updates


def refund_agent(state):
    llm = get_llm().bind_tools(REFUND_TOOLS)
    context = f"booking_ref={state.get('booking_ref')}\n"
    if state.get("policy_failure_reason"):
        context += f"POLICY FAILURE: {state['policy_failure_reason']}\n"

    messages = [
        SystemMessage(content=REFUND_SYSTEM),
        HumanMessage(content=context),
    ]
    response = llm.invoke(messages)
    updates = {"messages": [response], "active_agent": "refund"}
    booking = state.get("booking")

    if getattr(response, "tool_calls", None):
        tool_messages, found = _run_tools(response, REFUND_TOOLS)
        if found:
            booking = found
            updates["booking"] = found
        follow = get_llm().invoke(
            messages
            + [response]
            + tool_messages
            + [HumanMessage(content="Output the refund JSON now.")]
        )
        updates["messages"] = [response, *tool_messages, follow]
        parsed = _json_from_text(str(follow.content))
        if parsed and parsed.get("type") == "refund":
            updates["proposed_solution"] = parsed

    if not updates.get("proposed_solution"):
        booking = booking or _load_booking(state)
        if booking:
            updates["booking"] = booking
            updates["proposed_solution"] = _default_refund(booking)
    return updates


def compensation_agent(state):
    llm = get_llm().bind_tools(COMPENSATION_TOOLS)
    context = f"booking_ref={state.get('booking_ref')}\n"
    messages = [
        SystemMessage(content=COMPENSATION_SYSTEM),
        HumanMessage(content=context),
    ]
    response = llm.invoke(messages)
    updates = {"messages": [response], "active_agent": "compensation"}
    booking = state.get("booking")

    if getattr(response, "tool_calls", None):
        tool_messages, found = _run_tools(response, COMPENSATION_TOOLS)
        if found:
            booking = found
            updates["booking"] = found
        follow = get_llm().invoke(
            messages
            + [response]
            + tool_messages
            + [HumanMessage(content="Output the compensation JSON now.")]
        )
        updates["messages"] = [response, *tool_messages, follow]
        parsed = _json_from_text(str(follow.content))
        if parsed and parsed.get("type") == "compensation":
            updates["proposed_solution"] = parsed

    if not updates.get("proposed_solution"):
        booking = booking or _load_booking(state)
        if booking:
            updates["booking"] = booking
            updates["proposed_solution"] = _default_compensation(booking)
    return updates


def policy_checker(state):
    booking = _load_booking(state)
    passed, reason = evaluate_policy(booking, state.get("proposed_solution"))
    updates = {
        "booking": booking,
        "policy_passed": passed,
        "policy_failure_reason": None if passed else reason,
        "supervisor_approved": None,
    }
    if not passed:
        updates["retry_count"] = int(state.get("retry_count") or 0) + 1
    return updates


def supervisor_approval(state):
    from langgraph.types import interrupt
    from src.routing import SUPERVISOR_THRESHOLD, payout_amount

    solution = state.get("proposed_solution") or {}
    amount = payout_amount(state)
    decision = interrupt(
        {
            "type": "supervisor_approval",
            "threshold": SUPERVISOR_THRESHOLD,
            "amount": amount,
            "payout_type": solution.get("type"),
            "booking_ref": state.get("booking_ref"),
            "summary": solution.get("summary"),
            "message": (
                f"Supervisor approval required: {solution.get('type')} "
                f"of ${amount:.2f} (over ${SUPERVISOR_THRESHOLD})."
            ),
        }
    )
    approved = (
        decision.get("approved")
        if isinstance(decision, dict)
        else bool(decision)
    )
    if approved:
        return {"supervisor_approved": True}
    return {
        "supervisor_approved": False,
        "escalated": True,
        "escalation_note": (
            f"Supervisor rejected {solution.get('type')} of ${amount:.2f} "
            f"(threshold ${SUPERVISOR_THRESHOLD})."
        ),
    }


def escalation_agent(state):
    note = get_llm().invoke(
        [
            SystemMessage(content=ESCALATION_SYSTEM),
            HumanMessage(
                content=json.dumps(
                    {
                        "booking_ref": state.get("booking_ref"),
                        "intent": state.get("intent"),
                        "message": _passenger_text(state),
                        "policy_failure_reason": state.get("policy_failure_reason"),
                        "retry_count": state.get("retry_count"),
                    },
                    default=str,
                )
            ),
        ]
    )
    text = str(note.content)
    return {
        "escalated": True,
        "escalation_note": text,
        "messages": [AIMessage(content=text)],
    }


def final_response_agent(state):
    reply = get_llm().invoke(
        [
            SystemMessage(content=FINAL_RESPONSE_SYSTEM),
            HumanMessage(
                content=json.dumps(
                    {
                        "intent": state.get("intent"),
                        "booking": state.get("booking"),
                        "proposed_solution": state.get("proposed_solution"),
                        "policy_passed": state.get("policy_passed"),
                        "escalated": state.get("escalated"),
                        "escalation_note": state.get("escalation_note"),
                        "supervisor_approved": state.get("supervisor_approved"),
                    },
                    default=str,
                )
            ),
        ]
    )
    text = str(reply.content)
    return {"final_response": text, "messages": [AIMessage(content=text)]}
