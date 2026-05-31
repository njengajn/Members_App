import requests


def lookup_postcode(postcode):
    """
    Uses postcodes.io (UK free API)
    """
    url = f"https://api.postcodes.io/postcodes/{postcode}"

    response = requests.get(url)

    if response.status_code != 200:
        return None

    data = response.json().get("result")

    if not data:
        return None

    return {
        "town": data.get("admin_district"),
        "county": data.get("region"),
        "country": data.get("country"),
    }