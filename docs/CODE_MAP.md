# Mapa kódu

Tento dokument je praktický rozcestník pro údržbu. Architektonické souvislosti
a datové vztahy jsou podrobněji v [ARCHITECTURE.md](ARCHITECTURE.md).

## Jak požadavek prochází aplikací

Server-renderovaný web obvykle prochází touto cestou:

```text
bmx/urls.py
  → <app>/urls.py
    → view v <app>/views.py nebo <app>/views/
      → formulář / service / model
        → template v <app>/templates/<app>/
```

Mobilní API prochází cestou:

```text
bmx/urls.py → api/urls.py → api/views/<doména>.py
  → serializer → stejné doménové modely a služby jako web
```

Django admin používá `<app>/admin.py`. Admin třída má primárně skládat
formulář a volat doménovou službu; finanční nebo skladovou logiku není vhodné
duplikovat přímo v `save_model()`.

## Když chci změnit…

| Požadavek | Začni zde | Související místa |
|---|---|---|
| Homepage nebo novinky | `news/views.py`, `news/models.py` | `news/templates/`, `news/tasks.py` |
| Seznam/detail závodu | `event/views/views_public.py` | `event/models_events.py`, `event/templates/event/` |
| Povolené kategorie a ceny přihlášky | `event/views/entry_helpers.py` | `event/views/views_entry.py`, `event/models_entries.py` |
| Platbu přihlášky | `event/views/views_payment.py` | `event/services/checkout_sessions.py`, `event/services/payments.py` |
| Refund/checkout jezdce | `event/services/checkout_refunds.py` | `event/credit.py`, `event/models_finance.py`, `event/signals.py` |
| Zahraniční přihlášku | `event/views/views_entry.py` | `event/services/foreign_entry_refunds.py`, `event/models_entries.py` |
| Import výsledků | `event/views/views_admin.py` | `event/func.py`, `event/result.py`, `event/services/rem_tsv_import.py` |
| Výpočet rankingu | `ranking/ranking.py` | `ranking/tasks.py`, `ranking/views.py` |
| Kvalifikaci na MČR | `rider/rider.py` | `rider/tasks.py`, `event/models_events.py` |
| Profil nebo vyhledání jezdce | `rider/views/directory.py` | `rider/models.py`, `rider/templates/rider/` |
| Uživatelský účet jezdce | `rider/views/account.py` | `accounts/models.py`, `rider/user_urls.py` |
| Trenérský dashboard | `rider/views/trainer.py` | `rider/subscriptions.py`, `accounts/models.py` |
| Předplatné a promo kódy | `rider/subscriptions.py` | `rider/models.py`, `rider/views/premium.py`, `rider/views/account.py` |
| Licence z ČSC | `rider/rider.py` | `rider/views/directory.py`, `rider/views/admin.py` |
| Uživatelské role a přihlášení | `accounts/models.py`, `accounts/views.py` | `accounts/forms.py`, `accounts/urls.py` |
| Push notifikace | `accounts/push_notifications.py` | `accounts/models.py::FcmDevice`, `news/tasks.py` |
| Klub nebo klubové družstvo MČR | `club/models.py`, `club/views.py` | `event/views/views_admin.py` |
| Faktury a pokladní doklady | `finance/invoices.py`, `finance/views.py` | `finance/models.py`, `finance/subscription_invoices.py` |
| E-shop checkout | `eshop/views.py` | `eshop/cart.py`, `eshop/models.py`, `api/views/eshop.py` |
| Sklad a rezervace | `eshop/models.py` | `eshop/admin.py`, `eshop/management/commands/` |
| REST API endpoint | `api/urls.py` | odpovídající soubor v `api/views/`, serializery doménové app |
| Periodickou úlohu | `bmx/cron.py` | `bmx/tasks.py`, `bmx/settings.py`, `docker-compose.yml` |
| Cache nebo rate limit | `bmx/rate_limit.py` | `bmx/settings.py`, Redis |
| Globální navigaci/context | `bmx/context_processors.py` | `theme/templates/base.html` |
| Middleware, CSP, request ID | `bmx/middleware.py`, `bmx/views.py` | `bmx/settings.py`, `bmx/request_context.py` |
| Monitoring chyby | `bmx/observability.py`, `bmx/logging_config.py` | Sentry a strukturované logy |

## Doménové hranice

### `event`: závod, registrace, výsledek a finanční stopa

Modely jsou rozdělené podle odpovědnosti a znovu exportované z `event/models.py`:

- `models_events.py` — konfigurace sezony, třídy, závod a propozice;
- `models_entries.py` — domácí a zahraniční přihlášky a jejich audit;
- `models_results.py` — konečné výsledky a jednotlivé měřené jízdy;
- `models_finance.py` — kreditní/debetní transakce a finanční audit.

`Entry.checkout=True` neznamená zaplaceno. Znamená, že zaplacená přihláška
byla odbavena/refundována. Zda byla zaplacena určuje `payment_complete` a finanční
stopu potvrzují transakční modely.

### `rider`: identita jezdce a sportovní stav

Interní FK obvykle používají `Rider.pk`; veřejné URL, importy a některé výsledky
používají `Rider.uci_id`. Při opravě URL nebo dotazu je nutné ověřit, který
identifikátor daná vrstva očekává.

Sportovní třídy, rankingové body a kvalifikační příznaky jsou odvozená data.
Neměla by se bezdůvodně přepisovat přímo ve view; jejich zdrojem jsou přepočtové
služby.

### `accounts`: identita uživatele a oprávnění

`Account` je vlastní `AUTH_USER_MODEL`. Role jsou kombinovatelné boolean příznaky;
nelze předpokládat, že uživatel má právě jednu roli. Vazba uživatele na jezdce
je explicitní přes `AccountRiderLink`, nikoli podle shody e-mailu nebo jména.

### `finance` a `eshop`: peníze a sklad

Operace, které mění kredit, stav objednávky nebo sklad, musí proběhnout v
`transaction.atomic()` a pokud možno zamknout upravovaný řádek pomocí
`select_for_update()`. Auditní a skladové pohyby jsou součástí výsledku operace,
ne doplňkový log, který lze bezpečně vynechat.

## Kde hledat frontend

- Sdílený layout: `theme/templates/base.html`.
- Doménové šablony: `<app>/templates/<app>/`.
- Ruční JavaScript: `static/js/` a případně statika konkrétní app.
- Zdroj Tailwind CSS: `theme/static_src/src/styles.css`.
- Výsledné CSS: `theme/static/css/dist/styles.css` — neupravovat ručně.
- Dark mode: třída `dark` na elementu `<html>`.

Pokud view připravuje složitý slovník pro template, dej sestavení dat do
pojmenované helper funkce. Šablona by měla formátovat, podmiňovat viditelnost a
generovat odkazy; neměla by počítat doménové výsledky.

## Testy a diagnostika

Testy jsou převážně v `<app>/tests.py`; větší oblasti mají další soubory
`tests_*.py`. JavaScriptové smoke testy jsou v `tests/js/` a spouštějí se přímo
přes Node:

```bash
for file in tests/js/*_test.js; do node "$file" || exit 1; done
```

Doporučený postup při chybě HTTP 500:

1. najdi traceback v `logs/errors.log` nebo v testovacím výstupu;
2. reprodukuj nejmenším requestem přes Django test client;
3. ověř, zda je chyba závislá na konkrétních datech;
4. oprav příčinu, ne pouze error handler;
5. přidej regresní test s daty, která aktivují problematickou větev;
6. spusť `manage.py check`, cílený test a odpovídající smoke test.

## Komentáře v kódu

Komentář má vysvětlovat zejména **proč**:

- doménový invariant nebo historicky neobvyklé rozhodnutí;
- rozdíl mezi podobnými identifikátory/stavy;
- vedlejší efekt (audit, refund, přepočet, notifikace);
- důvod transakce, zámku, fallbacku nebo bezpečnostní pojistky;
- formát dat externí služby, který není z typu zřejmý.

Nevhodný komentář jen opakuje název následujícího příkazu. Při změně
chování se musí upravit i související docstring a dokumentace.
