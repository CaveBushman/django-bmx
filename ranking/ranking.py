"""Výpočet a koordinace materializovaného rankingu.

Cache klíče fungují jako jednoduchý distribuovaný stav PENDING/RUNNING. Pokud
během výpočtu přijde další požadavek, aktuální běh se neduplikuje; po dokončení se
provede ještě jeden přepočet nad novými daty.
"""

import logging
import datetime
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rider.models import Rider

logger = logging.getLogger(__name__)
from event.models import Result, Entry, Event, EventType, SeasonSettings
import threading

RANKING_RECOUNT_PENDING_KEY = "ranking_recount_pending"
RANKING_RECOUNT_RUNNING_KEY = "ranking_recount_running"
RANKING_RECOUNT_LOCK_TIMEOUT = 60 * 60
RANKING_RECOUNT_STATUS_KEY = "ranking_recount_status"


def get_ranking_recount_status():
    status = cache.get(RANKING_RECOUNT_STATUS_KEY, {}) or {}
    return {
        "is_pending": bool(cache.get(RANKING_RECOUNT_PENDING_KEY)),
        "is_running": bool(cache.get(RANKING_RECOUNT_RUNNING_KEY)),
        "last_started_at": status.get("last_started_at"),
        "last_finished_at": status.get("last_finished_at"),
        "last_duration_seconds": status.get("last_duration_seconds"),
        "last_success": status.get("last_success"),
        "last_message": status.get("last_message"),
        "last_rider_count": status.get("last_rider_count"),
    }

def _ranking_recount_once():
    """Jeden průchod přepočtu rankingu se status updaty v cache.
    Sdílí ho daemon vlákno (SetRanking) i Celery task (recount_ranking_task)."""
    cache.delete(RANKING_RECOUNT_PENDING_KEY)
    started_at = timezone.now()
    cache.set(
        RANKING_RECOUNT_STATUS_KEY,
        {
            **(cache.get(RANKING_RECOUNT_STATUS_KEY, {}) or {}),
            "last_started_at": started_at,
            "last_message": "Přepočet rankingu právě běží.",
        },
        timeout=RANKING_RECOUNT_LOCK_TIMEOUT,
    )
    try:
        rider_count = RankingCount.set_ranking_points()
        RankPositionCount().count_ranking_position()
        logger.info("Ranking přepočítán")
        finished_at = timezone.now()
        cache.set(
            RANKING_RECOUNT_STATUS_KEY,
            {
                "last_started_at": started_at,
                "last_finished_at": finished_at,
                "last_duration_seconds": round((finished_at - started_at).total_seconds(), 2),
                "last_success": True,
                "last_message": "Poslední přepočet rankingu doběhl úspěšně.",
                "last_rider_count": rider_count,
            },
            timeout=RANKING_RECOUNT_LOCK_TIMEOUT,
        )
    except Exception:
        logger.exception("Přepočet rankingu selhal")
        finished_at = timezone.now()
        cache.set(
            RANKING_RECOUNT_STATUS_KEY,
            {
                "last_started_at": started_at,
                "last_finished_at": finished_at,
                "last_duration_seconds": round((finished_at - started_at).total_seconds(), 2),
                "last_success": False,
                "last_message": "Poslední přepočet rankingu skončil chybou. Zkontroluj log.",
                "last_rider_count": None,
            },
            timeout=RANKING_RECOUNT_LOCK_TIMEOUT,
        )


def _ranking_recount_should_rerun():
    """Finally logika po jednom průchodu: vrátí True, pokud během přepočtu
    přišla další změna a má se spustit znovu (lock RUNNING zůstává držený)."""
    if cache.get(RANKING_RECOUNT_PENDING_KEY):
        logger.info("Během přepočtu přišla další změna, ranking se přepočítá znovu.")
        return True

    cache.delete(RANKING_RECOUNT_RUNNING_KEY)
    if cache.get(RANKING_RECOUNT_PENDING_KEY):
        if cache.add(RANKING_RECOUNT_RUNNING_KEY, True, timeout=RANKING_RECOUNT_LOCK_TIMEOUT):
            logger.info("Po uvolnění locku je naplánovaný další přepočet rankingu.")
            return True
    return False


class SetRanking (threading.Thread):
    """Daemon vlákno pro přepočet rankingu (fallback, když neběží Celery)."""

    def __init__(self):
        threading.Thread.__init__(self)
        self.daemon = True

    def run(self):
        while True:
            _ranking_recount_once()
            if _ranking_recount_should_rerun():
                continue
            break


def schedule_ranking_recount():
    """Naplánuje přepočet rankingu po dokončení aktuální DB transakce.
    Při dostupném Celery brokeru použije task, jinak spadne zpět na vlákno."""
    cache.set(RANKING_RECOUNT_PENDING_KEY, True, timeout=RANKING_RECOUNT_LOCK_TIMEOUT)
    cache.set(
        RANKING_RECOUNT_STATUS_KEY,
        {
            **(cache.get(RANKING_RECOUNT_STATUS_KEY, {}) or {}),
            "last_message": "Čeká naplánovaný přepočet rankingu.",
        },
        timeout=RANKING_RECOUNT_LOCK_TIMEOUT,
    )

    def _start():
        if not cache.add(RANKING_RECOUNT_RUNNING_KEY, True, timeout=RANKING_RECOUNT_LOCK_TIMEOUT):
            logger.info("Přepočet rankingu už běží, další průchod je zařazen do fronty.")
            return

        from bmx.background import should_use_celery

        if should_use_celery():
            from ranking.tasks import recount_ranking_task
            recount_ranking_task.delay()
            logger.info("Přepočet rankingu zařazen do Celery.")
        else:
            SetRanking().start()
            logger.info("Přepočet rankingu byl spuštěn na pozadí (vlákno).")

    transaction.on_commit(_start)

# Bodované skupiny závodů: (typy závodů, atribut se započítaným počtem závodů).
# MČR jednotlivců se počítá vždy jen jedno.
RANKING_BUCKETS = (
    ((EventType.MCR_JEDNOTLIVCU,), None),
    ((EventType.CESKY_POHAR,), "best_cup"),
    ((EventType.CESKA_LIGA, EventType.MORAVSKA_LIGA, EventType.VOLNY_ZAVOD), "best_league"),
)
_ID_CHUNK = 500


def _ranked_riders():
    return Rider.objects.filter(is_active=True, is_approved=True)


def _update_in_chunks(ids, **values):
    ids = list(ids)
    for start in range(0, len(ids), _ID_CHUNK):
        Result.objects.filter(id__in=ids[start:start + _ID_CHUNK]).update(**values)


class RankingCount:
    """Výpočet rankingových bodů a označení započítaných výsledků (marked_20/24)."""

    @staticmethod
    def _bucket_limits():
        year = datetime.date.today().year
        season = SeasonSettings.objects.filter(year=year).first()
        if season is None:
            logger.warning("Chybí SeasonSettings pro rok %s, ranking použije 0 započítaných závodů.", year)
        return [
            (event_types, 1 if attr is None else (getattr(season, attr) if season else 0))
            for event_types, attr in RANKING_BUCKETS
        ]

    @staticmethod
    def set_ranking_points():
        """Přepočte body všech aktivních schválených jezdců.

        Jezdec dostane za každou skupinu závodů součet nejlepších N výsledků
        (podle bodů, při shodě novější) za posledních 365 dní, zvlášť pro 20"
        a 24". Vše se načte jedním dotazem a zapíše hromadně v jedné transakci,
        takže čtenáři nikdy nevidí napůl vynulované body.
        """
        limits = RankingCount._bucket_limits()
        bucket_of = {
            event_type: index
            for index, (event_types, _limit) in enumerate(limits)
            for event_type in event_types
        }

        riders = list(_ranked_riders().only("id", "uci_id", "is_20", "is_24"))
        allowed = {
            True: {r.uci_id for r in riders if r.is_20},
            False: {r.uci_id for r in riders if r.is_24},
        }

        candidates = {}
        rows = Result.objects.filter(
            rider_id__in=_ranked_riders().values("uci_id"),
            event_type__in=list(bucket_of),
            points__gt=0,
            date__gte=timezone.localdate() - timedelta(days=365),
        ).values_list("id", "rider_id", "event_type", "is_20", "points", "date")
        for result_id, uci_id, event_type, is_20, points, date in rows:
            if uci_id in allowed[is_20]:
                key = (uci_id, is_20, bucket_of[event_type])
                candidates.setdefault(key, []).append((points, date, result_id))

        points = {True: {}, False: {}}
        marked = {True: [], False: []}
        for (uci_id, is_20, bucket), results in candidates.items():
            results.sort(key=lambda r: (-r[0], -r[1].toordinal(), r[2]))
            selected = results[:limits[bucket][1]]
            points[is_20][uci_id] = points[is_20].get(uci_id, 0) + sum(r[0] for r in selected)
            marked[is_20].extend(r[2] for r in selected)

        for rider in riders:
            rider.points_20 = points[True].get(rider.uci_id, 0)
            rider.points_24 = points[False].get(rider.uci_id, 0)

        with transaction.atomic():
            # Značky se nulují jen jezdcům, kterým se daná kategorie počítá.
            Result.objects.filter(
                marked_20=True, rider_id__in=_ranked_riders().filter(is_20=True).values("uci_id")
            ).update(marked_20=False)
            Result.objects.filter(
                marked_24=True, rider_id__in=_ranked_riders().filter(is_24=True).values("uci_id")
            ).update(marked_24=False)
            _update_in_chunks(marked[True], marked_20=True)
            _update_in_chunks(marked[False], marked_24=True)
            Rider.objects.bulk_update(riders, ["points_20", "points_24"], batch_size=_ID_CHUNK)
        return len(riders)


class RankPositionCount:
    """Pořadí jezdců v rankingu v rámci jejich kategorie."""

    @staticmethod
    def _positions(riders, points_attr):
        """Vrátí [(jezdec, pořadí)]; jezdci se shodnými body sdílí rozsah, např. "5 - 7"."""
        ordered = sorted(riders, key=lambda r: -getattr(r, points_attr))
        positions = []
        start = 0
        while start < len(ordered):
            end = start
            while end + 1 < len(ordered) and getattr(ordered[end + 1], points_attr) == getattr(ordered[start], points_attr):
                end += 1
            label = str(start + 1) if end == start else f"{start + 1} - {end + 1}"
            positions.extend((rider, label) for rider in ordered[start:end + 1])
            start = end + 1
        return positions

    def count_ranking_position(self):
        """Přepočte pořadí 20" i 24" pro všechny kategorie a zapíše jen změny."""
        riders = list(
            _ranked_riders().only(
                "id", "is_20", "is_24", "class_20", "class_24",
                "points_20", "points_24", "ranking_20", "ranking_24",
            )
        )
        changed = {}
        for is_20_flag, class_attr, points_attr, ranking_attr in (
            ("is_20", "class_20", "points_20", "ranking_20"),
            ("is_24", "class_24", "points_24", "ranking_24"),
        ):
            by_category = {}
            for rider in riders:
                if getattr(rider, is_20_flag) and getattr(rider, points_attr) != 0:
                    by_category.setdefault(getattr(rider, class_attr), []).append(rider)
            labels = {}
            for category_riders in by_category.values():
                labels.update(
                    (rider.id, label) for rider, label in self._positions(category_riders, points_attr)
                )
            # Jezdec bez bodů v rankingu není — nesmí mu zůstat staré pořadí.
            for rider in riders:
                label = labels.get(rider.id)
                if getattr(rider, ranking_attr) != label:
                    setattr(rider, ranking_attr, label)
                    changed[rider.id] = rider

        if changed:
            with transaction.atomic():
                Rider.objects.bulk_update(
                    list(changed.values()), ["ranking_20", "ranking_24"], batch_size=_ID_CHUNK
                )
        logger.info("Ranking všech jezdců přepočítán")


class Categories:
    """ Return set of classes """

    @staticmethod
    def get_categories(event=0):
        # events 0 is categories for ranking view
        if event == 0:
            clean_categories20 = sorted(
                Rider.objects.filter(is_active=True, is_approved=True, is_20=True)
                .exclude(class_20="")
                .order_by('class_20')
                .values_list('class_20', flat=True)
                .distinct()
            )
            clean_categories24 = sorted(
                f"Cruiser {c}" for c in
                Rider.objects.filter(is_active=True, is_approved=True, is_24=True)
                .exclude(class_24="")
                .order_by('class_24')
                .values_list('class_24', flat=True)
                .distinct()
            )
        # categories for entries
        else:
            current_event = Event.objects.get(pk=event)
            entries = Entry.objects.filter(event=current_event, payment_complete=True)
            logger.debug(f"Přihlášky k závodu: {entries}")

            clean_categories20 = sorted(
                entries.filter(is_20=True)
                .exclude(class_20="")
                .order_by('class_20')
                .values_list('class_20', flat=True)
                .distinct()
            )
            clean_categories24 = sorted(
                entries.filter(is_24=True)
                .exclude(class_24="")
                .order_by('class_24')
                .values_list('class_24', flat=True)
                .distinct()
            )

        return list(clean_categories20) + list(clean_categories24)
