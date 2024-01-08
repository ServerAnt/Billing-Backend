import logging

from django.db import models
from django.utils.translation import gettext_lazy as _
from django_fsm import FSMIntegerField
from model_utils import FieldTracker
from model_utils.models import TimeStampedModel

from waldur_core.core import models as core_models
from waldur_core.structure import models as structure_models
from waldur_mastermind.marketplace import models as marketplace_models
from waldur_mastermind.marketplace.models import SafeAttributesMixin

logger = logging.getLogger(__name__)


class CallManagingOrganisation(
    core_models.UuidMixin,
    core_models.DescribableMixin,
    structure_models.ImageModelMixin,
    structure_models.StructureModel,
    TimeStampedModel,
):
    customer = models.OneToOneField(structure_models.Customer, on_delete=models.CASCADE)

    class Permissions:
        customer_path = 'customer'

    class Meta:
        verbose_name = _('Call managing organisation')

    def __str__(self):
        return str(self.customer)

    @classmethod
    def get_url_name(cls):
        return 'call-managing-organisation'


class Call(
    TimeStampedModel,
    core_models.UuidMixin,
    core_models.NameMixin,
    core_models.DescribableMixin,
):
    class AllocationStrategies:
        BY_CALL_MANAGER = 1
        AUTOMATIC = 2

        CHOICES = (
            (BY_CALL_MANAGER, 'By call manager'),
            (AUTOMATIC, 'Automatic based on review scoring'),
        )

    class States:
        DRAFT = 1
        ACTIVE = 2
        ARCHIVED = 3

        CHOICES = (
            (DRAFT, 'Draft'),
            (ACTIVE, 'Active'),
            (ARCHIVED, 'Archived'),
        )

    manager = models.ForeignKey(CallManagingOrganisation, on_delete=models.PROTECT)
    created_by = models.ForeignKey(
        core_models.User,
        on_delete=models.PROTECT,
        null=True,
        related_name='+',
    )
    allocation_strategy = FSMIntegerField(
        default=AllocationStrategies.AUTOMATIC, choices=AllocationStrategies.CHOICES
    )
    state = FSMIntegerField(default=States.DRAFT, choices=States.CHOICES)
    offerings = models.ManyToManyField(
        marketplace_models.Offering, through='RequestedOffering'
    )
    reviewers = models.ManyToManyField(
        core_models.User, through='CallReviewer', through_fields=('call', 'user')
    )

    class Permissions:
        customer_path = 'manager__customer'

    def __str__(self):
        return f'{self.name} | {self.manager.customer}'


class RequestedOffering(SafeAttributesMixin, core_models.UuidMixin, TimeStampedModel):
    class States:
        REQUESTED = 1
        ACCEPTED = 2
        CANCELED = 3

        CHOICES = (
            (REQUESTED, 'Requested'),
            (ACCEPTED, 'Accepted'),
            (CANCELED, 'Canceled'),
        )

    approved_by = models.ForeignKey(
        core_models.User,
        on_delete=models.PROTECT,
        null=True,
        related_name='+',
        blank=True,
    )
    created_by = models.ForeignKey(
        core_models.User,
        on_delete=models.PROTECT,
        null=True,
        related_name='+',
    )
    state = FSMIntegerField(default=States.REQUESTED, choices=States.CHOICES)
    call = models.ForeignKey(Call, on_delete=models.CASCADE)


class CallReviewer(core_models.UuidMixin, TimeStampedModel):
    created_by = models.ForeignKey(
        core_models.User,
        on_delete=models.CASCADE,
        related_name='+',
    )
    user = models.ForeignKey(
        core_models.User,
        on_delete=models.CASCADE,
        related_name='+',
    )
    call = models.ForeignKey(Call, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'call')

    def __str__(self):
        return self.user.full_name


class Round(
    TimeStampedModel,
    core_models.UuidMixin,
):
    class ReviewStrategies:
        AFTER_ROUND = 1
        AFTER_PROPOSAL = 2

        CHOICES = (
            (AFTER_ROUND, 'After round is closed'),
            (AFTER_PROPOSAL, 'After proposal submission'),
        )

    review_strategy = FSMIntegerField(
        default=ReviewStrategies.AFTER_ROUND, choices=ReviewStrategies.CHOICES
    )
    review_duration_in_days = models.PositiveIntegerField(null=True, blank=True)
    minimum_number_of_reviewers = models.PositiveIntegerField(null=True, blank=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    call = models.ForeignKey(Call, on_delete=models.PROTECT)

    class Permissions:
        customer_path = 'call__manager__customer'

    def __str__(self):
        return f'{self.call.name} | {self.start_time} - {self.end_time}'


class Proposal(
    TimeStampedModel,
    core_models.UuidMixin,
    core_models.NameMixin,
):
    class States:
        DRAFT = 1
        SUBMITTED = 2
        IN_REVIEW = 3
        IN_REVISION = 4
        ACCEPTED = 5
        REJECTED = 6
        CANCELED = 7

        CHOICES = (
            (DRAFT, 'Draft'),
            (SUBMITTED, 'Submitted'),
            (IN_REVIEW, 'In review'),
            (IN_REVISION, 'In revision'),
            (ACCEPTED, 'Accepted'),
            (REJECTED, 'Rejected'),
            (CANCELED, 'Canceled'),
        )

    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    state = FSMIntegerField(default=States.DRAFT, choices=States.CHOICES)
    project = models.ForeignKey(
        structure_models.Project, on_delete=models.PROTECT, null=True, editable=False
    )
    duration_in_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Duration in days after provisioning of resources.',
    )
    approved_by = models.ForeignKey(
        core_models.User,
        on_delete=models.PROTECT,
        null=True,
        related_name='+',
        blank=True,
    )
    created_by = models.ForeignKey(
        core_models.User,
        on_delete=models.PROTECT,
        null=True,
        related_name='+',
    )

    tracker = FieldTracker()

    class Permissions:
        customer_path = 'round__call__manager__customer'

    def __str__(self):
        return f'{self.name} | {self.round.start_time} - {self.round.end_time} | {self.round.call}'

    @classmethod
    def get_url_name(cls):
        return 'proposal-proposal'


class Review(
    TimeStampedModel,
    core_models.UuidMixin,
):
    class States:
        CREATED = 1
        IN_REVIEW = 2
        SUBMITTED = 3
        REJECTED = 4

        CHOICES = (
            (CREATED, 'Created'),
            (IN_REVIEW, 'In review'),
            (SUBMITTED, 'Submitted'),
            (REJECTED, 'Rejected'),
        )

    proposal = models.ForeignKey(Proposal, on_delete=models.PROTECT)
    state = FSMIntegerField(default=States.CREATED, choices=States.CHOICES)
    summary_score = models.PositiveSmallIntegerField(blank=True, default=0)
    summary_public_comment = models.TextField(blank=True)
    summary_private_comment = models.TextField(blank=True)
    reviewer = models.ForeignKey(CallReviewer, on_delete=models.CASCADE)

    tracker = FieldTracker()

    @classmethod
    def get_url_name(cls):
        return 'proposal-review'


class ReviewComment(
    TimeStampedModel,
    core_models.UuidMixin,
):
    review = models.ForeignKey(Review, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)


class ResourceAllocator(
    TimeStampedModel,
    core_models.UuidMixin,
    core_models.NameMixin,
):
    call = models.ForeignKey(Call, on_delete=models.CASCADE)
    project = models.ForeignKey(structure_models.Project, on_delete=models.CASCADE)
