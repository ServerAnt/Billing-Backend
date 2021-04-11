import datetime

from django.core import mail
from freezegun import freeze_time
from rest_framework import test

from waldur_core.core import utils as core_utils
from waldur_core.structure.tests import factories as structure_factories
from waldur_core.structure.tests import fixtures as structure_fixtures
from waldur_mastermind.marketplace import exceptions, models, tasks

from . import factories, fixtures


class CalculateUsageForCurrentMonthTest(test.APITransactionTestCase):
    def setUp(self):
        offering = factories.OfferingFactory()
        plan = factories.PlanFactory(offering=offering)
        resource = factories.ResourceFactory(offering=offering)
        category_component = factories.CategoryComponentFactory()
        self.offering_component = factories.OfferingComponentFactory(
            offering=offering,
            parent=category_component,
            billing_type=models.OfferingComponent.BillingTypes.USAGE,
        )
        factories.PlanComponentFactory(plan=plan, component=self.offering_component)
        plan_period = models.ResourcePlanPeriod.objects.create(
            resource=resource, plan=plan, start=datetime.datetime.now()
        )
        models.ComponentUsage.objects.create(
            resource=resource,
            component=self.offering_component,
            usage=10,
            date=datetime.datetime.now(),
            billing_period=core_utils.month_start(datetime.datetime.now()),
            plan_period=plan_period,
        )

    def test_calculate_usage_if_category_component_is_set(self):
        tasks.calculate_usage_for_current_month()
        self.assertEqual(models.CategoryComponentUsage.objects.count(), 2)

    def test_calculate_usage_if_category_component_is_not_set(self):
        self.offering_component.parent = None
        self.offering_component.save()
        tasks.calculate_usage_for_current_month()
        self.assertEqual(models.CategoryComponentUsage.objects.count(), 0)


class NotificationTest(test.APITransactionTestCase):
    def test_notify_about_resource_change(self):
        project_fixture = structure_fixtures.ProjectFixture()
        admin = project_fixture.admin
        project = project_fixture.project
        resource = factories.ResourceFactory(project=project, name='Test resource')
        tasks.notify_about_resource_change(
            'marketplace_resource_create_succeeded',
            {'resource_name': resource.name},
            resource.uuid,
        )
        self.assertEqual(len(mail.outbox), 1)
        subject_template_name = '%s/%s_subject.txt' % (
            'marketplace',
            'marketplace_resource_create_succeeded',
        )
        subject = core_utils.format_text(
            subject_template_name, {'resource_name': resource.name}
        )
        self.assertEqual(mail.outbox[0].subject, subject)
        self.assertEqual(mail.outbox[0].to[0], admin.email)
        self.assertTrue(resource.name in mail.outbox[0].body)
        self.assertTrue(resource.name in mail.outbox[0].subject)


class TerminateResource(test.APITransactionTestCase):
    def setUp(self):
        fixture = structure_fixtures.UserFixture()
        self.user = fixture.staff
        offering = factories.OfferingFactory()
        self.resource = factories.ResourceFactory(offering=offering)
        factories.OrderItemFactory(
            resource=self.resource,
            type=models.OrderItem.Types.TERMINATE,
            state=models.OrderItem.States.EXECUTING,
        )

    def test_raise_exception_if_order_item_has_not_been_created(self):
        self.assertRaises(
            exceptions.ResourceTerminateException,
            tasks.terminate_resource,
            core_utils.serialize_instance(self.resource),
            core_utils.serialize_instance(self.user),
        )


class ProjectEndDate(test.APITransactionTestCase):
    def setUp(self):
        structure_factories.UserFactory(username='staff', is_staff=True)
        self.fixtures = fixtures.MarketplaceFixture()
        self.fixtures.project.end_date = datetime.datetime(day=1, month=1, year=2020)
        self.fixtures.project.save()
        self.fixtures.resource.set_state_ok()
        self.fixtures.resource.save()

    def test_terminate_resources_if_project_end_date_has_been_reached(self):
        with freeze_time('2020-01-02'):
            tasks.terminate_resources_if_project_end_date_has_been_reached()
            self.assertTrue(
                models.OrderItem.objects.filter(
                    resource=self.fixtures.resource,
                    type=models.OrderItem.Types.TERMINATE,
                ).count()
            )
            order_item = models.OrderItem.objects.get(
                resource=self.fixtures.resource, type=models.OrderItem.Types.TERMINATE
            )
            self.assertTrue(order_item.order.state, models.Order.States.EXECUTING)
