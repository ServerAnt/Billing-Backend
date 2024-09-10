import uuid
from unittest import mock

from celery import Signature
from cinderclient import exceptions as cinder_exceptions
from ddt import data, ddt
from django.conf import settings
from django.test import override_settings
from novaclient import exceptions as nova_exceptions
from rest_framework import status, test

from waldur_core.core.utils import serialize_instance
from waldur_core.structure.tests import factories as structure_factories
from waldur_mastermind.common import utils as common_utils
from waldur_openstack.openstack.models import FloatingIP, Port
from waldur_openstack.openstack.tests import (
    factories as openstack_factories,
)
from waldur_openstack.openstack.tests.unittests import test_backend
from waldur_openstack.openstack.utils import volume_type_name_to_quota_name
from waldur_openstack.openstack_base.exceptions import OpenStackBackendError
from waldur_openstack.openstack_tenant import executors, models, views
from waldur_openstack.openstack_tenant.tasks import LimitedPerTypeThrottleMixin
from waldur_openstack.openstack_tenant.tests import factories, fixtures, helpers
from waldur_openstack.openstack_tenant.tests.helpers import (
    override_openstack_tenant_settings,
)


class InstanceFilterTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.client.force_authenticate(user=self.fixture.owner)
        self.url = factories.InstanceFactory.get_list_url()

    def test_filter_instance_by_valid_volume_uuid(self):
        self.fixture.instance
        response = self.client.get(
            self.url, {"attach_volume_uuid": self.fixture.volume.uuid.hex}
        )
        self.assertEqual(len(response.data), 1)

    def test_filter_instance_by_invalid_volume_uuid(self):
        self.fixture.instance
        response = self.client.get(self.url, {"attach_volume_uuid": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_instance_by_availability_zone(self):
        vm_az = self.fixture.instance_availability_zone
        vm = self.fixture.instance
        vm.availability_zone = vm_az
        vm.save()

        volume_az = self.fixture.volume_availability_zone
        volume = self.fixture.volume
        volume.availability_zone = volume_az
        volume.save()

        private_settings = self.fixture.openstack_tenant_service_settings
        shared_settings = private_settings.scope.service_settings

        shared_settings.options = {
            "valid_availability_zones": {vm_az.name: volume_az.name}
        }
        shared_settings.save()

        response = self.client.get(self.url, {"attach_volume_uuid": volume.uuid.hex})
        self.assertEqual(len(response.data), 1)


@ddt
class InstanceCreateTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.tenant = self.fixture.tenant
        self.openstack_settings = self.fixture.openstack_tenant_service_settings
        self.openstack_settings.options = {"external_network_id": uuid.uuid4().hex}
        self.openstack_settings.save()
        self.project = self.fixture.project
        self.customer = self.fixture.customer
        self.image = openstack_factories.ImageFactory(
            settings=self.tenant.service_settings, min_disk=10240, min_ram=1024
        )
        self.flavor = openstack_factories.FlavorFactory(
            settings=self.tenant.service_settings
        )
        self.subnet = self.fixture.subnet
        self.volume_type = openstack_factories.VolumeTypeFactory(
            settings=self.tenant.service_settings
        )

    def create_instance(self, post_data=None):
        user = self.fixture.owner
        view = views.MarketplaceInstanceViewSet.as_view({"post": "create"})
        response = common_utils.create_request(view, user, post_data)
        return response

    def get_valid_data(self, **extra):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        default = {
            "service_settings": factories.OpenStackTenantServiceSettingsFactory.get_url(
                self.openstack_settings
            ),
            "project": structure_factories.ProjectFactory.get_url(self.project),
            "flavor": openstack_factories.FlavorFactory.get_url(self.flavor),
            "image": openstack_factories.ImageFactory.get_url(self.image),
            "name": "valid-name",
            "system_volume_size": self.image.min_disk,
            "ports": [{"subnet": subnet_url}],
        }
        default.update(extra)
        return default

    def test_instance_cannot_be_created_if_volume_exceeds_volume_type_quota(self):
        quota_name = volume_type_name_to_quota_name(self.volume_type.name)
        self.openstack_settings.set_quota_limit(quota_name, 100)
        self.openstack_settings.set_quota_usage(quota_name, 100)
        response = self.create_instance(
            self.get_valid_data(
                system_volume_type=openstack_factories.VolumeTypeFactory.get_url(
                    self.volume_type
                ),
                data_volume_type=openstack_factories.VolumeTypeFactory.get_url(
                    self.volume_type
                ),
            )
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quotas_update(self):
        response = self.create_instance(self.get_valid_data())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        Quotas = self.openstack_settings.Quotas
        self.assertEqual(
            self.openstack_settings.get_quota_usage(Quotas.ram), instance.ram
        )
        self.assertEqual(
            self.openstack_settings.get_quota_usage(Quotas.storage), instance.disk
        )
        self.assertEqual(
            self.openstack_settings.get_quota_usage(Quotas.vcpu), instance.cores
        )
        self.assertEqual(self.openstack_settings.get_quota_usage(Quotas.instances), 1)

        self.assertEqual(self.tenant.get_quota_usage(Quotas.ram), instance.ram)
        self.assertEqual(self.tenant.get_quota_usage(Quotas.storage), instance.disk)
        self.assertEqual(self.tenant.get_quota_usage(Quotas.vcpu), instance.cores)
        self.assertEqual(self.tenant.get_quota_usage(Quotas.instances), 1)

    def test_project_quotas_updated_when_instance_is_created(self):
        response = self.create_instance(self.get_valid_data())
        instance = models.Instance.objects.get(uuid=response.data["uuid"])

        self.assertEqual(self.project.get_quota_usage("os_cpu_count"), instance.cores)
        self.assertEqual(self.project.get_quota_usage("os_ram_size"), instance.ram)
        self.assertEqual(self.project.get_quota_usage("os_storage_size"), instance.disk)

    def test_customer_quotas_updated_when_instance_is_created(self):
        response = self.create_instance(self.get_valid_data())
        instance = models.Instance.objects.get(uuid=response.data["uuid"])

        self.assertEqual(self.customer.get_quota_usage("os_cpu_count"), instance.cores)
        self.assertEqual(self.customer.get_quota_usage("os_ram_size"), instance.ram)
        self.assertEqual(
            self.customer.get_quota_usage("os_storage_size"), instance.disk
        )

    def test_project_quotas_updated_when_instance_is_deleted(self):
        response = self.create_instance(self.get_valid_data())
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        instance.delete()

        self.assertEqual(self.project.get_quota_usage("os_cpu_count"), 0)
        self.assertEqual(self.project.get_quota_usage("os_ram_size"), 0)
        self.assertEqual(self.project.get_quota_usage("os_storage_size"), 0)

    def test_customer_quotas_updated_when_instance_is_deleted(self):
        response = self.create_instance(self.get_valid_data())
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        instance.delete()

        self.assertEqual(self.customer.get_quota_usage("os_cpu_count"), 0)
        self.assertEqual(self.customer.get_quota_usage("os_ram_size"), 0)
        self.assertEqual(self.customer.get_quota_usage("os_storage_size"), 0)

    @data("instances")
    def test_quota_validation(self, quota_name):
        self.openstack_settings.set_quota_limit(quota_name, 0)
        response = self.create_instance(self.get_valid_data())
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_provision_instance(self):
        response = self.create_instance(self.get_valid_data())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_user_can_define_instance_subnets(self):
        subnet = self.fixture.subnet
        data = self.get_valid_data(
            ports=[{"subnet": openstack_factories.SubNetFactory.get_url(subnet)}]
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        self.assertTrue(Port.objects.filter(subnet=subnet, instance=instance).exists())

    def test_user_cannot_assign_subnet_from_other_settings_to_instance(self):
        data = self.get_valid_data(
            ports=[{"subnet": openstack_factories.SubNetFactory.get_url()}]
        )
        response = self.create_instance(data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_define_instance_floating_ips(self):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        floating_ip = self.fixture.floating_ip
        floating_ip.state = models.FloatingIP.States.OK
        floating_ip.save()
        data = self.get_valid_data(
            floating_ips=[
                {
                    "subnet": subnet_url,
                    "url": openstack_factories.FloatingIPFactory.get_url(floating_ip),
                }
            ],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        self.assertIn(floating_ip, instance.floating_ips)

    def test_service_settings_should_have_external_network_id(self):
        self.openstack_settings.options = {"external_network_id": "invalid"}
        self.openstack_settings.save()

        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        data = self.get_valid_data(floating_ips=[{"subnet": subnet_url}])

        response = self.create_instance(data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_assign_floating_ip_from_other_settings_to_instance(self):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        floating_ip = openstack_factories.FloatingIPFactory()
        data = self.get_valid_data(
            floating_ips=[
                {
                    "subnet": subnet_url,
                    "url": openstack_factories.FloatingIPFactory.get_url(floating_ip),
                }
            ],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_assign_floating_ip_to_disconnected_subnet(self):
        disconnected_subnet = openstack_factories.SubNetFactory(
            tenant=self.fixture.tenant
        )
        disconnected_subnet_url = openstack_factories.SubNetFactory.get_url(
            disconnected_subnet
        )
        floating_ip = self.fixture.floating_ip
        data = self.get_valid_data(
            floating_ips=[
                {
                    "subnet": disconnected_subnet_url,
                    "url": openstack_factories.FloatingIPFactory.get_url(floating_ip),
                }
            ],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_use_floating_ip_assigned_to_other_instance(self):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        port = openstack_factories.PortFactory(subnet=self.subnet)
        floating_ip = openstack_factories.FloatingIPFactory(
            tenant=self.tenant,
            runtime_state="ACTIVE",
            port=port,
        )
        data = self.get_valid_data(
            floating_ips=[
                {
                    "subnet": subnet_url,
                    "url": openstack_factories.FloatingIPFactory.get_url(floating_ip),
                }
            ],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("floating_ips", response.data)

    def test_user_can_assign_active_floating_ip(self):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        floating_ip = openstack_factories.FloatingIPFactory(
            tenant=self.tenant, runtime_state="ACTIVE", state=FloatingIP.States.OK
        )
        data = self.get_valid_data(
            floating_ips=[
                {
                    "subnet": subnet_url,
                    "url": openstack_factories.FloatingIPFactory.get_url(floating_ip),
                }
            ],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_user_can_allocate_floating_ip(self):
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        self.fixture.floating_ip.runtime_state = "ACTIVE"
        self.fixture.floating_ip.save()
        data = self.get_valid_data(
            floating_ips=[{"subnet": subnet_url}],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        self.assertEqual(instance.floating_ips.count(), 1)

    def test_user_cannot_allocate_floating_ip_if_quota_limit_is_reached(self):
        self.tenant.set_quota_limit(self.tenant.Quotas.floating_ip_count, 0)
        subnet_url = openstack_factories.SubNetFactory.get_url(self.subnet)
        data = self.get_valid_data(
            floating_ips=[{"subnet": subnet_url}],
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_not_create_instance_without_ports(self):
        data = self.get_valid_data()
        del data["ports"]

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_not_create_instance_with_empty_ports_list(self):
        data = self.get_valid_data()
        data["ports"] = []

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_show_volume_type_in_instance_serializer(self):
        instance = factories.InstanceFactory()
        volume_type = openstack_factories.VolumeTypeFactory(
            settings=instance.tenant.service_settings
        )
        factories.VolumeFactory(
            service_settings=instance.service_settings,
            project=instance.project,
            instance=instance,
            type=volume_type,
            name="test-volume",
        )
        url = factories.InstanceFactory.get_url(instance)
        staff = structure_factories.UserFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        serialized_volume = [
            volume
            for volume in response.data["volumes"]
            if volume["name"] == "test-volume"
        ][0]
        self.assertEqual(serialized_volume["type_name"], volume_type.name)

    def test_user_can_define_instance_availability_zone(self):
        zone = self.fixture.instance_availability_zone
        data = self.get_valid_data(
            availability_zone=factories.InstanceAvailabilityZoneFactory.get_url(zone)
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])
        self.assertEqual(instance.availability_zone, zone)

    def test_availability_zone_should_be_available(self):
        zone = self.fixture.instance_availability_zone
        zone.available = False
        zone.save()
        data = self.get_valid_data(
            availability_zone=factories.InstanceAvailabilityZoneFactory.get_url(zone)
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_availability_zone_should_be_related_to_the_same_service_settings(self):
        zone = factories.InstanceAvailabilityZoneFactory()
        data = self.get_valid_data(
            availability_zone=factories.InstanceAvailabilityZoneFactory.get_url(zone)
        )

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_volume_AZ_should_be_matched_with_instance_AZ(self):
        # Arrange
        vm_az = self.fixture.instance_availability_zone
        volume_az = self.fixture.volume_availability_zone

        private_ss = self.fixture.openstack_tenant_service_settings
        shared_ss = private_ss.scope.service_settings

        shared_ss.options = {"valid_availability_zones": {vm_az.name: volume_az.name}}
        shared_ss.save()

        vm_az_url = factories.InstanceAvailabilityZoneFactory.get_url(vm_az)
        data = self.get_valid_data(availability_zone=vm_az_url)

        # Act
        response = self.create_instance(data)

        # Assert
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        instance = models.Instance.objects.get(uuid=response.data["uuid"])

        self.assertEqual(instance.availability_zone, vm_az)
        self.assertEqual(instance.volumes.first().availability_zone, volume_az)
        self.assertEqual(instance.volumes.last().availability_zone, volume_az)

    @override_openstack_tenant_settings(REQUIRE_AVAILABILITY_ZONE=True)
    def test_when_availability_zone_is_mandatory_and_exists_validation_fails(self):
        self.fixture.instance_availability_zone
        data = self.get_valid_data()

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @override_openstack_tenant_settings(REQUIRE_AVAILABILITY_ZONE=True)
    def test_when_availability_zone_is_mandatory_and_does_not_exist_validation_succeeds(
        self,
    ):
        data = self.get_valid_data()

        response = self.create_instance(data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @data("kt-experimental-ubuntu-18.04", "vm_name")
    def test_not_create_instance_with_invalid_name(self, name):
        data = self.get_valid_data()
        data["name"] = name
        response = self.create_instance(data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @data("test", "vm-name", "vm", "VM")
    def test_create_instance_with_valid_name(self, name):
        data = self.get_valid_data()
        data["name"] = name
        response = self.create_instance(data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


@ddt
class InstanceUpdateTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.instance = self.fixture.instance
        self.url = factories.InstanceFactory.get_url(self.instance)
        self.client.force_authenticate(user=self.fixture.owner)

    @data("kt-experimental-ubuntu-18.04", "vm_name")
    def test_update_instance_with_invalid_name(self, name):
        response = self.client.put(self.url, {"name": name})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @data("test", "vm-name", "vm", "VM")
    def test_update_instance_with_valid_name(self, name):
        response = self.client.put(self.url, {"name": name})
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(task_always_eager=True)
class InstanceDeleteTest(test_backend.BaseBackendTestCase):
    def setUp(self):
        super().setUp()
        self.instance = factories.InstanceFactory(
            state=models.Instance.States.OK,
            runtime_state=models.Instance.RuntimeStates.SHUTOFF,
            backend_id="VALID_ID",
        )
        self.instance.increase_backend_quotas_usage()
        self.mocked_nova.servers.get.side_effect = nova_exceptions.NotFound(code=404)
        views.MarketplaceInstanceViewSet.async_executor = False
        self.tenant = self.instance.service_settings.scope

    def tearDown(self):
        super().tearDown()
        views.MarketplaceInstanceViewSet.async_executor = True

    def mock_volumes(self, delete_data_volume=True):
        self.data_volume = self.instance.volumes.get(bootable=False)
        self.data_volume.backend_id = "DATA_VOLUME_ID"
        self.data_volume.state = models.Volume.States.OK
        self.data_volume.save()
        self.data_volume.increase_backend_quotas_usage()

        self.system_volume = self.instance.volumes.get(bootable=True)
        self.system_volume.backend_id = "SYSTEM_VOLUME_ID"
        self.system_volume.state = models.Volume.States.OK
        self.system_volume.save()
        self.system_volume.increase_backend_quotas_usage()

        def get_volume(backend_id):
            if not delete_data_volume and backend_id == self.data_volume.backend_id:
                mocked_volume = mock.Mock()
                mocked_volume.status = "available"
                return mocked_volume
            raise cinder_exceptions.NotFound(code=404)

        self.mocked_cinder.volumes.get.side_effect = get_volume

    def delete_instance(self, query_params=None, check_status_code=True):
        user = structure_factories.UserFactory(is_staff=True)
        view = views.MarketplaceInstanceViewSet.as_view({"delete": "destroy"})

        response = common_utils.delete_request(
            view, user, uuid=self.instance.uuid.hex, query_params=query_params
        )

        if check_status_code:
            self.assertEqual(
                response.status_code, status.HTTP_202_ACCEPTED, response.data
            )

        return response

    def assert_quota_usage(self, scope, name, value):
        self.assertEqual(scope.get_quota_usage(name), value)

    def test_nova_methods_are_called_if_instance_is_deleted_with_volumes(self):
        self.mock_volumes(True)
        self.delete_instance()

        self.mocked_nova.servers.delete.assert_called_once_with(
            self.instance.backend_id
        )
        self.mocked_nova.servers.get.assert_called_once_with(self.instance.backend_id)

    def test_database_models_deleted(self):
        self.mock_volumes(True)
        self.delete_instance()

        self.assertFalse(models.Instance.objects.filter(id=self.instance.id).exists())
        for volume in self.instance.volumes.all():
            self.assertFalse(models.Volume.objects.filter(id=volume.id).exists())

    def test_quotas_updated_if_instance_is_deleted_with_volumes(self):
        self.mock_volumes(True)
        self.delete_instance()

        self.instance.service_settings.refresh_from_db()

        for scope in (
            self.instance.service_settings,
            self.tenant,
        ):
            self.assert_quota_usage(scope, "instances", 0)
            self.assert_quota_usage(scope, "vcpu", 0)
            self.assert_quota_usage(scope, "ram", 0)

            self.assert_quota_usage(scope, "volumes", 0)
            self.assert_quota_usage(scope, "storage", 0)

    def test_backend_methods_are_called_if_instance_is_deleted_without_volumes(self):
        self.mock_volumes(False)
        self.delete_instance({"delete_volumes": False})

        nova = self.mocked_nova
        nova.volumes.delete_server_volume.assert_called_once_with(
            self.instance.backend_id, self.data_volume.backend_id
        )

        nova.servers.delete.assert_called_once_with(self.instance.backend_id)
        nova.servers.get.assert_called_once_with(self.instance.backend_id)

    def test_system_volume_is_deleted_but_data_volume_exists(self):
        self.mock_volumes(False)
        self.delete_instance({"delete_volumes": False})

        self.assertFalse(models.Instance.objects.filter(id=self.instance.id).exists())
        self.assertTrue(models.Volume.objects.filter(id=self.data_volume.id).exists())
        self.assertFalse(
            models.Volume.objects.filter(id=self.system_volume.id).exists()
        )

    def test_quotas_updated_if_instance_is_deleted_without_volumes(self):
        self.mock_volumes(False)
        self.delete_instance({"delete_volumes": False})

        settings = self.instance.service_settings
        settings.refresh_from_db()

        self.assert_quota_usage(settings, "instances", 0)
        self.assert_quota_usage(settings, "vcpu", 0)
        self.assert_quota_usage(settings, "ram", 0)

        self.assert_quota_usage(settings, "volumes", 1)
        self.assert_quota_usage(settings, "storage", self.data_volume.size)

    def test_instance_cannot_be_deleted_if_it_has_backups(self):
        self.instance = factories.InstanceFactory(
            state=models.Instance.States.OK,
            runtime_state=models.Instance.RuntimeStates.SHUTOFF,
            backend_id="VALID_ID",
        )
        factories.BackupFactory(instance=self.instance, state=models.Backup.States.OK)
        response = self.delete_instance(check_status_code=False)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT, response.data)

    def test_neutron_methods_are_called_if_instance_is_deleted_with_floating_ips(self):
        self.mock_volumes(False)
        fixture = fixtures.OpenStackTenantFixture()
        port = openstack_factories.PortFactory.create(
            instance=self.instance, subnet=fixture.subnet
        )
        floating_ip = openstack_factories.FloatingIPFactory.create(
            port=port, tenant=self.tenant
        )
        self.delete_instance(
            {
                "release_floating_ips": True,
                "delete_volumes": False,
            }
        )
        self.mocked_neutron.delete_floatingip.assert_called_once_with(
            floating_ip.backend_id
        )

    def test_neutron_methods_are_not_called_if_instance_does_not_have_any_floating_ips_yet(
        self,
    ):
        self.mock_volumes(False)
        self.delete_instance(
            {
                "release_floating_ips": True,
                "delete_volumes": False,
            }
        )
        self.assertEqual(self.mocked_neutron.delete_floatingip.call_count, 0)

    def test_neutron_methods_are_not_called_if_user_did_not_ask_for_floating_ip_removal_explicitly(
        self,
    ):
        self.mock_volumes(False)
        self.mocked_neutron.show_floatingip.return_value = {
            "floatingip": {"status": "DOWN"}
        }
        fixture = fixtures.OpenStackTenantFixture()
        port = openstack_factories.PortFactory.create(
            instance=self.instance, subnet=fixture.subnet
        )
        openstack_factories.FloatingIPFactory.create(port=port, tenant=self.tenant)
        self.delete_instance({"release_floating_ips": False, "delete_volumes": False})
        self.assertEqual(self.mocked_neutron.delete_floatingip.call_count, 0)

    def test_incomplete_instance_deletion_executor_produces_celery_signature(self):
        # Arrange
        self.instance.backend_id = None
        self.instance.save()

        # Act
        serialized_instance = serialize_instance(self.instance)
        signature = executors.InstanceDeleteExecutor.get_task_signature(
            self.instance, serialized_instance
        )

        # Assert
        self.assertIsInstance(signature, Signature)

    def test_delete_instance_via_openstack(self):
        staff = structure_factories.UserFactory(is_staff=True)
        self.client.force_authenticate(user=staff)
        url = factories.InstanceFactory.get_url(self.instance)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class InstanceCreateBackupSchedule(test.APITransactionTestCase):
    action_name = "create_backup_schedule"

    def setUp(self):
        self.user = structure_factories.UserFactory.create(is_staff=True)
        self.client.force_authenticate(user=self.user)
        self.instance = factories.InstanceFactory(state=models.Instance.States.OK)
        self.create_url = factories.InstanceFactory.get_url(
            self.instance, action=self.action_name
        )
        self.backup_schedule_data = {
            "name": "test schedule",
            "retention_time": 3,
            "schedule": "0 * * * *",
            "maximal_number_of_resources": 3,
        }

    def test_staff_can_create_backup_schedule(self):
        response = self.client.post(self.create_url, self.backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            response.data["retention_time"], self.backup_schedule_data["retention_time"]
        )
        self.assertEqual(
            response.data["maximal_number_of_resources"],
            self.backup_schedule_data["maximal_number_of_resources"],
        )
        self.assertEqual(
            response.data["schedule"], self.backup_schedule_data["schedule"]
        )

    def test_instance_should_have_bootable_volume(self):
        self.instance.volumes.filter(bootable=True).delete()
        response = self.client.post(self.create_url, self.backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_backup_schedule_default_state_is_OK(self):
        response = self.client.post(self.create_url, self.backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        backup_schedule = models.BackupSchedule.objects.first()
        self.assertIsNotNone(backup_schedule)
        self.assertEqual(backup_schedule.state, backup_schedule.States.OK)

    def test_backup_schedule_can_not_be_created_with_wrong_schedule(self):
        # wrong schedule:
        self.backup_schedule_data["schedule"] = "wrong schedule"
        response = self.client.post(self.create_url, self.backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(b"schedule", response.content)

    def test_backup_schedule_creation_with_correct_timezone(self):
        backupable = factories.InstanceFactory(state=models.Instance.States.OK)
        create_url = factories.InstanceFactory.get_url(
            backupable, action=self.action_name
        )
        backup_schedule_data = {
            "name": "test schedule",
            "retention_time": 3,
            "schedule": "0 * * * *",
            "timezone": "Europe/London",
            "maximal_number_of_resources": 3,
        }
        response = self.client.post(create_url, backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["timezone"], "Europe/London")

    def test_backup_schedule_creation_with_incorrect_timezone(self):
        backupable = factories.InstanceFactory(state=models.Instance.States.OK)
        create_url = factories.InstanceFactory.get_url(
            backupable, action=self.action_name
        )

        backup_schedule_data = {
            "name": "test schedule",
            "retention_time": 3,
            "schedule": "0 * * * *",
            "timezone": "incorrect",
            "maximal_number_of_resources": 3,
        }
        response = self.client.post(create_url, backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)

    def test_backup_schedule_creation_with_default_timezone(self):
        backupable = factories.InstanceFactory(state=models.Instance.States.OK)
        create_url = factories.InstanceFactory.get_url(
            backupable, action=self.action_name
        )
        backup_schedule_data = {
            "name": "test schedule",
            "retention_time": 3,
            "schedule": "0 * * * *",
            "maximal_number_of_resources": 3,
        }
        response = self.client.post(create_url, backup_schedule_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["timezone"], settings.TIME_ZONE)


class InstanceUpdatePortsTest(test.APITransactionTestCase):
    action_name = "update_ports"

    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.client.force_authenticate(user=self.fixture.admin)
        self.instance = self.fixture.instance
        self.url = factories.InstanceFactory.get_url(
            self.instance, action=self.action_name
        )

    def test_user_can_update_instance_ports(self):
        # instance had 2 ports
        ip_to_keep = openstack_factories.PortFactory(
            instance=self.instance, subnet=self.fixture.subnet
        )
        ip_to_delete = openstack_factories.PortFactory(instance=self.instance)
        # instance should be connected to new subnet
        subnet_to_connect = openstack_factories.SubNetFactory(
            tenant=self.fixture.tenant
        )

        response = self.client.post(
            self.url,
            data={
                "ports": [
                    {
                        "subnet": openstack_factories.SubNetFactory.get_url(
                            self.fixture.subnet
                        )
                    },
                    {
                        "subnet": openstack_factories.SubNetFactory.get_url(
                            subnet_to_connect
                        )
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(self.instance.ports.filter(pk=ip_to_keep.pk).exists())
        self.assertFalse(self.instance.ports.filter(pk=ip_to_delete.pk).exists())
        self.assertTrue(self.instance.ports.filter(subnet=subnet_to_connect).exists())

    def test_user_cannot_add_port_from_different_settings(self):
        subnet = openstack_factories.SubNetFactory()

        response = self.client.post(
            self.url,
            data={
                "ports": [
                    {"subnet": openstack_factories.SubNetFactory.get_url(subnet)},
                ]
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(self.instance.ports.filter(subnet=subnet).exists())

    def test_user_cannot_connect_instance_to_one_subnet_twice(self):
        response = self.client.post(
            self.url,
            data={
                "ports": [
                    {
                        "subnet": openstack_factories.SubNetFactory.get_url(
                            self.fixture.subnet
                        )
                    },
                    {
                        "subnet": openstack_factories.SubNetFactory.get_url(
                            self.fixture.subnet
                        )
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            self.instance.ports.filter(subnet=self.fixture.subnet).exists()
        )


class InstanceUpdateFloatingIPsTest(test.APITransactionTestCase):
    action_name = "update_floating_ips"

    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.fixture.openstack_tenant_service_settings.options = {
            "external_network_id": uuid.uuid4().hex
        }
        self.fixture.openstack_tenant_service_settings.save()
        self.client.force_authenticate(user=self.fixture.admin)
        self.instance = self.fixture.instance
        openstack_factories.PortFactory.create(
            instance=self.instance, subnet=self.fixture.subnet
        )
        self.url = factories.InstanceFactory.get_url(
            self.instance, action=self.action_name
        )
        self.subnet_url = openstack_factories.SubNetFactory.get_url(self.fixture.subnet)

    def test_user_can_update_instance_floating_ips(self):
        self.fixture.floating_ip.state = FloatingIP.States.OK
        self.fixture.floating_ip.save()
        floating_ip_url = openstack_factories.FloatingIPFactory.get_url(
            self.fixture.floating_ip
        )
        data = {
            "floating_ips": [
                {"subnet": self.subnet_url, "url": floating_ip_url},
            ]
        }

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.instance.floating_ips.count(), 1)
        self.assertIn(self.fixture.floating_ip, self.instance.floating_ips)

    def test_when_floating_ip_is_attached_action_details_are_updated(self):
        self.fixture.floating_ip.state = FloatingIP.States.OK
        self.fixture.floating_ip.save()
        floating_ip_url = openstack_factories.FloatingIPFactory.get_url(
            self.fixture.floating_ip
        )
        data = {
            "floating_ips": [
                {"subnet": self.subnet_url, "url": floating_ip_url},
            ]
        }

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.instance.refresh_from_db()
        self.assertEqual(
            self.instance.action_details,
            {
                "message": "Attached floating IPs: %s."
                % self.fixture.floating_ip.address,
                "attached": [self.fixture.floating_ip.address],
                "detached": [],
            },
        )

    def test_when_floating_ip_is_detached_action_details_are_updated(self):
        self.fixture.floating_ip.port = self.instance.ports.first()
        self.fixture.floating_ip.save()

        self.client.post(self.url, data={"floating_ips": []})

        self.instance.refresh_from_db()
        self.assertEqual(
            self.instance.action_details,
            {
                "message": "Detached floating IPs: %s."
                % self.fixture.floating_ip.address,
                "attached": [],
                "detached": [self.fixture.floating_ip.address],
            },
        )

    def test_user_can_not_assign_floating_ip_used_by_other_instance(self):
        port = openstack_factories.PortFactory(subnet=self.fixture.subnet)
        floating_ip = openstack_factories.FloatingIPFactory(
            tenant=self.fixture.tenant,
            runtime_state="DOWN",
            port=port,
        )
        floating_ip_url = openstack_factories.FloatingIPFactory.get_url(floating_ip)
        data = {
            "floating_ips": [
                {"subnet": self.subnet_url, "url": floating_ip_url},
            ]
        }

        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("floating_ips", response.data)

    def test_user_cannot_add_floating_ip_via_subnet_that_is_not_connected_to_instance(
        self,
    ):
        subnet_url = openstack_factories.SubNetFactory.get_url()
        data = {"floating_ips": [{"subnet": subnet_url}]}

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_remove_floating_ip_from_instance(self):
        self.fixture.floating_ip.port = self.instance.ports.first()
        self.fixture.floating_ip.save()
        data = {"floating_ips": []}

        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(self.instance.floating_ips.count(), 0)

    def test_free_floating_ip_is_used_for_allocation(self):
        external_network_id = self.fixture.openstack_tenant_service_settings.options[
            "external_network_id"
        ]
        self.fixture.floating_ip.backend_network_id = external_network_id
        self.fixture.floating_ip.save()
        data = {"floating_ips": [{"subnet": self.subnet_url}]}

        response = self.client.post(self.url, data=data)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn(self.fixture.floating_ip, self.instance.floating_ips)

    def test_user_cannot_use_same_subnet_twice(self):
        data = {
            "floating_ips": [{"subnet": self.subnet_url}, {"subnet": self.subnet_url}]
        }
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class InstanceBackupTest(test.APITransactionTestCase):
    action_name = "backup"

    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.client.force_authenticate(self.fixture.owner)

    def test_backup_can_be_created_for_instance_with_2_volumes(self):
        url = factories.InstanceFactory.get_url(self.fixture.instance, action="backup")
        payload = self.get_payload()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            models.Backup.objects.get(name=payload["name"]).snapshots.count(), 2
        )

    def test_backup_can_be_created_for_instance_only_with_system_volume(self):
        instance = self.fixture.instance
        instance.volumes.filter(bootable=False).delete()
        url = factories.InstanceFactory.get_url(instance, action="backup")
        payload = self.get_payload()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            models.Backup.objects.get(name=payload["name"]).snapshots.count(), 1
        )

    def test_backup_can_be_created_for_instance_with_3_volumes(self):
        instance = self.fixture.instance
        instance.volumes.add(
            factories.VolumeFactory(
                service_settings=instance.service_settings,
                project=instance.project,
            )
        )
        url = factories.InstanceFactory.get_url(instance, action="backup")
        payload = self.get_payload()
        response = self.client.post(url, payload)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            models.Backup.objects.get(name=payload["name"]).snapshots.count(), 3
        )

    def test_user_cannot_backup_unstable_instance(self):
        instance = self.fixture.instance
        instance.state = models.Instance.States.UPDATING
        instance.save()
        url = factories.InstanceFactory.get_url(instance, action="backup")

        response = self.client.post(url, data={"name": "test backup"})
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def get_payload(self):
        return {"name": "backup_name"}


@ddt
class InstanceActionsTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.fixture.openstack_tenant_service_settings.options = {
            "external_network_id": uuid.uuid4().hex,
            "tenant_id": self.fixture.tenant.id,
        }
        self.fixture.openstack_tenant_service_settings.save()
        self.instance = self.fixture.instance

        self.url = factories.InstanceFactory.get_url(self.instance, action=self.action)
        self.mock_path = mock.patch(
            "waldur_openstack.openstack_tenant.backend.OpenStackTenantBackend.%s"
            % self.backend_method
        )
        self.mock_console = self.mock_path.start()
        self.mock_console.return_value = self.backend_return_value

    def tearDown(self):
        super().tearDown()
        mock.patch.stopall()


@ddt
class InstanceConsoleTest(InstanceActionsTest):
    action = "console"
    backend_method = "get_console_url"
    backend_return_value = "url"

    @data("staff")
    def test_action_available_to_staff(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mock_console.assert_called_once_with(self.instance)

    @data("admin", "manager", "owner")
    @helpers.override_openstack_tenant_settings(
        ALLOW_CUSTOMER_USERS_OPENSTACK_CONSOLE_ACCESS=False
    )
    def test_action_not_available_for_users_if_this_is_disabled_in_settings(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @data("staff", "admin", "manager", "owner")
    def test_action_available_for_users(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @data("user")
    @helpers.override_openstack_tenant_settings(
        ALLOW_CUSTOMER_USERS_OPENSTACK_CONSOLE_ACCESS=True
    )
    def test_action_not_available_for_other_users(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_error_is_propagated_correctly(self):
        self.mock_console.side_effect = OpenStackBackendError("Invalid request.")
        self.client.force_authenticate(user=self.fixture.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("Invalid request." in response.data)


@ddt
class InstanceConsoleLogTest(InstanceActionsTest):
    action = "console_log"
    backend_method = "get_console_output"
    backend_return_value = "openstack-vm login: "

    @data("staff", "admin", "manager", "owner")
    def test_action_available_for_staff_and_users_associated_with_project(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.mock_console.assert_called_once_with(self.instance, None)

    @data("user")
    def test_action_not_available_for_users_unassociated_with_project(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_error_is_propagated_correctly(self):
        self.mock_console.side_effect = OpenStackBackendError("Invalid request.")
        self.client.force_authenticate(user=self.fixture.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue("Invalid request." in response.data)


@ddt
class InstanceRetrieveTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()
        self.instance = self.fixture.instance
        self.url = factories.InstanceFactory.get_url(self.instance)

    @data("staff", "global_support")
    def test_field_hypervisor_hostname_is_available(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue("hypervisor_hostname" in response.json())

    @data("admin", "manager", "owner")
    def test_field_hypervisor_hostname_is_not_available(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse("hypervisor_hostname" in response.json())


class MaxConcurrentProvisionTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackTenantFixture()

    def test_settings_limit_is_used_if_it_is_available(self):
        private_setting = self.fixture.openstack_tenant_service_settings
        shared_settings = private_setting.scope.service_settings
        shared_settings.options["max_concurrent_provision_instance"] = 10
        shared_settings.save()
        self.assertEqual(
            10, LimitedPerTypeThrottleMixin().get_limit(self.fixture.instance)
        )

    @override_openstack_tenant_settings(
        MAX_CONCURRENT_PROVISION={"OpenStackTenant.Instance": 5}
    )
    def test_plugin_settings_limit_is_used_if_it_is_available(self):
        self.assertEqual(
            5, LimitedPerTypeThrottleMixin().get_limit(self.fixture.instance)
        )
