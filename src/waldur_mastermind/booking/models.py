import uuid

from django.db import models
from model_utils.models import TimeStampedModel

from waldur_mastermind.marketplace import models as marketplace_models


class BusySlot(TimeStampedModel):
    offering = models.ForeignKey(marketplace_models.Offering, on_delete=models.CASCADE)
    start = models.DateTimeField()
    end = models.DateTimeField()
    backend_id = models.CharField(max_length=255, null=True, blank=True)

    class Permissions:
        customer_path = "offering__customer"


class BookingSlot(TimeStampedModel):
    resource = models.ForeignKey(marketplace_models.Resource, on_delete=models.CASCADE)
    start = models.DateTimeField()
    end = models.DateTimeField()
    backend_id = models.CharField(max_length=255, null=False, blank=False)

    class Permissions:
        customer_path = "resource__project__customer"
        project_path = "resource__project"

    def save(self, *args, **kwargs):
        if not self.backend_id:
            self.backend_id = "booking_" + uuid.uuid4().hex

        super().save(*args, **kwargs)
