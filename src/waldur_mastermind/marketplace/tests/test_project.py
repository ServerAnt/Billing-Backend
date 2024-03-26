import datetime

from freezegun import freeze_time
from rest_framework import status, test

from waldur_core.structure import models as structure_models
from waldur_core.structure.tests import factories as structure_factories
from waldur_core.structure.utils import move_project
from waldur_mastermind.marketplace import models
from waldur_mastermind.marketplace.tests import factories, fixtures


class RemovalOfExpiredProjectWithoutActiveResourcesTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.project = self.fixture.project
        self.resource_1 = self.fixture.resource
        self.resource_1.state = models.Resource.States.OK
        self.resource_1.save()
        self.resource_2 = models.Resource.objects.create(
            project=self.project,
            offering=self.fixture.offering,
            plan=self.fixture.plan,
            state=models.Resource.States.OK,
        )
        self.project.end_date = datetime.datetime(year=2020, month=1, day=1).date()
        self.project.save()

    def test_delete_expired_project_if_every_resource_has_been_terminated(self):
        with freeze_time("2020-01-01"):
            self.assertTrue(self.project.is_expired)
            self.resource_1.state = models.Resource.States.TERMINATED
            self.resource_1.save()
            self.assertTrue(
                structure_models.Project.available_objects.filter(
                    id=self.project.id
                ).exists()
            )
            self.resource_2.state = models.Resource.States.TERMINATED
            self.resource_2.save()
            self.assertFalse(
                structure_models.Project.available_objects.filter(
                    id=self.project.id
                ).exists()
            )


class MarketplaceResourceCountTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.project = self.fixture.project
        self.resource = self.fixture.resource
        self.resource.state = models.Resource.States.OK
        self.resource.save()

    def test_key_marketplace_resource_count_exists_in_project_response(self):
        user = self.fixture.staff
        self.client.force_authenticate(user)
        url = structure_factories.ProjectFactory.get_url(self.fixture.resource.project)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        counters = response.json()["marketplace_resource_count"]
        self.assertEqual(
            counters[self.resource.offering.category.uuid.hex],
            1,
        )


class ProjectMoveTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.offering = self.fixture.offering
        self.project = self.fixture.offering.project
        self.old_customer = self.project.customer
        self.new_customer = structure_factories.CustomerFactory()

    def change_customer(self):
        move_project(self.project, self.new_customer)
        self.project.refresh_from_db()

    def test_change_customer(self):
        self.change_customer()
        self.assertEqual(self.new_customer, self.project.customer)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.customer, self.new_customer)

    def test_change_customer_if_offering_scope_is_resource(self):
        resource = factories.ResourceFactory(project=self.project)
        self.offering.scope = resource
        self.offering.save()

        self.change_customer()
        self.assertEqual(self.new_customer, self.project.customer)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.customer, self.new_customer)

        resource.refresh_from_db()
        self.assertEqual(resource.customer, self.new_customer)

    def test_change_customer_for_private_offering(self):
        private_offering = factories.OfferingFactory(
            project=self.project,
            customer=self.old_customer,
            shared=False,
        )
        self.change_customer()
        self.assertEqual(self.new_customer, self.project.customer)
        private_offering.refresh_from_db()
        self.assertEqual(private_offering.customer, self.new_customer)
