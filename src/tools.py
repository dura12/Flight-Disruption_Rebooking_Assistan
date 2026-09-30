from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool


BOOKINGS: dict[str, dict[str, Any]] = {
    "XK9L2P": {
        "booking_ref": "XK9L2P",
        "passenger_name": "Alex Morgan",
        "origin": "LHR",
        "destination": "DXB",
        "flight_number": "EK002",
        "departure_datetime": "2026-10-01T08:00:00",
        "arrival_datetime": "2026-10-01T18:30:00",
        "cabin_class": "economy",
        "fare_type": "flex",
        "fare_amount": 650.0,
        "tax_amount": 85.0,
        "disruption_type": "cancelled",
        "delay_hours": 0.0,
        "status": "cancelled",
    },
    "DL6H01": {
        "booking_ref": "DL6H01",
        "passenger_name": "Sam Rivera",
        "origin": "JFK",
        "destination": "LAX",
        "flight_number": "AA100",
        "departure_datetime": "2026-10-02T09:00:00",
        "arrival_datetime": "2026-10-02T12:30:00",
        "cabin_class": "economy",
        "fare_type": "basic",
        "fare_amount": 320.0,
        "tax_amount": 45.0,
        "disruption_type": "delayed",
        "delay_hours": 6.0,
        "status": "delayed",
    },
    "BZONLY1": {
        "booking_ref": "BZONLY1",
        "passenger_name": "Jordan Lee",
        "origin": "CDG",
        "destination": "JFK",
        "flight_number": "AF006",
        "departure_datetime": "2026-10-03T10:00:00",
        "arrival_datetime": "2026-10-03T12:30:00",
        "cabin_class": "economy",
        "fare_type": "basic",
        "fare_amount": 480.0,
        "tax_amount": 60.0,
        "disruption_type": "cancelled",
        "delay_hours": 0.0,
        "status": "cancelled",
    },
    "CMPL01": {
        "booking_ref": "CMPL01",
        "passenger_name": "Casey Brooks",
        "origin": "ORD",
        "destination": "MIA",
        "flight_number": "UA455",
        "departure_datetime": "2026-10-04T14:00:00",
        "arrival_datetime": "2026-10-04T18:00:00",
        "cabin_class": "economy",
        "fare_type": "basic",
        "fare_amount": 210.0,
        "tax_amount": 35.0,
        "disruption_type": "cancelled",
        "delay_hours": 0.0,
        "status": "cancelled",
    },
}


FARE_RULES: dict[str, dict[str, Any]] = {
    "flex": {
        "fare_type": "flex",
        "refundable": True,
        "tax_amount_note": "Taxes are always refundable",
        "refund_on_airline_cancel": "full_fare",
        "refund_on_passenger_choice": "full_fare",
    },
    "basic": {
        "fare_type": "basic",
        "refundable": False,
        "tax_amount_note": "Only taxes refundable on passenger-initiated cancel",
        "refund_on_airline_cancel": "full_fare",
        "refund_on_passenger_choice": "taxes_only",
    },
}


FLIGHT_SEARCH: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("LHR", "DXB"): [
        {
            "flight_number": "EK004",
            "origin": "LHR",
            "destination": "DXB",
            "departure_datetime": "2026-10-01T22:00:00",
            "arrival_datetime": "2026-10-02T08:30:00",
            "cabin_class": "economy",
            "connection_minutes": None,
            "seats_available": 12,
        },
        {
            "flight_number": "BA109",
            "origin": "LHR",
            "destination": "DXB",
            "departure_datetime": "2026-10-01T14:00:00",
            "arrival_datetime": "2026-10-02T00:15:00",
            "cabin_class": "economy",
            "connection_minutes": None,
            "seats_available": 4,
        },
        {
            "flight_number": "EK008",
            "origin": "LHR",
            "destination": "DXB",
            "departure_datetime": "2026-10-01T11:00:00",
            "arrival_datetime": "2026-10-01T20:45:00",
            "cabin_class": "business",
            "connection_minutes": None,
            "seats_available": 2,
        },
    ],
    ("CDG", "JFK"): [
        {
            "flight_number": "AF010",
            "origin": "CDG",
            "destination": "JFK",
            "departure_datetime": "2026-10-03T16:00:00",
            "arrival_datetime": "2026-10-03T18:30:00",
            "cabin_class": "business",
            "connection_minutes": None,
            "seats_available": 3,
        },
        {
            "flight_number": "AF012",
            "origin": "CDG",
            "destination": "JFK",
            "departure_datetime": "2026-10-04T09:00:00",
            "arrival_datetime": "2026-10-04T11:45:00",
            "cabin_class": "business",
            "connection_minutes": 35,
            "seats_available": 1,
        },
        {
            "flight_number": "AF014",
            "origin": "CDG",
            "destination": "JFK",
            "departure_datetime": "2026-10-06T10:00:00",
            "arrival_datetime": "2026-10-06T12:30:00",
            "cabin_class": "business",
            "connection_minutes": None,
            "seats_available": 5,
        },
    ],
    ("JFK", "LAX"): [
        {
            "flight_number": "AA200",
            "origin": "JFK",
            "destination": "LAX",
            "departure_datetime": "2026-10-02T16:00:00",
            "arrival_datetime": "2026-10-02T19:30:00",
            "cabin_class": "economy",
            "connection_minutes": None,
            "seats_available": 8,
        },
    ],
}


@tool
def get_booking(booking_ref: str) -> str:
    """Look up a passenger booking by reference. Returns passenger, route, cabin, fare, disruption."""
    booking = BOOKINGS.get(booking_ref.upper())
    if not booking:
        return json.dumps({"error": f"No booking found for reference {booking_ref}"})
    return json.dumps(booking)


@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search alternative flights for a route on a given date (YYYY-MM-DD)."""
    key = (origin.upper(), destination.upper())
    flights = FLIGHT_SEARCH.get(key, [])
    payload = {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "date": date,
        "flights": flights,
        "count": len(flights),
    }
    if not flights:
        payload["message"] = "No flights found for this route in the mock catalogue."
    return json.dumps(payload)


@tool
def get_fare_rules(fare_type: str) -> str:
    """Return refundability rules and tax notes for a fare type."""
    rules = FARE_RULES.get(fare_type.lower())
    if not rules:
        return json.dumps({"error": f"Unknown fare type: {fare_type}"})
    return json.dumps(rules)


ALL_TOOLS = [get_booking, search_flights, get_fare_rules]
REBOOKING_TOOLS = [get_booking, search_flights]
REFUND_TOOLS = [get_booking, get_fare_rules]
COMPENSATION_TOOLS = [get_booking]
