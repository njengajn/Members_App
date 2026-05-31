from twilio.rest import Client

from django.conf import settings


def send_whatsapp_otp(phone, otp):

    """
    Send OTP via WhatsApp.
    """

    client = Client(
        settings.TWILIO_ACCOUNT_SID,
        settings.TWILIO_AUTH_TOKEN
    )

    message = client.messages.create(

        body=(
            f"KRO Verification Code: {otp}\n"
            f"Expires in 5 minutes."
        ),

        from_=settings.TWILIO_WHATSAPP_NUMBER,

        to=f"whatsapp:{phone}"
    )

    return message.sid