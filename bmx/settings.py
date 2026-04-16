from pathlib import Path
import os
from django.utils.translation import gettext_lazy as _
try:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
except ImportError:  # pragma: no cover - optional until dependency is installed
    sentry_sdk = None
    DjangoIntegration = None

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
HOMEPAGE_DATA_CACHE_SECONDS = 300
SITEMAP_CACHE_SECONDS = 900
AVATAR_REQUEST_EXPIRATION_DAYS = 30
AVATAR_FINAL_IMAGE_SIZE = 512
AVATAR_FINAL_IMAGE_QUALITY = 86

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


def config_float(name, default=0.0):
    return config(name, default=default, cast=float)


def config_first(names, default=""):
    for name in names:
        value = config(name, default="")
        if value not in ("", None):
            return value
    return default


# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config_bool("DEBUG", default=False)

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
    STRIPE_PUBLIC_KEY = config_first(["STRIPE_LIVE_PUBLIC_KEY", "STRIPE_PUBLIC_KEY"])
    STRIPE_SECRET_KEY = config_first(["STRIPE_LIVE_SECRET_KEY", "STRIPE_SECRET_KEY"])
    STRIPE_ENDPOINT_SECRET = config_first(
        ["STRIPE_LIVE_ENDPOINT_SECRET", "STRIPE_ENDPOINT_SECRET_LIVE", "STRIPE_ENDPOINT_SECRET"]
    )
    STRIPE_ENDPOINT_SECRETS = config_list(
        "STRIPE_LIVE_ENDPOINT_SECRETS",
        default=config(
            "STRIPE_ENDPOINT_SECRETS",
            default=STRIPE_ENDPOINT_SECRET,
        ),
    )
else:
    STRIPE_PUBLIC_KEY = config_first(["STRIPE_TEST_PUBLIC_KEY", "STRIPE_PUBLIC_KEY_TEST"])
    STRIPE_SECRET_KEY = config_first(["STRIPE_TEST_SECRET_KEY", "STRIPE_SECRET_KEY_TEST"])
    STRIPE_ENDPOINT_SECRET = config_first(
        ["STRIPE_TEST_ENDPOINT_SECRET", "STRIPE_ENDPOINT_SECRET_TEST", "STRIPE_ENDPOINT_SECRET"]
    )
    STRIPE_ENDPOINT_SECRETS = config_list(
        "STRIPE_TEST_ENDPOINT_SECRETS",
        default=config(
            "STRIPE_ENDPOINT_SECRETS",
            default=STRIPE_ENDPOINT_SECRET,
        ),
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
    "django_crontab",

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
                "bmx.context_processors.seo_context",
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

BASE_CSP_POLICY = {
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

CSP_ENFORCE = config_bool("CSP_ENFORCE", default=False)
if CSP_ENFORCE:
    SECURE_CSP = BASE_CSP_POLICY
else:
    SECURE_CSP_REPORT_ONLY = BASE_CSP_POLICY

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

ENABLE_HTTPS_SECURITY = config_bool("ENABLE_HTTPS_SECURITY", default=not DEBUG)

if ENABLE_HTTPS_SECURITY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
    SECURE_SSL_REDIRECT = config_bool("SECURE_SSL_REDIRECT", default=not DEBUG)
    if config_bool("SECURE_HSTS_ENABLE", default=not DEBUG):
        SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000, cast=int)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = config_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
        SECURE_HSTS_PRELOAD = config_bool("SECURE_HSTS_PRELOAD", default=True)

# email setting
EMAIL_HOST = config("EMAIL_HOST", default="smtp.seznam.cz")
EMAIL_PORT = config("EMAIL_PORT", default=465, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=False, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@czechbmx.cz")
ACCOUNT_PENDING_ACTIVATION_MAX_AGE_DAYS = config("ACCOUNT_PENDING_ACTIVATION_MAX_AGE_DAYS", default=7, cast=int)

APP_LOG_LEVEL = str(config("APP_LOG_LEVEL", default="INFO")).upper()
AUDIT_LOG_LEVEL = str(config("AUDIT_LOG_LEVEL", default="INFO")).upper()
ROOT_LOG_LEVEL = str(config("ROOT_LOG_LEVEL", default="ERROR")).upper()

SENTRY_DSN = config("SENTRY_DSN", default="")
SENTRY_ENABLED = config_bool("SENTRY_ENABLED", default=not DEBUG)
SENTRY_ENVIRONMENT = config(
    "SENTRY_ENVIRONMENT",
    default="development" if DEBUG else "production",
)
SENTRY_RELEASE = config("SENTRY_RELEASE", default="")
SENTRY_TRACES_SAMPLE_RATE = config_float("SENTRY_TRACES_SAMPLE_RATE", default=0.15)
SENTRY_PROFILES_SAMPLE_RATE = config_float("SENTRY_PROFILES_SAMPLE_RATE", default=0.0)
SENTRY_HEALTHCHECK_PATHS = {"/healthz", "/readyz", "/csp-report"}


def _scrub_sentry_event(event, hint):
    request_data = event.get("request") or {}
    headers = request_data.get("headers") or {}
    sanitized_headers = {}

    for key, value in headers.items():
        normalized = str(key).lower()
        if normalized in {"authorization", "cookie", "x-csrftoken", "x-csr-token", "stripe-signature"}:
            sanitized_headers[key] = "[Filtered]"
        else:
            sanitized_headers[key] = value

    if sanitized_headers:
        request_data["headers"] = sanitized_headers

    if "data" in request_data:
        request_data["data"] = "[Filtered]"
    if "cookies" in request_data:
        request_data["cookies"] = "[Filtered]"

    event["request"] = request_data
    return event


def _sentry_traces_sampler(sampling_context):
    transaction_context = sampling_context.get("transaction_context") or {}
    transaction_name = str(transaction_context.get("name") or "").lower()
    wsgi_environ = sampling_context.get("wsgi_environ") or {}
    path = str(wsgi_environ.get("PATH_INFO") or "").rstrip("/").lower()

    if path in SENTRY_HEALTHCHECK_PATHS:
        return 0.0
    if transaction_name in SENTRY_HEALTHCHECK_PATHS:
        return 0.0
    return SENTRY_TRACES_SAMPLE_RATE


def _before_send_transaction(event, hint):
    request_data = event.get("request") or {}
    url = str(request_data.get("url") or "").lower()
    transaction_name = str(event.get("transaction") or "").lower()
    if any(path in url or transaction_name == path for path in SENTRY_HEALTHCHECK_PATHS):
        return None
    return event


if SENTRY_DSN and SENTRY_ENABLED and sentry_sdk is not None:
    sentry_init_kwargs = {
        "dsn": SENTRY_DSN,
        "environment": SENTRY_ENVIRONMENT,
        "send_default_pii": False,
        "max_request_body_size": "never",
        "traces_sampler": _sentry_traces_sampler,
        "profiles_sample_rate": SENTRY_PROFILES_SAMPLE_RATE,
        "before_send": _scrub_sentry_event,
        "before_send_transaction": _before_send_transaction,
    }
    if SENTRY_RELEASE:
        sentry_init_kwargs["release"] = SENTRY_RELEASE
    if DjangoIntegration is not None:
        sentry_init_kwargs["integrations"] = [DjangoIntegration()]
    sentry_sdk.init(**sentry_init_kwargs)

FORM_PROTECTION = {
    "signup": {
        "min_fill_seconds": config("SIGNUP_MIN_FILL_SECONDS", default=3, cast=int),
        "rate_limit_window_seconds": config("SIGNUP_RATE_LIMIT_WINDOW_SECONDS", default=900, cast=int),
        "rate_limit_max_attempts": config("SIGNUP_RATE_LIMIT_MAX_ATTEMPTS", default=5, cast=int),
        "captcha_after_attempts": config("SIGNUP_CAPTCHA_AFTER_ATTEMPTS", default=2, cast=int),
    },
    "signin": {
        "min_fill_seconds": config("SIGNIN_MIN_FILL_SECONDS", default=1, cast=int),
        "rate_limit_window_seconds": config("SIGNIN_RATE_LIMIT_WINDOW_SECONDS", default=900, cast=int),
        "rate_limit_max_attempts": config("SIGNIN_RATE_LIMIT_MAX_ATTEMPTS", default=10, cast=int),
        "captcha_after_attempts": config("SIGNIN_CAPTCHA_AFTER_ATTEMPTS", default=3, cast=int),
    },
    "password_reset": {
        "min_fill_seconds": config("PASSWORD_RESET_MIN_FILL_SECONDS", default=1, cast=int),
        "rate_limit_window_seconds": config("PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS", default=900, cast=int),
        "rate_limit_max_attempts": config("PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS", default=5, cast=int),
        "captcha_after_attempts": config("PASSWORD_RESET_CAPTCHA_AFTER_ATTEMPTS", default=2, cast=int),
    },
    "activation_resend": {
        "min_fill_seconds": config("ACTIVATION_RESEND_MIN_FILL_SECONDS", default=1, cast=int),
        "rate_limit_window_seconds": config("ACTIVATION_RESEND_RATE_LIMIT_WINDOW_SECONDS", default=900, cast=int),
        "rate_limit_max_attempts": config("ACTIVATION_RESEND_RATE_LIMIT_MAX_ATTEMPTS", default=5, cast=int),
        "captcha_after_attempts": config("ACTIVATION_RESEND_CAPTCHA_AFTER_ATTEMPTS", default=2, cast=int),
    },
    "rider_request": {
        "min_fill_seconds": config("RIDER_REQUEST_MIN_FILL_SECONDS", default=3, cast=int),
        "rate_limit_window_seconds": config("RIDER_REQUEST_RATE_LIMIT_WINDOW_SECONDS", default=900, cast=int),
        "rate_limit_max_attempts": config("RIDER_REQUEST_RATE_LIMIT_MAX_ATTEMPTS", default=5, cast=int),
        "captcha_after_attempts": config("RIDER_REQUEST_CAPTCHA_AFTER_ATTEMPTS", default=2, cast=int),
    },
}

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
        "toolbar": {
            "items": [
                "heading",
                "|",
                "bold",
                "italic",
                "link",
                "imageUpload",
                "bulletedList",
                "numberedList",
                "blockQuote",
                "|",
                "undo",
                "redo",
            ],
            "shouldNotGroupWhenFull": True,
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
            ]
        },
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "|",
                "imageStyle:alignLeft",
                "imageStyle:alignCenter",
                "imageStyle:alignRight",
            ],
        },
        "language": "cs",
    },
    "news_content": {
        "toolbar": {
            "items": [
                "heading",
                "|",
                "bold",
                "italic",
                "link",
                "imageUpload",
                "bulletedList",
                "numberedList",
                "blockQuote",
                "|",
                "undo",
                "redo",
            ],
            "shouldNotGroupWhenFull": True,
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
            ]
        },
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "|",
                "imageStyle:alignLeft",
                "imageStyle:alignCenter",
                "imageStyle:alignRight",
            ],
        },
        "language": "cs",
    },
}
CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME = "event:proposition-editor-upload"
CKEDITOR_5_UPLOAD_FILE_TYPES = ["jpg", "jpeg", "png", "gif", "webp"]
CKEDITOR_5_MAX_FILE_SIZE = 8

CRONJOBS = [
    ("0 */6 * * *", "bmx.cron.valid_licence_scheduled"),
    ("0 2 * * *", "bmx.cron.renew_rider_stats_subscriptions_scheduled"),
    ("15 2 * * *", "bmx.cron.renew_trainer_club_subscriptions_scheduled"),
]

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
        "error_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "formatter": "verbose",
            "filename": str(LOG_DIR / "errors.log"),
            "when": "midnight",
            "interval": 1,
            "backupCount": 30,
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "audit": {
            "handlers": ["console", "audit_file"],
            "level": AUDIT_LOG_LEVEL,
            "propagate": False,
        },
        "api.views": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "bmx": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "ops.health": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "rider.views": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "security.csp": {
            "handlers": ["console"],
            "level": APP_LOG_LEVEL,
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "error_file"],
            "level": ROOT_LOG_LEVEL,
            "propagate": False,
        },
        "django.server": {
            "handlers": ["console", "error_file"],
            "level": ROOT_LOG_LEVEL,
            "propagate": False,
        },
        "admin_stats.middleware": {
            "handlers": ["console", "error_file"],
            "level": ROOT_LOG_LEVEL,
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console", "error_file"],
        "level": ROOT_LOG_LEVEL,
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
