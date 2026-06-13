"""Rider views rozdělené po doménách. Re-export zachovává `from rider import views`."""
from rider.views._common import *  # noqa: F401,F403
from rider.views._common import schedule_ranking_recount  # noqa: F401
from rider.views.trainer import *  # noqa: F401,F403
from rider.views.directory import *  # noqa: F401,F403
from rider.views.premium import *  # noqa: F401,F403
from rider.views.account import *  # noqa: F401,F403
from rider.views.admin import *  # noqa: F401,F403
