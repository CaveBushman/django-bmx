import logging
import datetime
from datetime import timedelta
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rider.models import Rider

logger = logging.getLogger(__name__)
from event.models import Result, Entry, Event, EventType, SeasonSettings
from django.db.models import Q
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

def sort_20(self, classes):
    CLASS_ORDER20 = {
    'Boys 6', 'Boys 7', 'Boys 8', 'Boys 9', 'Boys 10', 'Boys 11', 'Boys 12', 'Boys 13', 'Boys 14', 'Boys 15', 'Boys 16', 'Men 17-24', 'Men 25-29', 'Men 30-34', 'Men 35 and over', 'Girls 7', 'Girls 8', 'Girls 9', 'Girls 10', 'Girls 11', 'Girls 12',
    'Girls 12', 'Girls 13', 'Girls 14', 'Girls 15', 'Girls 16', 'Women 17-24', 'Women 25 and over', 'Men Junior', 'Men Under 23', 'Men Elite', 'Women Junior'
    'Women Under 23', 'Women Elite'}
    pass


def sort_24(self, classes):
    CLASS_ORDER_24 = {'Boys 12 and under', 'Boys 13 and 14', 'Boys 15 and 16', 'Men 17-24', 'Men 25-39', 'Men 30-34', 'Men 35-39', 'Men 40-44', 'Men 45-49', 'Men 50 and over', 'Girls 12 and under', 'Girls 13-16', 'Women 17-29', 'Women 30-99', 'Women 40 and over'}
    pass


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

class RankingCount:
    """ Class for rankings count"""

    def __init__(self, uci_id):
        self.uci_id = uci_id
        self.points_20:int = 0
        self.points_24:int = 0
        self.rider = None
        year = datetime.date.today().year
        season = SeasonSettings.objects.filter(year=year).first()
        if season is None:
            logger.warning("Chybí SeasonSettings pro rok %s, ranking použije 0 započítaných závodů.", year)
            self.CZECH_CUP = 0
            self.LIGA = 0
        else:
            self.CZECH_CUP = season.best_cup
            self.LIGA = season.best_league

    def resolve_category(self):
        self.rider = Rider.objects.select_related('club').get(uci_id=self.uci_id)

    def set_points(self, event_types, max_races, is_20):
        """ General method for setting points based on event type """
        all_results = Result.objects.filter(
            event_type__in=event_types,
            is_20=is_20,
            date__gte=datetime.datetime.now() - timedelta(days=365),
            rider_id=self.uci_id,
        )
        results = (
            all_results.filter(points__gt=0)
            .order_by('-points', '-date')
        )

        # Reset previous markings
        all_results.update(marked_20=False) if is_20 else all_results.update(marked_24=False)

        # Get top races
        num_race = min(results.count(), max_races)
        selected_results = results[:num_race]

        # Update selected results
        if is_20:
            self.points_20 += sum(result.points for result in selected_results)
            results.filter(id__in=[r.id for r in selected_results]).update(marked_20=True)
        else:
            self.points_24 += sum(result.points for result in selected_results)
            results.filter(id__in=[r.id for r in selected_results]).update(marked_24=True)

    def count_points(self):
        self.resolve_category()
        if self.rider.is_20:
            Result.objects.filter(rider_id=self.uci_id).update(marked_20=False)
            self.set_points([EventType.MCR_JEDNOTLIVCU], 1, is_20=1)
            self.set_points([EventType.CESKY_POHAR], self.CZECH_CUP, is_20=1)
            self.set_points([EventType.CESKA_LIGA, EventType.MORAVSKA_LIGA, EventType.VOLNY_ZAVOD], self.LIGA, is_20=1)

        if self.rider.is_24:
            Result.objects.filter(rider_id=self.uci_id).update(marked_24=False)
            self.set_points([EventType.MCR_JEDNOTLIVCU], 1, is_20=0)
            self.set_points([EventType.CESKY_POHAR], self.CZECH_CUP, is_20=0)
            self.set_points([EventType.CESKA_LIGA, EventType.MORAVSKA_LIGA, EventType.VOLNY_ZAVOD], self.LIGA, is_20=0)

    @staticmethod
    def set_ranking_points():
        """ Methods for setting ranking points for all riders """
        rider_count = 0
        for rider in Rider.objects.filter(is_active=True, is_approved=True).iterator():
            ranking = RankingCount(rider.uci_id)
            ranking.count_points()
            Rider.objects.filter(uci_id=rider.uci_id).update(
                points_20=ranking.points_20,
                points_24=ranking.points_24
            )
            rider_count += 1
        return rider_count

class RankPositionCount:
    """ Class for counting ranking positions of riders"""

    def get_categories(self, is_20):
        """ Method for getting all real classes returned as list
        Arguments: is_20 = True - the 20" challenge, junior and elite classes
                   is_20 = False - the Cruiser classes
        """
        if is_20:
            categories = list(
                Rider.objects.filter(is_active=True, is_approved=True, is_20=True)
                .exclude(points_20=0)
                .order_by('class_20')
                .values_list('class_20', flat=True)
                .distinct()
            )
        else:
            categories = list(
                Rider.objects.filter(is_active=True, is_approved=True, is_24=True)
                .exclude(points_24=0)
                .order_by('class_24')
                .values_list('class_24', flat=True)
                .distinct()
            )
        categories.sort()
        return categories

    def get_riders_by_class(self, category: str, is_20: bool):

        """ Method for getting riders by class returned as queryset sorted by points
        Arguments:  category, is_20 = True - the 20" bike, is_20 = False - the Cruiser classes
        """
        if is_20:
            riders = Rider.objects.filter(is_active=True, is_approved=True, is_20=True, class_20=category).order_by(
                '-points_20').exclude(points_20=0)
        else:
            riders = Rider.objects.filter(is_active=True, is_approved=True, is_24=True, class_24=category).order_by(
                '-points_24').exclude(points_24=0)
        return riders

    def write_ranking(self, rider, is_20, ranking):
        if is_20:
            Rider.objects.filter(id=rider).update(ranking_20=ranking)
        else:
            Rider.objects.filter(id=rider).update(ranking_24=ranking)

    def mark_same_position(self):
        categories_20 = self.get_categories(is_20=True)
        categories_24 = self.get_categories(is_20=False)

        all_positions = []
        duplicates = []
        for category_20 in categories_20:
            riders = list(Rider.objects.filter(
                class_20=category_20, is_active=True, is_approved=True, is_20=True
            ).exclude(points_20=0).values_list('ranking_20', flat=True))

            for ranking_val in riders:
                if ranking_val not in all_positions:
                    all_positions.append(ranking_val)
                else:
                    duplicates.append(ranking_val)

            if duplicates:
                for position in duplicates:
                    qs = Rider.objects.filter(
                        ranking_20=position, is_20=True, is_active=True,
                        class_20=category_20, is_approved=True
                    )
                    count = qs.count()
                    text_ranking = f"{position} - {int(position) + count - 1}"
                    qs.update(ranking_20=text_ranking)
            duplicates = []
            all_positions = []

        for category_24 in categories_24:
            riders = list(Rider.objects.filter(
                class_24=category_24, is_active=True, is_approved=True, is_24=True
            ).exclude(points_24=0).values_list('ranking_24', flat=True))

            for ranking_val in riders:
                if ranking_val not in all_positions:
                    all_positions.append(ranking_val)
                else:
                    duplicates.append(ranking_val)

            if duplicates:
                for position in duplicates:
                    qs = Rider.objects.filter(
                        ranking_24=position, is_24=True, is_active=True,
                        class_24=category_24, is_approved=True
                    )
                    count = qs.count()
                    text_ranking = f"{position} - {int(position) + count - 1}"
                    qs.update(ranking_24=text_ranking)
            duplicates = []
            all_positions = []

    def count_ranking_position(self):
        """ Method for counting ranking position for all riders. Without arguments """
        # RANKING POSITION FOR 20"
        categories_20 = self.get_categories(is_20=True)
        for category_20 in categories_20:
            riders_20 = list(self.get_riders_by_class(category=category_20, is_20=True))

            for i, rider in enumerate(riders_20):
                if i > 0:
                    if riders_20[i - 1].points_20 == rider.points_20:
                        ranking = riders_20[i - 1].ranking_20
                    else:
                        ranking = i + 1
                else:
                    ranking = 1
                self.write_ranking(rider=rider.id, is_20=True, ranking=ranking)
                rider.ranking_20 = ranking  # aktualizujeme in-memory pro další iteraci

        # RANKING POSITION FOR 24" (CRUISER)
        categories_24 = self.get_categories(is_20=False)
        for category_24 in categories_24:
            riders_24 = list(self.get_riders_by_class(category=category_24, is_20=False))

            for i, rider in enumerate(riders_24):
                if i > 0:
                    if riders_24[i - 1].points_24 == rider.points_24:
                        ranking = riders_24[i - 1].ranking_24
                    else:
                        ranking = i + 1
                else:
                    ranking = 1
                self.write_ranking(rider=rider.id, is_20=False, ranking=ranking)
                rider.ranking_24 = ranking  # aktualizujeme in-memory pro další iteraci

        self.mark_same_position()
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
