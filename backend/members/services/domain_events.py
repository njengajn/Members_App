#backend/members/services/domain_events.py

from backend.members.services.event_handlers import (
    handle_claim_approved,
    handle_payment_completed,
    handle_claim_settled
)


"""
Domain Event Dispatcher

Responsible for triggering event handlers
when important domain actions occur.
"""

EVENT_REGISTRY = {}


def register_event(event_name, handler):
    """
    Register event handlers.
    """
    if event_name not in EVENT_REGISTRY:
        EVENT_REGISTRY[event_name] = []

    EVENT_REGISTRY[event_name].append(handler)


def dispatch_event(event_name, payload):
    """
    Trigger all handlers for an event.
    """

    handlers = EVENT_REGISTRY.get(event_name, [])

    for handler in handlers:
        handler(payload)
        


        

