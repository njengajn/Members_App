"""
Django settings for core project.
Generated with Django 5.2.7.
"""

import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

# =========================================================
# LOAD ENV VARIABLES
# =========================================================

load_dotenv()

# -----------------------------
# BASE DIRECTORY
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# -----------------------------
# SECURITY
# -----------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "localhost,127.0.0.1",
).split(",")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]

# =========================================================
# SESSION SECURITY
# =========================================================

# 30 minutes of inactivity
SESSION_COOKIE_AGE = 1800

# Reset timeout on every request
SESSION_SAVE_EVERY_REQUEST = True

# Logout when browser closes
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# -----------------------------
# AUTHENTICATION
# -----------------------------
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'  # default landing page after login
LOGOUT_REDIRECT_URL = '/'  # default landing page after logout

#-------------------------
#STRIPE 
#------------------------

STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")


# -----------------------------
# INSTALLED APPS
# -----------------------------
INSTALLED_APPS = [
    # Django default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

     # Your apps
    'backend.members',
    
       # Third-party apps
    'rest_framework',

    "channels",
    
    'django_extensions',

]
ASGI_APPLICATION = "backend.core.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


# -----------------------------
# MIDDLEWARE
# -----------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    "whitenoise.middleware.WhiteNoiseMiddleware",
    'django.contrib.sessions.middleware.SessionMiddleware',  # before auth
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # after sessions
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'backend.members.middleware.incomplete_registration_redirect',  # custom middleware
    'backend.members.middleware.RetiredMemberMiddleware',
]

# -----------------------------
# URLS & WSGI
# -----------------------------
ROOT_URLCONF = "backend.core.urls"
WSGI_APPLICATION = 'backend.core.wsgi.application'

# -----------------------------
# DATABASE
# -----------------------------
DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv(
            "DATABASE_URL",
            "sqlite:///db.sqlite3",
        ),
        conn_max_age=600,
    )
}

STATIC_ROOT = BASE_DIR / "staticfiles"

# -----------------------------
# PASSWORD VALIDATORS
# -----------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# -----------------------------
# INTERNATIONALIZATION
# -----------------------------
LANGUAGE_CODE = "en-gb"
TIME_ZONE = 'Europe/London'
USE_L10N = True
USE_TZ = True

# -----------------------------
# STATIC FILES
# -----------------------------

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "backend" / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"


# -----------------------------
# TEMPLATES
# -----------------------------
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / "backend" / "members" / "templates",
            BASE_DIR / "backend" / "core" / "templates",
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',  # only once
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'backend.members.context_processors.user_role_context',  # custom
                #'backend.members.context_processors.pending_document_requests',
            ],
        },
    },
]

# -----------------------------
# DEFAULT AUTO FIELD
# -----------------------------
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -----------------------------
# REST FRAMEWORK
# -----------------------------
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ]
}

AUTHENTICATION_BACKENDS = [
     "backend.members.backends.EmailOrUsernameBackend",
]

# -----------------------------
# STRIPE SETTINGS
# -----------------------------
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

TWILIO_STRIPE_PAYMENT_TEMPLATE_SID = os.getenv("TWILIO_STRIPE_PAYMENT_TEMPLATE_SID")

TWILIO_PAYMENT_REQUEST_TEMPLATE_SID  = os.getenv(
    "TWILIO_PAYMENT_REQUEST_TEMPLATE_SID"
    )

TWILIO_PAYMENT_CONFIRMED_TEMPLATE_SID = os.getenv("TWILIO_PAYMENT_CONFIRMED_TEMPLATE_SID")

TWILIO_PAYMENT_REJECTED_TEMPLATE_SID = os.getenv("TWILIO_PAYMENT_REJECTED_TEMPLATE_SID")

TWILIO_MEMBER_RETIRED_TEMPLATE_SID = os.getenv("TWILIO_MEMBER_RETIRED_TEMPLATE_SID")

TWILIO_MEMBER_ACTIVATED_TEMPLATE_SID = os.getenv("TWILIO_MEMBER_ACTIVATED_TEMPLATE_SID")

TWILIO_STRIPE_PAYMENT_TEMPLATE_SID = os.getenv("TWILIO_STRIPE_PAYMENT_TEMPLATE_SID")

# Default fallback prefix if organization has none
DEFAULT_MEMBER_PREFIX = "KRO-"

# Starting number per organization
DEFAULT_MEMBER_START_NUMBER = 1000

#DEFAULT_FROM_EMAIL = "noreply@kenyareadingorganisation.com"
#EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# =========================================================
# EMAIL CONFIGURATION
# =========================================================

EMAIL_BACKEND = (
    "django.core.mail.backends.smtp.EmailBackend"
)

EMAIL_HOST = "smtp.gmail.com"

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.getenv(
    "EMAIL_HOST_USER"
)

EMAIL_HOST_PASSWORD = os.getenv(
    "EMAIL_HOST_PASSWORD"
)

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

EMAIL_TIMEOUT = 10

# ======================================================
# MEDIA FILES (USER UPLOADS)
# ======================================================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ============================================
# GOOGLE reCAPTCHA SETTINGS
# ============================================

RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY")


TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# =========================================================
# SITE URL
# =========================================================

SITE_URL = "https://i.ibb.co/39c3sC5s"

# =========================================================
# MEMBER PORTAL
# =========================================================

MEMBER_PORTAL_URL = (
    "http://127.0.0.1:8000"
)

#==========================
#MEMBER_PORTAL_URL = (
 #   "https://www.kro.com"
#)
#======================
PAYMENTS_PORTAL_URL = (
    f"{MEMBER_PORTAL_URL}/payments"
)








