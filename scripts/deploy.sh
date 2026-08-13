#!/usr/bin/env bash
#
# Deploy skript pro produkci (systemd + gunicorn + celery + django-crontab).
# Spustit na serveru z libovolného místa:  ./scripts/deploy.sh
#
# Pořadí kroků není libovolné:
#   migrate  → před restartem, ať nová verze nenaběhne na staré schéma
#   css/i18n → před collectstatic, ať se posbírá až hotový výstup
#   restart  → až po collectstatic, protože ManifestStaticFilesStorage drží
#              manifest (hashovaná jména) v paměti procesu; bez restartu
#              gunicorn servíruje staré hashe a změny v CSS/JS se neprojeví
#
# Přepínače (env proměnné):
#   DRY_RUN=1        jen vypíše, co by se stalo (nic nespustí)
#   FORCE=1          nevadí necommitnuté změny v pracovním stromu
#   DEPLOY_PIP=0     přeskočí pip install -r requirements.txt
#   DEPLOY_BACKUP=0  přeskočí zálohu databáze před migrací
#   DEPLOY_TESTS=1   před nasazením spustí testy (default vypnuto — trvá ~1 min)
#   DEPLOY_CSS=1     přebuilduje Tailwind na serveru (default 0, viz níže)
#   DEPLOY_I18N=0    přeskočí compilemessages
#   DEPLOY_CRON=0    přeskočí přeregistrování django-crontab úloh
#   HEALTH_URL=…     co se po restartu ověřuje (default http://127.0.0.1:8000/healthz)
#                    HEALTH_URL= (prázdné) kontrolu vypne
#
# Poznámka k CSS: theme/static/css/dist/styles.css je verzovaný, takže se
# Tailwind normálně buildí lokálně (`make css`) a commituje. Na serveru proto
# node vůbec není potřeba. DEPLOY_CSS=1 je pro případ, že build na serveru chceš.

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"

DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
DEPLOY_PIP="${DEPLOY_PIP:-1}"
DEPLOY_BACKUP="${DEPLOY_BACKUP:-1}"
DEPLOY_TESTS="${DEPLOY_TESTS:-0}"
DEPLOY_CSS="${DEPLOY_CSS:-0}"
DEPLOY_I18N="${DEPLOY_I18N:-1}"
DEPLOY_CRON="${DEPLOY_CRON:-1}"
HEALTH_URL="${HEALTH_URL-http://127.0.0.1:8000/healthz}"

DB_PATH="${DB_PATH:-$PROJECT_DIR/db.sqlite3}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups/db}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

CSS_DIST="theme/static/css/dist/styles.css"

# --- pomocné funkce ----------------------------------------------------------

STEP="start"
step()  { STEP="$1"; printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
info()  { printf '    %s\n' "$*"; }
warn()  { printf '\033[1;33m    ! %s\033[0m\n' "$*"; }
die()   { printf '\033[1;31m!! %s\033[0m\n' "$*" >&2; exit 1; }
have()  { command -v "$1" >/dev/null 2>&1; }
run()   {
  if [ "$DRY_RUN" = "1" ]; then printf '    [dry-run] %s\n' "$*"; else "$@"; fi
}
trap 'printf "\n\033[1;31m!! DEPLOY SELHAL v kroku: %s\033[0m\n" "$STEP" >&2' ERR

if [ "$(id -u)" = "0" ]; then SUDO=""; else SUDO="sudo"; fi

# Restartuje unit, jen pokud na tomhle stroji existuje (celery-beat běží
# jen při USE_CELERY_BEAT=True, jinak periodiku řídí django-crontab).
restart_unit() {
  local unit="$1"
  if $SUDO systemctl cat "$unit" >/dev/null 2>&1; then
    run $SUDO systemctl restart "$unit"
    info "restartováno: $unit"
  else
    info "přeskočeno (unit neexistuje): $unit"
  fi
}

http_status() {
  if have curl; then
    curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$1" || echo "000"
  else
    "$PY" - "$1" <<'PY' || echo "000"
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=10) as r:
        print(r.status)
except Exception:
    print("000")
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

# Lokálně přebuildované CSS by blokovalo ff-only pull — zahodíme ho,
# správná verze přijde z gitu (a případně se přebuilduje níž).
if [ "$DEPLOY_CSS" = "1" ] && ! git diff --quiet -- "$CSS_DIST" 2>/dev/null; then
  info "zahazuji lokální změny v $CSS_DIST (přijdou z gitu)"
  run git checkout -- "$CSS_DIST"
fi

DIRTY="$(git status --porcelain)"
if [ -n "$DIRTY" ]; then
  printf '%s\n' "$DIRTY"
  if [ "$FORCE" = "1" ]; then
    warn "pracovní strom není čistý, pokračuji kvůli FORCE=1"
  else
    die "Pracovní strom není čistý. Ukliď změny, nebo spusť s FORCE=1."
  fi
fi

REV_BEFORE="$(git rev-parse --short HEAD)"
run git pull --ff-only
REV_AFTER="$(git rev-parse --short HEAD)"
if [ "$REV_BEFORE" = "$REV_AFTER" ]; then
  info "žádné nové commity ($REV_AFTER) — jedeme dál, přebuild statiky má smysl i tak"
else
  info "$REV_BEFORE → $REV_AFTER"
  git --no-pager log --oneline "$REV_BEFORE..$REV_AFTER" | sed 's/^/    /'
fi

# --- závislosti -------------------------------------------------------------

step "Python závislosti"
if [ "$DEPLOY_PIP" = "1" ]; then
  # Ne pip-sync — ten odinstaluje cokoli mimo requirements.txt.
  run "$PY" -m pip install --quiet --upgrade pip
  run "$PY" -m pip install --quiet -r requirements.txt
  info "requirements.txt nainstalováno"
else
  info "přeskočeno (DEPLOY_PIP=0)"
fi

# --- kontroly před zásahem do DB --------------------------------------------

step "Kontroly"
run "$PY" manage.py makemigrations --check --dry-run
info "modely a migrace jsou v souladu"

if [ "$DEPLOY_TESTS" = "1" ]; then
  run "$PY" manage.py test
  info "testy prošly"
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
  info "build přeskočen — $CSS_DIST se bere z gitu (buildi lokálně: make css)"
elif ! have npm; then
  warn "DEPLOY_CSS=1, ale npm tu není — zůstává verze z gitu"
else
  run npm ci --prefix theme/static_src
  run npm run build --prefix theme/static_src
  info "CSS přebuildováno"
fi

step "Překlady (.mo)"
if [ "$DEPLOY_I18N" != "1" ]; then
  info "přeskočeno (DEPLOY_I18N=0)"
elif ! have msgfmt; then
  # .mo soubory nejsou ve verzování — bez nich web spadne zpátky na češtinu.
  warn "chybí gettext (msgfmt) → .mo se nezkompilují a web bude jen v češtině."
  warn "náprava: sudo apt-get install -y gettext"
else
  run "$PY" manage.py compilemessages
  info "překlady zkompilovány"
fi

# --- statika ----------------------------------------------------------------

step "Statické soubory"
run "$PY" manage.py collectstatic --noinput
info "collectstatic hotov (nový manifest → nutný restart gunicornu níž)"

step "Kontrola nastavení (informativně)"
run "$PY" manage.py check --deploy || warn "check --deploy něco hlásí, viz výše"

# --- periodické úlohy -------------------------------------------------------

step "Cron úlohy (django-crontab)"
if [ "$DEPLOY_CRON" = "1" ]; then
  # remove + add = idempotentní přeregistrování podle aktuálního CRONJOBS.
  # Při USE_CELERY_BEAT=True je CRONJOBS prázdný, takže add nic nepřidá
  # a remove uklidí staré záznamy — v obou režimech správně.
  run "$PY" manage.py crontab remove
  run "$PY" manage.py crontab add
  run "$PY" manage.py crontab show
else
  info "přeskočeno (DEPLOY_CRON=0)"
fi

# --- restart služeb ---------------------------------------------------------

step "Restart služeb"
restart_unit gunicorn.service
restart_unit celery-worker.service
restart_unit celery-beat.service

# --- health check -----------------------------------------------------------

step "Health check"
if [ -z "$HEALTH_URL" ]; then
  info "přeskočeno (HEALTH_URL je prázdné)"
elif [ "$DRY_RUN" = "1" ]; then
  info "[dry-run] GET $HEALTH_URL"
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
    die "Deploy dojel, ale health check neprošel — zkontroluj službu."
  fi
  READY_URL="${HEALTH_URL%/healthz}/readyz"
  if [ "$READY_URL" != "$HEALTH_URL" ]; then
    info "readyz → $(http_status "$READY_URL") (503 = některá závislost je degradovaná)"
  fi
fi

# --- hotovo -----------------------------------------------------------------

printf '\n\033[1;32m==> Deploy dokončen: %s (%s)\033[0m\n' "$REV_AFTER" "$(git log -1 --format=%s)"
