"""
================================================================
POSTCODE LOOKUP API
================================================================

Provides optional postcode assistance for registration.

The browser calls:

    /api/postcode-lookup/

This Django endpoint then calls:

    https://api.postcodes.io/postcodes/<postcode>

IMPORTANT
---------
Postcodes.io is an optional convenience service.

Registration MUST NOT depend on it.

If:
    - the postcode is invalid,
    - Postcodes.io is unavailable,
    - the network fails,
    - the external service times out,

the endpoint simply reports that the lookup was unsuccessful.

The member can still enter the complete address manually.

Postcodes.io provides postcode/geographic information. It does
NOT provide individual property addresses. Therefore this
endpoint returns only:

    town
    county
    country

The member remains responsible for:

    house number/name
    address line 1
    address line 2
    postcode
================================================================
"""

import requests

from django.http import JsonResponse


# ================================================================
# POSTCODES.IO
# ================================================================

POSTCODES_IO_URL = (
    "https://api.postcodes.io/postcodes/"
)


# ================================================================
# POSTCODE LOOKUP
# ================================================================

def postcode_lookup(request):
    """
    Look up a UK postcode using Postcodes.io.

    This is an OPTIONAL registration convenience.

    A failure here must never prevent manual address entry.
    """

    # ============================================================
    # GET POSTCODE
    # ============================================================

    postcode = (
        request.GET.get(
            "postcode",
            "",
        )
        .strip()
    )


    # ============================================================
    # NO POSTCODE
    # ============================================================

    if not postcode:

        return JsonResponse({
            "success": False,
            "error": "Postcode required",
        })


    # ============================================================
    # CALL POSTCODES.IO
    # ============================================================
    #
    # The postcode is passed as a URL path component.
    #
    # Postcodes.io accepts postcode variations such as:
    #
    #     SW1A 1AA
    #     sw1a1aa
    #
    # The service requires no API key.
    # ============================================================

    url = (
        f"{POSTCODES_IO_URL}"
        f"{postcode}"
    )


    try:

        response = requests.get(
            url,
            timeout=5,
        )


    except requests.RequestException:

        # ========================================================
        # EXTERNAL SERVICE UNAVAILABLE
        # ========================================================
        #
        # IMPORTANT:
        #
        # Do NOT turn this into a registration error.
        #
        # The frontend will allow manual address entry.
        # ========================================================

        return JsonResponse({
            "success": False,
            "error": "Postcode lookup unavailable",
        })


    # ============================================================
    # INVALID / UNKNOWN POSTCODE
    # ============================================================

    if response.status_code != 200:

        return JsonResponse({
            "success": False,
            "error": "Postcode not found",
        })


    # ============================================================
    # PARSE RESPONSE
    # ============================================================

    try:

        payload = response.json()

    except ValueError:

        return JsonResponse({
            "success": False,
            "error": "Invalid postcode lookup response",
        })


    result = payload.get(
        "result"
    )


    if not isinstance(
        result,
        dict,
    ):

        return JsonResponse({
            "success": False,
            "error": "Postcode information unavailable",
        })


    # ============================================================
    # RETURN USEFUL ADDRESS INFORMATION
    # ============================================================
    #
    # IMPORTANT:
    #
    # Postcodes.io has several geographic fields.
    #
    # We deliberately keep the registration response small.
    #
    # The existing registration model uses:
    #
    #     town
    #     county
    #     country
    #
    # Do not populate line_1 or house_number from geographic
    # fields. They are NOT property addresses.
    # ============================================================

    town = (
        result.get("admin_district")
        or result.get("parish")
        or ""
    )

    county = (
        result.get("admin_county")
        or result.get("region")
        or ""
    )

    country = (
        result.get("country")
        or ""
    )


    # ============================================================
    # SUCCESS
    # ============================================================

    return JsonResponse({
        "success": True,
        "town": town,
        "county": county,
        "country": country,
    })