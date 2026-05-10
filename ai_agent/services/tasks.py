"""
Implementace konkrétních AI úkolů pro BMX web.
Každá funkce dostane payload ze záznamu AgentTask,
sestaví prompt, zavolá LLM a vrátí textový výstup.
"""
import logging

from django.utils import timezone

from ai_agent.models import AgentLog, AgentTask
from ai_agent.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Jsi sportovní analytik a redaktor webu Českého BMX. "
    "Píšeš stručné, věcné texty v češtině pro závodníky, trenéry a fanoušky. "
    "Nepoužívej nadměrně superlativy. Drž se faktů z dat, která dostaneš."
)

# Maximální počet řádků výsledků posílaných do promptu.
# Chrání před příliš velkým kontextem u závodů s mnoha závodníky.
_MAX_RESULTS_IN_PROMPT = 200


# ---------------------------------------------------------------------------
# Shrnutí závodu
# ---------------------------------------------------------------------------

def run_race_summary(task: AgentTask, client: LLMClient) -> str:
    """
    payload očekává:
      event_id: int  – ID záznamu Event
    """
    from event.models import Event, Result

    event_id = int(task.payload.get("event_id") or 0)
    if not event_id:
        raise ValueError("Payload musí obsahovat event_id (celé číslo)")

    event = Event.objects.get(pk=event_id)
    results = list(
        Result.objects.filter(race_id=event.race_id)
        .order_by("category", "place")
        .values("first_name", "last_name", "category", "place", "club")
        [:_MAX_RESULTS_IN_PROMPT]
    )

    if not results:
        raise ValueError(f"Pro závod {event} nejsou výsledky")

    lines = [f"Závod: {event.name}", f"Datum: {event.date}", f"Typ: {event.type_for_ranking}", ""]
    current_cat = None
    for r in results:
        if r["category"] != current_cat:
            current_cat = r["category"]
            lines.append(f"\nKategorie {current_cat}:")
        lines.append(f"  {r['place']}. {r['first_name']} {r['last_name']} ({r['club'] or '–'})")

    data_text = "\n".join(lines)
    user_prompt = (
        f"Na základě následujících výsledků závodu napiš krátké tiskové shrnutí "
        f"(max. 200 slov). Vyzdvihni vítěze v klíčových kategoriích a atmosféru závodu.\n\n"
        f"{data_text}"
    )

    llm_resp = client.chat(SYSTEM_PROMPT, user_prompt)
    _save_log(task, user_prompt, llm_resp)
    return llm_resp.content


# ---------------------------------------------------------------------------
# Analýza závodníka
# ---------------------------------------------------------------------------

def run_rider_analysis(task: AgentTask, client: LLMClient) -> str:
    """
    payload očekává:
      rider_id: int  – ID záznamu Rider
      year: int      – rok sezóny (volitelné, výchozí aktuální)
    """
    from rider.models import Rider
    from event.models import Result

    rider_id = int(task.payload.get("rider_id") or 0)
    if not rider_id:
        raise ValueError("Payload musí obsahovat rider_id (celé číslo)")

    year = int(task.payload.get("year") or timezone.now().year)
    rider = Rider.objects.get(pk=rider_id)

    results = list(
        Result.objects.filter(uci_id=rider.uci_id, date__year=year)
        .order_by("date")
        .values("date", "name", "category", "place", "point")
        [:_MAX_RESULTS_IN_PROMPT]
    )

    if not results:
        raise ValueError(f"Pro závodníka {rider} v roce {year} nejsou výsledky")

    lines = [
        f"Závodník: {rider.first_name} {rider.last_name}",
        f"Kategorie: {rider.category_20 or rider.category_24 or '–'}",
        f"Klub: {rider.club or '–'}",
        f"Rok: {year}",
        "",
        "Výsledky:",
    ]
    total_points = 0
    for r in results:
        lines.append(
            f"  {r['date']} | {r['name']} | {r['category']} | "
            f"{r['place']}. místo | {r['point']} bodů"
        )
        total_points += r["point"] or 0

    lines.append(f"\nCelkem bodů: {total_points}")
    data_text = "\n".join(lines)

    user_prompt = (
        f"Analyzuj výkonnost závodníka na základě jeho výsledků ze sezóny. "
        f"Popiš trend (zlepšení/zhoršení), nejlepší a nejhorší závody "
        f"a doporuč oblasti, na které se zaměřit v tréninku (max. 150 slov).\n\n"
        f"{data_text}"
    )

    llm_resp = client.chat(SYSTEM_PROMPT, user_prompt)
    _save_log(task, user_prompt, llm_resp)
    return llm_resp.content


# ---------------------------------------------------------------------------
# Sezónní zpráva
# ---------------------------------------------------------------------------

def run_season_report(task: AgentTask, client: LLMClient) -> str:
    """
    payload očekává:
      year: int  – rok (volitelné, výchozí aktuální)
    """
    from event.models import Event, Result

    year = int(task.payload.get("year") or timezone.now().year)

    events = list(Event.objects.filter(date__year=year).order_by("date")[:50])
    if not events:
        raise ValueError(f"Pro rok {year} nejsou žádné závody")

    event_lines = []
    for ev in events:
        result_count = Result.objects.filter(race_id=ev.race_id).count()
        event_lines.append(f"  {ev.date} | {ev.name} | {ev.type_for_ranking} | {result_count} závodníků")

    total_riders = (
        Result.objects.filter(date__year=year)
        .values("uci_id")
        .distinct()
        .count()
    )

    data_text = (
        f"Sezóna {year}\n"
        f"Počet závodů: {len(events)}\n"
        f"Unikátní závodníků: {total_riders}\n\n"
        f"Přehled závodů:\n" + "\n".join(event_lines)
    )

    user_prompt = (
        f"Na základě statistik sezóny napiš shrnující zprávu (max. 250 slov) "
        f"o průběhu sezóny českého BMX. Zmiň počty závodů, účast závodníků "
        f"a celkové dojmy ze sezóny.\n\n"
        f"{data_text}"
    )

    llm_resp = client.chat(SYSTEM_PROMPT, user_prompt)
    _save_log(task, user_prompt, llm_resp)
    return llm_resp.content


# ---------------------------------------------------------------------------
# Vlastní úkol
# ---------------------------------------------------------------------------

def run_custom(task: AgentTask, client: LLMClient) -> str:
    """
    payload očekává:
      prompt: str           – uživatelský prompt
      system_prompt: str    – volitelné přepsání system promptu
    """
    user_prompt = str(task.payload.get("prompt") or "").strip()
    if not user_prompt:
        raise ValueError("Payload musí obsahovat 'prompt'")

    system = str(task.payload.get("system_prompt") or SYSTEM_PROMPT)
    llm_resp = client.chat(system, user_prompt)
    _save_log(task, user_prompt, llm_resp)
    return llm_resp.content


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

TASK_RUNNERS = {
    AgentTask.TaskType.RACE_SUMMARY: run_race_summary,
    AgentTask.TaskType.RIDER_ANALYSIS: run_rider_analysis,
    AgentTask.TaskType.SEASON_REPORT: run_season_report,
    AgentTask.TaskType.CUSTOM: run_custom,
}


def execute_task(task: AgentTask) -> str:
    """Spustí úkol a vrátí výsledný text. Aktualizuje stav záznamu."""
    runner = TASK_RUNNERS.get(task.task_type)
    if runner is None:
        raise ValueError(f"Neznámý typ úkolu: {task.task_type}")

    task.status = AgentTask.Status.RUNNING
    task.started_at = timezone.now()
    task.save(update_fields=["status", "started_at"])

    client = LLMClient()
    result = None
    try:
        result = runner(task, client)
        task.status = AgentTask.Status.DONE
        task.result = result
        task.error = ""
    except Exception as exc:
        task.status = AgentTask.Status.FAILED
        task.error = str(exc)
        logger.exception("Úkol %s selhal: %s", task.pk, exc)
        raise
    finally:
        task.finished_at = timezone.now()
        try:
            task.save(update_fields=["status", "finished_at", "result", "error"])
        except Exception as save_exc:
            logger.error("Nepodařilo se uložit stav úkolu %s: %s", task.pk, save_exc)

    return result


# ---------------------------------------------------------------------------
# Interní helper
# ---------------------------------------------------------------------------

def _save_log(task: AgentTask, prompt: str, llm_resp) -> None:
    AgentLog.objects.create(
        task=task,
        prompt=prompt,
        response=llm_resp.content,
        input_tokens=llm_resp.input_tokens,
        output_tokens=llm_resp.output_tokens,
        model_used=llm_resp.model,
        duration_ms=llm_resp.duration_ms,
    )
