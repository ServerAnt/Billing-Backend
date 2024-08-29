import django_filters
from django.db.models import Q

from waldur_core.core import filters as core_filters
from waldur_core.structure import filters as structure_filters

from . import models


class SecurityGroupFilter(structure_filters.BaseResourceFilter):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )
    query = django_filters.CharFilter(method="filter_query")

    class Meta(structure_filters.BaseResourceFilter.Meta):
        model = models.SecurityGroup

    def filter_query(self, queryset, name, value):
        query = queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )
        return query


class ServerGroupFilter(structure_filters.BaseResourceFilter):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )

    class Meta(structure_filters.BaseResourceFilter.Meta):
        model = models.ServerGroup


class FloatingIPFilter(structure_filters.BaseResourceFilter):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )

    class Meta(structure_filters.BaseResourceFilter.Meta):
        model = models.FloatingIP
        fields = structure_filters.BaseResourceFilter.Meta.fields + ("runtime_state",)


class FlavorFilter(structure_filters.ServicePropertySettingsFilter):
    o = django_filters.OrderingFilter(fields=("cores", "ram", "disk"))

    class Meta(structure_filters.ServicePropertySettingsFilter.Meta):
        model = models.Flavor
        fields = dict(
            {
                "cores": ["exact", "gte", "lte"],
                "ram": ["exact", "gte", "lte"],
                "disk": ["exact", "gte", "lte"],
            },
            **{
                field: ["exact"]
                for field in structure_filters.ServicePropertySettingsFilter.Meta.fields
            },
        )


class ImageFilter(structure_filters.ServicePropertySettingsFilter):
    class Meta(structure_filters.ServicePropertySettingsFilter.Meta):
        model = models.Image


class VolumeTypeFilter(structure_filters.ServicePropertySettingsFilter):
    class Meta(structure_filters.ServicePropertySettingsFilter.Meta):
        model = models.VolumeType


class RouterFilter(structure_filters.NameFilterSet):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )

    class Meta:
        model = models.Router
        fields = ("tenant", "tenant_uuid")


class PortFilter(structure_filters.NameFilterSet):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )
    o = django_filters.OrderingFilter(fields=(("network__name", "network_name"),))

    class Meta:
        model = models.Port
        fields = ("tenant", "tenant_uuid")


class NetworkFilter(structure_filters.BaseResourceFilter):
    tenant_uuid = django_filters.UUIDFilter(field_name="tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="tenant__uuid"
    )

    class Meta(structure_filters.BaseResourceFilter.Meta):
        model = models.Network
        fields = structure_filters.BaseResourceFilter.Meta.fields + (
            "type",
            "is_external",
        )


class SubNetFilter(structure_filters.BaseResourceFilter):
    tenant_uuid = django_filters.UUIDFilter(field_name="network__tenant__uuid")
    tenant = core_filters.URLFilter(
        view_name="openstack-tenant-detail", field_name="network__tenant__uuid"
    )
    network_uuid = django_filters.UUIDFilter(field_name="network__uuid")
    network = core_filters.URLFilter(
        view_name="openstack-network-detail", field_name="network__uuid"
    )

    class Meta(structure_filters.BaseResourceFilter.Meta):
        model = models.SubNet
        fields = structure_filters.BaseResourceFilter.Meta.fields + (
            "ip_version",
            "enable_dhcp",
        )
