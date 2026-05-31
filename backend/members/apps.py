from django.apps import AppConfig


class MembersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "backend.members"

    def ready(self):
        import backend.members.signals  # register signals

        # ✅ move here
        from backend.members.services.event_registry import register_all_events
        register_all_events()