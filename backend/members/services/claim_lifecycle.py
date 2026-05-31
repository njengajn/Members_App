
"""
Centralized claim lifecycle logic.

To prevent invalid status transitions
that cause regressions.
"""

VALID_TRANSITIONS = {

    "received": ["approved", "rejected"],

    "approved": ["open"],

    "open": ["settled"],

    "settled": [],

    "rejected": []
}


def can_transition(current_status, new_status):

    allowed = VALID_TRANSITIONS.get(current_status, [])

    return new_status in allowed

