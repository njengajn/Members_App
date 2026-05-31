from django.db import transaction
from backend.members.models import Member


# ==========================================================
# RESTORE MEMBER (WRAPPER)
# ==========================================================
@transaction.atomic
def restore_member(
    member,
    admin_user=None,
    reason="Member restored by administrator",
):
    """
    ADMIN: Restore member

    Delegates to model lifecycle method.
    """

    member.restore(
        admin_user=admin_user,
        reason=reason,
    )


# ==========================================================
# RETIRE MEMBER (WRAPPER)
# ==========================================================
@transaction.atomic
def retire_member_manually(member, admin_user=None, reason="manual_admin_action"):
    """
    ADMIN: Manually retire a member

    Delegates to model lifecycle method.
    """

    member.retire(
        reason=reason,
        admin_user=admin_user
    )