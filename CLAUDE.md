# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from `django-bmx/` (the Django project root).

```bash
# Development server
python manage.py runserver

# Migrations
python manage.py makemigrations
python manage.py migrate

# Run all tests
python manage.py test

# Run a single test class or method
python manage.py test event.tests.EventEntryWorkflowTests
python manage.py test event.tests.EventEntryWorkflowTests.test_mcr_entry_rejects_unqualified_rider_for_20_and_24

# Django shell (useful for one-off DB queries)
python manage.py shell

# Tailwind CSS (from theme/static_src/)
npm run dev      # watch mode during development
npm run build    # production optimized build (Purged & Lightning CSS minified)
```

The database is SQLite at `django-bmx/db.sqlite3`. Environment variables are loaded from `bmx/.env` (see `bmx/.env.example`).

## Architecture

### Apps

| App | Responsibility |
|---|---|
| `event` | Entries, results, race runs, payments (Stripe), financial ledger |
| `rider` | Rider profiles, UCI ID, licences, premium subscriptions, plates/transponders |
| `ranking` | Ranking calculation engine (threaded, cache-coordinated) |
| `accounts` | Custom user model (`Account`), authentication, roles |
| `club` | Club profiles, linked trainers |
| `finance` | Invoice/receipt generation |
| `eshop` | Product shop with cart, orders, transponder sales |
| `news` | Blog articles with CKEditor 5 |
| `commissar` | Race commissar assignments |
| `bmx` | Project root: URLs, settings, middleware, cron, context processors |
| `theme` | Tailwind CSS source and compiled output, base templates |

### Key models and their files

The `event` app splits its models across files re-exported from `event/models.py`:
- `models_events.py` — `Event`, `EntryClasses`, `SeasonSettings`
- `models_entries.py` — `Entry`, `EntryForeign`, `EntryAuditLog`
- `models_results.py` — `Result`, `RaceRun`
- `models_finance.py` — `CreditTransaction`, `DebetTransaction`, `FinanceAuditLog`

`Entry.rider` uses Django's default integer PK as FK (no DB constraint). `Result.rider` uses `to_field="uci_id"`. These are separate links — a rider can have `Result` records with no corresponding `Entry` (e.g. on-site registration).

### Event types (`Event.type_for_ranking`)

Use the `EventType` TextChoices enum from `event/models_events.py` (re-exported via
`event.models`), e.g. `EventType.CESKY_POHAR`, `EventType.MCR_JEDNOTLIVCU`. The enum
values are the Czech strings stored in the DB and compared across the logic — always
reference the constants, never the string literals. Members: `MCR_JEDNOTLIVCU`,
`MCR_DRUZSTEV`, `CESKY_POHAR`, `CESKA_LIGA`, `MORAVSKA_LIGA`, `VOLNY_ZAVOD`,
`EVROPSKY_POHAR`, `MISTROVSTVI_EVROPY`, `MISTROVSTVI_SVETA`, `SVETOVY_POHAR`,
`NEBODOVANY_ZAVOD`.

### Entry and payment flow

1. User selects categories (beginner / 20" / 24"); helpers in `event/views/entry_helpers.py` compute allowed categories and fees.
2. `CartEntry` (`event/func.py`) creates an `Entry` with `payment_complete=False`.
3. Stripe Checkout session is created; webhook sets `payment_complete=True` and writes a `DebetTransaction`.
4. `checkout=True` on an entry means a refund/credit has been issued.
5. MČR entry is blocked for riders where `rider.is_qualify_to_cn_20 / is_qualify_to_cn_24 = False` (checked in `entry_helpers.py`).

### MČR qualification

`perform_cn_qualification_recount(year)` (in `rider/rider.py`) recalculates
`Rider.is_qualify_to_cn_20/24` by counting `Result` records (not `Entry`), so riders who
compete without online registration are included. Threshold is `SeasonSettings.qualify_to_cn`
for the current year. It runs via the Celery task `rider.tasks.recount_cn_qualification_task`
or, without a broker, the `RiderQualifyToCNThread` fallback (see Background tasks).

Auto-trigger: after each result file upload (`event/func.py → SetResults.run()`),
`trigger_cn_qualification_recount_if_needed()` → `start_cn_qualification_recount()` fires if a
championship event exists for the year and enough cup races have occurred. Manual trigger:
`/rider/qualify` (admin only).

### Ranking engine

Core recount is `_ranking_recount_once()` / `_ranking_recount_should_rerun()` in
`ranking/ranking.py`, shared by the Celery task `ranking.tasks.recount_ranking_task` and the
`SetRanking` thread fallback. Uses Django cache keys (`RANKING_RECOUNT_RUNNING_KEY`,
`RANKING_RECOUNT_PENDING_KEY`, `RANKING_RECOUNT_STATUS_KEY`) to prevent concurrent runs, queue
a re-run when a change arrives mid-recount, and report status. `schedule_ranking_recount()`
queues a recount after results are imported.

### Result import

Results are uploaded as REM TSV files via the admin. `SetResults` (thread in `event/func.py`) parses rows and calls `GetResult.write_result()` (`event/result.py`) to create/update `Result` and `RaceRun` records. After import, ranking and MČR qualification recounts are both triggered.

### Rider categories

`Rider.set_class_20()` / `set_class_24()` derive the competition class from age and `is_elite` flag. Elite male riders: Junior (≤18), Under 23 (19–22), Elite (23+). Non-elite riders use age-based youth classes (Boys/Girls 6–16). Cruiser (24") uses separate age brackets.

### Background tasks

Recounts run on Celery when a broker is configured, with a daemon-thread fallback when not.
`bmx/background.py → should_use_celery()` decides (True unless `CELERY_TASK_ALWAYS_EAGER`,
i.e. no Redis). Dispatch helpers route to either path:

- Ranking: `ranking.tasks.recount_ranking_task` ↔ `SetRanking` thread (`schedule_ranking_recount()`)
- MČR qualification: `rider.tasks.recount_cn_qualification_task` ↔ `RiderQualifyToCNThread` (`start_cn_qualification_recount()`)
- `rider/rider.py → CheckValidLicenceThread` — licence validity from Czech Cycling API
- News: Celery tasks for audio/translation/push (`news/tasks.py`)

Periodic jobs run via **either** django-crontab (default) **or** Celery beat, never both:
when `USE_CELERY_BEAT=True`, settings empties `CRONJOBS` and `CELERY_BEAT_SCHEDULE`
(thin wrappers in `bmx/tasks.py` around `bmx/cron.py`) owns the schedule. Jobs: licence
check (6 h), subscription renewals (02:00–02:30), AI agent (03:00), DB backup (04:00),
SQLite integrity (Sun 04:30), visit prune (monthly), SQLite optimize (05:00), and
Entry/Result integrity check (Sun 05:15, see below).

`docker-compose.yml` provides `redis`, `celery-worker`, and `celery-beat` services.

### Referential integrity check

`Entry.rider` and `Result.rider` use `db_constraint=False`. The
`check_entry_integrity` management command (cron: Sun 05:15, `bmx.cron.check_entry_integrity_scheduled`)
finds orphaned references. `--fix` nulls orphaned **Entry** rows only — orphaned **Result**
rows are reported but never nulled, because `Result.rider` stores a `uci_id` that is
meaningful for foreign/unregistered riders even with no `Rider` row.

### Custom user model

`accounts.Account` extends `AbstractBaseUser`. Roles are boolean flags: `is_rider`, `is_commissar`, `is_trainer`, `is_club_manager`. `AUTH_USER_MODEL = "accounts.Account"`.

### Frontend

Tailwind CSS 4.x, built from `theme/static_src/`. Compiled output goes to
`theme/static/css/dist/styles.css`. Templates live in `{app}/templates/{app}/` with a shared
base in `theme/templates/`. Dark mode is toggled via a CSS class (`html.dark`). The core palette
lives in CSS design tokens at the top of `theme/static_src/src/styles.css` (`:root` + `.dark`
override `--bmx-*`); change colors there, not per-rule. Rich text uses CKEditor 5
(`django_ckeditor_5`); the local `ckeditor/` package is a plain-textarea compatibility shim kept
only for legacy `RichTextField` migrations. No jQuery — site JS is vanilla (the admin/DRF bundle
their own `django.jQuery`).

### i18n / translations

Source language is Czech (`LANGUAGE_CODE="cs"`); 8 target locales (en, de, es, fr, hu, it, pl, sk).
**`.mo` files are gitignored** and must be compiled — the site falls back to Czech source if they
aren't. `docker-entrypoint.sh` runs `compilemessages` on start (needs `gettext`, in the dockerfile);
locally use `make i18n`. Each template using `{% trans %}` must `{% load i18n %}` itself (no
builtins; `{% load %}` doesn't propagate into `{% include %}`). After adding strings:
`make i18n-make` (extract) → translate → `make i18n` (compile).

Bulk translation: `python manage.py translate_po` (in `news`) auto-translates untranslated/fuzzy
`.po` entries from Czech via the project's translator (DeepL when `DEEPL_API_KEY` is set, else
Google fallback) — same infra as article translation. Threaded (`--workers`). By default skips
format strings to protect interpolation; `--include-format` masks placeholders (`%(x)s`, `{x}`)
with `@@i@@` sentinels, translates, then restores them (leaves a string untranslated if a
sentinel is lost). Flags: `--include-fuzzy`, `--include-format`, `--compile`, `--limit`.

### View packages

Both `api/views/` and `rider/views/` are packages split by domain, with shared
imports/helpers/decorators in `_common.py` and `__init__.py` re-exporting everything (so
`from rider import views; views.X` and `from api.views import X` keep working). When mocking in
tests, patch the submodule where the name is resolved, e.g. `api.views.auth.stripe` or
`rider.views.admin.schedule_ranking_recount`.

