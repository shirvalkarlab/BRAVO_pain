from django.apps import AppConfig


class ServerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'Server'

    def ready(self):
        from modules.ReportCache import register_signals
        register_signals()
