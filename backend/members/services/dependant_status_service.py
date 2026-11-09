from django.db import transaction

from backend.members.models import Dependant


@transaction.atomic
def mark_dependant_deceased(dependant, *, deceased_at=None):
    """
    Permanently record a dependant's death.

    This operation must only be called after the associated
    death claim has passed the approved settlement checks.

    deceased_at is optional because the actual date of death
    may not be available from the verified claim information.
    """

    dependant = (
        Dependant.objects
        .select_for_update()
        .get(pk=dependant.pk)
    )

    # A deceased dependant must always remain retired.
    dependant.life_status = Dependant.LIFE_STATUS_DECEASED
    dependant.status = Dependant.STATUS_RETIRED

    # Do not replace an existing date with None.
    if deceased_at is not None:
        dependant.deceased_at = deceased_at

    dependant.save(
        update_fields=[
            "life_status",
            "status",
            "deceased_at",
        ]
    )

    return dependant