from pathlib import Path
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from django.conf import settings
from django.utils.translation import gettext_lazy as _

try:
    from django.utils.csp import CSP
except ImportError:
    class CSP:
        SELF = "'self'"
        NONE = "'none'"
        REPORT_SAMPLE = "'report-sample'"
        UNSAFE_INLINE = "'unsafe-inline'"

try:
    from decouple import config
except ImportError:
    def config(name, default="", cast=str):
        value = os.environ.get(name, default)
        if cast is bool:
            return str(value).lower() in {"1", "true", "yes", "on"}
        return cast(value) if cast and value != "" else value


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deploymentpyt/checklist/


def config_bool(name, default=False):
    raw_value = config(name, default=default)
    if isinstance(raw_value, bool):
        return raw_value

    normalized = str(raw_value).strip().lower()
    if normalized in {"1", "true", "yes", "on", "debug", "development", "dev"}:
        return True
    if normalized in {"0", "false", "no", "off", "release", "prod", "production"}:
        return False
    return bool(raw_value)


def config_list(name, default=""):
    raw_value = config(name, default=default)
    if isinstance(raw_value, (list, tuple)):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    return [item.strip() for item in str(raw_value).split(",") if item.strip()]


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config_bool("DEBUG", default=True)

DEFAULT_ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "[::1]",
    "testserver",
    "czechbmx.cz",
    "www.czechbmx.cz",
]
ALLOWED_HOSTS = config_list("ALLOWED_HOSTS", default=",".join(DEFAULT_ALLOWED_HOSTS))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config("SECRET_KEY")
OPENAI_API_KEY = config("OPENAI_API_KEY")

STRIPE_LIVE_MODE = config_bool("STRIPE_LIVE_MODE", default=not DEBUG)

# STRIPE KEYS
if STRIPE_LIVE_MODE:
    STRIPE_PUBLIC_KEY = config("STRIPE_PUBLIC_KEY")
    STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY")
else:
    STRIPE_PUBLIC_KEY = config("STRIPE_PUBLIC_KEY_TEST")
    STRIPE_SECRET_KEY = config("STRIPE_SECRET_KEY_TEST")

STRIPE_ENDPOINT_SECRET = config(
    "STRIPE_ENDPOINT_SECRET",
    default=config(
        "STRIPE_ENDPOINT_SECRET_LIVE" if STRIPE_LIVE_MODE else "STRIPE_ENDPOINT_SECRET_TEST",
        default="",
    ),
)
STRIPE_ENDPOINT_SECRETS = config_list(
    "STRIPE_ENDPOINT_SECRETS",
    default=STRIPE_ENDPOINT_SECRET,
)

# Application definition

INSTALLED_APPS = [
    #'material',
    #'material.admin',
    "django_cleanup.apps.CleanupConfig",
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # 3rd party
    "rest_framework",
    "ckeditor",
    "django_ckeditor_5",
    "tailwind",
    "theme",
    "import_export",

    # My app
    "rider",
    "event",
    "api",
    "club",
    "news",
    "ranking",
    "commissar",
    "accounts",
    "admin_stats",
    'finance',
    "todo",
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "admin_stats.middleware.VisitMiddleware",
]

ROOT_URLCONF = "bmx.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": ["theme/templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "bmx.context_processors.navbar_context",
            ],
        },
    },
]

# Tailwind settings
TAILWIND_APP_NAME = "theme"
TAILWIND_CSS_PATH = "css/dist/styles.css"
INTERNAL_IPS = [
    "127.0.0.1",
]

WSGI_APPLICATION = "bmx.wsgi.application"

AUTH_USER_MODEL = "accounts.Account"

# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",},
]

# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGES = [
    ("cs", _("Czech")),
    ("en", _("English")),
    ("de", _("German")),
    ("sk", _("Slovak")),
    ("es", _("Spanish")),
    ("it", _("Italian")),
    ("fr", _("French")),
]

LANGUAGE_CODE = "cs"  # Nastav na češtinu

TIME_ZONE = "Europe/Prague"

USE_I18N = True

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

STATIC_URL = "static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

REST_FRAMEWORK = {
    # Use Django's standard `django.contrib.auth` permissions,
    # or allow read-only access for unauthenticated users.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly"
    ]
}

SECURE_CSP_REPORT_ONLY = {
    "default-src": [CSP.SELF],
    "base-uri": [CSP.SELF],
    "object-src": [CSP.NONE],
    "frame-ancestors": [CSP.SELF],
    "form-action": [CSP.SELF],
    "script-src": [
        CSP.SELF,
        CSP.REPORT_SAMPLE,
        "https://js.stripe.com",
        "https://code.jquery.com",
        "https://unpkg.com",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://www.googletagmanager.com",
        "https://www.google-analytics.com",
    ],
    "style-src": [
        CSP.SELF,
        CSP.UNSAFE_INLINE,
        "https://unpkg.com",
        "https://cdn.jsdelivr.net",
        "https://cdnjs.cloudflare.com",
        "https://netdna.bootstrapcdn.com",
    ],
    "img-src": [
        CSP.SELF,
        "data:",
        "blob:",
        "https:",
    ],
    "font-src": [
        CSP.SELF,
        "data:",
        "https://cdnjs.cloudflare.com",
        "https://cdn.jsdelivr.net",
        "https://netdna.bootstrapcdn.com",
    ],
    "connect-src": [
        CSP.SELF,
        "https://www.google-analytics.com",
        "https://analytics.google.com",
        "https://api.stripe.com",
        "https://js.stripe.com",
    ],
    "frame-src": [
        CSP.SELF,
        "https://js.stripe.com",
        "https://hooks.stripe.com",
        "https://www.google.com",
    ],
    "media-src": [
        CSP.SELF,
        "blob:",
    ],
    "worker-src": [
        CSP.SELF,
        "blob:",
    ],
    "report-uri": ["/csp-report/"],
}

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

LOGIN_REDIRECT_URL = "accounts:login"
LOGOUT_REDIRECT_URL = "accounts:logout"

if DEBUG:
    # V lokálním vývoji vždy generuj HTTP URL, i když v env zůstalo produkční nastavení.
    YOUR_DOMAIN = config("YOUR_DOMAIN", default="http://localhost:8000")
else:
    YOUR_DOMAIN = config(
        "YOUR_DOMAIN",
        default="https://czechbmx.cz" if STRIPE_LIVE_MODE else "http://localhost:8000",
    )

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = config_bool("SECURE_SSL_REDIRECT", default=STRIPE_LIVE_MODE)
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
        SESSION_COOKIE_SECURE = True
        SESSION_COOKIE_HTTPONLY = True
        CSRF_COOKIE_SECURE = True
        CSRF_COOKIE_HTTPONLY = True

# email setting
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "noreply@czechbmx.cz"

CKEDITOR_CONFIGS = {
    "default": {
        "toolbar_Full": [
            [
                "Styles",
                "Format",
                "Bold",
                "Italic",
                "Underline",
                "Strike",
                "SpellChecker",
                "Undo",
                "Redo",
            ],
            ["Link", "Unlink", "Anchor"],
            ["Image", "Flash", "Table", "HorizontalRule"],
            ["TextColor", "BGColor"],
            ["Smiley", "SpecialChar"],
            ["Source"],
            ["JustifyLeft", "JustifyCenter", "JustifyRight", "JustifyBlock"],
            ["NumberedList", "BulletedList"],
            ["Indent", "Outdent"],
            ["Maximize"],
        ],
        "extraPlugins": "justify,liststyle,indent",
    },
}

CKEDITOR_5_CONFIGS = {
    "event_proposition": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "link",
            "bulletedList",
            "numberedList",
            "|",
            "undo",
            "redo",
        ],
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
            ]
        },
        "language": "cs",
    }
}

CRONJOBS = [("0 */6 * * *", "bmx.cron.valid_licence_scheduled")]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose",},
        "audit_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "verbose",
            "filename": str(LOG_DIR / "audit.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 30,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "audit": {
            "handlers": ["console", "audit_file"],
            "level": "INFO",
            "propagate": False,
        },
        "api.views": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "rider.views": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "security.csp": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
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
        {
            "name": "Logout",
            "url": "/bmx-admin/logout/",
            "new_window": False,
        },  # Opravený odkaz na logout
    ],
    "user_menu_links": [
        {"name": "My Profile", "url": "/bmx-admin/profile/", "new_window": False},
        {
            "name": "Change Password",
            "url": "/bmx-admin/password_change/",
            "new_window": False,
        },
    ],
}

INSTALLED_APPS += ["analytical"]
GOOGLE_ANALYTICS_GTAG_PROPERTY_ID = "G-6VFMEQ1EVX"  # GA4 measurement ID
