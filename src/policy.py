from __future__ import annotations

from datetime import datetime
from typing import Optional

from src.state import BookingDetails, ProposedSolution


CABIN_RANK = {"economy": 0, "premium_economy": 1, "business": 2, "first": 3}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", ""))
    except ValueError:
        return None


def check_rebook_policy(
    booking: BookingDetails,
    solution: ProposedSolution,
) -> tuple[bool, str]:
    flight = solution.get("flight") or {}
    if not flight:
        return False, "Rebooking proposal is missing a replacement flight."

    original_cabin = (booking.get("cabin_class") or "economy").lower()
    proposed_cabin = (flight.get("cabin_class") or "").lower()
    if CABIN_RANK.get(proposed_cabin, 99) > CABIN_RANK.get(original_cabin, 0):
        return (
            False,
            f"Cabin upgrade not allowed: booked {original_cabin}, proposed {proposed_cabin}. "
            "Same cabin or lower only.",
        )

    original_dep = _parse_dt(booking.get("departure_datetime"))
    proposed_dep = _parse_dt(flight.get("departure_datetime"))
    if original_dep and proposed_dep:
        hours = (proposed_dep - original_dep).total_seconds() / 3600
        if hours > 48:
            return (
                False,
                f"Replacement departs {hours:.0f}h after original (limit 48h).",
            )
        if hours < -12:
            return False, "Replacement departs too far before the original flight."

    connection = flight.get("connection_minutes")
    if connection is not None and connection < 60:
        return (
            False,
            f"Connection time {connection} minutes is under the 60-minute minimum.",
        )

    return True, "Rebooking proposal complies with policy."


def check_refund_policy(
    booking: BookingDetails,
    solution: ProposedSolution,
) -> tuple[bool, str]:
    amount = solution.get("refund_amount")
    if amount is None:
        return False, "Refund proposal is missing refund_amount."

    fare = float(booking.get("fare_amount") or 0)
    tax = float(booking.get("tax_amount") or 0)
    disruption = (booking.get("disruption_type") or "").lower()
    fare_type = (booking.get("fare_type") or "basic").lower()

    if disruption in {"cancelled", "delayed"}:
        expected = fare
        reason = "airline disruption → full fare"
    else:
        if fare_type == "flex" or booking.get("fare_type") == "refundable":
            expected = fare
            reason = "passenger choice on refundable fare → full fare"
        else:
            expected = tax
            reason = "passenger choice on non-refundable fare → taxes only"

    if abs(float(amount) - expected) > 0.01:
        return (
            False,
            f"Refund amount ${amount} incorrect; expected ${expected:.2f} ({reason}).",
        )
    return True, f"Refund of ${amount:.2f} complies with policy ({reason})."


def check_compensation_policy(
    booking: BookingDetails,
    solution: ProposedSolution,
) -> tuple[bool, str]:
    amount = solution.get("compensation_amount")
    if amount is None:
        return False, "Compensation proposal is missing compensation_amount."

    disruption = (booking.get("disruption_type") or "").lower()
    delay_hours = float(booking.get("delay_hours") or 0)

    if disruption == "cancelled" or delay_hours > 6:
        expected = 400.0
        band = "cancelled or delay over 6 hours"
    elif delay_hours >= 3:
        expected = 200.0
        band = "delay 3 to 6 hours"
    else:
        expected = 0.0
        band = "delay under 3 hours"

    if abs(float(amount) - expected) > 0.01:
        return (
            False,
            f"Compensation ${amount} incorrect; expected ${expected:.0f} ({band}).",
        )
    return True, f"Compensation of ${amount:.0f} complies with policy ({band})."


def evaluate_policy(
    booking: Optional[BookingDetails],
    solution: Optional[ProposedSolution],
) -> tuple[bool, str]:
    if not solution:
        return False, "No proposed solution to check."
    if not booking:
        return False, "Booking details are missing; cannot enforce policy."

    sol_type = solution.get("type")
    if sol_type == "rebook":
        return check_rebook_policy(booking, solution)
    if sol_type == "refund":
        return check_refund_policy(booking, solution)
    if sol_type == "compensation":
        return check_compensation_policy(booking, solution)
    return False, f"Unknown solution type: {sol_type}"


POLICY_RULES: dict[str, str] = {
    "rebook": (
        "Same cabin class or lower; departs within 48 hours of original; "
        "connection time at least 60 minutes."
    ),
    "refund": (
        "Airline cancelled/disrupted: full fare. "
        "Passenger choice on non-refundable fare: taxes only."
    ),
    "compensation": (
        "Delay under 3 hours: $0. 3 to 6 hours: $200. "
        "Over 6 hours or cancelled: $400."
    ),
}
