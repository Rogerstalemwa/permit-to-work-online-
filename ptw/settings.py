import os
import django
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent

# DJANGO_ENV=production is set on the online host. On a PC (run.bat) nothing is set and the demo behaves as before.
PRODUCTION = os.environ.get('DJANGO_ENV') == 'production'
SECRET_KEY = os.environ.get('SECRET_KEY') or ('' if PRODUCTION else 'demo-only-change-before-real-use')
if PRODUCTION and not SECRET_KEY:
    raise RuntimeError('Set the SECRET_KEY environment variable before running in production.')
DEBUG = not PRODUCTION
if PRODUCTION:
    ALLOWED_HOSTS = [h.strip() for h in os.environ.get('ALLOWED_HOSTS', '').split(',') if h.strip()]
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        ALLOWED_HOSTS.append(os.environ['RENDER_EXTERNAL_HOSTNAME'])
    if os.environ.get('PUBLIC_URL'):
        from urllib.parse import urlparse
        ALLOWED_HOSTS.append(urlparse(os.environ['PUBLIC_URL']).hostname or '')
else:
    ALLOWED_HOSTS = ['*']

INSTALLED_APPS = ['django.contrib.sessions', 'django.contrib.staticfiles', 'permits']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware']
try:
    import whitenoise  # noqa: F401  (serves the logo and QR script in production)
    MIDDLEWARE.append('whitenoise.middleware.WhiteNoiseMiddleware')
except ImportError:
    pass
MIDDLEWARE.append('django.contrib.sessions.middleware.SessionMiddleware')
ROOT_URLCONF = 'ptw.urls'
WSGI_APPLICATION = 'ptw.wsgi.application'

# Database: PostgreSQL when DATABASE_URL is set (online), otherwise the local SQLite file.
if os.environ.get('DATABASE_URL'):
    import dj_database_url
    DATABASES = {'default': dj_database_url.config(conn_max_age=60, ssl_require=os.environ.get('DB_SSL_REQUIRE') == '1')}
else:
    _db_options = {'timeout': 30}
    if django.VERSION >= (5, 1):
        _db_options['transaction_mode'] = 'IMMEDIATE'   # take the write lock up front so concurrent saves queue instead of failing
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3', 'OPTIONS': _db_options}}

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if PRODUCTION:
    STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
                'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'}}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
TIME_ZONE = 'Africa/Kampala'
USE_TZ = True

if PRODUCTION:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')   # the host terminates HTTPS and forwards
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    if os.environ.get('HSTS_SECONDS'):
        SECURE_HSTS_SECONDS = int(os.environ['HSTS_SECONDS'])

# Email. Choose one: BREVO_API_KEY (web API, works on free hosts), EMAIL_HOST (SMTP), or nothing (saved as files in "outbox").
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
if BREVO_API_KEY:
    EMAIL_BACKEND = 'permits.mailer.BrevoEmailBackend'
elif os.environ.get('EMAIL_HOST'):
    EMAIL_HOST = os.environ['EMAIL_HOST']
    EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = os.environ.get('EMAIL_USER', '')
    EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
    EMAIL_USE_TLS = True
else:
    EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
    EMAIL_FILE_PATH = BASE_DIR / 'outbox'
DEFAULT_FROM_EMAIL = os.environ.get('EMAIL_FROM', 'permits@ubl-demo.local')
