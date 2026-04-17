#!/bin/sh
set -eu

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

if [ "${DJANGO_MIGRATE:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
