from django.db import models


class AgentTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Čeká"
        RUNNING = "running", "Spouštím"
        DONE = "done", "Hotovo"
        FAILED = "failed", "Chyba"

    class TaskType(models.TextChoices):
        RACE_SUMMARY = "race_summary", "Shrnutí závodu"
        RIDER_ANALYSIS = "rider_analysis", "Analýza závodníka"
        SEASON_REPORT = "season_report", "Sezónní zpráva"
        CUSTOM = "custom", "Vlastní úkol"

    task_type = models.CharField(max_length=32, choices=TaskType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # JSON payload with task parameters (event_id, rider_id, year, prompt, …)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    result = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Úkol agenta"
        verbose_name_plural = "Úkoly agenta"

    def __str__(self):
        return f"{self.get_task_type_display()} [{self.status}] – {self.created_at:%d.%m.%Y %H:%M}"


class AgentLog(models.Model):
    task = models.ForeignKey(AgentTask, on_delete=models.CASCADE, related_name="logs")
    # Input sent to LLM
    prompt = models.TextField(blank=True)
    # Raw LLM output
    response = models.TextField(blank=True)
    # Token usage reported by the model
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    model_used = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Log agenta"
        verbose_name_plural = "Logy agenta"

    def __str__(self):
        return f"Log #{self.pk} pro úkol #{self.task_id}"
