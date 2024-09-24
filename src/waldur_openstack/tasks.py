import logging

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from waldur_core.core import models as core_models
from waldur_core.core import tasks as core_tasks
from waldur_core.core import utils as core_utils
from waldur_core.quotas import exceptions as quotas_exceptions
from waldur_core.structure import tasks as structure_tasks
from waldur_core.structure.registry import get_resource_type
from waldur_openstack.backend import OpenStackBackend

from . import log, models, serializers, signals

logger = logging.getLogger(__name__)


class TenantCreateErrorTask(core_tasks.ErrorStateTransitionTask):
    def execute(self, tenant):
        super().execute(tenant)
        # Delete network and subnet if they were not created on backend,
        # mark as erred if they were created
        network = tenant.networks.first()
        subnet = network.subnets.first()
        if subnet.state == models.SubNet.States.CREATION_SCHEDULED:
            subnet.delete()
        else:
            super().execute(subnet)
        if network.state == models.Network.States.CREATION_SCHEDULED:
            network.delete()
        else:
            super().execute(network)


class TenantCreateSuccessTask(core_tasks.StateTransitionTask):
    def execute(self, tenant):
        network = tenant.networks.first()
        subnet = network.subnets.first()
        self.state_transition(network, "set_ok")
        self.state_transition(subnet, "set_ok")
        self.state_transition(tenant, "set_ok")

        from . import executors

        executors.TenantPullExecutor.execute(tenant)
        return super().execute(tenant)


class TenantPullQuotas(core_tasks.BackgroundTask):
    name = "openstack.TenantPullQuotas"

    def is_equal(self, other_task):
        return self.name == other_task.get("name")

    def run(self):
        from . import executors

        for tenant in models.Tenant.objects.filter(state=models.Tenant.States.OK):
            executors.TenantPullQuotasExecutor.execute(tenant)


class SendSignalTenantPullSucceeded(core_tasks.Task):
    @classmethod
    def get_description(cls, *args, **kwargs):
        return "Send tenant_pull_succeeded signal."

    def execute(self, tenant):
        signals.tenant_pull_succeeded.send(models.Tenant, instance=tenant)


@shared_task(name="openstack.mark_as_erred_old_tenants_in_deleting_state")
def mark_as_erred_old_tenants_in_deleting_state():
    models.Tenant.objects.filter(
        modified__lte=timezone.now() - timezone.timedelta(days=1),
        state=models.Tenant.States.DELETING,
    ).update(
        state=models.Tenant.States.ERRED,
        error_message="Deletion error. Deleting took more than a day.",
    )


@shared_task
def check_existence_of_tenant(serialized_tenant):
    tenant = core_utils.deserialize_instance(serialized_tenant)
    backend = tenant.get_backend()

    if backend.does_tenant_exist_in_backend(tenant) is False:
        raise Exception(f"Tenant {tenant} does not exist in backend.")


@shared_task
def mark_tenant_as_deleted(serialized_tenant):
    tenant = core_utils.deserialize_instance(serialized_tenant)
    tenant.set_erred()
    tenant.save()

    signals.tenant_does_not_exist_in_backend.send(models.Tenant, instance=tenant)


class SetInstanceOKTask(core_tasks.StateTransitionTask):
    """Additionally mark or related floating IPs as free"""

    def pre_execute(self, instance):
        self.kwargs["state_transition"] = "set_ok"
        self.kwargs["action"] = ""
        self.kwargs["action_details"] = {}
        super().pre_execute(instance)

    def execute(self, instance, *args, **kwargs):
        super().execute(instance)
        instance.floating_ips.update(state=models.FloatingIP.States.OK)


class SetInstanceErredTask(core_tasks.ErrorStateTransitionTask):
    """Mark instance as erred and delete resources that were not created."""

    def execute(self, instance):
        super().execute(instance)

        # delete volumes if they were not created on backend,
        # mark as erred if creation was started, but not ended,
        # leave as is, if they are OK.
        for volume in instance.volumes.all():
            if volume.state == models.Volume.States.CREATION_SCHEDULED:
                volume.delete()
            elif volume.state == models.Volume.States.OK:
                pass
            else:
                volume.set_erred()
                volume.save(update_fields=["state"])

        # set instance floating IPs as free, delete not created ones.
        instance.floating_ips.filter(backend_id="").delete()
        instance.floating_ips.update(state=models.FloatingIP.States.OK)


class SetBackupErredTask(core_tasks.ErrorStateTransitionTask):
    """Mark DR backup and all related resources that are not in state OK as Erred"""

    def execute(self, backup):
        super().execute(backup)
        for snapshot in backup.snapshots.all():
            # If snapshot creation was not started - delete it from waldur DB.
            if snapshot.state == models.Snapshot.States.CREATION_SCHEDULED:
                snapshot.decrease_backend_quotas_usage()
                snapshot.delete()
            else:
                snapshot.set_erred()
                snapshot.save(update_fields=["state"])

        # Deactivate schedule if its backup become erred.
        schedule = backup.backup_schedule
        if schedule:
            schedule.error_message = f"Failed to execute backup schedule for {backup.instance}. Error: {backup.error_message}"
            schedule.is_active = False
            schedule.save()


class DeleteIncompleteInstanceTask(core_tasks.Task):
    def execute(self, instance):
        with transaction.atomic():
            scopes = (
                [instance] + list(instance.volumes.all()) + list(instance.floating_ips)
            )
            for scope in scopes:
                if not scope.backend_id:
                    scope.decrease_backend_quotas_usage()


class ForceDeleteBackupTask(core_tasks.DeletionTask):
    def execute(self, backup):
        backup.snapshots.all().delete()
        super().execute(backup)


class VolumeExtendErredTask(core_tasks.ErrorStateTransitionTask):
    """Mark volume and its instance as erred on fail"""

    def execute(self, volume):
        super().execute(volume)
        if volume.instance is not None:
            super().execute(volume.instance)


class BaseScheduleTask(core_tasks.BackgroundTask):
    """
    This task has several important caveats to consider.

    1. If user has decreased value of maximal_number_of_resources attribute,
       but exceeding resources have been already created, we would try to automatically delete
       exceeding resources before creating new resources.
       However, if new resource creation fails, old resources cannot be restored.

       Therefore, it is strongly advised to modify value of maximal_number_of_resources attribute very carefully.
       Also it is better to delete exceeding resources manually instead of relying on automatic deletion
       so that it is easier to explicitly select resources to be removed.

    2. _remove_exceeding_resources method orders resources by value of kept_until attribute in ASC order.
       It assumes that NULL values come *last* with ascending sort order.
       Therefore it would work correctly only in PostgreSQL.
       It would not work correctly in MySQL because in MySQL NULL values come *first*.

    3. Value of kept_until attribute is ignored as long as there are exceeding resources.
       It means that existing resources are deleted even if it is requested to be kept forever.
       Essentially, retention_time and maximal_number_of_resources attributes are mutually exclusive.

       Consider, for example, case when value of maximal_number_of_resources is 3 and there are 6 resources,
       out of which 2 with non-null value of kept_until attribute and 4 resources to be kept forever.
       As you can see, there are 3 exceeding resources, which should be removed.

       Then, both 2 first resources would be deleted, and 1 resource to be kept forever is deleted as well.
       Please note that last resource for deletion is chosen by value of *created* attribute.
       It means that oldest resource is selected for deletion.

    4. Database records for resources are created and deleted synchronously,
       but actual backend API task are scheduled asynchronously.
       Therefore, next iteration of schedule task does not wait
       until previous iteration tasks are completed.
       That's why there may several concurrent execution of the same schedule.

    5. Actual execution of schedule depends on number of Celery workers and their load.
       For example, even if schedule is expected to create new resources each hour,
       but all Celery workers have been overloaded for 2 hours, only one resource would be created.

    6. Schedule is disabled as long as resource quota is exceeded.
       Schedule is not reactivated automatically whenever quota limit
       is increased or quota usage is decreased.
       Instead it is expected that user would manually reactivate schedule in this case.

    7. Schedule is skipped and new resources are not created as long as schedule is disabled.
    """

    model = NotImplemented
    resource_attribute = NotImplemented

    def is_equal(self, other_task):
        return self.name == other_task.get("name")

    @transaction.atomic()
    def run(self):
        schedules = self.model.objects.filter(
            is_active=True, next_trigger_at__lt=timezone.now()
        )
        for schedule in schedules:
            existing_resources = self._get_resources(schedule)
            if (
                schedule.maximal_number_of_resources > 0
                and existing_resources.count() >= schedule.maximal_number_of_resources
            ):
                self._schedule_exceeding_resources_deletion(
                    schedule, existing_resources
                )
                logger.debug(
                    "Skipping schedule %s because number of resources %s has reached limit %s.",
                    schedule,
                    existing_resources,
                    schedule.maximal_number_of_resources,
                )
                continue

            kept_until = None
            if schedule.retention_time:
                kept_until = timezone.now() + timezone.timedelta(
                    days=schedule.retention_time
                )

            try:
                # Value of call_count attribute is used as suffix of new resource name
                schedule.call_count += 1
                schedule.save()
                resource = self._create_resource(schedule, kept_until=kept_until)
            except quotas_exceptions.QuotaValidationError as e:
                message = (
                    f'Failed to schedule "{self.model.__name__}" creation. Error: {e}'
                )
                logger.debug(
                    f"Resource schedule (PK: {schedule.pk}), (Name: {schedule.name}) execution failed. {message}"
                )
                schedule.is_active = False
                schedule.error_message = message
                schedule.save()
            else:
                executor = self._get_create_executor()
                executor.execute(resource, is_heavy_task=True)
                schedule.update_next_trigger_at()
                schedule.save()

    def _schedule_exceeding_resources_deletion(self, schedule, existing_resources):
        deleting_states = Q(state=core_models.StateMixin.States.DELETION_SCHEDULED) | Q(
            state=core_models.StateMixin.States.DELETING
        )

        terminal_states = Q(state=core_models.StateMixin.States.OK) | Q(
            state=core_models.StateMixin.States.ERRED
        )

        if existing_resources.filter(deleting_states).exists():
            logger.debug(
                "Deletion of exceeding resources for schedule %s is pending.", schedule
            )
            return

        total = existing_resources.count()
        amount_to_remove = max(1, total - schedule.maximal_number_of_resources)
        self._log_backup_cleanup(schedule, amount_to_remove, total)

        resources = existing_resources.filter(terminal_states).order_by(
            "kept_until", "created"
        )
        resources_to_remove = resources[:amount_to_remove]
        executor = self._get_delete_executor()
        for resource in resources_to_remove:
            executor.execute(resource)

    def _log_backup_cleanup(self, schedule, amount_to_remove, resources_count):
        raise NotImplementedError()

    def _create_resource(self, schedule, kept_until):
        raise NotImplementedError()

    def _get_create_executor(self):
        raise NotImplementedError()

    def _get_delete_executor(self):
        raise NotImplementedError()

    def _get_resources(self, schedule):
        return getattr(schedule, self.resource_attribute)


class ScheduleBackups(BaseScheduleTask):
    name = "openstack.ScheduleBackups"
    model = models.BackupSchedule
    resource_attribute = "backups"

    @transaction.atomic()
    def _create_resource(self, schedule, kept_until):
        backup = models.Backup.objects.create(
            name=f"Backup#{schedule.call_count} of {schedule.instance.name}",
            description='Scheduled backup of instance "%s"' % schedule.instance,
            service_settings=schedule.instance.service_settings,
            tenant=schedule.instance.tenant,
            project=schedule.instance.project,
            instance=schedule.instance,
            backup_schedule=schedule,
            metadata=serializers.BackupSerializer.get_backup_metadata(
                schedule.instance
            ),
            kept_until=kept_until,
        )
        serializers.BackupSerializer.create_backup_snapshots(backup)
        return backup

    def _get_create_executor(self):
        from . import executors

        return executors.BackupCreateExecutor

    def _get_delete_executor(self):
        from . import executors

        return executors.BackupDeleteExecutor

    def _log_backup_cleanup(self, schedule, amount_to_remove, resources_count):
        message_template = (
            'Maximum resource count "%s" has been reached.'
            '"%s" from "%s" resources are going to be removed.'
        )
        log.event_logger.openstack_backup_schedule.info(
            message_template
            % (schedule.maximal_number_of_resources, amount_to_remove, resources_count),
            event_type="resource_backup_schedule_cleaned_up",
            event_context={"resource": schedule.instance, "backup_schedule": schedule},
        )


class BaseDeleteExpiredResourcesTask(core_tasks.BackgroundTask):
    model = NotImplemented

    def is_equal(self, other_task):
        return self.name == other_task.get("name")

    def _get_executor(self):
        raise NotImplementedError()

    @transaction.atomic
    def run(self):
        executor = self._get_delete_executor()
        resources = self.model.objects.filter(
            kept_until__lt=timezone.now(), state=core_models.StateMixin.States.OK
        )
        for resource in resources:
            executor.execute(resource)


class DeleteExpiredBackups(BaseDeleteExpiredResourcesTask):
    name = "openstack.DeleteExpiredBackups"
    model = models.Backup

    def _get_delete_executor(self):
        from . import executors

        return executors.BackupDeleteExecutor


class ScheduleSnapshots(BaseScheduleTask):
    name = "openstack.ScheduleSnapshots"
    model = models.SnapshotSchedule
    resource_attribute = "snapshots"

    @transaction.atomic()
    def _create_resource(self, schedule: models.SnapshotSchedule, kept_until):
        snapshot = models.Snapshot.objects.create(
            name=f"Snapshot#{schedule.call_count} of {schedule.source_volume.name}",
            description='Scheduled snapshot of volume "%s"' % schedule.source_volume,
            service_settings=schedule.source_volume.service_settings,
            tenant=schedule.source_volume.tenant,
            project=schedule.source_volume.project,
            source_volume=schedule.source_volume,
            snapshot_schedule=schedule,
            size=schedule.source_volume.size,
            kept_until=kept_until,
        )
        snapshot.increase_backend_quotas_usage(validate=True)
        return snapshot

    def _get_create_executor(self):
        from . import executors

        return executors.SnapshotCreateExecutor

    def _get_delete_executor(self):
        from . import executors

        return executors.SnapshotDeleteExecutor

    def _log_backup_cleanup(
        self, schedule: models.SnapshotSchedule, amount_to_remove, resources_count
    ):
        message_template = (
            'Maximum resource count "%s" has been reached.'
            '"%s" from "%s" resources are going to be removed.'
        )
        log.event_logger.openstack_snapshot_schedule.info(
            message_template
            % (schedule.maximal_number_of_resources, amount_to_remove, resources_count),
            event_type="resource_snapshot_schedule_cleaned_up",
            event_context={
                "resource": schedule.source_volume,
                "snapshot_schedule": schedule,
            },
        )


class DeleteExpiredSnapshots(BaseDeleteExpiredResourcesTask):
    name = "openstack.DeleteExpiredSnapshots"
    model = models.Snapshot

    def _get_delete_executor(self):
        from . import executors

        return executors.SnapshotDeleteExecutor


class LimitedPerTypeThrottleMixin:
    def get_limit(self, resource):
        plugin_settings = getattr(settings, "WALDUR_OPENSTACK", {})
        limit_per_type = plugin_settings.get("MAX_CONCURRENT_PROVISION", {})
        model_name = get_resource_type(resource)
        default_limit = limit_per_type.get(model_name)
        tenant: models.Tenant = resource.tenant
        if tenant:
            key = f"max_concurrent_provision_{resource._meta.object_name.lower()}"
            settings_limit = tenant.service_settings.options.get(key)
            if settings_limit:
                return settings_limit
        return default_limit


class ThrottleProvisionTask(
    LimitedPerTypeThrottleMixin, structure_tasks.ThrottleProvisionTask
):
    pass


class ThrottleProvisionStateTask(
    LimitedPerTypeThrottleMixin, structure_tasks.ThrottleProvisionStateTask
):
    pass


class TenantResourcesPullTask(structure_tasks.BackgroundPullTask):
    def pull(self, tenant: models.Tenant):
        backend = OpenStackBackend(tenant.service_settings)
        backend.pull_tenant_instances(tenant)
        backend.pull_tenant_volumes(tenant)
        backend.pull_tenant_snapshots(tenant)


class TenantResourcesListPullTask(structure_tasks.BackgroundListPullTask):
    name = "openstack.tenant_resources_list_pull_task"
    pull_task = TenantResourcesPullTask
    model = models.Tenant


class TenantSubresourcesPullTask(structure_tasks.BackgroundPullTask):
    def pull(self, tenant: models.Tenant):
        backend = OpenStackBackend(tenant.service_settings)
        backend.pull_tenant_security_groups(tenant)
        backend.pull_tenant_server_groups(tenant)
        backend.pull_tenant_floating_ips(tenant)
        backend.pull_tenant_networks(tenant)
        backend.pull_tenant_subnets(tenant)
        backend.pull_tenant_routers(tenant)
        backend.pull_tenant_ports(tenant)


class TenantSubresourcesListPullTask(structure_tasks.BackgroundListPullTask):
    name = "openstack.tenant_subresources_list_pull_task"
    pull_task = TenantSubresourcesPullTask
    model = models.Tenant


class TenantPropertiesPullTask(structure_tasks.BackgroundPullTask):
    def pull(self, tenant: models.Tenant):
        backend = OpenStackBackend(tenant.service_settings)
        backend.pull_tenant_volume_types(tenant)
        backend.pull_tenant_volume_availability_zones(tenant)
        backend.pull_tenant_instance_availability_zones(tenant)
        backend.pull_tenant_flavors(tenant)
        backend.pull_tenant_images(tenant)


class TenantPropertiesListPullTask(structure_tasks.BackgroundListPullTask):
    name = "openstack.tenant_properties_list_pull_task"
    pull_task = TenantPropertiesPullTask
    model = models.Tenant
