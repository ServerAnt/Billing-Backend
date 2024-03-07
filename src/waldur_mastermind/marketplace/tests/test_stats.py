from ddt import data, ddt
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status, test

from waldur_core.core import utils as core_utils
from waldur_core.quotas.tests import factories as quotas_factories
from waldur_core.structure.tests import factories as structure_factories
from waldur_core.structure.tests import fixtures as structure_fixtures
from waldur_mastermind.common.mixins import UnitPriceMixin
from waldur_mastermind.common.utils import parse_date, parse_datetime
from waldur_mastermind.invoices import models as invoices_models
from waldur_mastermind.invoices import tasks as invoices_tasks
from waldur_mastermind.marketplace import models, tasks, utils
from waldur_mastermind.marketplace.tests import factories, fixtures
from waldur_mastermind.marketplace_openstack import TENANT_TYPE
from waldur_mastermind.marketplace_support import PLUGIN_NAME


class StatsBaseTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = structure_fixtures.ProjectFixture()
        self.customer = self.fixture.customer
        self.project = self.fixture.project

        self.category = factories.CategoryFactory()
        self.category_component = factories.CategoryComponentFactory(
            category=self.category
        )

        self.offering = factories.OfferingFactory(
            category=self.category,
            type=TENANT_TYPE,
            state=models.Offering.States.ACTIVE,
        )
        self.offering_component = factories.OfferingComponentFactory(
            offering=self.offering,
            parent=self.category_component,
            type="cores",
            billing_type=models.OfferingComponent.BillingTypes.LIMIT,
        )


@freeze_time("2019-01-22")
class StatsTest(StatsBaseTest):
    def setUp(self):
        super().setUp()

        self.date = parse_date("2019-01-01")

        self.plan = factories.PlanFactory(offering=self.offering)
        self.plan_component = factories.PlanComponentFactory(
            plan=self.plan, component=self.offering_component, amount=10
        )

        self.resource = factories.ResourceFactory(
            project=self.project, offering=self.offering, plan=self.plan
        )

    def test_reported_usage_is_aggregated_for_project_and_customer(self):
        # Arrange
        plan_period = models.ResourcePlanPeriod.objects.create(
            start=parse_datetime("2019-01-01"),
            resource=self.resource,
            plan=self.plan,
        )

        models.ComponentUsage.objects.create(
            resource=self.resource,
            component=self.offering_component,
            date=parse_date("2019-01-10"),
            billing_period=parse_date("2019-01-01"),
            plan_period=plan_period,
            usage=100,
        )

        self.new_resource = factories.ResourceFactory(
            project=self.project, offering=self.offering, plan=self.plan
        )

        new_plan_period = models.ResourcePlanPeriod.objects.create(
            start=parse_date("2019-01-01"),
            resource=self.new_resource,
            plan=self.plan,
        )

        models.ComponentUsage.objects.create(
            resource=self.resource,
            component=self.offering_component,
            date=parse_date("2019-01-20"),
            billing_period=parse_date("2019-01-01"),
            plan_period=new_plan_period,
            usage=200,
        )

        # Act
        tasks.calculate_usage_for_current_month()

        # Assert
        project_usage = (
            models.CategoryComponentUsage.objects.filter(
                scope=self.project, component=self.category_component, date=self.date
            )
            .get()
            .reported_usage
        )
        customer_usage = (
            models.CategoryComponentUsage.objects.filter(
                scope=self.customer, component=self.category_component, date=self.date
            )
            .get()
            .reported_usage
        )

        self.assertEqual(project_usage, 300)
        self.assertEqual(customer_usage, 300)

    def test_fixed_usage_is_aggregated_for_project_and_customer(self):
        # Arrange
        models.ResourcePlanPeriod.objects.create(
            resource=self.resource,
            plan=self.plan,
            start=parse_date("2019-01-10"),
            end=parse_date("2019-01-20"),
        )

        # Act
        tasks.calculate_usage_for_current_month()

        # Assert
        project_usage = (
            models.CategoryComponentUsage.objects.filter(
                scope=self.project,
                component=self.category_component,
                date=self.date,
            )
            .get()
            .fixed_usage
        )
        customer_usage = (
            models.CategoryComponentUsage.objects.filter(
                scope=self.customer, component=self.category_component, date=self.date
            )
            .get()
            .fixed_usage
        )

        self.assertEqual(project_usage, self.plan_component.amount)
        self.assertEqual(customer_usage, self.plan_component.amount)

    def test_offering_customers_stats(self):
        url = factories.OfferingFactory.get_url(self.offering, action="customers")
        self.client.force_authenticate(self.fixture.staff)
        result = self.client.get(url)
        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.assertEqual(len(result.data), 1)
        self.assertEqual(
            result.data[0]["uuid"], self.resource.project.customer.uuid.hex
        )


@freeze_time("2020-01-01")
class CostsStatsTest(StatsBaseTest):
    def setUp(self):
        super().setUp()
        self.url = factories.OfferingFactory.get_url(self.offering, action="costs")

        self.plan = factories.PlanFactory(
            offering=self.offering,
            unit=UnitPriceMixin.Units.PER_DAY,
        )
        self.plan_component = factories.PlanComponentFactory(
            plan=self.plan, component=self.offering_component, amount=10
        )

        self.resource = factories.ResourceFactory(
            offering=self.offering,
            state=models.Resource.States.OK,
            plan=self.plan,
            limits={"cores": 1},
        )
        invoices_tasks.create_monthly_invoices()

    def test_offering_costs_stats(self):
        with freeze_time("2020-03-01"):
            self._check_stats()

    def test_period_filter(self):
        self.client.force_authenticate(self.fixture.staff)

        result = self.client.get(self.url, {"other_param": ""})
        self.assertEqual(result.status_code, status.HTTP_200_OK)

        result = self.client.get(self.url, {"start": "2020-01"})
        self.assertEqual(result.status_code, status.HTTP_400_BAD_REQUEST)

    def test_offering_costs_stats_if_resource_has_been_failed(self):
        with freeze_time("2020-03-01"):
            self.resource.state = models.Resource.States.ERRED
            self.resource.save()
            self._check_stats()

    def _check_stats(self):
        self.client.force_authenticate(self.fixture.staff)
        result = self.client.get(self.url, {"start": "2020-01", "end": "2020-02"})
        self.assertEqual(result.status_code, status.HTTP_200_OK)
        self.assertDictEqual(
            result.data[0],
            {
                "tax": 0,
                "total": self.plan_component.price * 31,
                "price": self.plan_component.price * 31,
                "period": "2020-01",
            },
        )

    def test_stat_methods_are_not_available_for_anonymous_users(self):
        result = self.client.get(self.url)
        self.assertEqual(result.status_code, status.HTTP_401_UNAUTHORIZED)

        customers_url = factories.OfferingFactory.get_url(
            self.offering, action="customers"
        )
        result = self.client.get(customers_url)
        self.assertEqual(result.status_code, status.HTTP_401_UNAUTHORIZED)


@freeze_time("2020-03-01")
class ComponentStatsTest(StatsBaseTest):
    def setUp(self):
        super().setUp()
        self.url = factories.OfferingFactory.get_url(
            self.offering, action="component_stats"
        )

        self.plan = factories.PlanFactory(
            offering=self.offering,
            unit=UnitPriceMixin.Units.PER_DAY,
        )
        self.plan_component = factories.PlanComponentFactory(
            plan=self.plan, component=self.offering_component, amount=10
        )

        self.resource = factories.ResourceFactory(
            offering=self.offering,
            state=models.Resource.States.OK,
            plan=self.plan,
            limits={"cores": 1},
        )

    def _create_items(self):
        invoices_tasks.create_monthly_invoices()
        invoice = invoices_models.Invoice.objects.get(
            year=2020, month=3, customer=self.resource.project.customer
        )
        return invoice.items.filter(resource_id=self.resource.id)

    def test_item_details(self):
        sp = factories.ServiceProviderFactory(customer=self.resource.offering.customer)
        component = factories.OfferingComponentFactory(
            offering=self.resource.offering,
            billing_type=models.OfferingComponent.BillingTypes.LIMIT,
            type="storage",
        )
        factories.ComponentUsageFactory(
            resource=self.resource,
            billing_period=core_utils.month_start(timezone.now()),
            component=component,
        )
        item = self._create_items().first()
        self.assertDictEqual(
            item.details,
            {
                "resource_name": item.resource.name,
                "resource_uuid": item.resource.uuid.hex,
                "service_provider_name": self.resource.offering.customer.name,
                "service_provider_uuid": sp.uuid.hex,
                "offering_name": self.offering.name,
                "offering_type": TENANT_TYPE,
                "offering_uuid": self.offering.uuid.hex,
                "plan_name": self.resource.plan.name,
                "plan_uuid": self.resource.plan.uuid.hex,
                "plan_component_id": self.plan_component.id,
                "offering_component_type": self.plan_component.component.type,
                "offering_component_name": self.plan_component.component.name,
                "resource_limit_periods": [
                    {
                        "end": "2020-03-31T23:59:59.999999+00:00",
                        "start": "2020-03-01T00:00:00+00:00",
                        "total": "31",
                        "quantity": 1,
                        "billing_periods": 31,
                    }
                ],
            },
        )

    def test_component_stats_if_invoice_item_details_includes_plan_component_data(
        self,
    ):
        self.resource.offering.type = PLUGIN_NAME
        self.resource.offering.save()
        self.offering_component.billing_type = (
            models.OfferingComponent.BillingTypes.FIXED
        )
        self.offering_component.save()

        self._create_items()
        self.client.force_authenticate(self.fixture.staff)
        result = self.client.get(self.url, {"start": "2020-03", "end": "2020-03"})
        self.assertEqual(
            result.data,
            [
                {
                    "description": self.offering_component.description,
                    "measured_unit": self.offering_component.measured_unit,
                    "name": self.offering_component.name,
                    "period": "2020-03",
                    "date": "2020-03-31T00:00:00+00:00",
                    "type": self.offering_component.type,
                    "usage": 31,
                }
            ],
        )

    def test_handler(self):
        self.resource.offering.type = PLUGIN_NAME
        self.resource.offering.save()

        # add usage-based component to the offering and plan
        COMPONENT_TYPE = "storage"
        new_component = factories.OfferingComponentFactory(
            offering=self.resource.offering,
            billing_type=models.OfferingComponent.BillingTypes.USAGE,
            type=COMPONENT_TYPE,
        )
        factories.PlanComponentFactory(
            plan=self.plan,
            component=new_component,
        )

        self._create_items()
        factories.ComponentUsageFactory(
            resource=self.resource,
            date=timezone.now(),
            billing_period=core_utils.month_start(timezone.now()),
            component=new_component,
            usage=2,
        )
        self.client.force_authenticate(self.fixture.staff)
        result = self.client.get(self.url, {"start": "2020-03", "end": "2020-03"})
        component_cores = self.resource.offering.components.get(type="cores")
        component_storage = self.resource.offering.components.get(type="storage")
        self.assertEqual(len(result.data), 2)
        self.assertEqual(
            [r for r in result.data if r["type"] == component_cores.type][0],
            {
                "description": component_cores.description,
                "measured_unit": component_cores.measured_unit,
                "name": component_cores.name,
                "period": "2020-03",
                "date": "2020-03-31T00:00:00+00:00",
                "type": component_cores.type,
                "usage": 31,  # days in March of 1 core usage with per-day plan
            },
        )
        self.assertEqual(
            [r for r in result.data if r["type"] == component_storage.type][0],
            {
                "description": component_storage.description,
                "measured_unit": component_storage.measured_unit,
                "name": component_storage.name,
                "period": "2020-03",
                "date": "2020-03-31T00:00:00+00:00",
                "type": component_storage.type,
                "usage": 2,
            },
        )


@ddt
class CustomerStatsTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = structure_fixtures.ProjectFixture()

    @data(
        "staff",
        "global_support",
    )
    def test_user_can_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get("/api/marketplace-stats/customer_member_count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @data("owner", "user", "customer_support", "admin", "manager")
    def test_user_cannot_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get("/api/marketplace-stats/customer_member_count/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_field_of_count_if_several_quotas_exist(self):
        customer = self.fixture.customer
        quota_1 = quotas_factories.QuotaFactory(
            object_id=customer.id,
            content_type=ContentType.objects.get_for_model(customer.__class__),
            name="nc_user_count",
            delta=10,
        )
        quota_2 = quotas_factories.QuotaFactory(
            object_id=customer.id,
            content_type=ContentType.objects.get_for_model(customer.__class__),
            name="nc_user_count",
            delta=5,
        )
        user = getattr(self.fixture, "staff")
        self.client.force_authenticate(user)
        response = self.client.get("/api/marketplace-stats/customer_member_count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data[0]["count"], quota_1.delta + quota_2.delta)


@ddt
class LimitsStatsTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.resource_1 = factories.ResourceFactory(
            limits={"cpu": 5}, state=models.Resource.States.OK
        )
        factories.ResourceFactory(
            limits={"cpu": 2},
            state=models.Resource.States.OK,
            offering=self.resource_1.offering,
        )
        self.resource_2 = factories.ResourceFactory(
            limits={"cpu": 10, "ram": 1}, state=models.Resource.States.OK
        )
        self.url = "/api/marketplace-stats/resources_limits/"

        self.organization_group_1 = structure_factories.OrganizationGroupFactory()
        self.organization_group_2 = structure_factories.OrganizationGroupFactory()
        self.resource_1.offering.organization_groups.add(
            self.organization_group_1, self.organization_group_2
        )

        self.resource_1.offering.country = "EE"
        self.resource_1.offering.save()

        self.resource_2.offering.customer.country = "FI"
        self.resource_2.offering.customer.save()

    @data(
        # skipping because it is not stable now 'staff',
        "global_support",
    )
    def test_user_can_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            len(response.data),
            4,
        )
        self.assertTrue(
            {
                "offering_uuid": self.resource_1.offering.uuid,
                "name": "cpu",
                "value": 7,
                "offering_country": "EE",
                "organization_group_name": self.organization_group_1.name,
                "organization_group_uuid": self.organization_group_1.uuid.hex,
            }
            in response.data,
        )
        self.assertTrue(
            {
                "offering_uuid": self.resource_1.offering.uuid,
                "name": "cpu",
                "value": 7,
                "offering_country": "EE",
                "organization_group_name": self.organization_group_2.name,
                "organization_group_uuid": self.organization_group_2.uuid.hex,
            }
            in response.data,
        )
        self.assertTrue(
            {
                "offering_uuid": self.resource_2.offering.uuid,
                "name": "cpu",
                "value": 10,
                "offering_country": "FI",
                "organization_group_name": "",
                "organization_group_uuid": "",
            }
            in response.data,
        )
        self.assertTrue(
            {
                "offering_uuid": self.resource_2.offering.uuid,
                "name": "ram",
                "value": 1,
                "offering_country": "FI",
                "organization_group_name": "",
                "organization_group_uuid": "",
            }
            in response.data,
        )

    @data("owner", "user", "customer_support", "admin", "manager")
    def test_user_cannot_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@ddt
class CountUsersOfServiceProviderTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.url = "/api/marketplace-stats/count_users_of_service_providers/"

    @data(
        "staff",
        "global_support",
    )
    def test_user_can_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    @data("owner", "user", "customer_support", "admin", "manager")
    def test_user_cannot_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@ddt
class CountProjectsGroupedByOecdOfServiceProviderTest(test.APITransactionTestCase):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.url = "/api/marketplace-stats/count_projects_of_service_providers_grouped_by_oecd/"

    @data(
        "staff",
        "global_support",
    )
    def test_user_can_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    @data("owner", "user", "customer_support", "admin", "manager")
    def test_user_cannot_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@ddt
class CountUniqueUsersConnectedWithActiveResourcesOfServiceProviderTest(
    test.APITransactionTestCase
):
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.url = "/api/marketplace-stats/count_unique_users_connected_with_active_resources_of_service_provider/"

    @data(
        "staff",
        "global_support",
    )
    def test_user_can_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

        self.fixture.resource.state = models.Resource.States.OK
        self.fixture.resource.save()

        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["count_users"], 0)

        self.fixture.admin
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["count_users"], 1)

        self.fixture.member
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["count_users"], 2)

        self.fixture.manager
        response = self.client.get(self.url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["count_users"], 3)

    @data("owner", "user", "customer_support", "admin", "manager")
    def test_user_cannot_get_marketplace_stats(self, user):
        user = getattr(self.fixture, user)
        self.client.force_authenticate(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CountCustomersTest(test.APITransactionTestCase):
    @freeze_time("2020-01-01")
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.service_provider = self.fixture.service_provider
        self.fixture.resource.set_state_terminated()
        self.fixture.resource.save()

    def _create_resource(self, project=None):
        project = project or structure_factories.ProjectFactory()
        resource = factories.ResourceFactory(
            offering=self.fixture.offering,
            project=project,
        )
        factories.OrderFactory(
            offering=self.fixture.offering,
            project=project,
            resource=resource,
            type=models.Order.Types.CREATE,
            state=models.Order.States.DONE,
        )
        return resource

    def _terminate_resource(self, resource):
        factories.OrderFactory(
            offering=self.fixture.offering,
            state=models.Order.States.DONE,
            resource=resource,
            type=models.Order.Types.TERMINATE,
        )
        resource.state = models.Resource.States.TERMINATED
        return resource.save()

    def test_count_customers_number_change(self):
        with freeze_time("2022-01-10"):
            self.assertEqual(
                0, utils.count_customers_number_change(self.service_provider)
            )

            new_resource = self._create_resource()
            self.assertEqual(
                1, utils.count_customers_number_change(self.service_provider)
            )

            self._terminate_resource(new_resource)
            self.assertEqual(
                0, utils.count_customers_number_change(self.service_provider)
            )

            resource_1 = self._create_resource()
            resource_2 = self._create_resource()
            self.assertEqual(
                2, utils.count_customers_number_change(self.service_provider)
            )

        with freeze_time("2022-02-10"):
            self.assertEqual(
                0, utils.count_customers_number_change(self.service_provider)
            )

            self._terminate_resource(resource_1)
            self.assertEqual(
                -1, utils.count_customers_number_change(self.service_provider)
            )

            self._create_resource(project=resource_2.project)
            self.assertEqual(
                -1, utils.count_customers_number_change(self.service_provider)
            )

        with freeze_time("2022-03-10"):
            self.assertEqual(
                0, utils.count_customers_number_change(self.service_provider)
            )

            self._create_resource(project=new_resource.project)
            self.assertEqual(
                1, utils.count_customers_number_change(self.service_provider)
            )

    def test_count_resources_number_change(self):
        with freeze_time("2022-01-10"):
            self.assertEqual(
                0, utils.count_resources_number_change(self.service_provider)
            )

            new_resource = self._create_resource()
            self.assertEqual(
                1, utils.count_resources_number_change(self.service_provider)
            )

            self._terminate_resource(new_resource)
            self.assertEqual(
                0, utils.count_resources_number_change(self.service_provider)
            )

            resource_1 = self._create_resource()
            resource_2 = self._create_resource()
            self.assertEqual(
                2, utils.count_resources_number_change(self.service_provider)
            )

        with freeze_time("2022-02-10"):
            self.assertEqual(
                0, utils.count_resources_number_change(self.service_provider)
            )

            self._terminate_resource(resource_1)
            self.assertEqual(
                -1, utils.count_resources_number_change(self.service_provider)
            )

            self._create_resource(project=resource_2.project)
            self.assertEqual(
                0, utils.count_resources_number_change(self.service_provider)
            )

        with freeze_time("2022-03-10"):
            self.assertEqual(
                0, utils.count_resources_number_change(self.service_provider)
            )

            self._create_resource(project=new_resource.project)
            self.assertEqual(
                1, utils.count_resources_number_change(self.service_provider)
            )


class OfferingStatsTest(test.APITransactionTestCase):
    @freeze_time("2020-01-01")
    def setUp(self):
        self.fixture = fixtures.MarketplaceFixture()
        self.offering = self.fixture.offering
        self.url = factories.OfferingFactory.get_url(self.offering, "stats")

    def test_offering_stats(self):
        self.client.force_authenticate(self.fixture.offering_owner)
        response = self.client.get(self.url)
        self.assertEqual(response.data["resources_count"], 1)
        self.assertEqual(response.data["customers_count"], 1)

        new_resource = factories.ResourceFactory(offering=self.offering)
        response = self.client.get(self.url)
        self.assertEqual(response.data["resources_count"], 2)
        self.assertEqual(response.data["customers_count"], 2)

        new_resource.state = models.Resource.States.TERMINATED
        new_resource.save()
        response = self.client.get(self.url)
        self.assertEqual(response.data["resources_count"], 1)
        self.assertEqual(response.data["customers_count"], 1)

        factories.ResourceFactory(offering=self.offering, project=self.fixture.project)
        response = self.client.get(self.url)
        self.assertEqual(response.data["resources_count"], 2)
        self.assertEqual(response.data["customers_count"], 1)
