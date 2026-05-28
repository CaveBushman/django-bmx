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

The string values are used throughout logic and must match exactly:
`"Český pohár"`, `"Mistrovství ČR jednotlivců"`, `"Mistrovství ČR družstev"`, `"Česká liga"`, `"Moravská liga"`, `"Volný závod"`, `"Evropský pohár"`, `"Mistrovství Evropy"`, `"Mistrovství světa"`, `"Světový pohár"`, `"Nebodovaný závod"`

### Entry and payment flow

1. User selects categories (beginner / 20" / 24"); helpers in `event/views/entry_helpers.py` compute allowed categories and fees.
2. `CartEntry` (`event/func.py`) creates an `Entry` with `payment_complete=False`.
3. Stripe Checkout session is created; webhook sets `payment_complete=True` and writes a `DebetTransaction`.
4. `checkout=True` on an entry means a refund/credit has been issued.
5. MČR entry is blocked for riders where `rider.is_qualify_to_cn_20 / is_qualify_to_cn_24 = False` (checked in `entry_helpers.py`).

### MČR qualification

`RiderQualifyToCNThread` (in `rider/rider.py`) recalculates `Rider.is_qualify_to_cn_20/24` by counting `Result` records (not `Entry`), so riders who compete without online registration are included. Threshold is `SeasonSettings.qualify_to_cn` for the current year.

Auto-trigger: after each result file upload (`event/func.py → SetResults.run()`), `trigger_cn_qualification_recount_if_needed()` fires if a championship event exists for the year and enough cup races have occurred. Manual trigger: `/rider/qualify` (admin only).

### Ranking engine

`ranking/ranking.py → SetRanking` thread. Uses Django cache keys (`RANKING_RECOUNT_RUNNING_KEY`, `RANKING_RECOUNT_STATUS_KEY`) to prevent concurrent runs and report status. `schedule_ranking_recount()` in `event/func.py` queues a recount after results are imported.

### Result import

Results are uploaded as REM TSV files via the admin. `SetResults` (thread in `event/func.py`) parses rows and calls `GetResult.write_result()` (`event/result.py`) to create/update `Result` and `RaceRun` records. After import, ranking and MČR qualification recounts are both triggered.

### Rider categories

`Rider.set_class_20()` / `set_class_24()` derive the competition class from age and `is_elite` flag. Elite male riders: Junior (≤18), Under 23 (19–22), Elite (23+). Non-elite riders use age-based youth classes (Boys/Girls 6–16). Cruiser (24") uses separate age brackets.

### Background tasks

- `rider/rider.py → RiderQualifyToCNThread` — MČR qualification recalc
- `ranking/ranking.py → SetRanking` — ranking recalc
- `rider/rider.py → CheckValidLicenceThread` — licence validity from Czech Cycling API
- Cron (django-crontab): licence check every 6 hours, subscription renewals at 02:00/02:15

### Custom user model

`accounts.Account` extends `AbstractBaseUser`. Roles are boolean flags: `is_rider`, `is_commissar`, `is_trainer`, `is_club_manager`. `AUTH_USER_MODEL = "accounts.Account"`.

### Frontend

Tailwind CSS 4.x, built from `theme/static_src/`. Compiled output goes to `theme/static/css/dist/styles.css`. Templates live in `{app}/templates/{app}/` with a shared base in `theme/templates/`. Dark mode is toggled via a CSS class (`html.dark`).
