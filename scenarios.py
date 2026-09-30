SCENARIOS = [
    {
        "id": "1",
        "title": "Cancelled flight — rebook by noon",
        "booking_ref": "XK9L2P",
        "request_id": "R-7702",
        "message": "My flight to Dubai was cancelled. I need to be there by tomorrow noon.",
        "follow_up": False,
        "expected_path": "Classifier → Rebooking ⇄ Tools → Policy (pass) → Final response",
        "notes": "Passenger Alex Morgan, LHR→DXB, economy, cancelled. Pick an economy flight within 48h.",
    },
    {
        "id": "1b",
        "title": "Follow-up — refund instead",
        "booking_ref": "XK9L2P",
        "request_id": "R-7702",
        "message": "Actually, can I get a refund instead?",
        "follow_up": True,
        "requires": "1",
        "expected_path": "Same thread → Classifier → Refund → Policy (pass) → Final response",
        "notes": "Must run Scenario 1 first on the same thread. Reuses booking XK9L2P. Refund is $650 so supervisor approval (HITL) is required.",
    },
    {
        "id": "2",
        "title": "6-hour delay — compensation",
        "booking_ref": "DL6H01",
        "request_id": "R-8801",
        "message": "My flight is delayed 6 hours. Am I entitled to anything?",
        "follow_up": False,
        "expected_path": "Classifier → Compensation → Policy (pass) → Final response",
        "notes": "Passenger Sam Rivera, JFK→LAX, delayed 6h. Compensation should be $200.",
    },
    {
        "id": "3",
        "title": "Only business seats — retry then escalate",
        "booking_ref": "BZONLY1",
        "request_id": "R-9903",
        "message": "My flight from Paris to New York was cancelled. Please rebook me in economy.",
        "follow_up": False,
        "expected_path": "Classifier → Rebooking ⇄ Policy (fail ×3) → Escalation → Final response",
        "notes": "Passenger Jordan Lee, CDG→JFK, economy booked but search returns business only. Policy fails until escalation.",
    },
    {
        "id": "4",
        "title": "Complaint — speak to a manager",
        "booking_ref": "CMPL01",
        "request_id": "R-1104",
        "message": "This is the third time you've cancelled on me. I want to speak to a manager.",
        "follow_up": False,
        "expected_path": "Classifier → Escalation → Final response",
        "notes": "Passenger Casey Brooks. Complaint skips specialists and goes straight to escalation.",
    },
]


def get_scenario(scenario_id: str) -> dict:
    for scenario in SCENARIOS:
        if scenario["id"] == scenario_id:
            return scenario
    raise KeyError(f"Unknown scenario id: {scenario_id}")
