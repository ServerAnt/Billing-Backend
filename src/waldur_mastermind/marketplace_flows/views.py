from constance import config
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from waldur_core.core import validators as core_validators
from waldur_core.core.views import ActionsViewSet, ReviewViewSet
from waldur_core.permissions.enums import RoleEnum
from waldur_core.structure import permissions as structure_permissions
from waldur_core.structure.managers import get_connected_customers
from waldur_mastermind.marketplace.views import ConnectedOfferingDetailsMixin
from waldur_mastermind.support import models as support_models

from . import filters, models, serializers, utils


def is_owner_of_service_provider(request, view, obj=None):
    if not obj:
        return
    if request.user.is_staff:
        return
    if obj.offering.customer.has_user(request.user):
        return
    raise exceptions.PermissionDenied(
        _(
            "Only owner of service provider is allowed to review resource creation request."
        )
    )


class CustomerCreateRequestViewSet(ReviewViewSet):
    lookup_field = "flow__uuid"
    queryset = models.CustomerCreateRequest.objects.all()
    approve_permissions = reject_permissions = [structure_permissions.is_staff]
    filterset_class = filters.CustomerCreateRequestFilter
    serializer_class = serializers.CustomerCreateRequestSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        # Allow to see user's own requests only
        return qs.filter(flow__requested_by=self.request.user)


class ProjectCreateRequestViewSet(ReviewViewSet):
    lookup_field = "flow__uuid"
    queryset = models.ProjectCreateRequest.objects.all()
    approve_permissions = reject_permissions = [structure_permissions.is_owner]
    filterset_class = filters.ProjectCreateRequestFilter
    serializer_class = serializers.ProjectCreateRequestSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        connected_customers = get_connected_customers(user, RoleEnum.CUSTOMER_OWNER)
        return qs.filter(
            Q(flow__requested_by=user)
            | Q(flow__customer=None)
            | Q(flow__customer__in=connected_customers)
        )


class ResourceCreateRequestViewSet(ConnectedOfferingDetailsMixin, ReviewViewSet):
    lookup_field = "flow__uuid"
    queryset = models.ResourceCreateRequest.objects.all()
    approve_permissions = reject_permissions = [is_owner_of_service_provider]
    filterset_class = filters.ResourceCreateRequestFilter
    serializer_class = serializers.ResourceCreateRequestSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_staff:
            return qs
        connected_customers = get_connected_customers(user, RoleEnum.CUSTOMER_OWNER)
        return qs.filter(
            Q(flow__requested_by=user) | Q(offering__customer__in=connected_customers)
        )


class FlowViewSet(ActionsViewSet):
    queryset = models.FlowTracker.objects.all()
    lookup_field = "uuid"
    update_validators = (
        partial_update_validators
    ) = submit_validators = cancel_validators = [
        core_validators.StateValidator(models.ReviewMixin.States.DRAFT)
    ]
    disabled_actions = ["destroy"]
    serializer_class = serializers.FlowSerializer
    filterset_class = filters.FlowFilter

    @action(detail=True, methods=["post"])
    def submit(self, request, uuid=None):
        flow = self.get_object()
        flow.submit()
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, uuid=None):
        flow = self.get_object()
        flow.cancel()
        return Response(status=status.HTTP_200_OK)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        # Allow to see user's own requests only
        return qs.filter(requested_by=self.request.user)


class OfferingActivateRequestViewSet(ReviewViewSet):
    queryset = models.OfferingStateRequest.objects.all()
    approve_permissions = reject_permissions = [structure_permissions.is_staff]
    filterset_class = filters.OfferingActivateRequestFilter
    serializer_class = serializers.OfferingActivateRequestSerializer
    disabled_actions = ["destroy", "update", "partial_update"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.is_staff:
            return qs
        # Allow to see user's own requests only
        return qs.filter(requested_by=self.request.user)

    @transaction.atomic()
    def perform_create(self, serializer):
        offering_request = serializer.save()

        if config.WALDUR_SUPPORT_ENABLED:
            response = utils.create_issue(offering_request)

            if response.status_code == status.HTTP_201_CREATED:
                offering_request.submit()
                offering_request.issue = support_models.Issue.objects.get(
                    uuid=response.data["uuid"]
                )
                offering_request.save()
            else:
                raise exceptions.ValidationError(response.rendered_content)

    @action(detail=True, methods=["post"])
    def submit(self, request, **kwargs):
        review_request = self.get_object()
        review_request.submit()
        return Response(status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def cancel(self, request, **kwargs):
        review_request = self.get_object()
        review_request.cancel()
        return Response(status=status.HTTP_200_OK)

    approve_validators = reject_validators = [
        core_validators.StateValidator(models.ReviewMixin.States.PENDING)
    ]

    submit_validators = [
        core_validators.StateValidator(models.ReviewMixin.States.DRAFT)
    ]

    cancel_validators = [
        core_validators.StateValidator(
            models.ReviewMixin.States.DRAFT, models.ReviewMixin.States.PENDING
        )
    ]
