from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

User = get_user_model()


# =========================================================
# EMAIL OR USERNAME AUTH BACKEND
# =========================================================

class EmailOrUsernameBackend(ModelBackend):
    """
    Custom authentication backend.

    FEATURES
    -------------------------------------------------
    ✔ Login using email
    ✔ Login using username

    SECURITY
    -------------------------------------------------
    ✔ Blocks inactive users
    ✔ Blocks retired members

    IMPORTANT
    -------------------------------------------------
    Never raise exceptions inside
    user_can_authenticate().
    """

    # =====================================================
    # AUTHENTICATE
    # =====================================================

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs
    ):

        if username is None:
            username = kwargs.get("email")

        if username is None or password is None:
            return None

        # -------------------------------------------------
        # TRY EMAIL
        # -------------------------------------------------

        try:

            user = User.objects.get(
                email__iexact=username
            )

        except User.DoesNotExist:

            # -------------------------------------------------
            # FALLBACK TO USERNAME
            # -------------------------------------------------

            try:

                user = User.objects.get(
                    username__iexact=username
                )

            except User.DoesNotExist:
                return None

        # -------------------------------------------------
        # PASSWORD CHECK
        # -------------------------------------------------

        if not user.check_password(password):
            return None

        # -------------------------------------------------
        # SAFE AUTH CHECK
        # -------------------------------------------------

        if not self.user_can_authenticate(user):
            return None

        return user

    # =====================================================
    # SAFE AUTH CHECK
    # =====================================================

    def user_can_authenticate(self, user):
        """
        Prevent inactive and retired users
        from authenticating.

        IMPORTANT:
        Return False instead of raising exceptions.
        """

        # -------------------------------------------------
        # DJANGO ACTIVE FLAG
        # -------------------------------------------------

        if not getattr(user, "is_active", True):
            return False

        # -------------------------------------------------
        # MEMBER STATUS
        # -------------------------------------------------

        try:

            member = getattr(user, "member", None)

            if member and member.status == "retired":
                return False

        except Exception:
            pass

        return True


class CustomAuthBackendOnHold(ModelBackend):
    """
    Custom authentication backend to:
    - Allow login
    - But block inactive users with clear message
    """

    def user_can_authenticate(self, user):
        """
        Override default behaviour.
        Django normally just returns False silently.
        """
        if not user.is_active:
            raise Exception("inactive_account")
        return super().user_can_authenticate(user)
