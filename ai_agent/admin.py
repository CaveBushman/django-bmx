from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.text import Truncator

from ai_agent.models import AgentLog, AgentTask


class AgentLogInline(admin.TabularInline):
    model = AgentLog
    extra = 0
    readonly_fields = ("created_at", "model_used", "input_tokens", "output_tokens", "duration_ms", "prompt_short", "response_short")
    fields = ("created_at", "model_used", "input_tokens", "output_tokens", "duration_ms", "prompt_short", "response_short")
    can_delete = False
    show_change_link = True

    @admin.display(description="Prompt (začátek)")
    def prompt_short(self, obj):
        return Truncator(obj.prompt).chars(120)

    @admin.display(description="Odpověď (začátek)")
    def response_short(self, obj):
        return Truncator(obj.response).chars(200)


@admin.register(AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "task_type", "status_badge", "created_at", "finished_at", "duration", "result_preview")
    list_filter = ("task_type", "status")
    readonly_fields = ("created_at", "started_at", "finished_at", "status", "result", "error")
    inlines = [AgentLogInline]
    ordering = ["-created_at"]
    actions = ["run_selected", "reset_stuck"]

    @admin.display(description="Stav")
    def status_badge(self, obj):
        colors = {
            "pending": "#999",
            "running": "#2196f3",
            "done": "#4caf50",
            "failed": "#f44336",
        }
        color = colors.get(obj.status, "#999")
        return format_html(
            '<span style="color:white;background:{};padding:2px 8px;border-radius:4px">{}</span>',
            color,
            obj.get_status_display(),
        )

    @admin.display(description="Délka")
    def duration(self, obj):
        if obj.started_at and obj.finished_at:
            delta = obj.finished_at - obj.started_at
            return f"{delta.seconds}s"
        return "–"

    @admin.display(description="Výsledek")
    def result_preview(self, obj):
        if not obj.result:
            return "–"
        return Truncator(obj.result).chars(80)

    @admin.action(description="▶ Spustit vybrané úkoly")
    def run_selected(self, request, queryset):
        from ai_agent.services.tasks import execute_task

        ok = failed = 0
        for task in queryset.filter(status__in=[AgentTask.Status.PENDING, AgentTask.Status.FAILED]):
            try:
                execute_task(task)
                ok += 1
            except Exception as exc:
                failed += 1
                self.message_user(request, f"Úkol #{task.pk} selhal: {exc}", messages.ERROR)

        if ok:
            self.message_user(request, f"{ok} úkol(ů) úspěšně dokončeno.", messages.SUCCESS)
        if not ok and not failed:
            self.message_user(request, "Žádné úkoly ve stavu 'čeká' nebo 'chyba' nebyly vybrány.", messages.WARNING)

    @admin.action(description="↺ Resetovat zaseknuté úkoly (running → pending)")
    def reset_stuck(self, request, queryset):
        from django.utils import timezone
        from datetime import timedelta

        cutoff = timezone.now() - timedelta(minutes=30)
        stuck = queryset.filter(status=AgentTask.Status.RUNNING, started_at__lt=cutoff)
        count = stuck.update(status=AgentTask.Status.PENDING, started_at=None, error="Reset: úkol byl zaseknutý")
        self.message_user(request, f"Resetováno {count} zaseknutých úkol(ů).", messages.SUCCESS)


@admin.register(AgentLog)
class AgentLogAdmin(admin.ModelAdmin):
    list_display = ("id", "task", "model_used", "input_tokens", "output_tokens", "duration_ms", "created_at")
    list_filter = ("model_used",)
    readonly_fields = ("created_at", "task", "model_used", "input_tokens", "output_tokens", "duration_ms", "prompt", "response")
    ordering = ["-created_at"]
