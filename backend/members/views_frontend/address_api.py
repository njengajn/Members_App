"""
UK address lookup API used by member registration.

The registration form now uses a postcode-first lookup.  Ideal Postcodes is
used for the authoritative UK address list when an API key is configured.

For regression safety, the existing local Address table is retained as a
fallback.  This means development or an environment without the external API
key does not suddenly lose the existing address-search capability.
"""

import requests

from django.conf import settings
from django.http import JsonResponse

from backend.members.models import Address


IDEAL_POSTCODES_URL = (
    "https://api.ideal-postcodes.co.uk/v1/postcodes/"
)


def _local_address_results(query):
    """
    Preserve the application's existing database-backed lookup.

    This is intentionally retained as a fallback rather than deleting the
    previous behaviour.
    """
    addresses = Address.objects.filter(
        line_1__icontains=query
    )[:10]

    results = []

    for addr in addresses:
        results.append({
            "id": addr.id,
            "label": (
                f"{addr.house_number}, "
                f"{addr.line_1}, "
                f"{addr.town}, "
                f"{addr.postcode}"
            ),
            "house_number": addr.house_number,
            "line_1": addr.line_1,
            "line_2": addr.line_2,
            "town": addr.town,
            "county": addr.county,
            "postcode": addr.postcode,
            "country": addr.country,
        })

    return results


def _ideal_address_to_result(address):
    """
    Convert an Ideal Postcodes address into the field structure already
    expected by the registration template and JavaScript.

    We deliberately map:
        building_number -> house_number
        thoroughfare    -> line_1
        post_town       -> town
        county          -> county
        postcode        -> postcode
        country         -> country

    This avoids changing the existing Address model or registration session
    field names.
    """
    building_number = (
        address.get("building_number")
        or address.get("premise")
        or ""
    )

    line_1 = (
        address.get("thoroughfare")
        or address.get("line_1")
        or ""
    )

    # Preserve useful secondary address information such as a flat/building
    # name and dependant locality without inventing new model fields.
    raw_line_2 = (address.get("line_2") or "").strip()

    # Ideal's line_2 can contain the same building/street information that
    # we have already separated into house_number and line_1.  Only retain it
    # when it adds information that is not already represented.
    if (
        raw_line_2
        and raw_line_2.casefold() in {
            line_1.casefold(),
            f"{building_number} {line_1}".strip().casefold(),
        }
    ):
        raw_line_2 = ""

    secondary_parts = [
        address.get("sub_building_name"),
        address.get("building_name"),
        raw_line_2,
        address.get("dependant_locality"),
    ]

    line_2 = ", ".join(
        part.strip()
        for part in secondary_parts
        if part and part.strip()
    )

    source_country = (
        address.get("country")
        or ""
    ).strip()

    # The existing application uses "UK" as its default country value.
    # Keep that convention for all UK addresses instead of storing
    # "England", "Scotland", etc. as separate countries.
    if (
        address.get("country_iso_2") == "GB"
        or source_country.lower() in {
            "england",
            "scotland",
            "wales",
            "northern ireland",
            "united kingdom",
        }
    ):
        country = "UK"
    else:
        country = source_country or "UK"

    return {
        "id": address.get("id"),
        "label": ", ".join(
            part
            for part in [
                building_number,
                line_1,
                line_2,
                address.get("post_town"),
                address.get("postcode"),
            ]
            if part
        ),
        "house_number": building_number,
        "line_1": line_1,
        "line_2": line_2,
        "town": address.get("post_town") or "",
        "county": (
            address.get("county")
            or address.get("administrative_county")
            or ""
        ),
        "postcode": address.get("postcode") or "",
        "country": country,
    }


def _ideal_postcode_lookup(postcode):
    """
    Look up every address belonging to the supplied UK postcode.

    Ideal Postcodes documents this endpoint specifically for postcode-driven
    address lookup.  A timeout prevents registration from hanging if the
    external service is unavailable.
    """
    api_key = getattr(
        settings,
        "IDEAL_POSTCODES_API_KEY",
        "",
    ).strip()

    if not api_key:
        return None

    try:
        response = requests.get(
            f"{IDEAL_POSTCODES_URL}{postcode}",
            params={
                "api_key": api_key,
                "context": "GBR",
            },
            timeout=5,
        )

        if response.status_code != 200:
            return None

        payload = response.json()

        addresses = payload.get("result", [])

        return [
            _ideal_address_to_result(address)
            for address in addresses
        ]

    except (requests.RequestException, ValueError):
        # Registration must remain usable if the external address service
        # has a temporary failure.
        return None


def address_autocomplete(request):
    """
    Return registration address suggestions.

    Primary behaviour:
        /api/address-autocomplete/?q=RG1%201AA

    The JavaScript deliberately sends a postcode once it has reached the
    minimum postcode-search length.

    Regression behaviour:
        Non-postcode queries continue to search the local Address table,
        preserving the old endpoint contract for any other callers.
    """
    query = request.GET.get(
        "postcode",
        request.GET.get("q", ""),
    ).strip()

    if not query:
        return JsonResponse({"results": []})

    # Normalise the query for postcode lookup.  Spaces are harmless and
    # Ideal Postcodes accepts postcode searches case-insensitively.
    postcode = " ".join(query.upper().split())

    # A UK postcode normally contains a space and is between 5 and 8
    # characters after whitespace normalisation.  We do not attempt to
    # implement a full postcode regex here; the address service is the
    # authoritative source for whether the postcode exists.
    looks_like_postcode = (
        len(postcode.replace(" ", "")) >= 5
        and any(char.isdigit() for char in postcode)
    )

    if looks_like_postcode:
        results = _ideal_postcode_lookup(postcode)

        if results is not None:
            return JsonResponse({
                "results": results,
            })

        # External service unavailable/no key: retain the existing local
        # Address model as a safe fallback.
        local_results = list(
            Address.objects.filter(
                postcode__iexact=postcode
            )[:100]
        )

        if local_results:
            return JsonResponse({
                "results": [
                    {
                        "id": addr.id,
                        "label": (
                            f"{addr.house_number}, "
                            f"{addr.line_1}, "
                            f"{addr.town}, "
                            f"{addr.postcode}"
                        ),
                        "house_number": addr.house_number,
                        "line_1": addr.line_1,
                        "line_2": addr.line_2,
                        "town": addr.town,
                        "county": addr.county,
                        "postcode": addr.postcode,
                        "country": addr.country,
                    }
                    for addr in local_results
                ],
            })

        return JsonResponse({
            "results": [],
            "error": (
                "Address lookup is temporarily unavailable. "
                "Please enter the address manually."
            ),
        })

    # Preserve the old free-text local address search for any existing
    # callers that still use q=street-name.
    return JsonResponse({
        "results": _local_address_results(query),
    })
