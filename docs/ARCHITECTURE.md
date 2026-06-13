# Přehled architektury

Czech BMX (czechbmx.cz) je Django 6 monolit pro českou BMX komunitu:
kalendář závodů a online přihlášky s platbami, výsledky a rankingy, správa
jezdců a klubů, e-shop, novinky a REST API pro mobilní aplikaci ve Flutteru.

```
                ┌────────────────────────────────────────────────┐
                │                  Django (bmx)                  │
 Prohlížeč ────►│  server-rendered views + Tailwind šablony      │
                │                                                │
 Flutter app ──►│  DRF API  /api/v1/  (JWT + token)              │
                │                                                │
                │  Admin (Jazzmin)  /bmx-admin/                  │
                └───────┬───────────────┬────────────────────────┘
                        │               │
            SQLite (db.sqlite3)   Redis (cache, rate limity,
                        │          Celery broker)
                        │               │
        background: vlákna · Celery workery · django-crontab
                        │
        externí: Stripe · Firebase FCM · API Českého svazu cyklistiky
                 · DeepL · edge-tts · ABRA Flexi · Sentry · GA4
```

## Technologie

| Vrstva | Technologie |
|---|---|
| Framework | Django ≥ 6.0, Python |
| API | Django REST Framework, SimpleJWT (+ token blacklist), drf-spectacular, django-filter |
| Databáze | SQLite (`db.sqlite3`); zálohovací a cron kód je připraven na budoucí migraci na PostgreSQL |
| Cache / fronta | Redis (django-redis) — v produkci nutný kvůli sdíleným rate limitům; Celery s django-celery-results |
| Frontend | Server-rendered Django šablony + Tailwind CSS 4 (django-tailwind, app `theme`), dark mode přes `html.dark` |
| Admin | Django admin s motivem Jazzmin, django-import-export |
| Statika/média | WhiteNoise pro statické soubory; média lokálně |
| Platby | Stripe Checkout + webhooky |
| Monitoring | Sentry, GA4 (django-analytical), strukturované logování s request ID |
| Plánování | django-crontab (systémový cron) + ad-hoc daemon vlákna + Celery tasky |

## Aplikace

### Doménové aplikace

| App | Zodpovědnost |
|---|---|
| `event` | Jádro domény: závody (`Event`, `EntryClasses`, `SeasonSettings`, `EventProposition`, `EventPhoto`), online přihlášky (`Entry`, `EntryForeign`, `EntryAuditLog`), výsledky (`Result`, `RaceRun`) a finanční evidence (`DebetTransaction`, `CreditTransaction`, `StripeFee`, `FinanceAuditLog`). Views jsou rozdělené v `event/views/` (public, entry, payment, admin, PDF, propozice). Services v `event/services/` řeší Stripe checkout sessions/refundy, import REM TSV výsledků, import rozjížděk, UCI export, stav registrací a reporty nezaplacených moto. |
| `rider` | Profily jezdců s klíčem UCI ID, platnost licencí, výkonnostní třídy (20"/24", elite vs. věkové), kvalifikační flagy na MČR, tabulky a změny transpondérů, `ForeignRider`. Vlastní také placené produkty: `RiderStatsSubscription`, `TrainerClubSubscription`, `MobileAppSubscription` (+ charge modely) a `PromoCode`/`PromoCodeUsage`. Background přepočty jsou v `rider/rider.py`. |
| `ranking` | `Ranking` (jeden řádek na jezdce, body a pozice pro 20"/24"). Přepočtový engine je `ranking/ranking.py → SetRanking`, vlákno koordinované přes cache klíče proti souběžným spuštěním. |
| `club` | Profily klubů (`Club`), propojení trenérů a týmové přihlášky na MČR (`McrClubTeam`, `McrClubTeamMember`). |
| `accounts` | Vlastní uživatelský model `accounts.Account` (`AUTH_USER_MODEL`) s booleovskými rolemi (`is_rider`, `is_commissar`, `is_trainer`, `is_club_manager`), audit log aktivací, propojení účet↔jezdec, moderované žádosti o změnu avataru a `FcmDevice` push tokeny. |
| `finance` | Generování faktur a dokladů pro závody a předplatná (`EventInvoice`, `EventInvoiceOverride`, `EventCashReceipt`, `SubscriptionInvoice`); PDF přes reportlab/pikepdf. |
| `eshop` | Katalog produktů s variantami, košík, objednávky se skladovými rezervacemi a pohyby, hlídání skladu, historie objednávek a export do účetnictví ABRA Flexi (`FlexiExportSettings`). |
| `news` | Články s CKEditorem 5, tagy, sekce ke stažení. Celery tasky generují audio verze (edge-tts), překládají články (DeepL) a posílají push notifikace. |
| `commissar` | Registr komisařů a jejich delegace na závody. |
| `todo` | Interní úkolovník komise (`CommissionTask`). |

### Podpůrné aplikace

| App | Zodpovědnost |
|---|---|
| `bmx` | Projektový balíček: settings, kořenové URL, middleware (request ID), CSP, rate limiting, vstupní body cronu, health checky, e-mail, HTML sanitizer, observabilita (Sentry), context processory. |
| `api` | DRF endpointy (~60 rout) na `/api/v1/` (namespace `api` pro `reverse("api:...")`). Views jsou v balíčku `api/views/` rozděleném po doménách (auth, riders, clubs, plates, news, events, foreign_entries, eshop, ranking, subscriptions, search) se sdílenými serializery/helpery v `_common.py`. Pokrývá auth (login/logout/registrace/reset hesla, JWT), čtecí API pro jezdce/kluby/závody/novinky/ranking/výsledky, přihlášení na závod z aplikace, e-shop košík + checkout, tabulky, avatary, FCM tokeny a dobíjení kreditu. |
| `admin_stats` | Sledování návštěv přes `VisitMiddleware` + admin dashboardy; staré návštěvy maže měsíční cron. |
| `ai_agent` | Fronta LLM úkolů (`AgentTask`, `AgentLog`). Management command `run_ai_agent` (cron, denně 03:00) zpracovává čekající úkoly — shrnutí závodů, analýzy jezdců, sezónní zprávy — přes OpenAI-kompatibilního klienta (`services/llm_client.py`, funguje s Ollamou i OpenAI). |
| `theme` | Zdrojové soubory Tailwindu (`static_src/`), zkompilované CSS (`static/css/dist/styles.css`), sdílené base šablony. |
| `ckeditor` | Kompatibilní shim (`RichTextField` = prostý `TextField`) kvůli starým migracím. Rich-text editor je CKEditor 5 (`django_ckeditor_5`); původní CKEditor 4 (`django-ckeditor`) byl odstraněn. |

## Klíčové datové vztahy

- `Entry.rider` → FK na celočíselný PK; `Result.rider` → `to_field="uci_id"`. Jde o
  nezávislé vazby: jezdec může mít `Result` záznamy bez `Entry` (registrace na místě).
- `Ranking.rider` → FK na `Rider` (SET_NULL), jeden řádek na jezdce s pořadím pro 20" i 24".
- Peníze: `DebetTransaction` (zaplacené přihlášky přes Stripe webhook) a `CreditTransaction`
  (refundy/kredity, `Entry.checkout=True`) tvoří evidenci; `finance` z ní generuje
  faktury. `StripeFee` eviduje poplatky procesoru.
- `Event.type_for_ranking` je množina přesných českých řetězců (např. `"Český pohár"`,
  `"Mistrovství ČR jednotlivců"`) používaných napříč logikou — musí sedět přesně.

## Hlavní toky

### Přihláška a platba
1. Helpery v `event/views/entry_helpers.py` spočítají povolené kategorie (začátečník / 20" / 24") a poplatky.
2. `CartEntry` (`event/func.py`) vytvoří `Entry` s `payment_complete=False`.
3. Vytvoří se Stripe Checkout session (`event/services/checkout_sessions.py`); webhook
   nastaví `payment_complete=True` a zapíše `DebetTransaction`.
4. Přihlášky na MČR jsou blokované jezdcům bez `is_qualify_to_cn_20/24`.

### Import výsledků → přepočty
Admin nahraje REM TSV soubor → vlákno `SetResults` (`event/func.py`) parsuje řádky a
zapisuje `Result`/`RaceRun` přes `GetResult.write_result()` (`event/result.py`). Po
importu se spustí přepočet rankingu (`schedule_ranking_recount()`) a při splnění
podmínek i přepočet kvalifikace na MČR (`RiderQualifyToCNThread`), který počítá
`Result` záznamy proti `SeasonSettings.qualify_to_cn`.

## Background zpracování

Přepočty běží na Celery, když je nakonfigurovaný broker (Redis), jinak spadnou zpět
na daemon vlákno. Volbu řídí `bmx/background.py → should_use_celery()` (True, dokud není
`CELERY_TASK_ALWAYS_EAGER`, tj. dokud je broker). Jádro přepočtu sdílí obě cesty.

| Mechanismus | Použití |
|---|---|
| Celery task ↔ vlákno (fallback) | Přepočet rankingu (`ranking.tasks.recount_ranking_task` ↔ `SetRanking`), kvalifikace na MČR (`rider.tasks.recount_cn_qualification_task` ↔ `RiderQualifyToCNThread`) — koordinace přes cache klíče (PENDING/RUNNING/STATUS) |
| Celery (Redis broker) | News tasky: audio (edge-tts), překlady (DeepL), push notifikace |
| Daemon vlákna | Platnost licencí (`CheckValidLicenceThread`), import výsledků (`SetResults`) |
| Periodika: django-crontab **nebo** Celery beat | Kontrola licencí (6 h), obnovy předplatných (02:00–02:30), AI agent (03:00), záloha DB + off-site (04:00), SQLite integrity (Ne 04:30), mazání návštěv (měsíčně), SQLite `PRAGMA optimize` (05:00), integrita Entry/Result (Ne 05:15). Při `USE_CELERY_BEAT=True` settings vyprázdní `CRONJOBS` a schedule vlastní `CELERY_BEAT_SCHEDULE` (tasky v `bmx/tasks.py` nad `bmx/cron.py`), aby úlohy neběžely dvakrát. |

`docker-compose.yml` poskytuje služby `redis`, `celery-worker` a `celery-beat`.

### Kontrola referenční integrity

`Entry.rider` a `Result.rider` mají `db_constraint=False`. Command `check_entry_integrity`
(cron Ne 05:15) najde osiřelé reference. `--fix` vynuluje jen osiřelé **Entry** — osiřelé
**Result** se reportují, ale nikdy nevynulují (uci_id má smysl pro zahraniční jezdce i bez
`Rider` řádku).

## Externí integrace

| Služba | Účel | Kde |
|---|---|---|
| Stripe | Platby přihlášek, dobíjení kreditu, e-shop checkout, platby předplatných, refundy | `event/services/`, `rider/subscriptions.py`, `eshop` |
| API Českého svazu cyklistiky (`portal.api.czechcyclingfederation.com`) | Platnost licence podle UCI ID | `rider/rider.py` |
| Firebase (FCM) | Push notifikace do mobilů (tokeny v `FcmDevice`) | `accounts/push_notifications.py`, `news/tasks.py` |
| DeepL | Překlady článků | `news/tasks.py` |
| edge-tts | Audio verze článků | `news/tasks.py` |
| ABRA Flexi | Export e-shop objednávek do účetnictví | `eshop` |
| Ollama / OpenAI-kompatibilní LLM | Zprávy AI agenta (`AI_AGENT_BASE_URL`, výchozí lokální Ollama) | `ai_agent/services/llm_client.py` |
| Sentry, GA4 | Monitoring chyb, analytika | `bmx/observability.py`, settings |

## HTTP rozhraní

- `/` — novinky/homepage; `/event/`, `/rider/`, `/user/`, `/club/`, `/ranking/`,
  `/finance/`, `/eshop/`, `/todo/`, `/admin-stats/` — server-rendered views.
- `/api/v1/` — DRF API pro mobilní klienty (namespace `api`).
- `/bmx-admin/` — Django admin (Jazzmin).
- Provozní endpointy: `/healthz`, `/readyz`, `/csp-report/`, `/sitemap.xml`, `/robots.txt`.

## Konfigurace a provoz

- Prostředí přes python-decouple z `bmx/.env` (klíče dokumentuje `.env.example`).
  `DEBUG`, `ALLOWED_HOSTS`, `REDIS_URL`, Stripe klíče atd.
- Produkční varování: bez `REDIS_URL` LocMemCache nesdílí rate limity mezi
  Gunicorn workery — settings vyhodí `RuntimeWarning`.
- Docker: `dockerfile` + `docker-compose.yml` + `docker-entrypoint.sh`.
- Lokalizace: primárně česky s i18n (`locale/`, `LocaleMiddleware`); doménové
  řetězce (typy závodů, třídy) jsou záměrně české literály.
- Zálohy: denní dump SQLite, gzip, off-site upload s mazáním starých záloh
  (viz `docs/BACKUP.md`).
