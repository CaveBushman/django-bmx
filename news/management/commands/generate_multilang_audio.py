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

    def handle(self, *args, **options):
        force = options["all"]
        only_lang = options["lang"]
        ids = options["ids"]

        qs = News.objects.filter(published=True, publish_in_app=True).order_by("id")
        if ids:
            qs = qs.filter(pk__in=ids)

        langs = ["cs"] + list(_AUDIO_LANGS)
        if only_lang:
            langs = [only_lang]

        total = qs.count()
        self.stdout.write(f"Processing {total} article(s), language(s): {', '.join(langs)}")

        for article in qs:
            for lang in langs:
                field = "audio_file" if lang == "cs" else f"audio_file_{lang}"
                existing = getattr(article, field)
                if existing and not force:
                    continue
                self.stdout.write(f"  [{article.pk}] {lang} ...", ending=" ")
                self.stdout.flush()
                try:
                    _generate_audio(article.pk, lang)
                    self.stdout.write(self.style.SUCCESS("ok"))
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))

        self.stdout.write(self.style.SUCCESS("Done."))
