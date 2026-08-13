# Czech BMX

Czech BMX je Django aplikace pro správu české BMX komunity. Spojuje kalendář
závodů, registrace a platby, výsledky, ranking, profily jezdců, kluby, fakturaci,
e-shop, novinky a REST API pro mobilní aplikaci.

## Kde začít

- [Přehled architektury](docs/ARCHITECTURE.md) vysvětluje aplikace, datové vztahy,
  integrační body a background úlohy.
- [Mapa kódu](docs/CODE_MAP.md) odpovídá na praktickou otázku: „Který soubor
  mám upravit, když chci změnit konkrétní chování?“
- [Zálohování](docs/BACKUP.md) popisuje obnovu a provozní zálohy.
- [Bezpečné čištění databáze](docs/SECURITY_DB_PURGE.md) popisuje destruktivní
  databázové operace a jejich pojistky.

## Lokální spuštění

Příkazy se spouštějí z adresáře `django-bmx/`:

```bash
../.env/bin/python manage.py migrate
../.env/bin/python manage.py runserver
```

Kontrola a testy:

```bash
../.env/bin/python manage.py check
../.env/bin/python manage.py test
```

Frontendové styly se sestavují v `theme/static_src/`:

```bash
cd theme/static_src
npm run dev       # watch režim
npm run build     # produkční CSS
```

## Základní pravidla pro změny

1. Doménovou logiku drž ve službách a helper funkcích, ne v šabloně.
2. Pro typ závodu používej `EventType`; neporovnávej ručně české texty.
3. Nezaměňuj interní `Rider.pk` a veřejné `Rider.uci_id`.
4. Změny plateb, kreditu, checkoutu a skladu musí být atomické a auditované.
5. Po změně modelu vytvoř migraci; migrace zpětně neupravuj.
6. Ke každé opravě chyby přidej regresní test, který původní chybu reprodukuje.

## Hlavní vstupní body

| Rozhraní | URL | Kód |
|---|---|---|
| Web | `/` | `bmx/urls.py`, jednotlivé `<app>/urls.py` |
| REST API | `/api/v1/` | `api/urls.py`, `api/views/` |
| Django admin | `/bmx-admin/` | `<app>/admin.py` |
| Health check | `/healthz`, `/readyz` | `bmx/health.py`, `bmx/views.py` |
| Periodické úlohy | cron / Celery beat | `bmx/cron.py`, `bmx/tasks.py` |

Konfigurace se načítá z proměnných prostředí; jejich seznam a bezpečné
výchozí hodnoty jsou v `bmx/.env.example`.
