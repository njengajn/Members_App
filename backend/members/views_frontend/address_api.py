from django.http import JsonResponse
from backend.members.models import Address


def address_autocomplete(request):
    """
    Returns address suggestions based on user input.
    Used for live dropdown autocomplete.
    """

    query = request.GET.get("q", "").strip()

    if not query:
        return JsonResponse({"results": []})

    # 🔎 Search across key fields
    addresses = Address.objects.filter(
        line_1__icontains=query
    )[:10]

    results = []

    for addr in addresses:
        results.append({
            "id": addr.id,
            "label": f"{addr.house_number}, {addr.line_1}, {addr.town}, {addr.postcode}",
            "house_number": addr.house_number,
            "line_1": addr.line_1,
            "line_2": addr.line_2,
            "town": addr.town,
            "county": addr.county,
            "postcode": addr.postcode,
            "country": addr.country,
        })

    return JsonResponse({"results": results})

