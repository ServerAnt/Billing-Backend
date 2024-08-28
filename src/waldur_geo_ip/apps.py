from django.apps import AppConfig
from django.conf import settings
from django.db.models import signals
from django_fsm import signals as fsm_signals


class GeoIPConfig(AppConfig):
    name = "waldur_geo_ip"

    def ready(self):
        from waldur_core.logging.models import Event
        from waldur_geo_ip.mixins import IPCoordinatesMixin

        from . import handlers

        # Check if geolocation is enabled
        if not settings.WALDUR_CORE.get("ENABLE_GEOIP", False):
            return

        for index, model in enumerate(IPCoordinatesMixin.get_all_models()):
            fsm_signals.post_transition.connect(
                handlers.detect_vm_coordinates,
                sender=model,
                dispatch_uid=f"waldur_geo_ip.handlers.detect_vm_coordinates_{model.__name__}_{index}",
            )

        signals.post_save.connect(
            handlers.detect_event_geo_location,
            sender=Event,
            dispatch_uid="waldur_geo_ip.handlers.detect_event_geo_location",
        )
