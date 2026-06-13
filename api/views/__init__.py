"""API views rozdělené po doménách. Re-export zachovává `from api import views`."""
from api.views._common import *  # noqa: F401,F403
from api.views.riders import *  # noqa: F401,F403
from api.views.clubs import *  # noqa: F401,F403
from api.views.plates import *  # noqa: F401,F403
from api.views.news import *  # noqa: F401,F403
from api.views.auth import *  # noqa: F401,F403
from api.views.eshop import *  # noqa: F401,F403
from api.views.ranking import *  # noqa: F401,F403
from api.views.events import *  # noqa: F401,F403
from api.views.foreign_entries import *  # noqa: F401,F403
from api.views.subscriptions import *  # noqa: F401,F403
from api.views.search import *  # noqa: F401,F403
