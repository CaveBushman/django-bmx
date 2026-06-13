"""Celery tasky pro jezdce — přepočet kvalifikace na MČR."""

import logging

from celery import shared_task

from rider.rider import perform_cn_qualification_recount

logger = logging.getLogger(__name__)


@shared_task(name="rider.recount_cn_qualification")
def recount_cn_qualification_task(year=None):
    """Přepočte kvalifikaci na MČR (is_qualify_to_cn_20/24) pro daný rok."""
    perform_cn_qualification_recount(year)
