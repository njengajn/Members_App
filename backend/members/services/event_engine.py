# backend/members/services/event_engine.py

"""
DOMAIN EVENT ENGINE

Central system to:
✔ register event handlers
✔ trigger events safely
✔ avoid circular imports

Used by:
- claims lifecycle
- payments
- compliance
"""

from collections import defaultdict


# Stores all registered events
_EVENT_REGISTRY = defaultdict(list)


def register_event(event_name, handler):
    """
    Register a function to an event.

    Example:
    register_event("claim_approved", handle_claim_approved)
    """

    _EVENT_REGISTRY[event_name].append(handler)


def trigger_event(event_name, **kwargs):
    """
    Trigger all handlers attached to event.

    Example:
    trigger_event("claim_approved", claim=claim)
    """

    handlers = _EVENT_REGISTRY.get(event_name, [])

    for handler in handlers:
        try:
            handler(**kwargs)
        except Exception as e:
            # Prevent system crash — log instead
            print(f"[EVENT ERROR] {event_name}: {e}")
