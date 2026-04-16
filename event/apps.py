from django.apps import AppConfig


class EventConfig(AppConfig):
    name = 'event'
    verbose_name = "Závody"

    def ready(self):
        import event.signals  # noqa: F401
