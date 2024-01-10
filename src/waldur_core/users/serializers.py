from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from waldur_core.structure import models as structure_models
from waldur_core.users import models

User = get_user_model()


class GroupInvitationSerializer(serializers.HyperlinkedModelSerializer):
    project = serializers.HyperlinkedRelatedField(
        view_name="project-detail",
        lookup_field="uuid",
        queryset=structure_models.Project.available_objects.all(),
        required=False,
        allow_null=True,
    )
    project_name = serializers.ReadOnlyField(source="project.name")
    project_uuid = serializers.ReadOnlyField(source="project.uuid")
    created_by_full_name = serializers.ReadOnlyField(source="created_by.full_name")
    created_by_username = serializers.ReadOnlyField(source="created_by.username")
    customer = serializers.HyperlinkedRelatedField(
        view_name="customer-detail",
        lookup_field="uuid",
        queryset=structure_models.Customer.objects.all(),
        required=False,
        allow_null=True,
    )
    customer_name = serializers.ReadOnlyField(source="customer.name")
    customer_uuid = serializers.ReadOnlyField(source="customer.uuid")

    expires = serializers.DateTimeField(source="get_expiration_time", read_only=True)

    class Meta:
        model = models.GroupInvitation
        fields = (
            "url",
            "uuid",
            "project",
            "project_role",
            "project_name",
            "customer",
            "customer_role",
            "customer_name",
            "created",
            "expires",
            "created_by_full_name",
            "created_by_username",
            "is_active",
            "project_uuid",
            "customer_uuid",
        )
        read_only_fields = (
            "url",
            "uuid",
            "created",
            "expires",
            "is_active",
        )
        extra_kwargs = {
            "url": {
                "lookup_field": "uuid",
                "view_name": "user-group-invitation-detail",
            },
            "project_role": {"required": False, "allow_null": True},
            "customer_role": {"required": False, "allow_null": True},
        }

    def validate(self, attrs):
        project = attrs.get("project")
        customer = attrs.get("customer")

        project_role = attrs.get("project_role", "")
        customer_role = attrs.get("customer_role", "")

        if customer and project:
            raise serializers.ValidationError(
                _("Cannot create invitation to project and customer simultaneously.")
            )
        elif not (customer or project):
            raise serializers.ValidationError(
                _("Customer or project must be provided.")
            )
        elif (customer and not customer_role) or (customer_role and not customer):
            raise serializers.ValidationError(
                {"customer_role": _("Customer and its role must be provided.")}
            )
        elif (project and not project_role) or (project_role and not project):
            raise serializers.ValidationError(
                {"project_role": _("Project and its role must be provided.")}
            )

        return attrs

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        project = validated_data.get("project")
        if project:
            validated_data["customer"] = project.customer
        return super().create(validated_data)


class InvitationSerializer(GroupInvitationSerializer):
    class Meta:
        model = models.Invitation
        detail_fields = (
            "full_name",
            "native_name",
            "tax_number",
            "phone_number",
            "organization",
            "job_title",
        )
        fields = (
            "url",
            "uuid",
            "email",
            "civil_number",
            "project",
            "project_role",
            "project_name",
            "customer",
            "customer_role",
            "customer_name",
            "state",
            "error_message",
            "created",
            "expires",
            "created_by_full_name",
            "created_by_username",
            "extra_invitation_text",
        ) + detail_fields
        read_only_fields = (
            "url",
            "uuid",
            "state",
            "error_message",
            "created",
            "expires",
        )
        extra_kwargs = {
            "url": {
                "lookup_field": "uuid",
                "view_name": "user-invitation-detail",
            },
            "project_role": {
                "required": False,
                "allow_null": True,
            },
            "customer_role": {
                "required": False,
                "allow_null": True,
            },
        }


class PendingInvitationDetailsSerializer(serializers.ModelSerializer):
    project_name = serializers.ReadOnlyField(source="project.name")
    customer_name = serializers.ReadOnlyField(source="customer.name")
    project_uuid = serializers.ReadOnlyField(source="project.uuid")
    customer_uuid = serializers.ReadOnlyField(source="customer.uuid")
    created_by_full_name = serializers.ReadOnlyField(source="created_by.full_name")
    created_by_username = serializers.ReadOnlyField(source="created_by.username")

    class Meta:
        model = models.Invitation
        fields = (
            "email",
            "project_name",
            "project_role",
            "project_uuid",
            "customer_name",
            "customer_role",
            "customer_uuid",
            "created_by_full_name",
            "created_by_username",
        )


class PermissionRequestSerializer(serializers.HyperlinkedModelSerializer):
    created_by_full_name = serializers.ReadOnlyField(source="created_by.full_name")
    created_by_username = serializers.ReadOnlyField(source="created_by.username")
    reviewed_by_full_name = serializers.ReadOnlyField(source="reviewed_by.full_name")
    reviewed_by_username = serializers.ReadOnlyField(source="reviewed_by.username")
    state = serializers.ReadOnlyField(source="get_state_display")
    project_uuid = serializers.ReadOnlyField(source="invitation.project.uuid")
    project_role = serializers.ReadOnlyField(source="invitation.project_role")
    project_name = serializers.ReadOnlyField(source="invitation.project.name")
    customer_uuid = serializers.ReadOnlyField(source="invitation.customer.uuid")
    customer_role = serializers.ReadOnlyField(source="invitation.customer_role")
    customer_name = serializers.ReadOnlyField(source="invitation.customer.name")

    class Meta:
        model = models.PermissionRequest
        fields = (
            "url",
            "uuid",
            "invitation",
            "state",
            "created",
            "created_by_full_name",
            "created_by_username",
            "reviewed_by_full_name",
            "reviewed_by_username",
            "reviewed_at",
            "review_comment",
            "project_uuid",
            "project_role",
            "project_name",
            "customer_uuid",
            "customer_role",
            "customer_name",
        )

        extra_kwargs = {
            "url": {
                "lookup_field": "uuid",
                "view_name": "user-permission-request-detail",
            },
            "invitation": {
                "lookup_field": "uuid",
                "view_name": "user-group-invitation-detail",
            },
        }
