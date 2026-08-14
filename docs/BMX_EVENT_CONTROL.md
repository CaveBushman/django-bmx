# BMX Event Control — import přihlášených jezdců přes API

Integrace umožňuje stáhnout do BMX Event Control startovní listinu závodu přímo
ze serveru, bez mezikroku s REM/XLSX souborem.

Nastavuje se na dvou místech BMX Event Control:

| Kde v BMX Event Control | Co se zadává | Odkud to vzít na webu |
|---|---|---|
| Nastavení organizace | **Server**, **Username**, **Password** | Admin → Kluby → *klub* → panel „BMX Event Control“ |
| Nastavení závodu | **Kód závodu** | Admin → Závody → *závod* → panel „BMX Event Control“ (Kód závodu) |

Všechny hodnoty mají v adminu tlačítko **Kopírovat do schránky**.

## Přístupové údaje organizace

* `Club.event_control_username` — vygeneruje se ve tvaru `ec-<nazev-klubu>`, je unikátní.
* `Club.event_control_password` — ukládá se **jen jako hash**. Plaintext se zobrazí
  jedině na stránce, kde se heslo generuje; potom už ho nelze zjistit, jen vygenerovat nové.
* `Club.event_control_enabled` — vypnutím se přístup okamžitě zneplatní.
* `Club.event_control_last_access` — čas posledního úspěšného dotazu (kontrola, že Event Control opravdu stahuje).

Generování a zneplatnění: Admin → Kluby → *klub* → **Vygenerovat / změnit heslo**
(`/bmx-admin/club/club/<id>/event-control-credentials/`). Stránka zároveň vypíše
kódy posledních závodů daného pořadatele.

## Kód závodu

`Event.event_code` je UUID, vzniká automaticky při vytvoření závodu, je unikátní
a needitovatelný. Do veřejného API se **nepropisuje** (`EventSerializer` ho
vylučuje) — funguje jako párovací kód, ne jako veřejné ID závodu.

## Endpointy

Server pro nastavení organizace: `https://<domena>/api/v1/event-control/`

| Metoda | Cesta | Popis |
|---|---|---|
| GET | `/api/v1/event-control/ping/` | Test připojení; vrátí organizaci a kódy jejích posledních závodů |
| GET | `/api/v1/event-control/events/<event_code>/` | Metadata závodu |
| GET | `/api/v1/event-control/events/<event_code>/entries/` | Přihlášení jezdci |

Autentizace: **HTTP Basic** (username + password organizace). Přihlášený staff
účet (session/JWT) projde také — kvůli ověření z prohlížeče. Neúspěch vrací 401
s hlavičkou `WWW-Authenticate: Basic`.

Autorizace: organizace vidí jen závody, kde je uvedená jako **pořadatel**
(`Event.organizer`). Cizí i neexistující kód vrací shodně 403, aby odpověď
neprozradila existenci závodu.

Throttling: 120 požadavků/min na username (scope `event_control`).

Parametry `entries`:

* `include_unpaid=1` — přidá i nezaplacené přihlášky (jen pro kontrolu, ne pro startovku).

Výchozí filtr je stejný jako u REM exportu přihlášek: `payment_complete=True`,
`checkout=False` (odhlášené/refundované se nevrací).

## Formát odpovědi `entries`

```json
{
  "event": {
    "code": "0f1e...", "id": 42, "name": "Český pohár Praha", "date": "2026-05-10",
    "type_for_ranking": "Český pohár", "system": "3 základní rozjíždky a KO system",
    "organizer": "BMX Praha", "is_uci_race": false, "uci_event_code": ""
  },
  "generated_at": "2026-05-01T09:00:00+02:00",
  "include_unpaid": false,
  "count": 1,
  "starts_count": 2,
  "riders": [
    {
      "entry_id": 1234,
      "entry_type": "domestic",
      "transaction_id": "cs_test_...",
      "uci_id": "100000011",
      "first_name": "Adam", "last_name": "Novák",
      "email": "adam@example.com",
      "club": "BMX Praha", "team": "", "country": "CZE",
      "date_of_birth": "2012-01-01", "date_of_birth_display": "01.01.2012",
      "sex": "m", "rider_type": "C", "licence_type": "U", "licence_valid": true,
      "paid": true, "fee_total": 500, "updated": "2026-04-20",
      "starts": [
        {"wheel": "20", "is_beginner": false, "class": "Boys 14", "plate": "12", "transponder": "1234", "fee": 300},
        {"wheel": "24", "is_beginner": false, "class": "Cruiser 13-14", "plate": "12", "transponder": "5678", "fee": 200}
      ]
    }
  ]
}
```

Poznámky k datům (shodné s REM exportem `event.entry.REMRiders`):

* `entry_type` — `domestic` (`Entry`) nebo `foreign` (`EntryForeign`).
* jedna přihláška = jeden jezdec se **seznamem startů**; začátečnický start má `is_beginner: true`.
* `class` je název třídy podle tabulky kategorií závodu (`EntryClasses`), uložený v přihlášce.
* `plate` — championship plate má prefix `W` (např. `W3`), jinak číslo/text tabulky jezdce.
* `rider_type` — `E` pro elite licenci, jinak `C`.

## Synchronizace jezdců a klubů s Event Control Admin

Jezdci a kluby se v Event Control Admin zakládají centrálně, ale **master dat
zůstává web** (czechbmx.cz). Synchronizace je proto obousměrná a asymetrická:

| Směr | Kdo volá | Co dělá |
|---|---|---|
| Výdej (push) | Event Control Admin → API webu | Čte kompletní jezdce a kluby (identita, licence, klub, tabulka, čip, třídy) |
| Stahování (pull) | Web → API Event Control Admin | Doplní párovací `event_control_id`, založí neznámé záznamy, rozdíly zapíše jako konflikt (nepřepisuje) |

### Výdej master dat (příchozí požadavky)

| Metoda | Cesta | Parametry |
|---|---|---|
| GET | `/api/v1/event-control/riders/` | `updated_since`, `limit` (max 2000), `offset`, `include_inactive` |
| GET | `/api/v1/event-control/clubs/` | `updated_since`, `limit`, `offset`, `include_inactive` |

Autentizace: HTTP Basic **centrálními** údaji ze settings
(`EVENT_CONTROL_CENTRAL_USERNAME` / `EVENT_CONTROL_CENTRAL_PASSWORD`), případně
přihlášený staff účet. Přístupové údaje jednotlivých organizací sem **nemají
přístup** — jde o celofederační data, ne o jeden závod.

Odpověď: `{"count", "limit", "offset", "next_offset", "generated_at", "results": [...]}`.
Výchozí filtr jezdců je `is_active=True, is_approved=True`, klubů `is_active=True`;
`include_inactive=1` filtr vypne. Přírůstkově se čte podle `updated`.

### Stahování centrálně založených záznamů (odchozí)

Nastavení v `bmx/.env`:

```
EVENT_CONTROL_ADMIN_URL=https://<centralni-server>/api
EVENT_CONTROL_ADMIN_USERNAME=...
EVENT_CONTROL_ADMIN_PASSWORD=...
EVENT_CONTROL_ADMIN_TIMEOUT=30
EVENT_CONTROL_ADMIN_PAGE_SIZE=500
```

Bez `EVENT_CONTROL_ADMIN_URL` je stahování vypnuté (cron úloha jen zaloguje a skončí).

Web očekává na `\<URL\>/riders/` a `\<URL\>/clubs/` JSON — buď pole záznamů, nebo
`{"results": [...], "next_offset": n}` (stránkování se dotahuje automaticky).
Mapování klíčů je tolerantní: `id`/`event_control_id`, `uci_id`/`uciid`,
`gender`/`sex` (`m`/`f`), `date_of_birth`/`birthdate`, `team_name`/`name`, `ico`.

Pravidla párování:

* klub — `event_control_id` → `ico` → název (`team_name`/`club_name`, case-insensitive),
* jezdec — `event_control_id` → `uci_id`.

Co se stane s výsledkem:

* **spárováno** — doplní se `event_control_id` a `event_control_synced`; lokální
  hodnoty se nemění, rozdíly se uloží do logu jako `conflicts`,
* **neznámý klub** — založí se (název, IČO, město),
* **neznámý jezdec** — založí se jako `is_approved=False`, aby prošel běžným
  schválením; třídy dopočítá `pre_save` signál. Bez UCI ID, jména, data narození
  nebo pohlaví se záznam přeskočí (`skipped`),
* každý běh se zapíše do `EventControlSyncLog` (admin → „Synchronizace Event Control“).

Spuštění ručně:

```bash
python manage.py sync_event_control                    # kluby + jezdci z API
python manage.py sync_event_control --entity riders --since 2026-01-01
python manage.py sync_event_control --dry-run          # jen report konfliktů
python manage.py sync_event_control --entity clubs --file kluby.json
```

Pravidelně: `bmx.cron.sync_event_control_scheduled` (django-crontab, denně 1:30)
nebo Celery beat task `bmx.sync_event_control` — podle `USE_CELERY_BEAT`.

## Kód na serveru

* `event/services/event_control.py` — sestavení payloadu, ověření údajů organizace, autorizace na pořadatele.
* `api/views/event_control.py` — endpointy (`ping`, detail závodu, přihlášky), Basic auth, throttle.
* `bmx/admin_widgets.py` + `static/js/admin_copy_code.js` — panely s tlačítky „Kopírovat do schránky“.

Audit log (logger `audit`): `event_control_auth_failed`, `event_control_event_forbidden`,
`event_control_entries_exported`, `club_event_control_credentials_generated`,
`club_event_control_credentials_revoked`.
