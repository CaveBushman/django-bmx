
from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import pre_save
from django.db.models import F
from django.apps import apps
from ckeditor.fields import RichTextField
from accounts.models import Account
import datetime
import io
from django.core.files.base import ContentFile
import asyncio
import concurrent.futures
import edge_tts
import logging
import hashlib

import re
import time
import html as html_stdlib
import requests as _requests
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.utils.text import slugify
from bmx.html_sanitizer import sanitize_rich_html

# Jazyky, pro které generujeme přeložené TTS audio (cs se generuje zvlášť)
_AUDIO_LANGS = ("en", "de", "sk", "es", "it", "fr", "pl", "hu")

# Všechna pole s audio soubory na modelu News
_ALL_AUDIO_FIELDS = ["audio_file"] + [f"audio_file_{lang}" for lang in _AUDIO_LANGS]

# Označení sekcí pro TTS – v každém jazyce
_TTS_LABELS = {
    "cs": ("NADPIS.", "TEXT."),
    "en": ("TITLE.", "TEXT."),
    "de": ("ÜBERSCHRIFT.", "TEXT."),
    "sk": ("NADPIS.", "TEXT."),
    "es": ("TÍTULO.", "TEXTO."),
    "it": ("TITOLO.", "TESTO."),
    "fr": ("TITRE.", "TEXTE."),
    "pl": ("TYTUŁ.", "TEKST."),
    "hu": ("CÍM.", "SZÖVEG."),
}

# TTS labels (bez přesné pauzy varianta)
TTS_SECTION_TITLE = "NADPIS."
TTS_SECTION_BODY = "TEXT."



# Create your models here.

class Tag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption


logger = logging.getLogger(__name__)


def _send_article_push_notification(article_id: int):
    """Odešle push notifikaci o novém článku všem zaregistrovaným zařízením."""
    try:
        from accounts.push_notifications import send_to_all_users
        NewsModel = apps.get_model("news", "News")
        article = NewsModel.objects.get(pk=article_id)
        slug = article.slug or str(article.pk)
        result = send_to_all_users(
            title=article.title or "Nový článek",
            body="Přečti si nejnovější zprávy z Czech BMX.",
            path=f"/news/{slug}",
        )
        logger.info(
            "[FCM] Article %s: notifikace odeslána — %d úspěch, %d selhání.",
            article_id, result.get("success", 0), result.get("failure", 0),
        )
    except Exception:
        logger.exception("[FCM] Chyba při odesílání push notifikace pro Article %s", article_id)


def _delete_all_audio(article_id: int):
    """Smaže všechny audio soubory článku z disku a vymaže DB pole."""
    try:
        NewsModel = apps.get_model("news", "News")
        article = NewsModel.objects.get(pk=article_id)
        cleared = []
        for field_name in _ALL_AUDIO_FIELDS:
            f = getattr(article, field_name)
            if f:
                try:
                    f.delete(save=False)
                except Exception:
                    pass
                setattr(article, field_name, None)
                cleared.append(field_name)
        if cleared:
            article.audio_hash = ""
            article.save(update_fields=cleared + ["audio_hash"])
            logger.info("[TTS] Article %s: smazáno %d audio souborů.", article_id, len(cleared))
    except Exception:
        logger.exception("[TTS] Chyba při mazání audio souborů Article %s", article_id)


def enqueue_article_tts(article_id: int):
    from news.tasks import generate_audio_task
    generate_audio_task.delay(article_id, "cs")
    for lang in _AUDIO_LANGS:
        generate_audio_task.delay(article_id, lang)


def enqueue_article_translation(article_id: int):
    from news.tasks import translate_article_task
    for lang in _AUDIO_LANGS:
        translate_article_task.delay(article_id, lang)


def _html_to_blocks(html: str) -> list[str]:
    """Splits HTML into plain-text paragraphs for translation."""
    s = re.sub(r'<br\s*/?>', '\n', html or '', flags=re.IGNORECASE)
    s = re.sub(r'</(p|div|li|h[1-6]|blockquote|tr)>', '\n', s, flags=re.IGNORECASE)
    s = re.sub(r'<script\b[^>]*>[\s\S]*?</script>', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r'<style\b[^>]*>[\s\S]*?</style>', ' ', s, flags=re.IGNORECASE)
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html_stdlib.unescape(s)
    return [b.strip() for b in s.splitlines() if b.strip()]


def _translate_article_content(article_id: int, lang: str):
    """Background task: translates article prefix/content to target language."""
    try:
        NewsModel = apps.get_model("news", "News")
        article = NewsModel.objects.get(pk=article_id)

        def _translate_html(html: str) -> str:
            blocks = _html_to_blocks(html)
            if not blocks:
                return ""
            parts = []
            for block in blocks:
                translated = _translate_text(block, lang)
                if translated:
                    parts.append(f"<p>{translated}</p>")
                time.sleep(0.8)
            return "\n".join(parts)

        title_t = _translate_text(article.title or "", lang) if article.title else ""
        prefix_t = _translate_html(article.prefix or "")
        content_t = _translate_html(article.content or "")

        if not (title_t or prefix_t or content_t):
            logger.warning("[TRANSLATE] Article %s lang=%s: překlad selhal.", article_id, lang)
            return

        NewsModel.objects.filter(pk=article_id).update(**{
            f"title_{lang}": title_t,
            f"prefix_{lang}": prefix_t,
            f"content_{lang}": content_t,
        })
        logger.info("[TRANSLATE] Article %s lang=%s: přeloženo.", article_id, lang)
    except Exception as exc:
        logger.exception("[TRANSLATE] Chyba Article %s lang=%s: %s", article_id, lang, exc)


# DeepL kódy jazyků — DeepL používá jiné kódy než ISO 639-1
_DEEPL_LANG_MAP = {
    "en": "EN-US", "de": "DE", "sk": "SK", "es": "ES",
    "it": "IT", "fr": "FR", "pl": "PL", "hu": "HU",
}


def _translate_text(text: str, target_lang: str) -> str:
    """Přeloží text z češtiny. Primárně DeepL, záloha Google Translate."""
    if not text.strip():
        return text
    from django.conf import settings
    api_key = getattr(settings, "DEEPL_API_KEY", "")
    if api_key:
        result = _deepl_translate(text, target_lang, api_key)
        if result:
            return result
    return _google_translate(text, target_lang)


def _deepl_translate(text: str, target_lang: str, api_key: str) -> str:
    try:
        import deepl
        dl_lang = _DEEPL_LANG_MAP.get(target_lang, target_lang.upper())
        translator = deepl.Translator(api_key)
        result = translator.translate_text(text, source_lang="CS", target_lang=dl_lang)
        return result.text
    except Exception as exc:
        logger.warning("[TRANSLATE] DeepL selhal lang=%s: %s — zkouším zálohu.", target_lang, exc)
        return ""


def _google_translate(text: str, target_lang: str) -> str:
    chunks = _split_text(text, max_len=4800)
    parts = []
    for chunk in chunks:
        try:
            resp = _requests.get(
                "https://translate.googleapis.com/translate_a/single",
                params={"client": "gtx", "sl": "cs", "tl": target_lang, "dt": "t", "q": chunk},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            parts.append("".join(seg[0] for seg in data[0] if seg[0]))
        except Exception as exc:
            logger.warning("[TRANSLATE] Google Translate selhal lang=%s: %s", target_lang, exc)
            return ""
    return " ".join(parts)

def _split_text(text: str, max_len: int = 4500):
    """Rozdělí dlouhý text na kratší části (gTTS lépe snáší <5k znaků)."""
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return [text]
    chunks, buf, length = [], [], 0
    for word in text.split(" "):
        wlen = len(word) + (1 if length else 0)
        if length + wlen > max_len and buf:
            chunks.append(" ".join(buf))
            buf, length = [word], len(word)
        else:
            buf.append(word)
            length += wlen
    if buf:
        chunks.append(" ".join(buf))
    return chunks


# Helper to get plain text from article (title + prefix + content), stripping HTML/scripts/styles

# Vrátí (title, prefix, content) bez HTML/script/style značek a se znormalizovanými mezerami.
def _article_parts_plain(article):
    """Vrátí (title, prefix, content) bez HTML/script/style značek a se znormalizovanými mezerami."""
    raw_title = article.title or ""
    raw_prefix = getattr(article, "prefix", "") or ""
    raw_content = article.content or ""

    def _clean_html(s: str) -> str:
        s = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", s, flags=re.IGNORECASE)
        s = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", s, flags=re.IGNORECASE)
        s = strip_tags(s)
        s = html_stdlib.unescape(s)
        s = " ".join(s.split())
        return s.strip()

    title = _clean_html(raw_title)
    prefix = _clean_html(raw_prefix)
    content = _clean_html(raw_content)
    return title, prefix, content

def _article_text_plain(article) -> str:
    """Poskládá text článku (title + prefix + content) a odstraní HTML / skripty / styly."""
    title, prefix, content = _article_parts_plain(article)
    text = " ".join(p for p in ("NADPIS:     ",title, "TEXT:      ", prefix, content) if p)
    return text.strip()

# Neural voice mapping for edge-tts (Microsoft Azure voices via Edge endpoint).
# Higher quality than gTTS and not subject to the same IP rate-limiting.
_EDGE_VOICES = {
    "cs": "cs-CZ-VlastaNeural",
    "en": "en-US-AriaNeural",
    "de": "de-DE-KatjaNeural",
    "sk": "sk-SK-ViktoriaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "fr": "fr-FR-DeniseNeural",
    "pl": "pl-PL-ZofiaNeural",
    "hu": "hu-HU-NoemiNeural",
}


async def _edge_tts_bytes(text: str, voice: str) -> bytes:
    """Streams edge-tts audio and returns raw MP3 bytes."""
    communicate = edge_tts.Communicate(text, voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


def _run_async(coro):
    # asyncio.run() inside a ThreadPoolExecutor thread shares Python's default
    # executor with aiohttp's run_in_executor calls. During interpreter shutdown
    # that executor is already closed, causing RuntimeError. Fix: give each
    # event loop its own isolated executor so it is never the shutting-down one.
    loop = asyncio.new_event_loop()
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    loop.set_default_executor(executor)
    try:
        return loop.run_until_complete(coro)
    finally:
        executor.shutdown(wait=False)
        loop.close()


def _tts_chunk(text: str, lang: str, max_retries: int = 4) -> io.BytesIO:
    """Generates a single MP3 chunk via edge-tts with retry on network errors."""
    voice = _EDGE_VOICES.get(lang, "en-US-AriaNeural")
    for attempt in range(max_retries):
        try:
            data = _run_async(_edge_tts_bytes(text, voice))
            return io.BytesIO(data)
        except RuntimeError as exc:
            if "interpreter shutdown" in str(exc):
                raise  # server restarts — don't retry
            if attempt == max_retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            logger.warning(
                "[TTS] edge-tts pokus %d/%d selhal (lang=%s), čekám %ds: %s",
                attempt + 1, max_retries, lang, wait, exc,
            )
            time.sleep(wait)
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** (attempt + 1)
            logger.warning(
                "[TTS] edge-tts pokus %d/%d selhal (lang=%s), čekám %ds: %s",
                attempt + 1, max_retries, lang, wait, exc,
            )
            time.sleep(wait)
    raise RuntimeError("unreachable")


def _generate_audio(article_id: int, lang: str = "cs"):
    """
    Běží v samostatném vlákně. Generuje MP3 pomocí Google TTS API.
    Pro jiné jazyky než CS nejprve přeloží text přes Google Translate.
    """
    try:
        NewsModel = apps.get_model("news", "News")
        article = NewsModel.objects.get(pk=article_id)

        title_plain, prefix_plain, content_plain = _article_parts_plain(article)
        body_plain = " ".join(p for p in (prefix_plain, content_plain) if p).strip()

        if not (title_plain or body_plain):
            logger.info("[TTS] Article %s lang=%s: prázdný text, nic negeneruji.", article_id, lang)
            return

        # Překlad pro ne-české jazyky
        if lang != "cs":
            title_plain = _translate_text(title_plain, lang) if title_plain else ""
            body_plain = _translate_text(body_plain, lang) if body_plain else ""
            if not (title_plain or body_plain):
                logger.warning("[TTS] Article %s lang=%s: překlad selhal, audio nevygenerováno.", article_id, lang)
                return

        field_name = "audio_file" if lang == "cs" else f"audio_file_{lang}"

        section_title, section_body = _TTS_LABELS.get(lang, ("TITLE.", "TEXT."))
        out = io.BytesIO()

        if title_plain:
            for chunk in _split_text(f"{section_title} {title_plain}"):
                out.write(_tts_chunk(chunk, lang).getvalue())

        if body_plain:
            for chunk in _split_text(f"{section_body} {body_plain}"):
                out.write(_tts_chunk(chunk, lang).getvalue())

        # Delete old file only after new audio is successfully generated —
        # avoids a window where published_audio=True but file is missing (404).
        old_audio = getattr(article, field_name)
        if old_audio:
            try:
                old_audio.delete(save=False)
            except Exception:
                pass

        out.seek(0)
        filename = f"article_{article.pk}_{lang}.mp3"
        getattr(article, field_name).save(filename, ContentFile(out.read()), save=True)
        logger.info("[TTS] Article %s lang=%s: audio uloženo jako %s", article_id, lang, filename)

    except Exception as e:
        logger.exception("[TTS] Chyba při generování audia pro Article %s lang=%s: %s", article_id, lang, e)



class News (models.Model):
    """ Class for news on this website """

    title = models.CharField(max_length=255, default="")
    slug = models.SlugField(max_length=255, unique=True, blank=True, null=True, help_text=_("Automaticky generováno z titulku pro hezké URL"))
    prefix = RichTextField(max_length=4000, default="", blank=True, null=True)
    content = RichTextField(max_length=30000, blank=True, null=True)
    tags = models.ManyToManyField(Tag)

    photo_01 = models.ImageField (upload_to = 'images/news', null=True, blank=True, default="images/news/AKBMX.jpg")
    photo_02 = models.ImageField (upload_to = 'images/news', null=True, blank=True)
    photo_03 = models.ImageField (upload_to = 'images/news', null=True, blank=True)

    time_to_read = models.IntegerField(default=0)

    view_count = models.PositiveIntegerField(default=0, db_index=True, help_text=_("Počet zhlédnutí"))

    # Přeložený obsah (generováno automaticky při uložení)
    title_en = models.CharField(max_length=255, blank=True, default="")
    title_de = models.CharField(max_length=255, blank=True, default="")
    title_sk = models.CharField(max_length=255, blank=True, default="")
    title_es = models.CharField(max_length=255, blank=True, default="")
    title_it = models.CharField(max_length=255, blank=True, default="")
    title_fr = models.CharField(max_length=255, blank=True, default="")
    title_pl = models.CharField(max_length=255, blank=True, default="")
    title_hu = models.CharField(max_length=255, blank=True, default="")
    prefix_en = models.TextField(blank=True, default="")
    prefix_de = models.TextField(blank=True, default="")
    prefix_sk = models.TextField(blank=True, default="")
    prefix_es = models.TextField(blank=True, default="")
    prefix_it = models.TextField(blank=True, default="")
    prefix_fr = models.TextField(blank=True, default="")
    prefix_pl = models.TextField(blank=True, default="")
    prefix_hu = models.TextField(blank=True, default="")
    content_en = models.TextField(blank=True, default="")
    content_de = models.TextField(blank=True, default="")
    content_sk = models.TextField(blank=True, default="")
    content_es = models.TextField(blank=True, default="")
    content_it = models.TextField(blank=True, default="")
    content_fr = models.TextField(blank=True, default="")
    content_pl = models.TextField(blank=True, default="")
    content_hu = models.TextField(blank=True, default="")

    audio_file = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_en = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_de = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_sk = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_es = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_it = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_fr = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_pl = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_hu = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_hash = models.CharField(max_length=64, blank=True, default="")
    published_audio = models.BooleanField(default=False, help_text=_("Audio zveřejněno"))

    on_homepage = models.BooleanField(default=False)
    published = models.BooleanField(default=False, help_text=_("Článek zveřejněn"))
    publish_in_app = models.BooleanField(default=False, help_text=_("Zveřejnit v mobilní aplikaci"))

    created_date = models.DateTimeField(editable=True, auto_now_add=True, null=True, blank=True)
    created = models.ForeignKey(Account, on_delete = models.SET_NULL, null=True, blank = True)

    publish_date = models.DateField(default=datetime.date.today)

    def __str__(self):
        return self.title

    @property
    def photo_01_url(self):
        try:
            return self.photo_01.url if self.photo_01 else ""
        except (ValueError, OSError):
            return ""

    @property
    def audio_file_url(self):
        try:
            return self.audio_file.url if self.audio_file else ""
        except (ValueError, OSError):
            return ""

    def get_absolute_url(self):
        return reverse("news:news-detail", kwargs={"slug": self.slug or self.pk})

    def increment_views(self):
        # atomicky, bez race condition:
        News.objects.filter(pk=self.pk).update(view_count=F('view_count') + 1)
        self.refresh_from_db(fields=['view_count'])

    @staticmethod
    def sum_of_news():
        """ fukce vrací hodnotu všech zveřejněných článků """
        return News.objects.filter(published=True).count()

    @property
    def audio_duration_estimate(self):
        """Odhad délky audia v minutách pro UI."""
        title, prefix, content = _article_parts_plain(self)
        total_chars = len(title) + len(prefix) + len(content)
        return max(1, round(total_chars / 900)) # průměrně 900 znaků za minutu

    def save(self, *args, **kwargs):
        self.prefix = sanitize_rich_html(self.prefix)
        self.content = sanitize_rich_html(self.content)

        if not self.slug and self.title:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            # Zajistíme unikátnost slugu, pokud už existuje
            while News.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        # Hash z očištěného textu (bez HTML/script/style) – porovnáváme to, co TTS skutečně čte
        joined = _article_text_plain(self)
        new_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest() if joined else ""

        creating = self.pk is None
        old_hash = self.audio_hash
        # Stará hodnota published_audio zachycená v pre_save signálu
        old_published_audio = getattr(self, "_old_published_audio", self.published_audio)
        # Ulož nový hash do instance před uložením do DB
        self.audio_hash = new_hash

        super().save(*args, **kwargs)

        # transaction.on_commit zajistí, že se thread spustí až ve chvíli,
        # kdy jsou data bezpečně v databázi (prevence Race Condition).
        old_published = getattr(self, "_old_published", self.published)
        old_publish_in_app = getattr(self, "_old_publish_in_app", self.publish_in_app)

        def _enqueue():
            from news.tasks import delete_audio_task, send_push_task
            if not self.published_audio:
                # audio vypnuto — smaž soubory pokud byl přechod True → False
                if old_published_audio:
                    logger.info("[TTS] Article %s: published_audio=False, mažu audio soubory.", self.pk)
                    delete_audio_task.delay(self.pk)
            elif self.published:
                audio_newly_enabled = not old_published_audio
                should_generate = creating or (old_hash != new_hash) or (not self.audio_file) or audio_newly_enabled
                if should_generate:
                    logger.info(
                        "[TTS] Enqueue article %s (creating=%s, hash_changed=%s, audio_enabled=%s)",
                        self.pk, creating, old_hash != new_hash, audio_newly_enabled,
                    )
                    enqueue_article_tts(self.pk)
                    enqueue_article_translation(self.pk)

            # Push notifikace — odešli při prvním publikování do app
            if self.published and self.publish_in_app:
                just_published = not old_published and self.published
                just_enabled_in_app = not old_publish_in_app and self.publish_in_app
                if creating or just_published or just_enabled_in_app:
                    send_push_task.delay(self.pk)

        transaction.on_commit(_enqueue)

    class Meta:
        verbose_name = _("Článek")
        verbose_name_plural = _('Články')

# nastavení time_to_read při ukládání článku
@receiver(pre_save, sender=News)
def set_time_to_read(sender, instance, *args, **kwargs):
    clean = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", (instance.content or ""), flags=re.IGNORECASE)
    clean = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", clean, flags=re.IGNORECASE)
    world_list = (" ".join(strip_tags(clean).split())).split()
    number_of_words = len(world_list)
    time_to_read = int(number_of_words / 200)
    if time_to_read < 1:
        time_to_read = 1
    instance.time_to_read = time_to_read

# Zachytí staré hodnoty před uložením, aby save() věděl o přechodech stavů
@receiver(pre_save, sender=News)
def capture_old_published_audio(sender, instance, **kwargs):
    if instance.pk:
        row = (
            News.objects.filter(pk=instance.pk)
            .values("published_audio", "published", "publish_in_app")
            .first()
        )
        if row:
            instance._old_published_audio = row["published_audio"]
            instance._old_published = row["published"]
            instance._old_publish_in_app = row["publish_in_app"]
        else:
            instance._old_published_audio = False
            instance._old_published = False
            instance._old_publish_in_app = False
    else:
        instance._old_published_audio = False
        instance._old_published = False
        instance._old_publish_in_app = False


# vymazání staré fotky z disku při její změně
@receiver(pre_save, sender=News)
def delete_photo_on_change_extension(sender, instance, *args, **kwargs):
    if instance.pk:
        try:
            old = News.objects.get(pk=instance.pk)
            old_photo_01 = old.photo_01
            old_photo_02 = old.photo_02
            old_photo_03 = old.photo_03
        except News.DoesNotExist:
            return
        else:
            new_photo_01 = instance.photo_01
            new_photo_02 = instance.photo_02
            new_photo_03 = instance.photo_03
            old_photo_01_url = ""
            new_photo_01_url = ""
            old_photo_02_url = ""
            new_photo_02_url = ""
            old_photo_03_url = ""
            new_photo_03_url = ""
            try:
                old_photo_01_url = old_photo_01.url if old_photo_01 else ""
            except (ValueError, OSError):
                old_photo_01_url = ""
            try:
                new_photo_01_url = new_photo_01.url if new_photo_01 else ""
            except (ValueError, OSError):
                new_photo_01_url = ""
            try:
                old_photo_02_url = old_photo_02.url if old_photo_02 else ""
            except (ValueError, OSError):
                old_photo_02_url = ""
            try:
                new_photo_02_url = new_photo_02.url if new_photo_02 else ""
            except (ValueError, OSError):
                new_photo_02_url = ""
            try:
                old_photo_03_url = old_photo_03.url if old_photo_03 else ""
            except (ValueError, OSError):
                old_photo_03_url = ""
            try:
                new_photo_03_url = new_photo_03.url if new_photo_03 else ""
            except (ValueError, OSError):
                new_photo_03_url = ""

            if old_photo_01_url and old_photo_01_url != new_photo_01_url:
                old_photo_01.delete(save=False)
            if old_photo_02_url and old_photo_02_url != new_photo_02_url:
                old_photo_02.delete(save=False)
            if old_photo_03_url and old_photo_03_url != new_photo_03_url:
                old_photo_03.delete(save=False)

class DocumentTag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption
    
    class Meta:
        verbose_name = _("Typ dokumentu")
        verbose_name_plural = _('Typ dokumentů')

class Downloads(models.Model):
    """ Model for downloads section """
    title = models.CharField(max_length=255)
    description = RichTextField(max_length=10000, blank=True, null=True)
    tags=models.ManyToManyField(DocumentTag)
    path = models.FileField(upload_to="documents", blank=True, null=True)
    published = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True, null=True)
    downloads_count = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.description = sanitize_rich_html(self.description)
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = _("Ke stažení")
        verbose_name_plural = _('Ke stažení')
