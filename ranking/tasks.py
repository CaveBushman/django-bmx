"""Celery tasky pro přepočet rankingu.

Sdílí jádro přepočtu (_ranking_recount_once / _ranking_recount_should_rerun)
s daemon vláknem SetRanking, takže obě cesty se chovají stejně včetně
re-runu, když během přepočtu přijde další změna."""

import logging

from celery import shared_task

from ranking.ranking import _ranking_recount_once, _ranking_recount_should_rerun

logger = logging.getLogger(__name__)


@shared_task(name="ranking.recount", bind=True)
def recount_ranking_task(self):
    """Jeden průchod přepočtu rankingu. Pokud během běhu přišla další změna,
    znovu se zařadí do fronty (lock RUNNING zůstává držený mezi průchody)."""
    _ranking_recount_once()
    if _ranking_recount_should_rerun():
        logger.info("Ranking: zařazuji další průchod přepočtu do Celery.")
        recount_ranking_task.delay()
