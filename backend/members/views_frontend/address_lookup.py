import requests
from django.http import JsonResponse


def postcode_lookup(request):
    postcode = request.GET.get("postcode", "").strip()

    if not postcode:
        return JsonResponse({"error": "Postcode required"}, status=400)

    url = f"https://api.postcodes.io/postcodes/{postcode}"

    try:
        response = requests.get(url, timeout=5)
        data = response.json()

        if data["status"] != 200:
            return JsonResponse({"error": "Invalid postcode"}, status=400)

        result = data["result"]

        return JsonResponse({
            "line_1": result.get("admin_ward"),
            "town": result.get("admin_district"),
            "county": result.get("region"),
            "country": result.get("country"),
        })

    except Exception:
        return JsonResponse({"error": "Lookup failed"}, status=500)