"""
Registration and member credential validation helpers.

This module contains the validation rules that must remain consistent across
registration and password reset.  Views should call these helpers rather than
duplicating regular expressions or password rules.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


# UK mobile numbers accepted by the application.
#
# Local form:
#   07123456789  -> exactly 11 digits and starts with 07
#
# International form:
#   +447123456789 -> +44 followed by 10 digits beginning with 7
#
# We deliberately do not silently accept arbitrary international numbers
# because this field is currently defined as a UK mobile number.
UK_MOBILE_LOCAL_RE = re.compile(r"^07\d{9}$")
UK_MOBILE_INTL_RE = re.compile(r"^\+447\d{9}$")


def clean_email(value):
    """Return a normalised email address suitable for validation/storage."""
    return (value or "").strip().lower()


def validate_email_address(value):
    """
    Validate an email address using Django's EmailValidator.

    A ValidationError is raised when the value is not a valid email address.
    """
    email = clean_email(value)

    if not email:
        raise ValidationError("Email address is required.")

    EmailValidator(
        message="Enter a valid email address."
    )(email)

    return email


def clean_uk_mobile(value):
    """
    Normalise and validate a UK mobile number.

    Accepted:
        07123456789
        +447123456789

    The stored value is normalised to +44XXXXXXXXXX.
    """
    phone = (value or "").strip()

    # Remove ordinary formatting characters without changing the number's
    # meaning. This permits common user input such as 07123 456789.
    phone = re.sub(r"[\s().-]+", "", phone)

    if UK_MOBILE_LOCAL_RE.fullmatch(phone):
        return "+44" + phone[1:]

    if UK_MOBILE_INTL_RE.fullmatch(phone):
        return phone

    raise ValidationError(
        "Enter a valid UK mobile number, for example "
        "07123456789 or +447123456789."
    )


def validate_member_password(password, user=None):
    """
    Validate the application's member password policy.

    This explicit policy is intentionally independent of browser validation.
    It is called by both registration and password reset so the two flows
    cannot drift apart.

    Rules:
        - at least 8 characters
        - at least one uppercase letter
        - at least one lowercase letter
        - at least one number
        - at least one special character
    """
    password = password or ""
    errors = []

    if len(password) < 8:
        errors.append("at least 8 characters")

    if not re.search(r"[A-Z]", password):
        errors.append("one uppercase letter")

    if not re.search(r"[a-z]", password):
        errors.append("one lowercase letter")

    if not re.search(r"\d", password):
        errors.append("one number")

    if not re.search(r"[^A-Za-z0-9]", password):
        errors.append("one special character")

    if errors:
        raise ValidationError(
            "Password must contain " + ", ".join(errors) + "."
        )

    return True