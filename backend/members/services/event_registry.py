# backend/members/services/event_registry.py

"""
REGISTER ALL EVENTS HERE

This runs once when Django starts.
"""

from backend.members.services.event_engine import register_event

# Import handlers (safe direction)
from backend.members.services.event_handlers import (
    handle_claim_approved,
    handle_payment_completed,
    handle_claim_settled,
)


def register_all_events():
    register_event("claim_approved", handle_claim_approved)
    register_event("payment_completed", handle_payment_completed)
    register_event("claim_settled", handle_claim_settled)
    
    
def register_all_events():
    """
    Register all system events.

    Called once on app startup.
    """
    register_event("claim_approved", handle_claim_approved)
    register_event("payment_completed", handle_payment_completed)
    register_event("claim_settled", handle_claim_settled)

