"""
Smaže soubory v MEDIA_ROOT, na které neodkazuje žádný záznam v DB.

Bezpečnostní opatření:
  - Výchozí režim je --dry-run (pouze vypíše, co by smazal).
  - Přidej --delete pro skutečné smazání.
  - Složky v SKIP_DIRS jsou vždy ignorovány.
  - Soubory v PROTECTED_FILES jsou vždy zachovány.
"""

import os
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models as django_models

# Složky relativně k MEDIA_ROOT, které se nikdy nesmažou (výsledky závodů, exporty atd.)
SKIP_DIRS = {
    "api-payloads",
    "bem-files",
    "bem_backup",
    "bem_riders",
    "ec-files",
    "event_stats",
    "full_results",
    "html_results",
    "participation",
    "proposition_uploads",
    "propositions",
    "rem-files",
    "rem_entries",
    "rem_results",
    "rem_riders",
    "riders-list",
    "series",
    "uci-templates",
    "xls_results",
    "cash-receipts",  # finance doklady — zachovat
    "invoices",
    "subscription-invoices",
}

# Konkrétní soubory (relativní cesta k MEDIA_ROOT), které se nikdy nesmažou
PROTECTED_FILES = {
    "images/news/AKBMX.jpg",
    "images/users/blank-avatar-200x200.jpg",
}


class Command(BaseCommand):
    help = (
        "Najde soubory v MEDIA_ROOT, na které neodkazuje žádný model, "
        "a volitelně je smaže. Výchozí režim je --dry-run."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Skutečně smaže osiřelé soubory (bez tohoto přepínače jen vypíše).",
        )
        parser.add_argument(
            "--skip-dir",
            nargs="+",
            metavar="DIR",
            help="Přidá další složky (relativně k MEDIA_ROOT) do seznamu ignorovaných.",
        )
        parser.add_argument(
            "--only-dir",
            metavar="DIR",
            help="Kontroluje pouze tuto podsložku MEDIA_ROOT (relativně).",
        )

    def handle(self, *args, **options):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            self.stderr.write(f"MEDIA_ROOT neexistuje: {media_root}")
            return

        do_delete = options["delete"]
        skip_dirs = set(SKIP_DIRS)
        if options["skip_dir"]:
            skip_dirs.update(options["skip_dir"])

        only_dir = options["only_dir"]

        # --- Sbírání DB referencí ---
        self.stdout.write("Načítám reference z DB …")
        referenced: set[str] = set()
        for model in apps.get_models():
            file_fields = [
                f for f in model._meta.get_fields()
                if isinstance(f, (django_models.FileField, django_models.ImageField))
            ]
            if not file_fields:
                continue
            field_names = [f.name for f in file_fields]
            for obj in model.objects.only(*field_names).iterator(chunk_size=500):
                for field_name in field_names:
                    value = getattr(obj, field_name, None)
                    if value and str(value):
                        referenced.add(str(value))  # relativní cesta k MEDIA_ROOT

        self.stdout.write(f"  Nalezeno {len(referenced)} odkazovaných souborů v DB.")

        # --- Prohledávání disku ---
        scan_root = media_root / only_dir if only_dir else media_root
        if not scan_root.exists():
            self.stderr.write(f"Cílová složka neexistuje: {scan_root}")
            return

        orphaned: list[Path] = []
        skipped_dirs_hit: set[str] = set()

        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue

            rel = path.relative_to(media_root)
            rel_str = str(rel)

            # Přeskočit chráněné soubory
            if rel_str in PROTECTED_FILES:
                continue

            # Přeskočit ignorované složky (první složka v cestě)
            top_dir = rel.parts[0]
            if top_dir in skip_dirs:
                skipped_dirs_hit.add(top_dir)
                continue

            if rel_str not in referenced:
                orphaned.append(path)

        # --- Výstup ---
        if skipped_dirs_hit:
            self.stdout.write(
                f"  Přeskočené složky: {', '.join(sorted(skipped_dirs_hit))}"
            )

        if not orphaned:
            self.stdout.write(self.style.SUCCESS("Žádné osiřelé soubory nenalezeny."))
            return

        total_size = sum(p.stat().st_size for p in orphaned)
        self.stdout.write(
            f"\nOsiřelé soubory ({len(orphaned)}, {_human_size(total_size)}):"
        )
        for p in orphaned:
            rel = p.relative_to(media_root)
            self.stdout.write(f"  {rel}")

        if not do_delete:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry-run: {len(orphaned)} soubor(ů) by bylo smazáno "
                    f"({_human_size(total_size)}). Spusť s --delete pro skutečné smazání."
                )
            )
            return

        # --- Smazání ---
        deleted = 0
        errors = 0
        for p in orphaned:
            try:
                p.unlink()
                deleted += 1
            except OSError as exc:
                self.stderr.write(f"  CHYBA při mazání {p}: {exc}")
                errors += 1

        # Smaž prázdné složky (zdola nahoru)
        dirs_removed = 0
        for dirpath in sorted(
            {p.parent for p in orphaned}, key=lambda d: len(d.parts), reverse=True
        ):
            if dirpath == media_root:
                continue
            try:
                if dirpath.is_dir() and not any(dirpath.iterdir()):
                    dirpath.rmdir()
                    dirs_removed += 1
            except OSError:
                pass

        msg = f"Smazáno {deleted} soubor(ů) ({_human_size(total_size)})"
        if dirs_removed:
            msg += f", {dirs_removed} prázdná složka/složek"
        if errors:
            msg += f", {errors} chyb"
        self.stdout.write(self.style.SUCCESS(msg + "."))


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
