"""
Django settings for Lamarca AI.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ── Load .env manually (no third-party library) ───────────
def _load_env():
    env_path = BASE_DIR / '.env'
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, _, val = line.partition('=')
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

# ── Security ──────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-local-dev-key-change-in-prod')
DEBUG = os.environ.get('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '127.0.0.1,localhost,.onrender.com,.run.app,.vercel.app').split(',')

# Django needs these for POST requests over HTTPS behind a proxy (Cloud Run, Render, Vercel)
CSRF_TRUSTED_ORIGINS = [
    'https://*.onrender.com',
    'https://*.run.app',
    'https://*.vercel.app',
]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# When set, CanonicalHostRedirectMiddleware bounces requests on Vercel
# deploy-hash URLs to this host so Google Sign-In etc. always see the
# registered origin. Leave empty in local dev.
CANONICAL_HOST = os.environ.get('CANONICAL_HOST', '')

# Google Sign-In's popup posts the credential back via window.opener.postMessage.
# Django's default COOP of 'same-origin' breaks that. Allow popups to keep their opener.
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin-allow-popups'

# ── Apps ──────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'tailwind',
    'theme',
    'core',
]

TAILWIND_APP_NAME = 'theme'
INTERNAL_IPS = ['127.0.0.1']

# ── Middleware ─────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.CanonicalHostRedirectMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'lamarca_ai.urls'

# ── Templates ─────────────────────────────────────────────
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

WSGI_APPLICATION = 'lamarca_ai.wsgi.application'

# ── Database ───────────────────────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import dj_database_url
    DATABASES = {'default': dj_database_url.parse(DATABASE_URL, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ── Auth ───────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

# ── i18n ───────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ── Static files ───────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
# Vercel doesn't run collectstatic, so let WhiteNoise serve directly
# from each app's static/ directory via Django's finders.
WHITENOISE_USE_FINDERS = True
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── Google Gemini ──────────────────────────────────────────
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

# ── Google Sign-In (OAuth Client ID from GCP Console) ──────
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')

# Only allow signups from @gmail.com addresses
ALLOWED_EMAIL_DOMAIN = 'gmail.com'

# ── Supadata (YouTube transcript API) ──────────────────────────────────────
SUPADATA_API_KEY = os.environ.get('SUPADATA_API_KEY', '')

# ── Stripe (credit packs) ──────────────────────────────────────────────────
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# Each entry maps a Stripe Price ID → number of generation credits granted.
# We accept several env var name spellings so Vercel can use whichever
# convention feels natural (singular/plural, by dollar amount, by credit count).
def _first_env(*names: str) -> str:
    for n in names:
        v = os.environ.get(n, '').strip()
        if v:
            return v
    return ''

STRIPE_CREDIT_PACKS = [
    {
        'price_id': _first_env('STRIPE_PRICE_1_CREDIT', 'STRIPE_PRICE_1_CREDITS'),
        'credits': 1,
        'price_label': '$1',
        'tagline': 'One draft, one dollar.',
    },
    {
        'price_id': _first_env('STRIPE_PRICE_5_CREDITS', 'STRIPE_PRICE_5_CREDIT'),
        'credits': 5,
        'price_label': '$5',
        'tagline': 'Five drafts. Same price as a coffee.',
    },
    {
        'price_id': _first_env(
            'STRIPE_PRICE_12_CREDITS',
            'STRIPE_PRICE_10_CREDIT',
            'STRIPE_PRICE_10_CREDITS',
        ),
        'credits': 12,
        'price_label': '$10',
        'tagline': 'Twelve drafts. Two free on the house.',
        'badge': 'Best value',
    },
]
# Lookup for the webhook: price_id → credits
STRIPE_PRICE_TO_CREDITS = {p['price_id']: p['credits'] for p in STRIPE_CREDIT_PACKS if p['price_id']}

# Free generations new users get before they need to buy credits
FREE_GENERATIONS = 3
