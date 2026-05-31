from backend.members.models import Claim, PaymentRequest


def get_claim_metrics():

    return {
        "received": Claim.objects.filter(status="received").count(),
        "approved": Claim.objects.filter(status="approved").count(),
        "open": Claim.objects.filter(status="open").count(),
        "rejected": Claim.objects.filter(status="rejected").count(),
    }


def get_payment_metrics():

    return {
        "active": PaymentRequest.objects.filter(status="active").count(),
        "closed": PaymentRequest.objects.filter(status="closed").count(),
    }
