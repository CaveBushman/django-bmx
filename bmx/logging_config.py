import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def __init__(self, *, release="", environment=""):
        super().__init__()
        self.release = release
        self.environment = environment

    def format(self, record):
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if self.release:
            payload["release"] = self.release
        if self.environment:
            payload["environment"] = self.environment

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        return json.dumps(payload, ensure_ascii=True)


def build_logging_config(
    *,
    log_dir,
    app_log_level,
    audit_log_level,
    root_log_level,
    log_as_json=False,
    release="",
    environment="",
):
    formatter_name = "json" if log_as_json else "verbose"

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "verbose": {
                "format": "[{asctime}] {levelname} {name}: {message}",
                "style": "{",
            },
            "json": {
                "()": "bmx.logging_config.JsonFormatter",
                "release": release,
                "environment": environment,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter_name,
            },
            "audit_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "verbose",
                "filename": str(log_dir / "audit.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 30,
                "encoding": "utf-8",
            },
            "error_file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "verbose",
                "filename": str(log_dir / "errors.log"),
                "when": "midnight",
                "interval": 1,
                "backupCount": 30,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "audit": {
                "handlers": ["console", "audit_file"],
                "level": audit_log_level,
                "propagate": False,
            },
            "api.views": {
                "handlers": ["console"],
                "level": app_log_level,
                "propagate": False,
            },
            "bmx": {
                "handlers": ["console"],
                "level": app_log_level,
                "propagate": False,
            },
            "ops.health": {
                "handlers": ["console"],
                "level": app_log_level,
                "propagate": False,
            },
            "rider.views": {
                "handlers": ["console"],
                "level": app_log_level,
                "propagate": False,
            },
            "security.csp": {
                "handlers": ["console"],
                "level": app_log_level,
                "propagate": False,
            },
            "django.request": {
                "handlers": ["console", "error_file"],
                "level": root_log_level,
                "propagate": False,
            },
            "django.server": {
                "handlers": ["console", "error_file"],
                "level": root_log_level,
                "propagate": False,
            },
            "admin_stats.middleware": {
                "handlers": ["console", "error_file"],
                "level": root_log_level,
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console", "error_file"],
            "level": root_log_level,
        },
    }
