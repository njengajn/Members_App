import requests
from django.http import JsonResponse


def postcode_lookup(request):
    postcode = request.GET.get("postcode")

    if not postcode:
        return JsonResponse({"success": False})

    url = f"https://api.postcodes.io/postcodes/{postcode}"

    response = requests.get(url)

    if response.status_code != 200:
        return JsonResponse({"success": False})

    data = response.json().get("result")

    return JsonResponse({
        "success": True,
        "town": data.get("admin_district"),
        "county": data.get("region"),
        "country": data.get("country"),
    })