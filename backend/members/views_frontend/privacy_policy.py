from django.shortcuts import render


def privacy_policy(request):

    """
    GDPR / Privacy policy page.
    """

    return render(
        request,
        "members/privacy_policy.html"
    )