import django_filters
from django.contrib.auth import get_user_model
from django.db.models import Q

from waldur_core.core import filters as core_filters

from . import models

User = get_user_model()


class CallManagingOrganisationFilter(django_filters.FilterSet):
    customer = core_filters.URLFilter(
        view_name='customer-detail', field_name='customer__uuid'
    )
    customer_uuid = django_filters.UUIDFilter(field_name='customer__uuid')
    customer_keyword = django_filters.CharFilter(method='filter_customer_keyword')
    o = django_filters.OrderingFilter(fields=(('customer__name', 'customer_name'),))

    class Meta:
        model = models.CallManagingOrganisation
        fields = []

    def filter_customer_keyword(self, queryset, name, value):
        return queryset.filter(
            Q(customer__name__icontains=value)
            | Q(customer__abbreviation__icontains=value)
            | Q(customer__native_name__icontains=value)
        )


class CallFilter(django_filters.FilterSet):
    customer = core_filters.URLFilter(
        view_name='customer-detail', field_name='manager__customer__uuid'
    )
    customer_uuid = django_filters.UUIDFilter(field_name='manager__customer__uuid')
    customer_keyword = django_filters.CharFilter(method='filter_customer_keyword')
    o = django_filters.OrderingFilter(
        fields=('manager__customer__name', 'start_time', 'end_time')
    )

    class Meta:
        model = models.Call
        fields = []

    def filter_customer_keyword(self, queryset, name, value):
        return queryset.filter(
            Q(manager__customer__name__icontains=value)
            | Q(manager__customer__abbreviation__icontains=value)
            | Q(manager__customer__native_name__icontains=value)
        )
