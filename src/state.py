from typing import Annotated, Optional, TypedDict

from langgraph.graph.message import add_messages


class RebookingState(TypedDict):
    request_id: str
    booking_ref: str
    messages: Annotated[list, add_messages]
    intent: Optional[str]
    constraints: dict
    active_agent: Optional[str]
    booking: Optional[dict]
    proposed_solution: Optional[dict]
    policy_passed: Optional[bool]
    policy_failure_reason: Optional[str]
    retry_count: int
    escalated: bool
    escalation_note: Optional[str]
    final_response: Optional[str]
    supervisor_approved: Optional[bool]
