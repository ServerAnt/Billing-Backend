import collections
import logging

from django.db import models, transaction
from django.utils.lru_cache import lru_cache
from django.utils.topological_sort import stable_topological_sort
from django.utils.translation import ugettext_lazy as _
from rest_framework.exceptions import ValidationError

from waldur_core.structure import models as structure_models
from waldur_core.structure.signals import project_moved

from . import SupportedServices

logger = logging.getLogger(__name__)
FieldInfo = collections.namedtuple(
    'FieldInfo', 'fields fields_required extra_fields_required extra_fields_default'
)


@lru_cache(maxsize=1)
def get_sorted_dependencies(service_model):
    """
    Returns list of application models in topological order.
    It is used in order to correctly delete dependent resources.
    """
    app_models = list(service_model._meta.app_config.get_models())
    dependencies = {model: set() for model in app_models}
    relations = (
        relation
        for model in app_models
        for relation in model._meta.related_objects
        if relation.on_delete in (models.PROTECT, models.CASCADE)
    )
    for rel in relations:
        dependencies[rel.model].add(rel.related_model)
    return stable_topological_sort(app_models, dependencies)


def sort_dependencies(service_model, resources):
    ordering = get_sorted_dependencies(service_model)
    resources.sort(key=lambda resource: ordering.index(resource._meta.model))
    return resources


@lru_cache(maxsize=1)
def get_all_services_field_info():
    services_fields = dict()
    services_fields_default_value = dict()
    services_fields_required = dict()
    services_extra_fields_required = dict()
    service_models = SupportedServices.get_service_models()

    for service_name in service_models:
        service_model = service_models[service_name]['service']
        service_serializer = SupportedServices.get_service_serializer(service_model)

        fields = (
            service_serializer.SERVICE_ACCOUNT_FIELDS.keys()
            if service_serializer.SERVICE_ACCOUNT_FIELDS is not NotImplemented
            else []
        )

        extra_field_options = getattr(
            service_serializer.Meta, 'extra_field_options', {}
        )
        fields_default_value = {
            k: v.get('default_value')
            for k, v in extra_field_options.items()
            if v.get('default_value')
        }

        fields_extra = (
            service_serializer.SERVICE_ACCOUNT_EXTRA_FIELDS.keys()
            if service_serializer.SERVICE_ACCOUNT_EXTRA_FIELDS is not NotImplemented
            else []
        )

        fields_required = (
            service_serializer.Meta.required_fields
            if hasattr(service_serializer.Meta, 'required_fields')
            else []
        )

        services_fields[service_name] = list(fields)
        services_fields_required[service_name] = list(
            set(fields) & set(fields_required)
        )
        services_extra_fields_required[service_name] = list(
            set(fields_extra) & set(fields_required)
        )
        services_fields_default_value[service_name] = fields_default_value

    return FieldInfo(
        fields=services_fields,
        fields_required=services_fields_required,
        extra_fields_required=services_extra_fields_required,
        extra_fields_default=services_fields_default_value,
    )


def update_pulled_fields(instance, imported_instance, fields):
    """
    Update instance fields based on imported from backend data.
    Save changes to DB only one or more fields were changed.
    """
    modified = False
    for field in fields:
        pulled_value = getattr(imported_instance, field)
        current_value = getattr(instance, field)
        if current_value != pulled_value:
            setattr(instance, field, pulled_value)
            logger.info(
                "%s's with PK %s %s field updated from value '%s' to value '%s'",
                instance.__class__.__name__,
                instance.pk,
                field,
                current_value,
                pulled_value,
            )
            modified = True
    error_message = getattr(imported_instance, 'error_message', '') or getattr(
        instance, 'error_message', ''
    )
    if error_message and instance.error_message != error_message:
        instance.error_message = imported_instance.error_message
        modified = True
    if modified:
        instance.save()
    return modified


def handle_resource_not_found(resource):
    """
    Set resource state to ERRED and append/create "not found" error message.
    """
    resource.set_erred()
    resource.runtime_state = ''
    message = 'Does not exist at backend.'
    if message not in resource.error_message:
        if not resource.error_message:
            resource.error_message = message
        else:
            resource.error_message += ' (%s)' % message
    resource.save()
    logger.warning(
        '%s %s (PK: %s) does not exist at backend.'
        % (resource.__class__.__name__, resource, resource.pk)
    )


def handle_resource_update_success(resource):
    """
    Recover resource if its state is ERRED and clear error message.
    """
    update_fields = []
    if resource.state == resource.States.ERRED:
        resource.recover()
        update_fields.append('state')

    if resource.state in (resource.States.UPDATING, resource.States.CREATING):
        resource.set_ok()
        update_fields.append('state')

    if resource.error_message:
        resource.error_message = ''
        update_fields.append('error_message')

    if update_fields:
        resource.save(update_fields=update_fields)
    logger.info(
        '%s %s (PK: %s) was successfully updated.'
        % (resource.__class__.__name__, resource, resource.pk)
    )


def check_customer_blocked(obj):
    from waldur_core.structure import permissions

    customer = permissions._get_customer(obj)
    if customer and customer.blocked:
        raise ValidationError(_('Blocked organization is not available.'))


@transaction.atomic
def move_project(project, customer):
    if customer.blocked:
        raise ValidationError(_('New customer must be not blocked'))

    old_customer = project.customer
    if customer == old_customer:
        raise ValidationError(_('New customer must be different than current one'))

    project.customer = customer
    project.save(update_fields=['customer'])

    for permission in structure_models.ProjectPermission.objects.filter(
        project=project
    ):
        permission.revoke()
        logger.info('Permission %s has been revoked' % permission)

    project_moved.send(
        sender=project.__class__,
        project=project,
        old_customer=old_customer,
        new_customer=customer,
    )
