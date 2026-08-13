#!/usr/bin/env bash
#
# Deploy skript pro produkci (systemd + gunicorn + celery + django-crontab).
# Na serveru stačí spustit:
#
#     cd /home/david/django-bmx && git pull && ./deploy.sh
#
# Skript sám najde venv (env313/), stáhne kód, doinstaluje závislosti,
# zmigruje DB (se zálohou), zkompiluje překlady, posbírá statiku,
# přeregistruje cron úlohy, restartuje služby a nakonec ověří, že běžící
# aplikace opravdu servíruje novou statiku.
#
# Pořadí kroků není libovolné:
#   migrate        → před restartem, ať nová verze nenaběhne na staré schéma
#   css/i18n       → před collectstatic, ať se posbírá až hotový výstup
#   collectstatic  → před restartem: ManifestStaticFilesStorage drží manifest
#                    (hashovaná jména) v paměti procesu. Když se restartuje
#                    dřív než se posbírá statika, aplikace servíruje staré
#                    hashe → v prohlížeči staré CSS/JS i po "úspěšném" deployi.
#   verify         → porovná hash v manifestu s hashem, který aplikace reálně
#                    vrací v HTML. Přesně tohle odhalí půlku nasazení.
#
# Nepovinné kroky (pip, testy, i18n, cron, check --deploy) při chybě jen
# varují a deploy pokračuje — cílem je nikdy neskončit v půlce, tj. s novým
# kódem a starou statikou. Kritické kroky (pull, migrace, collectstatic,
# restart, ověření) deploy ukončí s chybou.
#
# Přepínače (env proměnné):
#   DRY_RUN=1              jen vypíše, co by se stalo (nic nespustí)
#   FORCE=1                nevadí necommitnuté změny v pracovním stromu
#   DEPLOY_PIP=0           přeskočí pip install -r requirements.txt
#   DEPLOY_BACKUP=0        přeskočí zálohu databáze před migrací
#   DEPLOY_TESTS=1         před nasazením spustí testy (default vypnuto, ~1 min)
#   DEPLOY_CSS=1           přebuilduje Tailwind na serveru (default 0, viz níže)
#   DEPLOY_I18N=0          přeskočí compilemessages
#   DEPLOY_CRON=0          přeskočí přeregistrování django-crontab úloh
#   CLEAR_STATIC=1         collectstatic --clear (smaže staré hashované soubory)
#   HEALTH_URL=…           default http://127.0.0.1:8000/healthz; prázdné = vypnuto
#
# Poznámka k CSS: theme/static/css/dist/styles.css je verzovaný, takže se
# Tailwind normálně buildí lokálně (`make css`) a commituje — server nepotřebuje
# node. DEPLOY_CSS=1 je pro případ, že build na serveru chceš.

set -euo pipefail

# Projektový adresář = ten, kde leží manage.py. Skript tak funguje jak z korene
# repa (./deploy.sh), tak kdyby se přesunul do podadresáře (./scripts/deploy.sh).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/manage.py" ]; then
  PROJECT_DIR="$SCRIPT_DIR"
elif [ -f "$SCRIPT_DIR/../manage.py" ]; then
  PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
else
  printf '!! Nenašel jsem manage.py vedle skriptu ani o úroveň výš.\n' >&2
  exit 1
fi
cd "$PROJECT_DIR"

DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
DEPLOY_PIP="${DEPLOY_PIP:-1}"
DEPLOY_BACKUP="${DEPLOY_BACKUP:-1}"
DEPLOY_TESTS="${DEPLOY_TESTS:-0}"
DEPLOY_CSS="${DEPLOY_CSS:-0}"
DEPLOY_I18N="${DEPLOY_I18N:-1}"
DEPLOY_CRON="${DEPLOY_CRON:-1}"
CLEAR_STATIC="${CLEAR_STATIC:-0}"
HEALTH_URL="${HEALTH_URL-http://127.0.0.1:8000/healthz}"

DB_PATH="${DB_PATH:-$PROJECT_DIR/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups/db}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

CSS_DIST="theme/static/css/dist/styles.css"
MANIFEST="staticfiles/staticfiles.json"

# --- pomocné funkce ----------------------------------------------------------

STEP="start"
WARNINGS=()

step()  { STEP="$1"; printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
info()  { printf '    %s\n' "$*"; }
warn()  { WARNINGS+=("$*"); printf '\033[1;33m    ! %s\033[0m\n' "$*"; }
die()   { printf '\n\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }

# Kritický krok — při chybě spadne celý skript (set -e + ERR trap).
run()  {
  if [ "$DRY_RUN" = "1" ]; then printf '    [dry-run] %s\n' "$*"; else "$@"; fi
}

# Nepovinný krok — při chybě jen varuje a jde se dál.
soft() {
  if [ "$DRY_RUN" = "1" ]; then printf '    [dry-run] %s\n' "$*"; return 0; fi
  if ! "$@"; then warn "krok selhal (pokračuji): $*"; return 0; fi
}

trap 'printf "\n\033[1;31m!! DEPLOY PŘERUŠEN v kroku: %s\033[0m\n" "$STEP" >&2' ERR

if [ "$(id -u)" = "0" ]; then SUDO=""; else SUDO="sudo"; fi

# Restartuje unit, jen pokud na tomhle stroji existuje (celery-beat běží
# jen při USE_CELERY_BEAT=True, jinak periodiku řídí django-crontab).
restart_unit() {
  local unit="$1"
  local required="${2:-0}"
  if $SUDO systemctl cat "$unit" >/dev/null 2>&1; then
    run $SUDO systemctl restart "$unit"
    info "restartováno: $unit"
  elif [ "$required" = "1" ]; then
    warn "$unit na tomhle stroji neexistuje — web nikdo nerestartoval!"
  else
    info "přeskočeno (unit neexistuje): $unit"
  fi
}

http_status() {
  if have curl; then
    curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$1" || echo "000"
  else
    "$PY" - "$1" <<'PY' || echo "000"
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=15) as r:
        print(r.status)
except Exception:
    print("000")
PY
  fi
}

http_body() {
  if have curl; then
    curl -s --max-time 15 "$1" || true
  else
    "$PY" - "$1" <<'PY' || true
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=15) as r:
        sys.stdout.write(r.read().decode("utf-8", "replace"))
except Exception:
    pass
PY
  fi
}

# --- volba interpretu --------------------------------------------------------

step "Prostředí"
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
elif [ -x "$PROJECT_DIR/env313/bin/python" ]; then
  PY="$PROJECT_DIR/env313/bin/python"     # cesta z scripts/celery-worker.service
elif [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
  PY="$PROJECT_DIR/.venv/bin/python"
elif have python3; then
  PY="python3"
else
  die "Nenašel jsem Python (ani venv, ani python3)."
fi
info "projekt: $PROJECT_DIR"
info "python:  $PY ($("$PY" --version 2>&1))"
[ "$DRY_RUN" = "1" ] && warn "DRY_RUN=1 — nic se opravdu nespustí"

# --- git --------------------------------------------------------------------

step "Git"
have git || die "git není k dispozici."

# Přebuildované CSS na serveru by blokovalo ff-only pull — zahodíme ho,
# správná verze přijde z gitu (a případně se přebuilduje níž).
if ! git diff --quiet -- "$CSS_DIST" 2>/dev/null; then
  info "zahazuji lokální změny v $CSS_DIST (verze přijde z gitu)"
  run git checkout -- "$CSS_DIST"
fi

# Netrackované soubory (zálohy DB, ruční exporty…) pull nijak neblokují,
# takže je jen vypíšeme. Blokovat může jen změna ve verzovaném souboru.
UNTRACKED_COUNT="$(git ls-files --others --exclude-standard | wc -l | tr -d ' ')"
if [ "$UNTRACKED_COUNT" != "0" ]; then
  info "netrackovaných souborů: $UNTRACKED_COUNT (pull neblokují, ignoruji)"
  git ls-files --others --exclude-standard | head -5 | sed 's/^/      ?? /'
fi

DIRTY="$(git status --porcelain --untracked-files=no)"
if [ -n "$DIRTY" ]; then
  printf '%s\n' "$DIRTY"
  if [ "$FORCE" = "1" ]; then
    warn "verzované soubory jsou změněné, pokračuji kvůli FORCE=1"
  else
    die "Změny ve verzovaných souborech. Ukliď je (git checkout/stash), nebo spusť s FORCE=1."
  fi
fi

REV_BEFORE="$(git rev-parse --short HEAD)"
run git pull --ff-only
REV_AFTER="$(git rev-parse --short HEAD)"
if [ "$REV_BEFORE" = "$REV_AFTER" ]; then
  info "žádné nové commity ($REV_AFTER) — statiku i tak přegenerujeme"
else
  info "$REV_BEFORE → $REV_AFTER"
  git --no-pager log --oneline "$REV_BEFORE..$REV_AFTER" | sed 's/^/    /'
fi

# --- závislosti -------------------------------------------------------------

step "Python závislosti"
if [ "$DEPLOY_PIP" = "1" ]; then
  # Ne pip-sync — ten odinstaluje cokoli mimo requirements.txt.
  soft "$PY" -m pip install --quiet --upgrade pip
  soft "$PY" -m pip install --quiet -r requirements.txt
  info "requirements.txt zpracován"
else
  info "přeskočeno (DEPLOY_PIP=0)"
fi

# --- kontroly ---------------------------------------------------------------

step "Kontroly"
soft "$PY" manage.py makemigrations --check --dry-run
if [ "$DEPLOY_TESTS" = "1" ]; then
  soft "$PY" manage.py test
else
  info "testy přeskočeny (DEPLOY_TESTS=1 je zapne)"
fi

# --- záloha databáze --------------------------------------------------------

step "Záloha databáze"
if [ "$DEPLOY_BACKUP" != "1" ]; then
  info "přeskočeno (DEPLOY_BACKUP=0)"
elif [ ! -f "$DB_PATH" ]; then
  warn "databáze $DB_PATH neexistuje — zálohu přeskakuji"
elif [ "$DRY_RUN" = "1" ]; then
  info "[dry-run] sqlite .backup → $BACKUP_DIR"
else
  mkdir -p "$BACKUP_DIR"
  SNAP="$BACKUP_DIR/predeploy-$(date '+%Y%m%d-%H%M%S').sqlite3"
  # Online .backup přes Python — konzistentní i nad běžící DB (WAL) a bez
  # závislosti na sqlite3 CLI, který na serveru být nemusí.
  "$PY" - "$DB_PATH" "$SNAP" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dst)
with target:
    source.backup(target)
target.close()
source.close()
PY
  gzip -f "$SNAP"
  info "záloha: $SNAP.gz"
  find "$BACKUP_DIR" -type f -name 'predeploy-*.sqlite3.gz' -mtime +"$RETENTION_DAYS" -delete
fi

# --- migrace ----------------------------------------------------------------

step "Migrace"
run "$PY" manage.py migrate --noinput

# --- build assetů -----------------------------------------------------------

step "Tailwind CSS"
if [ "$DEPLOY_CSS" != "1" ]; then
  info "build přeskočen — $CSS_DIST se bere z gitu (lokálně: make css)"
elif ! have npm; then
  warn "DEPLOY_CSS=1, ale npm tu není — zůstává verze z gitu"
else
  soft npm ci --prefix theme/static_src
  soft npm run build --prefix theme/static_src
fi

step "Překlady (.mo)"
if [ "$DEPLOY_I18N" != "1" ]; then
  info "přeskočeno (DEPLOY_I18N=0)"
elif ! have msgfmt; then
  # .mo soubory nejsou ve verzování — bez nich web spadne zpátky na češtinu.
  warn "chybí gettext (msgfmt) → .mo se nezkompilují a web bude jen v češtině."
  warn "náprava: $SUDO apt-get install -y gettext"
else
  soft "$PY" manage.py compilemessages
fi

# --- statika ----------------------------------------------------------------

step "Statické soubory"
if [ "$CLEAR_STATIC" = "1" ]; then
  run "$PY" manage.py collectstatic --noinput --clear
else
  run "$PY" manage.py collectstatic --noinput
fi
if [ -f "$MANIFEST" ] && [ "$DRY_RUN" != "1" ]; then
  MANIFEST_CSS="$("$PY" - "$MANIFEST" <<'PY'
import json, sys
paths = json.load(open(sys.argv[1]))["paths"]
print(paths.get("css/dist/styles.css", ""))
PY
)"
  info "manifest: css/dist/styles.css → ${MANIFEST_CSS:-(nenalezeno)}"
else
  MANIFEST_CSS=""
fi

step "Kontrola nastavení (informativně)"
soft "$PY" manage.py check --deploy

# --- periodické úlohy -------------------------------------------------------

step "Cron úlohy (django-crontab)"
if [ "$DEPLOY_CRON" = "1" ]; then
  # remove + add = idempotentní přeregistrování podle aktuálního CRONJOBS.
  # Při USE_CELERY_BEAT=True je CRONJOBS prázdný, takže add nic nepřidá
  # a remove uklidí staré záznamy — v obou režimech správně.
  soft "$PY" manage.py crontab remove
  soft "$PY" manage.py crontab add
  soft "$PY" manage.py crontab show
else
  info "přeskočeno (DEPLOY_CRON=0)"
fi

# --- restart služeb ---------------------------------------------------------

step "Restart služeb"
restart_unit gunicorn.service 1
restart_unit celery-worker.service
restart_unit celery-beat.service

# --- health check -----------------------------------------------------------

step "Health check"
if [ -z "$HEALTH_URL" ] || [ "$DRY_RUN" = "1" ]; then
  info "přeskočeno (HEALTH_URL prázdné nebo dry-run)"
else
  OK=0
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    CODE="$(http_status "$HEALTH_URL")"
    if [ "$CODE" = "200" ]; then
      info "$HEALTH_URL → 200 (pokus $attempt)"
      OK=1
      break
    fi
    info "pokus $attempt: $CODE, zkouším znovu…"
    sleep 2
  done
  if [ "$OK" != "1" ]; then
    warn "Aplikace neodpovídá 200 na $HEALTH_URL"
    warn "logy: $SUDO journalctl -u gunicorn.service -n 50 --no-pager"
    die "Health check neprošel — web pravděpodobně neběží."
  fi
  READY_URL="${HEALTH_URL%/healthz}/readyz"
  if [ "$READY_URL" != "$HEALTH_URL" ]; then
    info "readyz → $(http_status "$READY_URL") (503 = některá závislost je degradovaná)"
  fi
fi

# --- ověření, že běžící aplikace servíruje novou statiku --------------------
#
# Hash v HTML pochází z manifestu, který si proces načte při startu. Když
# nesedí na manifest na disku, znamená to, že se restartovalo dřív než se
# posbírala statika (nebo běží jiný STATIC_ROOT / jiný pracovní adresář) —
# uživatel pak vidí staré CSS i po "úspěšném" deployi.

step "Ověření statiky"
BASE_URL="${HEALTH_URL%/healthz}"
if [ -z "$HEALTH_URL" ] || [ "$DRY_RUN" = "1" ]; then
  info "přeskočeno (HEALTH_URL prázdné nebo dry-run)"
elif [ -z "$MANIFEST_CSS" ]; then
  warn "nepřečetl jsem $MANIFEST — ověření přeskočeno"
else
  LIVE_CSS="$(http_body "$BASE_URL/" | grep -o 'css/dist/styles\.[0-9a-f]*\.css' | head -1)"
  if [ -z "$LIVE_CSS" ]; then
    warn "v HTML z $BASE_URL/ jsem nenašel odkaz na styles.css — ověření přeskočeno"
  elif [ "$LIVE_CSS" = "$MANIFEST_CSS" ]; then
    info "OK: aplikace servíruje $LIVE_CSS (shoda s manifestem)"
  else
    warn "manifest na disku: $MANIFEST_CSS"
    warn "aplikace vrací:    $LIVE_CSS"
    warn "→ proces drží starý manifest. Zkus znovu: $SUDO systemctl restart gunicorn.service"
    warn "→ pokud to nepomůže, běží gunicorn z jiného adresáře/venv než tento skript."
    die "Aplikace servíruje starou statiku — deploy není dokončený."
  fi
fi

# --- hotovo -----------------------------------------------------------------

if [ "${#WARNINGS[@]}" -gt 0 ]; then
  printf '\n\033[1;33m==> Deploy dokončen s %s varováními:\033[0m\n' "${#WARNINGS[@]}"
  for w in "${WARNINGS[@]}"; do printf '\033[1;33m    ! %s\033[0m\n' "$w"; done
else
  printf '\n'
fi
printf '\033[1;32m==> Deploy dokončen: %s (%s)\033[0m\n' "$REV_AFTER" "$(git log -1 --format=%s)"
