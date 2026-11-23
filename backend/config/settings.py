"""Django settings. All environment-specific values come from the .env file in the project root."""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
PROJECT_ROOT = BASE_DIR.parent  # llm-gateway/
load_dotenv(PROJECT_ROOT / ".env")


def env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() == "true"


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key")
DEBUG = env_bool("DJANGO_DEBUG", "true")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",  # refresh tokens that were logged out / rotated
    "gateway",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "llm_gateway"),
        "USER": os.environ.get("POSTGRES_USER", "llm_gateway"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
# Monthly budgets and the dashboard's "per day" numbers use this time zone.
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Two kinds of callers:
# - apps calling models: API key (gateway/auth.py), set on the chat view itself
# - dashboard users: JWT ("Authorization: Bearer <access token>"), the default below
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "EXCEPTION_HANDLER": "gateway.exceptions.api_exception_handler",
}

# access token: short-lived, sent with every dashboard call.
# refresh token: only used to get a new access token; rotates on every use, the old one is blacklisted.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES") or "15")),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=int(os.environ.get("JWT_REFRESH_HOURS") or "8")),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Redis: answer cache. Without REDIS_URL (laptop, tests) Django's in-memory cache is used.
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- AWS / Bedrock ---
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_SESSION_TOKEN = os.environ.get("AWS_SESSION_TOKEN", "")
BEDROCK_READ_TIMEOUT = int(os.environ.get("BEDROCK_READ_TIMEOUT") or "120")

# --- Gateway ---
GATEWAY_MAX_TOKENS = int(os.environ.get("GATEWAY_MAX_TOKENS") or "4096")
GATEWAY_BUDGET_ALERT_PERCENT = int(os.environ.get("GATEWAY_BUDGET_ALERT_PERCENT") or "80")
GATEWAY_CACHE_TTL_SECONDS = int(os.environ.get("GATEWAY_CACHE_TTL_SECONDS") or "3600")
# Fake model answers (no AWS, no cost) for load tests and demos. Only works while DEBUG is on.
GATEWAY_FAKE_BEDROCK = env_bool("GATEWAY_FAKE_BEDROCK")
GATEWAY_FAKE_LATENCY_MS = int(os.environ.get("GATEWAY_FAKE_LATENCY_MS") or "0")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO").upper()},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
