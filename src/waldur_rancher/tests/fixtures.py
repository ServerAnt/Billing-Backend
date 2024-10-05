from django.contrib.contenttypes.models import ContentType
from django.utils.functional import cached_property

from waldur_core.core.models import StateMixin
from waldur_core.structure.tests.fixtures import ProjectFixture
from waldur_openstack.models import Tenant
from waldur_openstack.tests import factories as openstack_factories
from waldur_rancher import models

from . import factories


class RancherFixture(ProjectFixture):
    def __init__(self):
        super().__init__()
        self.node

    @cached_property
    def settings(self):
        return factories.RancherServiceSettingsFactory(customer=self.customer)

    @cached_property
    def tenant(self) -> Tenant:
        return openstack_factories.TenantFactory(project=self.project)

    @cached_property
    def cluster(self):
        return factories.ClusterFactory(
            settings=self.settings,
            service_settings=self.settings,
            project=self.project,
            state=models.Cluster.States.OK,
            tenant=self.tenant,
            name="my-cluster",
        )

    @cached_property
    def instance(self):
        return openstack_factories.InstanceFactory(
            service_settings=self.tenant.service_settings,
            tenant=self.tenant,
            project=self.project,
            state=StateMixin.States.OK,
        )

    @cached_property
    def node(self):
        content_type = ContentType.objects.get_for_model(self.instance)
        return factories.NodeFactory(
            cluster=self.cluster,
            object_id=self.instance.id,
            content_type=content_type,
            state=models.Node.States.OK,
        )
