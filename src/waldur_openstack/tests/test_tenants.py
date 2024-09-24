from unittest import mock

from ddt import data, ddt
from rest_framework import status, test

from . import factories, fixtures


@ddt
class TenantTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.OpenStackFixture()
        self.fixture.tenant.project = self.fixture.project
        self.fixture.tenant.save()
        self.backend_instance = factories.InstanceFactory()
        self.backend_volume = factories.VolumeFactory()
        self.url_instance = factories.TenantFactory.get_url(
            self.fixture.tenant, "backend_instances"
        )
        self.url_volumes = factories.TenantFactory.get_url(
            self.fixture.tenant, "backend_volumes"
        )
        self.mock_path = mock.patch("waldur_openstack.views.OpenStackBackend")
        self.mock_openstack_backend = self.mock_path.start()
        self.mock_openstack_backend().get_instances.return_value = [
            self.backend_instance
        ]
        self.mock_openstack_backend().get_volumes.return_value = [self.backend_volume]

    def tearDown(self):
        super().tearDown()
        mock.patch.stopall()

    @data("staff", "global_support", "owner", "admin", "manager")
    def test_user_can_get_backend_instances(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url_instance)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1)

    @data("user")
    def test_user_can_not_get_backend_instances(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url_instance)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @data("staff", "global_support", "owner", "admin", "manager")
    def test_user_can_get_backend_volumes(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url_volumes)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    @data("user")
    def test_user_can_not_get_backend_volumes(self, user):
        self.client.force_authenticate(user=getattr(self.fixture, user))
        response = self.client.get(self.url_volumes)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
