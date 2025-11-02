
from django.db import models, transaction
from django.dispatch import receiver
from django.db.models.signals import pre_save, post_save
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
import html as html_stdlib
from django.utils.html import strip_tags

# TTS labels (bez přesné pauzy varianta)
TTS_SECTION_TITLE = "NADPIS."
TTS_SECTION_BODY = "TEXT."



# Create your models here.

class Tag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption


logger = logging.getLogger(__name__)

_EXECUTOR = ThreadPoolExecutor(max_workers=2)
atexit.register(_EXECUTOR.shutdown, wait=False)

def enqueue_article_tts(article_id: int):
    # Spustíme mimo request thread, po commitu
    _EXECUTOR.submit(_generate_audio, article_id)

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

def _generate_audio(article_id: int):
    """
    Běží ve vlákně. ŽÁDNÝ přímý import News z models.py!
    Načte model dynamicky přes apps.get_model -> žádné kruhy importů.
    """
    try:
        NewsModel = apps.get_model("news", "News")
        article = NewsModel.objects.get(pk=article_id)

        # Připrav označené sekce: NADPIS + titulek, TEXT + (prefix+content)
        title_plain, prefix_plain, content_plain = _article_parts_plain(article)
        body_plain = " ".join(p for p in (prefix_plain, content_plain) if p).strip()

        if not (title_plain or body_plain):
            logger.info("[TTS] Article %s: prázdný text, nic negeneruji.", article_id)
            return

        # Smazat staré audio, pokud existuje
        if article.audio_file:
            try:
                article.audio_file.delete(save=False)
            except Exception:
                pass

        # gTTS volá Google – server musí mít internet
        out = io.BytesIO()

        # 1) NADPIS + titulek (pokud existuje titulek)
        if title_plain:
            title_text = f"{TTS_SECTION_TITLE} {title_plain}".strip()
            for idx, chunk in enumerate(_split_text(title_text), start=1):
                buf = io.BytesIO()
                gTTS(text=chunk, lang="cs").write_to_fp(buf)
                out.write(buf.getvalue())

        # (Bez přesné pauzy – fallback varianta: žádná garantovaná 1s tichá mezera)
        # Pokud chceš přesnou pauzu, je třeba pydub+ffmpeg.

        # 2) TEXT + tělo (prefix+content)
        if body_plain:
            body_text = f"{TTS_SECTION_BODY} {body_plain}".strip()
            first = True
            for idx, chunk in enumerate(_split_text(body_text), start=1):
                buf = io.BytesIO()
                gTTS(text=chunk, lang="cs").write_to_fp(buf)
                out.write(buf.getvalue())

        out.seek(0)
        filename = f"article_{article.pk}.mp3"
        article.audio_file.save(filename, ContentFile(out.read()), save=True)
        logger.info("[TTS] Article %s: audio uloženo jako %s", article_id, filename)

    except Exception as e:
        logger.exception("[TTS] Chyba při generování audia pro Article %s: %s", article_id, e)



class News (models.Model):
    """ Class for news on this website """

    title = models.CharField(max_length=255, default="")
    prefix = RichTextField(max_length=4000, default="", blank=True, null=True)
    content = RichTextField(max_length=10000, blank=True, null=True)
    tags = models.ManyToManyField(Tag)

    photo_01 = models.ImageField (upload_to = 'images/news', null=True, blank=True, default="images/news/AKBMX.jpg")
    photo_02 = models.ImageField (upload_to = 'images/news', null=True, blank=True)
    photo_03 = models.ImageField (upload_to = 'images/news', null=True, blank=True)

    time_to_read = models.IntegerField(default=0)

    view_count = models.PositiveIntegerField(default=0, db_index=True, help_text="Počet zhlédnutí")

    audio_file = models.FileField(upload_to="audio/news/", blank=True, null=True)
    audio_hash = models.CharField(max_length=64, blank=True, default="")
    published_audio = models.BooleanField(default=False, help_text="Audio zveřejněno")

    on_homepage = models.BooleanField(default=False)
    published = models.BooleanField(default=False, help_text="Článek zveřejněn")

    created_date = models.DateTimeField(editable=True, auto_now_add=True, null=True, blank=True)
    created = models.ForeignKey(Account, on_delete = models.SET_NULL, null=True, blank = True)

    publish_date = models.DateField(default=datetime.date.today)

    def __str__(self):
        return self.title

    def increment_views(self):
        # atomicky, bez race condition:
        News.objects.filter(pk=self.pk).update(view_count=F('view_count') + 1)
        self.refresh_from_db(fields=['view_count'])

    def sum_of_news():
        """ fukce vrací hodnotu všech zveřejněných článků """
        return News.objects.filter(published = True).count()

    def save(self, *args, **kwargs):
        # Hash z očištěného textu (bez HTML/script/style) – porovnáváme to, co TTS skutečně čte
        joined = _article_text_plain(self)
        new_hash = hashlib.sha256(joined.encode("utf-8")).hexdigest() if joined else ""

        creating = self.pk is None
        old_hash = self.audio_hash
        # Ulož nový hash do instance před uložením do DB
        self.audio_hash = new_hash

        super().save(*args, **kwargs)

        def _enqueue():
            # Generuj jen pro publikované články a pokud je to nový článek,
            # změnil se obsah (hash) NEBO zatím neexistuje audio soubor (první publikace)
            if not self.published:
                return
            should_generate = creating or (old_hash != new_hash) or (not self.audio_file)
            if should_generate:
                logger.info("[TTS] Enqueue article %s (creating=%s, hash_changed=%s, has_audio=%s)", self.pk, creating, old_hash != new_hash, bool(self.audio_file))
                _EXECUTOR.submit(_generate_audio, self.pk)

        transaction.on_commit(_enqueue)

    class Meta:
        verbose_name = "Článek"
        verbose_name_plural = 'Články'

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
pre_save.connect(set_time_to_read, sender=News)

# vymazání staré fotky z disku při její změně
@receiver(pre_save, sender=News)
def delete_photo_on_change_extension(sender, instance, *args, **kwargs):
    if instance.pk:
        try:
            old_photo_01 = News.objects.get(pk=instance.pk).photo_01
            old_photo_02 = News.objects.get(pk=instance.pk).photo_02
            old_photo_03 = News.objects.get(pk=instance.pk).photo_03
        except News.DoesNotExist:
            return
        else:
            new_photo_01 = instance.photo_01
            new_photo_02 = instance.photo_02
            new_photo_03 = instance.photo_03
            if old_photo_01 and old_photo_01.url != new_photo_01.url:
                old_photo_01.delete(save=False)
            if old_photo_02 and old_photo_02.url != new_photo_02.url:
                old_photo_02.delete(save=False)
            if old_photo_03 and old_photo_03.url != new_photo_03.url:
                old_photo_03.delete(save=False)
pre_save.connect(delete_photo_on_change_extension, sender=News)

class DocumentTag(models.Model):
    caption=models.CharField(max_length=20)

    def __str__(self):
        return self.caption
    
    class Meta:
        verbose_name = "Typ dokumentu"
        verbose_name_plural = 'Typ dokumentů'

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

    class Meta:
        verbose_name = "Ke stažení"
        verbose_name_plural = 'Ke stažení'