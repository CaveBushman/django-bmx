
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
from gtts import gTTS
import logging
from concurrent.futures import ThreadPoolExecutor
import atexit
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
_AUDIO_LANGS = ("en", "de", "sk", "es", "it", "fr")

# Označení sekcí pro TTS – v každém jazyce
_TTS_LABELS = {
    "cs": ("NADPIS.", "TEXT."),
    "en": ("TITLE.", "TEXT."),
    "de": ("ÜBERSCHRIFT.", "TEXT."),
    "sk": ("NADPIS.", "TEXT."),
    "es": ("TÍTULO.", "TEXTO."),
    "it": ("TITOLO.", "TESTO."),
    "fr": ("TITRE.", "TEXTE."),
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

# POZNÁMKA PRO PRODUKCI:
# Používáme ThreadPoolExecutor pro jednoduché asynchronní zpracování TTS.
# Pro high-traffic aplikaci ("World Class") zvážit migraci na Celery/Redis,
# aby se úlohy neztratily při restartu serveru a lépe se škálovaly.
_EXECUTOR = ThreadPoolExecutor(max_workers=2)
atexit.register(_EXECUTOR.shutdown, wait=False)

def enqueue_article_tts(article_id: int):
    # CS audio
    _EXECUTOR.submit(_generate_audio, article_id, "cs")
    # Přeložená audio pro ostatní jazyky
    for lang in _AUDIO_LANGS:
        _EXECUTOR.submit(_generate_audio, article_id, lang)


def _translate_text(text: str, target_lang: str) -> str:
    """Přeloží text z češtiny do cílového jazyka (Google Translate, bez API klíče)."""
    if not text.strip():
        return text
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
            logger.warning("[TTS] Překlad selhal lang=%s: %s", target_lang, exc)
            return ""  # prázdný string = přeskočit generování
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

def _gtts_chunk(text: str, lang: str, max_retries: int = 4) -> io.BytesIO:
    """Calls gTTS with exponential backoff on 429 / network errors."""
    for attempt in range(max_retries):
        try:
            buf = io.BytesIO()
            gTTS(text=text, lang=lang).write_to_fp(buf)
            return buf
        except Exception as exc:
            if attempt == max_retries - 1:
                raise
            wait = 2 ** (attempt + 2)  # 4, 8, 16 s
            logger.warning(
                "[TTS] gTTS pokus %d/%d selhal (lang=%s), čekám %ds: %s",
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

        # Pole na modelu: cs → audio_file, ostatní → audio_file_en apod.
        field_name = "audio_file" if lang == "cs" else f"audio_file_{lang}"
        old_audio = getattr(article, field_name)
        if old_audio:
            try:
                old_audio.delete(save=False)
            except Exception:
                pass

        section_title, section_body = _TTS_LABELS.get(lang, ("TITLE.", "TEXT."))
        out = io.BytesIO()

        if title_plain:
            for chunk in _split_text(f"{section_title} {title_plain}"):
                out.write(_gtts_chunk(chunk, lang).getvalue())
                time.sleep(1.5)

        if body_plain:
            for chunk in _split_text(f"{section_body} {body_plain}"):
                out.write(_gtts_chunk(chunk, lang).getvalue())
                time.sleep(1.5)

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

    audio_file = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_en = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_de = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_sk = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_es = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_it = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_file_fr = models.FileField(upload_to="audio/news/", blank=True, null=True)
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
        # Ulož nový hash do instance před uložením do DB
        self.audio_hash = new_hash

        super().save(*args, **kwargs)

        # transaction.on_commit zajistí, že se thread spustí až ve chvíli,
        # kdy jsou data bezpečně v databázi (prevence Race Condition).
        def _enqueue():
            if not self.published:
                return
            should_generate = creating or (old_hash != new_hash) or (not self.audio_file)
            if should_generate:
                logger.info("[TTS] Enqueue article %s (creating=%s, hash_changed=%s)", self.pk, creating, old_hash != new_hash)
                enqueue_article_tts(self.pk)

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
