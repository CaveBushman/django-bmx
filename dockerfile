# Použij oficiální Python 3.14 slim image (malý, rychlý)
FROM python:3.14-slim

# Nastav pracovní adresář v kontejneru
WORKDIR /app

# Zamez Pythonu ukládat .pyc a bufferování výstupu
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Nainstaluj systémové závislosti (např. psycopg2, Pillow, libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Zkopíruj requirements a nainstaluj Python závislosti
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Zkopíruj zbytek aplikace do image
COPY . .

# Nastav proměnnou prostředí pro Django settings
ENV DJANGO_SETTINGS_MODULE=bmx.settings

# Otevři port 8000 (typicky pro Gunicorn)
EXPOSE 8000

# Spusť Django pomocí Gunicornu (produkční server)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]