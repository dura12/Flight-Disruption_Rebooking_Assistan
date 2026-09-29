"""Shared typed state for the disruption rebooking graph."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, TypedDict

from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


Intent = Literal["rebook", "refund", "compensation", "complaint"]
ActiveAgent = Literal["rebooking", "refund", "compensation"]


class PassengerConstraints(TypedDict, total=False):
    latest_arrival: Optional[str]
    preferred_cabin: Optional[str]
    notes: Optional[str]


class BookingDetails(TypedDict, total=False):
    booking_ref: str
    passenger_name: str
    origin: str
    destination: str
    flight_number: str
    departure_datetime: str
    arrival_datetime: str
    cabin_class: str
    fare_type: str
    fare_amount: float
    tax_amount: float
    disruption_type: str
    delay_hours: float
    status: str


class ProposedSolution(TypedDict, total=False):
    type: Literal["rebook", "refund", "compensation"]
    summary: str
    flight: Optional[dict[str, Any]]
    refund_amount: Optional[float]
    compensation_amount: Optional[float]
    reason: Optional[str]


class RebookingState(TypedDict):
    """State shared by every node in the graph.

    Each node updates only the fields it owns:
    - classifier: intent, constraints, active_agent
    - specialist agents: booking, proposed_solution, messages
    - policy checker: policy_passed, policy_failure_reason, retry_count
    - escalation: escalated, escalation_note
    - final response: final_response, messages
    """

    # Intake / identity
    request_id: str
    booking_ref: str

    # Conversation history (reducer appends new messages)
    messages: Annotated[list[BaseMessage], add_messages]

    # Classification
    intent: Optional[Intent]
    constraints: PassengerConstraints
    active_agent: Optional[ActiveAgent]

    # Booking context loaded via tools / agents
    booking: Optional[BookingDetails]

    # Solution under review
    proposed_solution: Optional[ProposedSolution]

    # Policy enforcement
    policy_passed: Optional[bool]
    policy_failure_reason: Optional[str]
    retry_count: int

    # Escalation
    escalated: bool
    escalation_note: Optional[str]

    # Passenger-facing reply
    final_response: Optional[str]
