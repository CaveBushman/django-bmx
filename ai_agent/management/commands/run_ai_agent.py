"""
Management command: run_ai_agent

Zpracuje čekající AgentTask záznamy nebo spustí nový úkol přímo.

Použití:
  # Zpracovat všechny čekající úkoly
  python manage.py run_ai_agent

  # Zpracovat konkrétní úkol (dle ID)
  python manage.py run_ai_agent --task-id 42

  # Vytvořit a spustit shrnutí závodu
  python manage.py run_ai_agent --type race_summary --event-id 5

  # Vytvořit a spustit analýzu závodníka
  python manage.py run_ai_agent --type rider_analysis --rider-id 123 --year 2025

  # Vytvořit a spustit sezónní zprávu
  python manage.py run_ai_agent --type season_report --year 2025

  # Vlastní prompt
  python manage.py run_ai_agent --type custom --prompt "Napiš krátký článek o BMX sportu."

  # Jen zkontrolovat dostupnost LLM serveru
  python manage.py run_ai_agent --check
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from ai_agent.models import AgentTask
from ai_agent.services.llm_client import LLMClient
from ai_agent.services.tasks import execute_task

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Spustí AI agenta – zpracuje čekající úkoly nebo vytvoří nový"

    def add_arguments(self, parser):
        parser.add_argument("--task-id", type=int, help="ID konkrétního AgentTask záznamu")
        parser.add_argument(
            "--type",
            choices=[t.value for t in AgentTask.TaskType],
            help="Typ nového úkolu",
        )
        parser.add_argument("--event-id", type=int, help="ID závodu (pro race_summary)")
        parser.add_argument("--rider-id", type=int, help="ID závodníka (pro rider_analysis)")
        parser.add_argument("--year", type=int, help="Rok sezóny")
        parser.add_argument("--prompt", type=str, help="Text promptu (pro custom)")
        parser.add_argument("--system-prompt", type=str, help="Přepsat systémový prompt (pro custom)")
        parser.add_argument("--check", action="store_true", help="Zkontrolovat dostupnost LLM serveru")

    def handle(self, *args, **options):
        if options["check"]:
            self._check_server()
            return

        if options["type"]:
            task = self._create_task(options)
            self._run_task(task)
        elif options["task_id"]:
            try:
                task = AgentTask.objects.get(pk=options["task_id"])
            except AgentTask.DoesNotExist:
                raise CommandError(f"Úkol #{options['task_id']} neexistuje")
            self._run_task(task)
        else:
            self._run_pending()

    # ------------------------------------------------------------------

    def _check_server(self):
        client = LLMClient()
        if client.is_available():
            self.stdout.write(
                self.style.SUCCESS(f"✓ LLM server dostupný: {client.base_url} | model: {client.model}")
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"✗ LLM server nedostupný: {client.base_url}")
            )

    def _create_task(self, options: dict) -> AgentTask:
        task_type = options["type"]
        payload: dict = {}

        if task_type == AgentTask.TaskType.RACE_SUMMARY:
            if not options.get("event_id"):
                raise CommandError("Pro race_summary zadejte --event-id")
            payload["event_id"] = options["event_id"]

        elif task_type == AgentTask.TaskType.RIDER_ANALYSIS:
            if not options.get("rider_id"):
                raise CommandError("Pro rider_analysis zadejte --rider-id")
            payload["rider_id"] = options["rider_id"]
            if options.get("year"):
                payload["year"] = options["year"]

        elif task_type == AgentTask.TaskType.SEASON_REPORT:
            if options.get("year"):
                payload["year"] = options["year"]

        elif task_type == AgentTask.TaskType.CUSTOM:
            if not options.get("prompt"):
                raise CommandError("Pro custom zadejte --prompt")
            payload["prompt"] = options["prompt"]
            if options.get("system_prompt"):
                payload["system_prompt"] = options["system_prompt"]

        task = AgentTask.objects.create(task_type=task_type, payload=payload)
        self.stdout.write(f"Vytvořen úkol #{task.pk}: {task.get_task_type_display()}")
        return task

    def _run_task(self, task: AgentTask):
        self.stdout.write(f"Spouštím úkol #{task.pk}: {task.get_task_type_display()} …")
        try:
            result = execute_task(task)
            self.stdout.write(self.style.SUCCESS(f"\n=== VÝSLEDEK ===\n{result}\n"))
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"Úkol #{task.pk} selhal: {exc}"))
            raise CommandError(str(exc))

    def _reset_stuck(self):
        from datetime import timedelta
        from django.utils import timezone

        cutoff = timezone.now() - timedelta(minutes=30)
        stuck = AgentTask.objects.filter(
            status=AgentTask.Status.RUNNING,
            started_at__lt=cutoff,
        )
        count = stuck.update(
            status=AgentTask.Status.PENDING,
            started_at=None,
            error="Reset: úkol byl zaseknutý (running > 30 min)",
        )
        if count:
            self.stdout.write(self.style.WARNING(f"Resetováno {count} zaseknutých úkol(ů) → pending."))

    def _run_pending(self):
        self._reset_stuck()

        pending = AgentTask.objects.filter(status=AgentTask.Status.PENDING)
        count = pending.count()
        if count == 0:
            self.stdout.write("Žádné čekající úkoly.")
            return

        self.stdout.write(f"Zpracovávám {count} čekající úkol(y) …")
        errors = 0
        for task in pending:
            try:
                self._run_task(task)
            except CommandError:
                errors += 1

        if errors:
            self.stdout.write(self.style.WARNING(f"Dokončeno. {errors} úkol(ů) selhalo."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Všechny úkoly úspěšně zpracovány."))
