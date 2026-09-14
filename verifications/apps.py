from django.apps import AppConfig


class VerificationsConfig(AppConfig):
    name = 'verifications'

    def ready(self):
        import verifications.signals
