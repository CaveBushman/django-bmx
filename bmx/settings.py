from pathlib import Path
import os
import logging
from logging.handlers import TimedRotatingFileHandler

from django.conf import settings

import openai
from django.conf import settings
BASE_DIR = Path(__file__).resolve().parent.parent

from decouple import AutoConfig
config = AutoConfig(search_path=BASE_DIR)

print(f"SECRET_KEY from .env: {config('SECRET_KEY')}")

# START LOGING EVENTS
# logging.basicConfig(filename='django_bmx.log', encoding='utf-8', level=logging.DEBUG)


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deploymentpyt/checklist/

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['*']

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')
OPENAI_API_KEY = config("OPENAI_API_KEY")
OPENROUTER_API_KEY = config("OPENROUTER_API_KEY")

# STRIPE KEYS
if DEBUG:
    STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY_TEST')
    STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY_TEST')
else:
    STRIPE_PUBLIC_KEY = config('STRIPE_PUBLIC_KEY')
    STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY')
    STRIPE_ENDPOINT_SECRET = config('STRIPE_ENDPOINT_SECRET')

# Application definition

INSTALLED_APPS = [

    #'material',
    #'material.admin',
    'django_cleanup',
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',

    # 3rd party
    'rest_framework',
    'ckeditor',
    'tailwind',
    'theme',
    'django_browser_reload',
    'import_export',
    # 'fontawesomefree',
    # 'django_crontab',

    # My app
    'rider',
    'event',
    'api',
    'club',
    'news',
    'ranking',
    'commissar',
    'accounts',
    'admin_stats',
    'chat',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',

    "django_browser_reload.middleware.BrowserReloadMiddleware",

    "admin_stats.middleware.VisitMiddleware",
]

ROOT_URLCONF = 'bmx.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': ['theme/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'bmx.context_processors.navbar_context',
            ],
        },
    },
]

# Tailwind settings
TAILWIND_APP_NAME = 'theme'
TAILWIND_CSS_PATH = os.path.join(BASE_DIR, 'static/css/styles.css')
INTERNAL_IPS = [
    '127.0.0.1',
]

WSGI_APPLICATION = 'bmx.wsgi.application'

AUTH_USER_MODEL = 'accounts.Account'

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGES = [
    ('cs', 'Czech'),
    # další jazyky...
]

LANGUAGE_CODE = 'cs'  # Nastav na češtinu

TIME_ZONE = 'Europe/Prague'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ]
}

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

LOGIN_REDIRECT_URL = 'accounts:login'
LOGOUT_REDIRECT_URL = 'accounts:logout'

if DEBUG:
    YOUR_DOMAIN = "http://localhost:8000"
else:
    YOUR_DOMAIN = "http://czechbmx.cz"

# email setting
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_POST = "587"
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

CKEDITOR_CONFIGS = {
    'default': {
        'toolbar_Full': [
            ['Styles', 'Format', 'Bold', 'Italic', 'Underline', 'Strike', 'SpellChecker', 'Undo', 'Redo'],
            ['Link', 'Unlink', 'Anchor'],
            ['Image', 'Flash', 'Table', 'HorizontalRule'],
            ['TextColor', 'BGColor'],
            ['Smiley', 'SpecialChar'], ['Source'],
            ['JustifyLeft', 'JustifyCenter', 'JustifyRight', 'JustifyBlock'],
            ['NumberedList', 'BulletedList'],
            ['Indent', 'Outdent'],
            ['Maximize'],
        ],
        'extraPlugins': 'justify,liststyle,indent',
    },
}

TAILWIND_CSS_PATH = 'css/dist/styles.css'

CRONJOBS = [
    ('*/180 * * * *', 'bmx.cron.valid_licence_scheduled')
]

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'chatbot_file': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'chatbot.log'),
            'when': 'midnight',
            'interval': 1,
            'backupCount': 14,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        'api.views': {
            'handlers': ['console', 'chatbot_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

JAZZMIN_SETTINGS = {
    "site_title": "Django Czech BMX Admin",
    "site_header": "Django Czech BMX Admin",
    "site_brand": "BMX",
    "welcome_sign": "Welcome to the Django Czech BMX Admin",
    "topmenu_links": [
        {"name": "Home", "url": "/", "new_window": False},
        {"name": "Logout", "url": "/bmx-admin/logout/", "new_window": False},  # Opravený odkaz na logout
    ],
    "user_menu_links": [
        {"name": "My Profile", "url": "/bmx-admin/profile/", "new_window": False},
        {"name": "Change Password", "url": "/bmx-admin/password_change/", "new_window": False},
    ],
}
