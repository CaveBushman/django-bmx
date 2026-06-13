# Odstranění souboru `db` z git historie (GDPR)

V repozitáři byl verzovaný soubor `db` — 6,5MB SQLite databáze obsahující
reálné osobní údaje (e-maily účtů, tabulky jezdců). Soubor byl odtrackován
a přidán do `.gitignore` (`/db`), takže **se už nedostane do nových commitů**.

Stále ale zůstává v **historii** repozitáře. Aby zmizel úplně, je nutné
historii přepsat. To je destruktivní operace s force-push — proveď ji
cíleně a koordinovaně s ostatními vývojáři.

## Postup

1. **Záloha repozitáře** (pro jistotu):

   ```bash
   git clone --mirror git@github.com:CaveBushman/django-bmx.git django-bmx-backup.git
   ```

2. **Instalace git-filter-repo** (rychlejší a bezpečnější než filter-branch):

   ```bash
   pip install git-filter-repo
   ```

3. **Odstranění souboru ze vší historie** (spouštěj v čistém klonu repozitáře):

   ```bash
   git filter-repo --invert-paths --path db
   ```

   `git filter-repo` po doběhnutí odstraní `origin` remote (ochrana proti
   omylem provedenému push). Přidej ho zpět:

   ```bash
   git remote add origin git@github.com:CaveBushman/django-bmx.git
   ```

4. **Force-push přepsané historie** (POZOR: přepíše vzdálenou historii):

   ```bash
   git push origin --force --all
   git push origin --force --tags
   ```

5. **Ostatní vývojáři** musí svůj klon zahodit a naklonovat znovu
   (jejich staré klony obsahují odstraněná data a mohla by se vrátit při merge).

## Po přepisu

- Rotuj jakékoli tajné údaje, které kdy byly v repu (i když `db` je hlavní problém).
- Na GitHubu zvaž požádání o purge cache: smazané objekty mohou nějakou dobu
  zůstat dostupné přes přímý SHA odkaz. Viz GitHub docs „Removing sensitive data".
- Ověř, že `git log --all -- db` už nic nevrací.
