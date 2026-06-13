"""Automatický překlad nepřeložených .po řetězců přes projektovou infrastrukturu.

Používá `news.models._translate_text` (DeepL, je-li nastaven DEEPL_API_KEY, jinak
záloha Google Translate) — stejně jako překlad článků. Vyplní prázdné a (volitelně)
fuzzy entries z češtiny do cílových jazyků. Formátovací řetězce (%(x)s, {x}, %s)
přeskakuje, aby nerozbil interpolaci — ty je potřeba přeložit ručně.

Příklady:
    python manage.py translate_po                 # všechny jazyky, prázdné entries
    python manage.py translate_po --lang en,de     # jen vybrané jazyky
    python manage.py translate_po --include-fuzzy   # i fuzzy (přepíše je)
    python manage.py translate_po --limit 50        # max 50 entries na jazyk (dávkování)
    python manage.py translate_po --compile         # po překladu spustí compilemessages
"""

import re
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

DEFAULT_LANGS = ["en", "de", "es", "fr", "hu", "it", "pl", "sk"]
# Detekce interpolace (rozhoduje, zda je entry "formátovací").
FORMAT_RE = re.compile(r"%\(|%[sd]|%\d|\{\w*\}|\{\{")
# Jednotlivé placeholdery k zamaskování při překladu format-stringů.
TOKEN_RE = re.compile(r"%\([^)]*\)[a-zA-Z]|%[a-zA-Z]|\{[^{}]*\}|\{\{|\}\}")


def _mask(text):
    """Nahradí placeholdery sentinely @@i@@; vrátí (maskovaný text, seznam tokenů)."""
    tokens = []

    def repl(m):
        tokens.append(m.group(0))
        return f"@@{len(tokens) - 1}@@"

    return TOKEN_RE.sub(repl, text), tokens


def _unmask(text, tokens):
    """Obnoví placeholdery. Vrátí None, pokud některý sentinel v překladu chybí
    (radši nechat nepřeložené než rozbít interpolaci)."""
    for i, tok in enumerate(tokens):
        sentinel = f"@@{i}@@"
        if sentinel not in text:
            return None
        text = text.replace(sentinel, tok)
    return text


def _match_edge_newlines(msgid, msgstr):
    """Sjednotí vedoucí/koncové \\n msgstr s msgid (gettext to vyžaduje, jinak
    msgfmt hlásí fatal error)."""
    msgstr = msgstr.strip("\n")
    if msgid.startswith("\n"):
        msgstr = "\n" + msgstr
    if msgid.endswith("\n"):
        msgstr = msgstr + "\n"
    return msgstr


class Command(BaseCommand):
    help = "Přeloží nepřeložené .po řetězce (DeepL/Google) z češtiny do cílových jazyků."

    def add_arguments(self, parser):
        parser.add_argument("--lang", default=",".join(DEFAULT_LANGS),
                            help="Čárkou oddělené jazyky. Výchozí: všechny cílové.")
        parser.add_argument("--limit", type=int, default=0,
                            help="Max počet přeložených entries na jazyk (0 = bez limitu).")
        parser.add_argument("--include-fuzzy", action="store_true",
                            help="Přeložit i fuzzy entries (jinak jen prázdné).")
        parser.add_argument("--include-format", action="store_true",
                            help="Přeložit i řetězce s placeholdery (maskuje je sentinely @@i@@).")
        parser.add_argument("--workers", type=int, default=8,
                            help="Počet paralelních překladových requestů. Výchozí 8.")
        parser.add_argument("--compile", action="store_true",
                            help="Po překladu spustit compilemessages.")

    def handle(self, *args, **options):
        try:
            import polib
        except ImportError:
            self.stderr.write("Chybí polib: pip install polib")
            return

        from news.models import _translate_text

        langs = [l.strip() for l in options["lang"].split(",") if l.strip()]
        limit = options["limit"]
        include_fuzzy = options["include_fuzzy"]
        include_format = options["include_format"]
        workers = max(1, options["workers"])
        locale_root = settings.LOCALE_PATHS[0]

        for lang in langs:
            po_path = f"{locale_root}/{lang}/LC_MESSAGES/django.po"
            try:
                po = polib.pofile(po_path)
            except OSError:
                self.stderr.write(f"[{lang}] .po nenalezen: {po_path}")
                continue

            # Vyber entries k překladu
            targets, skipped = [], 0
            for entry in po:
                if entry.obsolete:
                    continue
                needs = entry.msgstr.strip() == "" or (include_fuzzy and "fuzzy" in entry.flags)
                if not needs:
                    continue
                if FORMAT_RE.search(entry.msgid) and not include_format:
                    skipped += 1
                    continue
                targets.append(entry)
            if limit:
                targets = targets[:limit]

            done = failed = processed = 0

            def _translate(entry):
                masked, tokens = _mask(entry.msgid)
                result = _translate_text(masked, lang)
                if tokens:
                    result = _unmask(result, tokens) if result else result
                if result:
                    result = _match_edge_newlines(entry.msgid, result)
                return entry, result

            with ThreadPoolExecutor(max_workers=workers) as pool:
                for entry, translated in pool.map(_translate, targets):
                    processed += 1
                    if translated and translated.strip():
                        entry.msgstr = translated
                        if "fuzzy" in entry.flags:
                            entry.flags.remove("fuzzy")
                        done += 1
                    else:
                        failed += 1
                    # Průběžné ukládání (resumable při přerušení)
                    if processed % 100 == 0:
                        po.save(po_path)

            po.save(po_path)
            self.stdout.write(self.style.SUCCESS(
                f"[{lang}] přeloženo={done} přeskočeno(format)={skipped} selhalo={failed}"
            ))

        if options["compile"]:
            self.stdout.write("Spouštím compilemessages…")
            call_command("compilemessages")
