import logging

from django.contrib.contenttypes.models import ContentType
from django.core import exceptions as django_exceptions
from django.db import IntegrityError, transaction
from django.db.models import Q

from waldur_core.core.models import StateMixin
from waldur_core.quotas.models import QuotaLimit
from waldur_core.structure import models as structure_models

from ..openstack import apps as openstack_apps
from ..openstack import models as openstack_models
from . import apps, log, models

logger = logging.getLogger(__name__)


def _log_scheduled_action(resource, action, action_details):
    class_name = resource.__class__.__name__.lower()
    message = _get_action_message(action, action_details)
    log.event_logger.openstack_resource_action.info(
        f'Operation "{message}" has been scheduled for {class_name} "{resource.name}"',
        event_type=_get_action_event_type(action, "scheduled"),
        event_context={"resource": resource, "action_details": action_details},
    )


def _log_succeeded_action(resource, action, action_details):
    if not action:
        return
    class_name = resource.__class__.__name__.lower()
    message = _get_action_message(action, action_details)
    log.event_logger.openstack_resource_action.info(
        f'Successfully executed "{message}" operation for {class_name} "{resource.name}"',
        event_type=_get_action_event_type(action, "succeeded"),
        event_context={"resource": resource, "action_details": action_details},
    )


def _log_failed_action(resource, action, action_details):
    class_name = resource.__class__.__name__.lower()
    message = _get_action_message(action, action_details)
    log.event_logger.openstack_resource_action.warning(
        f'Failed to execute "{message}" operation for {class_name} "{resource.name}"',
        event_type=_get_action_event_type(action, "failed"),
        event_context={"resource": resource, "action_details": action_details},
    )


def _get_action_message(action, action_details):
    return action_details.pop("message", action)


def _get_action_event_type(action, event_state):
    return "resource_{}_{}".format(action.replace(" ", "_").lower(), event_state)


def log_action(sender, instance, created=False, **kwargs):
    """Log any resource action.

    Example of logged volume extend action:
    {
        'event_type': 'volume_extend_succeeded',
        'message': 'Successfully executed "Extend volume from 1024 MB to 2048 MB" operation for volume "pavel-test"',
        'action_details': {'old_size': 1024, 'new_size': 2048}
    }
    """
    resource = instance
    if created or not resource.tracker.has_changed("action"):
        return
    if resource.state == StateMixin.States.UPDATE_SCHEDULED:
        _log_scheduled_action(resource, resource.action, resource.action_details)
    if resource.state == StateMixin.States.OK:
        _log_succeeded_action(
            resource,
            resource.tracker.previous("action"),
            resource.tracker.previous("action_details"),
        )
    elif resource.state == StateMixin.States.ERRED:
        _log_failed_action(
            resource,
            resource.tracker.previous("action"),
            resource.tracker.previous("action_details"),
        )


def log_snapshot_schedule_creation(sender, instance, created=False, **kwargs):
    if not created:
        return

    snapshot_schedule = instance
    log.event_logger.openstack_snapshot_schedule.info(
        'Snapshot schedule "%s" has been created' % snapshot_schedule.name,
        event_type="resource_snapshot_schedule_created",
        event_context={
            "resource": snapshot_schedule.source_volume,
            "snapshot_schedule": snapshot_schedule,
        },
    )


def log_snapshot_schedule_action(sender, instance, created=False, **kwargs):
    snapshot_schedule = instance
    if created or not snapshot_schedule.tracker.has_changed("is_active"):
        return

    context = {
        "resource": snapshot_schedule.source_volume,
        "snapshot_schedule": snapshot_schedule,
    }
    if snapshot_schedule.is_active:
        log.event_logger.openstack_snapshot_schedule.info(
            'Snapshot schedule "%s" has been activated' % snapshot_schedule.name,
            event_type="resource_snapshot_schedule_activated",
            event_context=context,
        )
    else:
        if snapshot_schedule.error_message:
            message = f'Snapshot schedule "{snapshot_schedule.name}" has been deactivated because of error: {snapshot_schedule.error_message}'
        else:
            message = (
                'Snapshot schedule "%s" has been deactivated' % snapshot_schedule.name
            )
        log.event_logger.openstack_snapshot_schedule.warning(
            message,
            event_type="resource_snapshot_schedule_deactivated",
            event_context=context,
        )


def log_snapshot_schedule_deletion(sender, instance, **kwargs):
    snapshot_schedule = instance
    log.event_logger.openstack_snapshot_schedule.info(
        'Snapshot schedule "%s" has been deleted' % snapshot_schedule.name,
        event_type="resource_snapshot_schedule_deleted",
        event_context={
            "resource": snapshot_schedule.source_volume,
            "snapshot_schedule": snapshot_schedule,
        },
    )


def log_backup_schedule_creation(sender, instance, created=False, **kwargs):
    if not created:
        return

    backup_schedule = instance
    log.event_logger.openstack_backup_schedule.info(
        'Backup schedule "%s" has been created' % backup_schedule.name,
        event_type="resource_backup_schedule_created",
        event_context={
            "resource": backup_schedule.instance,
            "backup_schedule": backup_schedule,
        },
    )


def log_backup_schedule_action(sender, instance, created=False, **kwargs):
    backup_schedule = instance
    if created or not backup_schedule.tracker.has_changed("is_active"):
        return

    context = {"resource": backup_schedule.instance, "backup_schedule": backup_schedule}
    if backup_schedule.is_active:
        log.event_logger.openstack_backup_schedule.info(
            'Backup schedule "%s" has been activated' % backup_schedule.name,
            event_type="resource_backup_schedule_activated",
            event_context=context,
        )
    else:
        if backup_schedule.error_message:
            message = f'Backup schedule "{backup_schedule.name}" has been deactivated because of error: {backup_schedule.error_message}'
        else:
            message = 'Backup schedule "%s" has been deactivated' % backup_schedule.name
        log.event_logger.openstack_backup_schedule.warning(
            message,
            event_type="resource_backup_schedule_deactivated",
            event_context=context,
        )


def log_backup_schedule_deletion(sender, instance, **kwargs):
    backup_schedule = instance
    log.event_logger.openstack_backup_schedule.info(
        'Backup schedule "%s" has been deleted' % backup_schedule.name,
        event_type="resource_backup_schedule_deleted",
        event_context={
            "resource": backup_schedule.instance,
            "backup_schedule": backup_schedule,
        },
    )


def update_service_settings_credentials(sender, instance, created=False, **kwargs):
    """
    Updates service settings credentials on tenant user_password or user_username change.
    It is possible to change a user password in tenant,
    as service settings copies tenant user password on creation it has to be update on change.
    """
    if created:
        return

    tenant = instance
    if tenant.tracker.has_changed("user_password") or tenant.tracker.has_changed(
        "user_username"
    ):
        service_settings = structure_models.ServiceSettings.objects.filter(
            scope=tenant
        ).first()
        if service_settings:
            service_settings.username = tenant.user_username
            service_settings.password = tenant.user_password
            service_settings.save()


class BaseSynchronizationHandler:
    """
    This class provides signal handlers for synchronization of OpenStack properties
    when parent OpenStack resource are created, updated or deleted.
    Security groups, floating IPs, networks and subnets are implemented as
    resources in openstack application. However they are implemented as service properties
    in the openstack_tenant application.
    """

    property_model = None
    resource_model = None
    fields = []

    def get_tenant(self, resource):
        return resource.tenant

    def get_service_settings(self, resource):
        try:
            return structure_models.ServiceSettings.objects.get(
                scope=self.get_tenant(resource),
                type=apps.OpenStackTenantConfig.service_name,
            )
        except (
            django_exceptions.ObjectDoesNotExist,
            django_exceptions.MultipleObjectsReturned,
        ):
            return

    def get_service_property(self, resource, settings):
        try:
            return self.property_model.objects.get(
                settings=settings, backend_id=resource.backend_id
            )
        except (
            django_exceptions.ObjectDoesNotExist,
            django_exceptions.MultipleObjectsReturned,
        ):
            return

    def map_resource_to_dict(self, resource):
        return {field: getattr(resource, field) for field in self.fields}

    def create_service_property(self, resource, settings):
        defaults = dict(name=resource.name, **self.map_resource_to_dict(resource))

        try:
            with transaction.atomic():
                return self.property_model.objects.get_or_create(
                    settings=settings, backend_id=resource.backend_id, defaults=defaults
                )
        except IntegrityError:
            logger.warning(
                "Could not create %s with backend ID %s "
                "and service settings %s due to concurrent update.",
                self.property_model,
                resource.backend_id,
                settings,
            )

    def update_service_property(self, resource, settings):
        service_property = self.get_service_property(resource, settings)
        if not service_property:
            return
        params = self.map_resource_to_dict(resource)
        for key, value in params.items():
            setattr(service_property, key, value)
        service_property.name = resource.name
        service_property.save()
        return service_property

    def create_handler(self, sender, instance, name, source, target, **kwargs):
        """
        Creates service property on resource transition from 'CREATING' state to 'OK'.
        """
        if source == StateMixin.States.CREATING and target == StateMixin.States.OK:
            settings = self.get_service_settings(instance)
            if settings and not self.get_service_property(instance, settings):
                self.create_service_property(instance, settings)

    def import_handler(self, sender, instance, created=False, **kwargs):
        """
        Creates service property on when resource is imported.
        """
        if created and instance.state == StateMixin.States.OK:
            settings = self.get_service_settings(instance)
            if settings and not self.get_service_property(instance, settings):
                self.create_service_property(instance, settings)

    def update_handler(self, sender, instance, name, source, target, **kwargs):
        """
        Updates service property on resource transition from 'UPDATING' state to 'OK'.
        """
        if source == StateMixin.States.UPDATING and target == StateMixin.States.OK:
            settings = self.get_service_settings(instance)
            if settings:
                self.update_service_property(instance, settings)

    def delete_handler(self, sender, instance, **kwargs):
        """
        Deletes service property on resource deletion
        """
        settings = self.get_service_settings(instance)
        if not settings:
            return
        service_property = self.get_service_property(instance, settings)
        if not service_property:
            return
        service_property.delete()


class FloatingIPHandler(BaseSynchronizationHandler):
    property_model = models.FloatingIP
    resource_model = openstack_models.FloatingIP
    fields = ("address", "backend_network_id", "runtime_state")


class SecurityGroupHandler(BaseSynchronizationHandler):
    property_model = models.SecurityGroup
    resource_model = openstack_models.SecurityGroup
    fields = ("description",)

    def map_rules(self, security_group, openstack_security_group):
        return [
            models.SecurityGroupRule(
                ethertype=rule.ethertype,
                direction=rule.direction,
                protocol=rule.protocol,
                from_port=rule.from_port,
                to_port=rule.to_port,
                cidr=rule.cidr,
                description=rule.description,
                backend_id=rule.backend_id,
                security_group=security_group,
            )
            for rule in openstack_security_group.rules.exclude(backend_id="")
        ]

    def pull_remote_group(self, group_property, group_resource, service_settings):
        # Skip rules with empty backend ID (ie rules being created)
        for rule_resource in group_resource.rules.exclude(
            Q(remote_group=None) | Q(backend_id="")
        ):
            try:
                remote_group = models.SecurityGroup.objects.get(
                    settings=service_settings,
                    backend_id=rule_resource.remote_group.backend_id,
                )
                rule_property = models.SecurityGroupRule.objects.get(
                    security_group=group_property, backend_id=rule_resource.backend_id
                )
            except django_exceptions.ObjectDoesNotExist:
                continue
            else:
                if rule_property.remote_group != remote_group:
                    rule_property.remote_group = remote_group
                    rule_property.save(update_fields=["remote_group"])

    def create_service_property(self, resource, settings):
        service_property, _ = super().create_service_property(resource, settings)
        if resource.rules.count() > 0:
            group_rules = self.map_rules(service_property, resource)
            service_property.rules.bulk_create(group_rules)
        self.pull_remote_group(service_property, resource, settings)
        return service_property

    def update_service_property(self, resource, settings):
        service_property = super().update_service_property(resource, settings)
        if not service_property:
            return

        return service_property


class NetworkHandler(BaseSynchronizationHandler):
    property_model = models.Network
    resource_model = openstack_models.Network
    fields = ("is_external", "segmentation_id", "type")


class SubNetHandler(BaseSynchronizationHandler):
    property_model = models.SubNet
    resource_model = openstack_models.SubNet
    fields = (
        "allocation_pools",
        "cidr",
        "dns_nameservers",
        "enable_dhcp",
        "ip_version",
        "is_connected",
    )

    def get_tenant(self, resource):
        return resource.network.tenant

    def map_resource_to_dict(self, resource):
        params = super().map_resource_to_dict(resource)
        params["network"] = models.Network.objects.get(
            backend_id=resource.network.backend_id
        )
        return params


resource_handlers = (
    FloatingIPHandler(),
    SecurityGroupHandler(),
    NetworkHandler(),
    SubNetHandler(),
)


def copy_flavor_exclude_regex_to_openstacktenant_service_settings(
    sender, instance, created=False, **kwargs
):
    if not created or instance.type != apps.OpenStackTenantConfig.service_name:
        return

    tenant = instance.scope
    if not isinstance(tenant, openstack_models.Tenant):
        return

    admin_settings = tenant.service_settings
    instance.options["flavor_exclude_regex"] = admin_settings.options.get(
        "flavor_exclude_regex", ""
    )
    instance.save(update_fields=["options"])


def copy_config_drive_to_openstacktenant_service_settings(
    sender, instance, created=False, **kwargs
):
    if created:
        return

    if instance.type != openstack_apps.OpenStackConfig.service_name:
        return

    if not instance.tracker.has_changed("options"):
        return

    old_value = (instance.tracker.previous("options") or {}).get("config_drive", False)
    new_value = instance.options.get("config_drive", False)

    if old_value == new_value:
        return

    tenants = openstack_models.Tenant.objects.filter(service_settings=instance)
    ctype = ContentType.objects.get_for_model(openstack_models.Tenant)
    tenant_settings = structure_models.ServiceSettings.objects.filter(
        object_id__in=tenants.values_list("id"), content_type=ctype
    )
    for item in tenant_settings:
        item.options["config_drive"] = new_value
        item.save(update_fields=["options"])


def create_service_from_tenant(sender, instance, created=False, **kwargs):
    if not created:
        return

    if structure_models.ServiceSettings.objects.filter(
        scope=instance,
        type=apps.OpenStackTenantConfig.service_name,
    ).exists():
        return

    tenant = instance
    admin_settings = tenant.service_settings
    customer = tenant.project.customer
    service_settings = structure_models.ServiceSettings.objects.create(
        name=tenant.name,
        scope=tenant,
        customer=customer,
        type=apps.OpenStackTenantConfig.service_name,
        backend_url=admin_settings.backend_url,
        username=tenant.user_username,
        password=tenant.user_password,
        domain=admin_settings.domain,
        options={
            "availability_zone": tenant.availability_zone,
            "tenant_id": tenant.backend_id,
        },
    )

    if admin_settings.options.get("console_type"):
        service_settings.options["console_type"] = admin_settings.options.get(
            "console_type"
        )
        service_settings.save()

    if admin_settings.options.get("config_drive"):
        service_settings.options["config_drive"] = admin_settings.options[
            "config_drive"
        ]
        service_settings.save()


def update_service_settings(sender, instance, created=False, **kwargs):
    tenant = instance

    if created or not (
        {"name", "backend_id", "internal_network_id", "external_network_id"}
        & set(tenant.tracker.changed())
    ):
        return

    try:
        service_settings = structure_models.ServiceSettings.objects.get(
            scope=tenant, type=apps.OpenStackTenantConfig.service_name
        )
    except structure_models.ServiceSettings.DoesNotExist:
        return
    except structure_models.ServiceSettings.MultipleObjectsReturned:
        return
    else:
        service_settings.options["internal_network_id"] = tenant.internal_network_id
        service_settings.options["external_network_id"] = tenant.external_network_id
        service_settings.options["tenant_id"] = tenant.backend_id
        service_settings.name = tenant.name
        service_settings.save()


def mark_private_settings_as_erred_if_tenant_creation_failed(
    sender, instance, name, source, target, **kwargs
):
    if target == StateMixin.States.ERRED and source == StateMixin.States.CREATING:
        try:
            service_settings = structure_models.ServiceSettings.objects.get(
                scope=instance, type=apps.OpenStackTenantConfig.service_name
            )
        except structure_models.ServiceSettings.DoesNotExist:
            return
        except structure_models.ServiceSettings.MultipleObjectsReturned:
            return
        else:
            service_settings.set_erred()
            service_settings.error_message = "Failed to create tenant: %s." % instance
            service_settings.save(update_fields=["state", "error_message"])


def sync_private_settings_quota_limit_with_tenant_quotas(
    sender, instance, created=False, **kwargs
):
    quota = instance
    if not isinstance(quota.scope, openstack_models.Tenant):
        return

    for private_settings in structure_models.ServiceSettings.objects.filter(
        scope=quota.scope
    ):
        private_settings.set_quota_limit(quota.name, quota.value)


def sync_private_settings_quota_usage_with_tenant_quotas(
    sender, instance, created=False, **kwargs
):
    quota = instance
    if not isinstance(quota.scope, openstack_models.Tenant):
        return

    usage = quota.scope.get_quota_usage(quota.name)

    for private_settings in structure_models.ServiceSettings.objects.filter(
        scope=quota.scope
    ):
        private_settings.set_quota_usage(quota.name, usage)


def delete_volume_type_quotas_from_private_service_settings(sender, instance, **kwargs):
    quota = instance

    if not quota.name.startswith("gigabytes_"):
        return

    if not isinstance(quota.scope, openstack_models.Tenant):
        return

    tenant = quota.scope
    private_settings = structure_models.ServiceSettings.objects.filter(scope=tenant)
    QuotaLimit.objects.filter(scope__in=private_settings, name=quota.name).delete()


def sync_security_group_rule_property_when_resource_is_updated_or_created(
    sender, instance, created=False, **kwargs
):
    rule = instance

    try:
        service_settings = structure_models.ServiceSettings.objects.get(
            scope=rule.security_group.tenant,
            type=apps.OpenStackTenantConfig.service_name,
        )
    except (
        django_exceptions.ObjectDoesNotExist,
        django_exceptions.MultipleObjectsReturned,
    ):
        return

    try:
        security_group = models.SecurityGroup.objects.get(
            settings=service_settings, backend_id=rule.security_group.backend_id
        )
    except django_exceptions.ObjectDoesNotExist:
        return

    if not rule.backend_id:
        return

    remote_group = None
    if rule.remote_group and rule.remote_group.backend_id:
        try:
            remote_group = models.SecurityGroup.objects.get(
                settings=service_settings, backend_id=rule.remote_group.backend_id
            )
        except django_exceptions.ObjectDoesNotExist:
            pass

    models.SecurityGroupRule.objects.update_or_create(
        security_group=security_group,
        backend_id=rule.backend_id,
        defaults=dict(
            ethertype=rule.ethertype,
            direction=rule.direction,
            protocol=rule.protocol,
            from_port=rule.from_port,
            to_port=rule.to_port,
            cidr=rule.cidr,
            description=rule.description,
            remote_group=remote_group,
        ),
    )


def sync_security_group_rule_on_delete(sender, instance, **kwargs):
    rule = instance

    if not rule.backend_id:
        return

    try:
        service_settings = structure_models.ServiceSettings.objects.get(
            scope=rule.security_group.tenant,
            type=apps.OpenStackTenantConfig.service_name,
        )
    except (
        django_exceptions.ObjectDoesNotExist,
        django_exceptions.MultipleObjectsReturned,
    ):
        return

    try:
        security_group = models.SecurityGroup.objects.get(
            settings=service_settings, backend_id=rule.security_group.backend_id
        )
    except django_exceptions.ObjectDoesNotExist:
        return

    try:
        rule = models.SecurityGroupRule.objects.get(
            security_group=security_group, backend_id=rule.backend_id
        )
    except django_exceptions.ObjectDoesNotExist:
        return
    else:
        rule.delete()


def sync_server_group_property_when_resource_is_updated_or_created(
    sender, instance, created=False, **kwargs
):
    server_group_instance = instance

    if not server_group_instance.backend_id:
        return

    try:
        service_settings = structure_models.ServiceSettings.objects.get(
            scope=server_group_instance.tenant,
            type=apps.OpenStackTenantConfig.service_name,
        )
    except (
        django_exceptions.ObjectDoesNotExist,
        django_exceptions.MultipleObjectsReturned,
    ):
        return

    models.ServerGroup.objects.update_or_create(
        backend_id=server_group_instance.backend_id,
        settings=service_settings,
        defaults=dict(
            name=server_group_instance.name,
            policy=server_group_instance.policy,
            settings=service_settings,
        ),
    )


def sync_server_group_property_on_delete(sender, instance, **kwargs):
    server_group_instance = instance

    if not server_group_instance.backend_id:
        return

    try:
        service_settings = structure_models.ServiceSettings.objects.get(
            scope=server_group_instance.tenant,
            type=apps.OpenStackTenantConfig.service_name,
        )
    except (
        django_exceptions.ObjectDoesNotExist,
        django_exceptions.MultipleObjectsReturned,
    ):
        return

    try:
        server_group = models.ServerGroup.objects.get(
            settings=service_settings, backend_id=server_group_instance.backend_id
        )
    except django_exceptions.ObjectDoesNotExist:
        return

    server_group.delete()
