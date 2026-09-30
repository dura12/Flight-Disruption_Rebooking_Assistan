from src.state import RebookingState

MAX_RETRIES = 2
SUPERVISOR_THRESHOLD = 300


def payout_amount(state: RebookingState) -> float:
    solution = state.get("proposed_solution") or {}
    kind = solution.get("type")
    if kind == "refund":
        return float(solution.get("refund_amount") or 0)
    if kind == "compensation":
        return float(solution.get("compensation_amount") or 0)
    return 0.0


def needs_supervisor_approval(state: RebookingState) -> bool:
    solution = state.get("proposed_solution") or {}
    if solution.get("type") not in {"refund", "compensation"}:
        return False
    return payout_amount(state) > SUPERVISOR_THRESHOLD


def route_after_classifier(state: RebookingState):
    intent = state.get("intent")
    if intent == "complaint":
        return "escalation"
    if intent == "refund":
        return "refund_agent"
    if intent == "compensation":
        return "compensation_agent"
    return "rebooking_agent"


def route_after_policy(state: RebookingState):
    if state.get("policy_passed"):
        if needs_supervisor_approval(state):
            return "supervisor_approval"
        return "final_response"
    if int(state.get("retry_count") or 0) > MAX_RETRIES:
        return "escalation"
    agent = state.get("active_agent") or "rebooking"
    if agent == "refund":
        return "refund_agent"
    if agent == "compensation":
        return "compensation_agent"
    return "rebooking_agent"


def route_after_supervisor(state: RebookingState):
    if state.get("supervisor_approved"):
        return "final_response"
    return "escalation"
