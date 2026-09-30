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
    request_id: str
    booking_ref: str
    messages: Annotated[list[BaseMessage], add_messages]
    intent: Optional[Intent]
    constraints: PassengerConstraints
    active_agent: Optional[ActiveAgent]
    booking: Optional[BookingDetails]
    proposed_solution: Optional[ProposedSolution]
    policy_passed: Optional[bool]
    policy_failure_reason: Optional[str]
    retry_count: int
    escalated: bool
    escalation_note: Optional[str]
    final_response: Optional[str]
