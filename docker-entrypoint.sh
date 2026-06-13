#!/bin/sh
set -eu

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
  python manage.py collectstatic --noinput
fi

# Překlady: .mo soubory nejsou ve verzování (jen .po), takže je nutné je
# zkompilovat při startu — jinak se web zobrazuje jen ve zdrojovém jazyce (cs).
if [ "${DJANGO_COMPILEMESSAGES:-1}" = "1" ]; then
  python manage.py compilemessages
fi

if [ "${DJANGO_MIGRATE:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi

exec "$@"
