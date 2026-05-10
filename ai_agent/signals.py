import logging

from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver

from ai_agent.models import AgentLog, AgentTask

logger = logging.getLogger(__name__)


@receiver(post_save, sender=AgentTask)
def notify_admin_on_completion(sender, instance: AgentTask, **kwargs):
    """Po přechodu úkolu do stavu done nebo failed pošle e-mail superuserům."""
    from django.conf import settings as _settings
    if not getattr(_settings, "AI_AGENT_ENABLED", False):
        return

    if instance.status not in (AgentTask.Status.DONE, AgentTask.Status.FAILED):
        return

    # Vyhnout se opakovanému odesílání při dalších save() (např. update_fields)
    # – zkontrolujeme, zda má úkol finished_at (nastavuje se právě jednou)
    if not instance.finished_at:
        return

    allowed = getattr(_settings, "AI_AGENT_NOTIFY_EMAILS", [])
    if not allowed:
        return

    from accounts.models import Account
    recipients = list(
        Account.objects.filter(is_superuser=True, is_active=True, email__in=allowed)
        .values_list("email", flat=True)
    )
    if not recipients:
        return

    if instance.status == AgentTask.Status.DONE:
        log = AgentLog.objects.filter(task=instance).order_by("-created_at").first()
        result_text = log.response if log else "(výsledek není k dispozici)"
        subject = f"[AI Agent] ✓ {instance.get_task_type_display()} dokončeno"
        body = (
            f"Úkol #{instance.pk} – {instance.get_task_type_display()}\n"
            f"Dokončeno: {instance.finished_at:%d.%m.%Y %H:%M}\n"
            f"Model: {log.model_used if log else '–'} | "
            f"Tokeny: {log.input_tokens + log.output_tokens if log else '–'}\n"
            f"\n--- VÝSLEDEK ---\n\n{result_text}"
        )
    else:
        subject = f"[AI Agent] ✗ {instance.get_task_type_display()} selhalo"
        error_excerpt = (instance.error[:500] + "…") if len(instance.error) > 500 else instance.error
        body = (
            f"Úkol #{instance.pk} – {instance.get_task_type_display()}\n"
            f"Selhal: {instance.finished_at:%d.%m.%Y %H:%M}\n"
            f"Chyba: {error_excerpt}"
        )

    try:
        send_mail(subject, body, None, recipients, fail_silently=False)
        logger.info("AI agent: e-mail odeslán na %s", recipients)
    except Exception as exc:
        logger.error("AI agent: nepodařilo se odeslat e-mail: %s", exc)
