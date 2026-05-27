import os
import time

from django.core.management.base import BaseCommand

from news.models import News, _AUDIO_LANGS, _ALL_AUDIO_FIELDS, _generate_audio, _delete_all_audio


class Command(BaseCommand):
    help = "Generate or clean up multilingual TTS audio for published news articles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Regenerate all audio files, even if they already exist.",
        )
        parser.add_argument(
            "--lang",
            choices=["cs"] + list(_AUDIO_LANGS),
            help="Restrict generation to a single language.",
        )
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            metavar="ID",
            help="Process only specific article IDs.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            metavar="SECONDS",
            help="Pause between articles (default: 1s).",
        )
        parser.add_argument(
            "--app-only",
            action="store_true",
            help="Restrict to articles with publish_in_app=True.",
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help=(
                "Delete audio files for articles where published_audio=False. "
                "Nelze kombinovat s generováním."
            ),
        )

    def handle(self, *args, **options):
        force = options["all"]
        only_lang = options["lang"]
        ids = options["ids"]
        delay = options["delay"]
        app_only = options["app_only"]
        cleanup = options["cleanup"]

        if cleanup:
            self._run_cleanup(ids)
            return

        # Generuj audio jen pro články kde je audio povoleno
        qs = News.objects.filter(published=True, published_audio=True).order_by("id")
        if app_only:
            qs = qs.filter(publish_in_app=True)
        if ids:
            qs = qs.filter(pk__in=ids)

        langs = ["cs"] + list(_AUDIO_LANGS)
        if only_lang:
            langs = [only_lang]

        total = qs.count()
        self.stdout.write(
            f"Processing {total} article(s) with audio enabled, language(s): {', '.join(langs)}"
            + (f", delay={delay}s" if delay else "")
        )

        for idx, article in enumerate(qs):
            any_generated = False
            for lang in langs:
                field = "audio_file" if lang == "cs" else f"audio_file_{lang}"
                existing = getattr(article, field)
                file_exists = bool(existing) and os.path.isfile(existing.path)
                if file_exists and not force:
                    continue
                self.stdout.write(f"  [{article.pk}] {lang} ...", ending=" ")
                self.stdout.flush()
                try:
                    _generate_audio(article.pk, lang)
                    self.stdout.write(self.style.SUCCESS("ok"))
                    any_generated = True
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))

            if any_generated and delay and idx < total - 1:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("Done."))

    def _run_cleanup(self, ids):
        """Smaže audio soubory článků kde published_audio=False."""
        qs = News.objects.filter(published_audio=False).order_by("id")
        if ids:
            qs = qs.filter(pk__in=ids)

        # Jen ty, které vůbec nějaký soubor mají
        has_audio_filter = None
        for field in _ALL_AUDIO_FIELDS:
            from django.db.models import Q
            q = Q(**{f"{field}__isnull": False}) & ~Q(**{f"{field}": ""})
            has_audio_filter = q if has_audio_filter is None else has_audio_filter | q
        if has_audio_filter:
            qs = qs.filter(has_audio_filter)

        total = qs.count()
        self.stdout.write(f"Cleaning up audio for {total} article(s) with published_audio=False ...")

        deleted_count = 0
        for article in qs:
            self.stdout.write(f"  [{article.pk}] {article.title[:60]} ...", ending=" ")
            self.stdout.flush()
            try:
                _delete_all_audio(article.pk)
                self.stdout.write(self.style.SUCCESS("smazáno"))
                deleted_count += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))

        self.stdout.write(self.style.SUCCESS(f"Done. Smazáno {deleted_count}/{total} článků."))
