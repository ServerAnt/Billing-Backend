from django.conf import settings
from django.db import models
from model_utils import FieldTracker

from waldur_core.core.mixins import ReviewMixin
from waldur_core.core.models import DESCRIPTION_LENGTH, UuidMixin
from waldur_core.structure.models import PROJECT_NAME_LENGTH, Project
from waldur_mastermind.marketplace.models import Offering


class ProjectUpdateRequest(UuidMixin, ReviewMixin):
    class Meta:
        ordering = ["created"]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="+")
    offering = models.ForeignKey(Offering, on_delete=models.CASCADE, related_name="+")
    tracker = FieldTracker()
    old_name = models.CharField(max_length=PROJECT_NAME_LENGTH, blank=True)
    new_name = models.CharField(max_length=PROJECT_NAME_LENGTH, blank=True)
    old_description = models.CharField(max_length=DESCRIPTION_LENGTH, blank=True)
    new_description = models.CharField(max_length=DESCRIPTION_LENGTH, blank=True)
    old_end_date = models.DateField(null=True, blank=True)
    new_end_date = models.DateField(null=True, blank=True)
    old_oecd_fos_2007_code = models.CharField(null=True, blank=True, max_length=5)
    new_oecd_fos_2007_code = models.CharField(null=True, blank=True, max_length=5)
    old_is_industry = models.BooleanField(null=True, blank=True)
    new_is_industry = models.BooleanField(null=True, blank=True)
    created_by = models.ForeignKey(
        on_delete=models.CASCADE,
        to=settings.AUTH_USER_MODEL,
        related_name="+",
        blank=True,
        null=True,
    )

    def get_old_oecd_fos_2007_code_display(self):
        return Project.OECD_FOS_2007_CODES_DICT.get(self.old_oecd_fos_2007_code)

    def get_new_oecd_fos_2007_code_display(self):
        return Project.OECD_FOS_2007_CODES_DICT.get(self.new_oecd_fos_2007_code)

    class Permissions:
        customer_path = "offering__customer"
        project_path = "project"
