import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get('DATA_DIR', BASE_DIR / 'var'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DEBUG = os.environ.get('DEBUG', '1') == '1'
_secret_file = DATA_DIR / '.secret-key'
if not _secret_file.exists():
    import secrets
    fd = os.open(_secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f: f.write(secrets.token_urlsafe(64))
SECRET_KEY = os.environ.get('SECRET_KEY') or _secret_file.read_text()
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [x for x in os.environ.get('CSRF_TRUSTED_ORIGINS','').split(',') if x]
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','core']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','core.middleware.LanguageMiddleware','core.middleware.StaffMFAMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','core.context.brand']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':DATA_DIR/'keran.sqlite3','OPTIONS':{'timeout':30,'transaction_mode':'IMMEDIATE'}}}
if os.environ.get('POSTGRES_DB'):
    DATABASES = {'default':{'ENGINE':'django.db.backends.postgresql','NAME':os.environ['POSTGRES_DB'],'USER':os.environ['POSTGRES_USER'],'PASSWORD':os.environ['POSTGRES_PASSWORD'],'HOST':os.environ.get('POSTGRES_HOST','db'),'PORT':os.environ.get('POSTGRES_PORT','5432'),'CONN_MAX_AGE':60}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
TIME_ZONE = 'America/New_York'
USE_TZ = True
LANGUAGE_CODE = 'en'
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR/'static']
STATIC_ROOT = BASE_DIR/'staticfiles'
MEDIA_ROOT = DATA_DIR/'private'
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/account/'
LOGOUT_REDIRECT_URL = '/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 6*1024*1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5*1024*1024
PAYMENT_MODE = os.environ.get('PAYMENT_MODE','sandbox')
WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', '')
if PAYMENT_MODE != 'sandbox':
    raise ImproperlyConfigured('Live payments are deliberately disabled until a reviewed provider integration is installed.')
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
REQUIRE_STAFF_MFA = os.environ.get('REQUIRE_STAFF_MFA','0' if DEBUG else '1') == '1'
# Trust X-Forwarded-Proto only behind the documented private reverse proxy.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO','https')
