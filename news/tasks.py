from celery import shared_task


@shared_task(bind=True, max_retries=3, default_retry_delay=60, name="news.generate_audio")
def generate_audio_task(self, article_id: int, lang: str):
    try:
        from news.models import _generate_audio
        _generate_audio(article_id, lang)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=120, name="news.translate_article")
def translate_article_task(self, article_id: int, lang: str):
    try:
        from news.models import _translate_article_content
        _translate_article_content(article_id, lang)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(name="news.delete_audio")
def delete_audio_task(article_id: int):
    from news.models import _delete_all_audio
    _delete_all_audio(article_id)


@shared_task(name="news.send_push")
def send_push_task(article_id: int):
    from news.models import _send_article_push_notification
    _send_article_push_notification(article_id)
