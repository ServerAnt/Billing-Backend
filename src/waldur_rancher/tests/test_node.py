import json
from unittest import mock

import pkg_resources
from rest_framework import status, test

from waldur_openstack.openstack_tenant.tests import factories as openstack_tenant_factories

from . import factories, fixtures, test_cluster
from .. import models, tasks


class NodeGetTest(test.APITransactionTestCase):
    def setUp(self):
        super(NodeGetTest, self).setUp()
        self.fixture = fixtures.RancherFixture()
        self.fixture_2 = fixtures.RancherFixture()
        self.url = factories.NodeFactory.get_list_url()

    def test_get_node_list(self):
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list(response.data)), 2)

    def test_user_cannot_get_strangers_nodes(self):
        self.client.force_authenticate(self.fixture.owner)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list(response.data)), 1)


class NodeCreateTest(test_cluster.BaseClusterCreateTest):
    def setUp(self):
        super(NodeCreateTest, self).setUp()
        self.node_url = factories.NodeFactory.get_list_url()
        self.payload = {
            'cluster': factories.ClusterFactory.get_url(self.fixture.cluster),
            'subnet': openstack_tenant_factories.SubNetFactory.get_url(self.subnet),
            'system_volume_size': 1024,
            'memory': 1,
            'cpu': 1,
            'roles': ['controlplane', 'etcd', 'worker'],
        }

    @mock.patch('waldur_rancher.views.executors')
    def test_create_node_if_cluster_has_been_created(self, mock_executors):
        self.client.force_authenticate(self.fixture.owner)
        response = self._create_request_(name='name')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        cluster = models.Cluster.objects.get(name='name')
        self.assertTrue(mock_executors.ClusterCreateExecutor.execute.called)
        create_node_task = tasks.CreateNodeTask()
        create_node_task.execute(
            mock_executors.ClusterCreateExecutor.execute.mock_calls[0][1][0].node_set.first(),
            user_id=mock_executors.ClusterCreateExecutor.execute.mock_calls[0][2]['user'].id,
        )
        self.assertTrue(cluster.node_set.filter(cluster=cluster).exists())
        node = cluster.node_set.first()
        self.assertTrue(node.controlplane_role)
        self.assertTrue(node.etcd_role)
        self.assertTrue(node.worker_role)

    def create_node(self, user):
        self.client.force_authenticate(user)
        return self.client.post(self.node_url, self.payload)

    @mock.patch('waldur_rancher.executors.tasks')
    def test_staff_can_create_node(self, mock_tasks):
        response = self.create_node(self.fixture.staff)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_tasks.CreateNodeTask.return_value.si.call_count, 1)

    def test_others_cannot_create_node(self):
        response = self.create_node(self.fixture.owner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_cannot_create_node_if_cpu_has_not_been_specified(self):
        del self.payload['cpu']
        response = self.create_node(self.fixture.staff)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('waldur_rancher.executors.tasks')
    def test_create_node_if_flavor_has_been_specified(self, mock_tasks):
        del self.payload['cpu']
        del self.payload['memory']
        self.payload['flavor'] = openstack_tenant_factories.FlavorFactory.get_url(self.flavor)
        response = self.create_node(self.fixture.staff)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(mock_tasks.CreateNodeTask.return_value.si.call_count, 1)

    @mock.patch('waldur_rancher.executors.tasks')
    def test_do_not_create_node_if_flavor_does_not_meet_requirements(self, mock_tasks):
        self.flavor.cores = 1
        self.flavor.ram = 1024
        self.flavor.save()

        del self.payload['cpu']
        del self.payload['memory']
        self.payload['flavor'] = openstack_tenant_factories.FlavorFactory.get_url(self.flavor)
        response = self.create_node(self.fixture.staff)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_linking_rancher_nodes_with_openStack_instance(self):
        self.client.force_authenticate(self.fixture.staff)
        node = factories.NodeFactory()
        url = factories.NodeFactory.get_url(node, 'link_openstack')
        instance = openstack_tenant_factories.InstanceFactory()
        instance_url = openstack_tenant_factories.InstanceFactory.get_url(instance)
        response = self.client.post(url, {'instance': instance_url})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        node.refresh_from_db()
        self.assertEqual(node.instance, instance)


class NodeDeleteTest(test.APITransactionTestCase):
    def setUp(self):
        super(NodeDeleteTest, self).setUp()
        self.fixture = fixtures.RancherFixture()
        self.cluster_name = self.fixture.cluster.name
        self.url = factories.NodeFactory.get_url(self.fixture.node)

    def test_delete_node(self):
        self.client.force_authenticate(self.fixture.owner)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class NodeDetailsUpdateTest(test.APITransactionTestCase):
    def setUp(self):
        super(NodeDetailsUpdateTest, self).setUp()
        self.fixture = fixtures.RancherFixture()
        self.fixture.node.backend_id = 'backend_id'
        self.fixture.node.save()

        self.patcher_client = mock.patch('waldur_rancher.backend.RancherBackend.client')
        self.mock_client = self.patcher_client.start()
        self.mock_client.get_node.return_value = json.loads(
            pkg_resources.resource_stream(__name__, 'backend_node.json').read().decode())
        self.mock_client.get_cluster.return_value = json.loads(
            pkg_resources.resource_stream(__name__, 'backend_cluster.json').read().decode())

    def _check_node_fields(self, node):
        node.refresh_from_db()
        self.assertEqual(node.docker_version, '19.3.4')
        self.assertEqual(node.k8s_version, 'v1.14.6')
        self.assertEqual(node.cpu_allocated, 0.38)
        self.assertEqual(node.cpu_total, 1)
        self.assertEqual(node.ram_allocated, 8002)
        self.assertEqual(node.ram_total, 15784)
        self.assertEqual(node.pods_allocated, 8)
        self.assertEqual(node.pods_total, 110)
        self.assertEqual(node.state, models.Node.States.OK)

    def test_update_node_details(self):
        tasks.update_nodes(self.fixture.cluster.id)
        self._check_node_fields(self.fixture.node)

    def test_pull_cluster_import_new_node(self):
        backend = self.fixture.node.cluster.get_backend()
        backend.pull_cluster(self.fixture.node.cluster)
        self.assertEqual(self.fixture.cluster.node_set.count(), 2)
        node = self.fixture.cluster.node_set.get(name='k8s-cluster')
        self._check_node_fields(node)

    def test_pull_cluster_update_node(self):
        backend = self.fixture.node.cluster.get_backend()
        self.fixture.node.name = 'k8s-cluster'
        self.fixture.node.backend_id = ''
        self.fixture.node.save()
        backend.pull_cluster(self.fixture.node.cluster)
        self._check_node_fields(self.fixture.node)
