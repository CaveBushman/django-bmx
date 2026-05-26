import time

from django.core.management.base import BaseCommand

from news.models import News, _AUDIO_LANGS, _translate_article_content, _translate_text


class Command(BaseCommand):
    help = "Generate missing multilingual translations for published news articles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Regenerate all translations, even if they already exist.",
        )
        parser.add_argument(
            "--lang",
            choices=list(_AUDIO_LANGS),
            help="Restrict to a single target language.",
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
            default=2.0,
            metavar="SECONDS",
            help="Pause between articles to avoid Google Translate rate limiting (default: 2s).",
        )
        parser.add_argument(
            "--app-only",
            action="store_true",
            help="Restrict to articles with publish_in_app=True.",
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

        langs = [only_lang] if only_lang else list(_AUDIO_LANGS)

        total = qs.count()
        self.stdout.write(
            f"Processing {total} article(s), language(s): {', '.join(langs)}, delay={delay}s"
        )

        for idx, article in enumerate(qs):
            any_generated = False
            for lang in langs:
                title_field = f"title_{lang}"
                prefix_field = f"prefix_{lang}"
                content_field = f"content_{lang}"

                title_missing = not getattr(article, title_field, "").strip()
                body_done = (
                    bool(getattr(article, prefix_field, "").strip())
                    or bool(getattr(article, content_field, "").strip())
                )

                if not force:
                    if not title_missing and body_done:
                        # Fully translated — skip.
                        continue

                    if title_missing and body_done:
                        # Tělo již existuje, chybí jen titulek — přeložíme pouze ho.
                        self.stdout.write(
                            f"  [{article.pk}] {article.title[:50]!r} → {lang} (title only) ...",
                            ending=" ",
                        )
                        self.stdout.flush()
                        try:
                            translated = _translate_text(article.title or "", lang)
                            if translated:
                                News.objects.filter(pk=article.pk).update(**{title_field: translated})
                                self.stdout.write(self.style.SUCCESS("ok"))
                                any_generated = True
                            else:
                                self.stdout.write(self.style.WARNING("empty — skipped"))
                        except Exception as exc:
                            self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))
                        continue

                # Plný překlad (titulek + prefix + content).
                self.stdout.write(f"  [{article.pk}] {article.title[:50]!r} → {lang} ...", ending=" ")
                self.stdout.flush()
                try:
                    _translate_article_content(article.pk, lang)
                    self.stdout.write(self.style.SUCCESS("ok"))
                    any_generated = True
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"FAILED: {exc}"))

            if any_generated and delay and idx < total - 1:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS("Done."))
