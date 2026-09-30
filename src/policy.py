from datetime import datetime


CABIN_RANK = {"economy": 0, "premium_economy": 1, "business": 2, "first": 3}


def _parse(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def evaluate_policy(booking, solution):
    if not solution:
        return False, "No proposed solution to check."
    if not booking:
        return False, "Booking details are missing."

    kind = solution.get("type")

    if kind == "rebook":
        flight = solution.get("flight") or {}
        if not flight:
            return False, "Missing replacement flight."
        booked = (booking.get("cabin_class") or "economy").lower()
        proposed = (flight.get("cabin_class") or "").lower()
        if CABIN_RANK.get(proposed, 99) > CABIN_RANK.get(booked, 0):
            return False, f"Cabin upgrade not allowed: {booked} -> {proposed}."
        original = _parse(booking.get("departure_datetime"))
        new_dep = _parse(flight.get("departure_datetime"))
        if original and new_dep:
            hours = (new_dep - original).total_seconds() / 3600
            if hours > 48:
                return False, f"Departs {hours:.0f}h after original (max 48h)."
        connection = flight.get("connection_minutes")
        if connection is not None and connection < 60:
            return False, f"Connection {connection} min is under 60."
        return True, "Rebooking OK."

    if kind == "refund":
        amount = solution.get("refund_amount")
        if amount is None:
            return False, "Missing refund_amount."
        fare = float(booking.get("fare_amount") or 0)
        tax = float(booking.get("tax_amount") or 0)
        disruption = (booking.get("disruption_type") or "").lower()
        if disruption in {"cancelled", "delayed"}:
            expected = fare
        elif (booking.get("fare_type") or "").lower() == "flex":
            expected = fare
        else:
            expected = tax
        if abs(float(amount) - expected) > 0.01:
            return False, f"Refund ${amount} wrong; expected ${expected}."
        return True, "Refund OK."

    if kind == "compensation":
        amount = solution.get("compensation_amount")
        if amount is None:
            return False, "Missing compensation_amount."
        disruption = (booking.get("disruption_type") or "").lower()
        delay = float(booking.get("delay_hours") or 0)
        if disruption == "cancelled" or delay > 6:
            expected = 400.0
        elif delay >= 3:
            expected = 200.0
        else:
            expected = 0.0
        if abs(float(amount) - expected) > 0.01:
            return False, f"Compensation ${amount} wrong; expected ${expected}."
        return True, "Compensation OK."

    return False, f"Unknown solution type: {kind}"
