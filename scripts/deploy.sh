#!/bin/bash
# Deploy skript pro produkci. Spustit z django-bmx/ s aktivovaným venv.
set -euo pipefail

cd "$(dirname "$0")/.."

git pull
python manage.py migrate --noinput
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn.service
sudo systemctl restart celery-worker.service

echo "Deploy dokončen."
