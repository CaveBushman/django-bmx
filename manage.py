#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import weakref
import dotenv


def patch_django_autoreload():
    """Work around intermittent KeyError in Django autoreload on Python 3.13."""
    if sys.version_info < (3, 13):
        return

    try:
        from django.utils import autoreload
    except Exception:
        return

    if getattr(autoreload, "_bmx_keyerror_patch", False):
        return

    def iter_all_python_module_files():
        keys = sorted(sys.modules)
        modules = tuple(
            module
            for key in keys
            for module in [sys.modules.get(key)]
            if module is not None and not isinstance(module, weakref.ProxyTypes)
        )
        return autoreload.iter_modules_and_files(modules, frozenset(autoreload._error_files))

    autoreload.iter_all_python_module_files = iter_all_python_module_files
    autoreload._bmx_keyerror_patch = True


def main():
    """Run administrative tasks."""
    dotenv.load_dotenv()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bmx.settings')
    try:
        patch_django_autoreload()
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
