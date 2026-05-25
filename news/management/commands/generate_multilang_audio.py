import os
import time

from django.core.management.base import BaseCommand

from news.models import News, _AUDIO_LANGS, _generate_audio


class Command(BaseCommand):
    help = "Generate missing multilingual TTS audio for published news articles."

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
            help="Restrict to articles with publish_in_app=True (default: all published).",
        )

    def handle(self, *args, **options):
        force = options["all"]
        only_lang = options["lang"]
        ids = options["ids"]
        delay = options["delay"]
        app_only = options["app_only"]

        qs = News.objects.filter(published=True).order_by("id")
        if app_only:
            qs = qs.filter(publish_in_app=True)
        if ids:
            qs = qs.filter(pk__in=ids)

        langs = ["cs"] + list(_AUDIO_LANGS)
        if only_lang:
            langs = [only_lang]

        total = qs.count()
        self.stdout.write(
            f"Processing {total} article(s), language(s): {', '.join(langs)}"
            + (f", delay={delay}s" if delay else "")
        )

        for idx, article in enumerate(qs):
            any_generated = False
            for lang in langs:
                field = "audio_file" if lang == "cs" else f"audio_file_{lang}"
                existing = getattr(article, field)
                # Check if the file actually exists on disk, not just in the DB —
                # a deleted or moved file leaves a stale DB path that looks non-empty.
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

            # Pause between articles (not after the last one)
            if any_generated and delay and idx < total - 1:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("Done."))
