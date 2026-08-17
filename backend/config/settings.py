"""
Django settings for config project.

The HTTP API is served by django-bolt (Rust/Actix) rather than Django's own
request path — see users/api.py for the routes and README.md for how to run
it. Django itself is still fully present: it owns the models, the migrations,
the admin, and the auth password hashing. django-bolt mounts Django's ASGI
application for anything it does not route itself, which is how /admin/ keeps
working.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/topics/settings/
"""

from pathlib import Path
import environ
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False) # Sets a default value and casts to boolean
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env('DEBUG')

ALLOWED_HOSTS = ['*']

# django-bolt reads these under the same names django-cors-headers used, and
# applies them in Rust, so there is no CORS middleware in MIDDLEWARE anymore.
# Note this only covers Bolt's own routes — the mounted Django app (i.e. the
# admin) is same-origin and does not need them.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True  # Allow cookies/auth headers

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party apps
    'django_bolt',

    # Local apps
    'users',
    'qr_generator',
]

# Only the mounted Django application (the admin) runs this chain; Bolt routes
# never touch it. Sessions and auth are what the admin actually needs.
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    },
    "OPTIONS": {
        # Executes whenever Django establishes a database connection
        "init_command": (
            "PRAGMA journal_mode=WAL;"
            "PRAGMA synchronous=NORMAL;"
            "PRAGMA busy_timeout=5000;"
        ),
        # Prevents "database is locked" errors by acquiring a write-lock immediately
        "transaction_mode": "IMMEDIATE",
    },
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


AUTH_USER_MODEL = "users.User"

# The API `runbolt` serves. Naming it explicitly turns off Bolt's per-app
# autodiscovery, so there is exactly one route table (see config/api.py).
BOLT_API = ["config.api:api"]

# Authentication defaults are not configured here — see config/security.py for
# why, and config/api.py for the routers that apply them.
#
# JWT lifetimes, carried over verbatim from the SimpleJWT config this replaces
# so existing clients see the same session behaviour.
ACCESS_TOKEN_LIFETIME = 60 * 60          # 60 minutes
REFRESH_TOKEN_LIFETIME = 60 * 60 * 24    # 1 day

CREATE_TEAMS=env('CREATE_TEAM', default=True)
TEAM_COUNT=env('TEAM_COUNT', default=3)
MAX_TEAM_HEALTH=env('MAX_TEAM_HEALTH', default=5)

# django-silk, off by default. `SILK=1` in .env turns it on and mounts the UI
# at /silk/ (staff login required — see SILKY_AUTHENTICATION below).
#
# What it can see is limited by the architecture: Silk is Django middleware,
# and Bolt routes /api/ in Rust without ever entering Django's chain. So Silk
# profiles what falls through to Django's ASGI application — the admin, and
# Silk itself — and records nothing for the Bolt API. Its overhead is real
# (a cProfile run and a row written per request), which is why it is a flag
# rather than a DEBUG-only default.
SILK_ENABLED = env.bool('SILK', default=False)

if SILK_ENABLED:
    INSTALLED_APPS.append('silk')
    # First in the chain, so the time it reports covers the whole of the rest
    # of it rather than just the view.
    MIDDLEWARE.insert(0, 'silk.middleware.SilkyMiddleware')

    SILKY_PYTHON_PROFILER = True
    # Only staff can read the recordings; without this the UI, and every
    # request body in it, is public — and ALLOWED_HOSTS here is '*'.
    SILKY_AUTHENTICATION = True
    SILKY_AUTHORISATION = True
    # Silk gates its views with @login_required, which sends anyone signed out
    # to LOGIN_URL. Django's default is /accounts/login/ and nothing serves
    # that here, so point it at the admin's login — the only one there is.
    # Scoped to this block because no other view in the project uses it.
    LOGIN_URL = '/admin/login/'
    # The recordings land in the same SQLite file as the game state, so cap
    # them. The check runs on ~10% of requests and trims back to the limit.
    SILKY_MAX_RECORDED_REQUESTS = 1000
    SILKY_MAX_RECORDED_REQUESTS_CHECK_PERCENT = 10

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "ERROR",
        },
    },
}
