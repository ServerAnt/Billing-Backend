import re
from urllib.parse import urljoin

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from model_utils.models import TimeStampedModel

from waldur_core.core import models as core_models
from waldur_core.structure import models as structure_models


class ProjectTemplate(
    core_models.UiDescribableMixin, structure_models.GeneralServiceProperty
):
    @classmethod
    def get_url_name(cls):
        return "jira-project-templates"

    @classmethod
    def get_backend_fields(cls):
        return super().get_backend_fields() + (
            "icon_url",
            "description",
        )


class Project(
    core_models.ActionMixin,
    structure_models.BaseResource,
    core_models.RuntimeStateMixin,
):
    class Permissions(structure_models.BaseResource.Permissions):
        pass

    template = models.ForeignKey(
        on_delete=models.CASCADE, to=ProjectTemplate, blank=True, null=True
    )

    def get_backend(self):
        return super().get_backend(project=self.backend_id)

    def get_access_url(self):
        base_url = self.service_settings.backend_url
        return urljoin(base_url, "projects/" + self.backend_id)

    @classmethod
    def get_url_name(cls):
        return "jira-projects"

    @property
    def priorities(self):
        return Priority.objects.filter(settings=self.service_settings)

    class Meta:
        ordering = ["-created"]


class JiraPropertyIssue(
    core_models.UuidMixin, core_models.StateMixin, TimeStampedModel
):
    user = models.ForeignKey(
        on_delete=models.CASCADE, to=settings.AUTH_USER_MODEL, null=True
    )
    backend_id = models.CharField(max_length=255, null=True)

    class Permissions:
        customer_path = "project__project__customer"
        project_path = "project__project"

    class Meta:
        abstract = True


class IssueType(core_models.UiDescribableMixin, structure_models.ServiceProperty):
    projects = models.ManyToManyField(Project, related_name="issue_types")
    subtask = models.BooleanField(default=False)

    class Meta(structure_models.ServiceProperty.Meta):
        verbose_name = _("Issue type")
        verbose_name_plural = _("Issue types")

    @classmethod
    def get_url_name(cls):
        return "jira-issue-types"

    def __str__(self):
        return self.name

    @classmethod
    def get_backend_fields(cls):
        return super().get_backend_fields() + (
            "icon_url",
            "description",
            "subtask",
            "projects",
        )


class Priority(core_models.UiDescribableMixin, structure_models.ServiceProperty):
    class Meta(structure_models.ServiceProperty.Meta):
        verbose_name = _("Priority")
        verbose_name_plural = _("Priorities")

    @classmethod
    def get_url_name(cls):
        return "jira-priorities"

    def __str__(self):
        return self.name

    @classmethod
    def get_backend_fields(cls):
        return super().get_backend_fields() + ("icon_url", "description")


class Issue(structure_models.StructureLoggableMixin, JiraPropertyIssue):
    type = models.ForeignKey(on_delete=models.CASCADE, to=IssueType)
    parent = models.ForeignKey(
        on_delete=models.CASCADE, to="Issue", blank=True, null=True
    )
    project = models.ForeignKey(
        on_delete=models.CASCADE, to=Project, related_name="issues"
    )
    summary = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    creator_name = models.CharField(blank=True, max_length=255)
    creator_email = models.CharField(blank=True, max_length=255)
    creator_username = models.CharField(blank=True, max_length=255)
    reporter_name = models.CharField(blank=True, max_length=255)
    reporter_email = models.CharField(blank=True, max_length=255)
    reporter_username = models.CharField(blank=True, max_length=255)
    assignee_name = models.CharField(blank=True, max_length=255)
    assignee_email = models.CharField(blank=True, max_length=255)
    assignee_username = models.CharField(blank=True, max_length=255)
    resolution = models.CharField(blank=True, max_length=255)
    resolution_date = models.CharField(blank=True, null=True, max_length=255)
    priority = models.ForeignKey(on_delete=models.CASCADE, to=Priority)
    status = models.CharField(max_length=255)
    updated = models.DateTimeField(auto_now_add=True)

    resource_content_type = models.ForeignKey(
        on_delete=models.CASCADE,
        to=ContentType,
        blank=True,
        null=True,
        related_name="jira_issues",
    )
    resource_object_id = models.PositiveIntegerField(blank=True, null=True)
    resource = GenericForeignKey("resource_content_type", "resource_object_id")

    resolution_sla = models.IntegerField(blank=True, null=True)

    tracker = FieldTracker()

    class Meta:
        unique_together = ("project", "backend_id")
        ordering = ["-created"]

    def get_backend(self):
        return self.project.get_backend()

    @classmethod
    def get_url_name(cls):
        return "jira-issues"

    @property
    def key(self):
        return self.backend_id or ""

    @property
    def issue_user(self):
        return self.user  # XXX: avoid logging conflicts

    @property
    def issue_project(self):
        return self.project  # XXX: avoid logging conflicts

    def get_access_url(self):
        base_url = self.project.service_settings.backend_url
        return urljoin(base_url, "browse/" + (self.backend_id or ""))

    def get_log_fields(self):
        return ("uuid", "issue_user", "key", "summary", "status", "issue_project")

    def get_description(self):
        template = settings.WALDUR_JIRA["ISSUE_TEMPLATE"]["RESOURCE_INFO"]
        if template and self.resource:
            return self.description + template.format(resource=self.resource)

        return self.description

    def __str__(self):
        return "{}: {}".format(self.uuid.hex, self.backend_id or "???")


class JiraSubPropertyIssue(JiraPropertyIssue):
    class Permissions:
        customer_path = "issue__project__project__customer"
        project_path = "issue__project__project"

    class Meta:
        abstract = True


class Comment(structure_models.StructureLoggableMixin, JiraSubPropertyIssue):
    issue = models.ForeignKey(
        on_delete=models.CASCADE, to=Issue, related_name="comments"
    )
    message = models.TextField(blank=True)

    class Meta:
        unique_together = ("issue", "backend_id")

    def get_backend(self):
        return self.issue.project.get_backend()

    @classmethod
    def get_url_name(cls):
        return "jira-comments"

    @property
    def comment_user(self):
        return self.user  # XXX: avoid logging conflicts

    def get_log_fields(self):
        return ("uuid", "comment_user", "issue")

    def clean_message(self, message):
        template = settings.WALDUR_JIRA["COMMENT_TEMPLATE"]
        if not template:
            return self.message

        User = get_user_model()
        template = re.sub(r"([\^~*?:\(\)\[\]|+])", r"\\\1", template)
        pattern = template.format(
            body="", user=User(full_name=r"(.+?)", username=r"([\w.@+-]+)")
        )
        match = re.search(pattern, message)

        if match:
            try:
                self.user = User.objects.get(username=match.group(2))
            except User.DoesNotExist:
                pass
            self.message = message[: match.start()]
        else:
            self.message = message

        return self.message

    def prepare_message(self):
        template = settings.WALDUR_JIRA["COMMENT_TEMPLATE"]
        if template and self.user:
            return template.format(user=self.user, body=self.message)
        return self.message

    def update_message(self, message):
        self.message = self.clean_message(message)

    def __str__(self):
        return "{}: {}".format(self.issue.backend_id or "???", self.backend_id or "")


class Attachment(JiraSubPropertyIssue):
    issue = models.ForeignKey(
        on_delete=models.CASCADE, to=Issue, related_name="attachments"
    )
    file = models.FileField(upload_to="jira_attachments")
    thumbnail = models.FileField(
        upload_to="jira_attachments_thumbnails", blank=True, null=True
    )

    class Meta:
        unique_together = ("issue", "backend_id")

    def get_backend(self):
        return self.issue.project.get_backend()

    @classmethod
    def get_url_name(cls):
        return "jira-attachments"
