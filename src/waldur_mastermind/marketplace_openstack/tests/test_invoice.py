from unittest import mock

from django.utils import timezone
from freezegun import freeze_time
from rest_framework import test

from waldur_mastermind.common.utils import parse_datetime
from waldur_mastermind.invoices import models as invoices_models
from waldur_mastermind.marketplace import callbacks
from waldur_mastermind.marketplace import models as marketplace_models
from waldur_mastermind.marketplace.signals import resource_limit_update_succeeded
from waldur_mastermind.marketplace.tests import factories as marketplace_factories
from waldur_mastermind.marketplace_openstack import (
    CORES_TYPE,
    RAM_TYPE,
    SHARED_INSTANCE_TYPE,
    STORAGE_MODE_DYNAMIC,
    STORAGE_MODE_FIXED,
    STORAGE_TYPE,
)
from waldur_openstack.openstack_base.tests.fixtures import OpenStackFixture
from waldur_openstack.openstack_tenant.tests.factories import FlavorFactory
from waldur_openstack.openstack_tenant.tests.fixtures import OpenStackTenantFixture

from .. import TENANT_TYPE


@freeze_time('2019-09-10')
class BaseTenantInvoiceTest(test.APITransactionTestCase):
    def setUp(self):
        self.offering = marketplace_factories.OfferingFactory(type=TENANT_TYPE)
        self.limits = {
            RAM_TYPE: 1 * 1024,
            CORES_TYPE: 2,
            STORAGE_TYPE: 3 * 1024,
        }
        self.prices = {
            RAM_TYPE: 10,
            CORES_TYPE: 100,
            STORAGE_TYPE: 1,
        }
        for ct in [RAM_TYPE, CORES_TYPE, STORAGE_TYPE]:
            marketplace_factories.OfferingComponentFactory(
                offering=self.offering,
                type=ct,
                billing_type=marketplace_models.OfferingComponent.BillingTypes.LIMIT,
            )

    def create_plan(self, prices, unit=marketplace_models.Plan.Units.PER_DAY):
        plan = marketplace_factories.PlanFactory(offering=self.offering, unit=unit)
        for ct in prices.keys():
            marketplace_factories.PlanComponentFactory(
                plan=plan,
                component=self.offering.components.get(type=ct),
                price=prices[ct],
            )
        return plan

    def create_resource(
        self, prices, limits, unit=marketplace_models.Plan.Units.PER_DAY
    ) -> marketplace_models.Resource:
        plan = self.create_plan(prices, unit)
        resource = marketplace_factories.ResourceFactory(
            offering=self.offering,
            plan=plan,
            limits=limits,
            state=marketplace_models.Resource.States.CREATING,
        )
        callbacks.resource_creation_succeeded(resource)
        return resource

    def update_resource_limits(self, resource: marketplace_models.Resource, new_limits):
        order = marketplace_factories.OrderFactory(
            project=resource.project,
            offering=self.offering,
            resource=resource,
            type=marketplace_models.Order.Types.UPDATE,
            state=marketplace_models.Order.States.EXECUTING,
            limits=new_limits,
        )
        resource.set_state_updating()
        resource.save()
        resource_limit_update_succeeded.send(sender=resource.__class__, order=order)

    def delete_resource(self, resource):
        callbacks.resource_deletion_succeeded(resource)


class TenantInvoiceTest(BaseTenantInvoiceTest):
    def test_when_resource_is_created_invoice_is_updated(self):
        resource = self.create_resource(self.prices, self.limits)
        invoice_items = invoices_models.InvoiceItem.objects.filter(resource=resource)
        self.assertEqual(invoice_items.count(), 3)

    def test_when_resource_limits_are_updated_invoice_items_are_updated(self):
        new_limits = {
            RAM_TYPE: 10 * 1024,
            CORES_TYPE: 20,
            STORAGE_TYPE: 30 * 1024,
        }
        with freeze_time('2017-01-01'):
            resource = self.create_resource(self.prices, self.limits)

        with freeze_time('2017-01-10'):
            self.update_resource_limits(resource, new_limits)

        invoice_items = invoices_models.InvoiceItem.objects.filter(resource=resource)
        self.assertEqual(invoice_items.count(), 3)

    def test_when_resource_is_deleted_invoice_is_updated(self):
        resource = self.create_resource(self.prices, self.limits)
        with freeze_time('2019-09-18'):
            resource.set_state_terminating()
            resource.save()
            self.delete_resource(resource)
        invoice_item = invoices_models.InvoiceItem.objects.filter(
            resource=resource
        ).last()
        self.assertEqual(invoice_item.end.day, 18)

    def test_resource_limit_period_is_updated_when_resource_is_terminated(self):
        resource = self.create_resource(self.prices, self.limits)
        with freeze_time('2019-09-18'):
            resource.set_state_terminating()
            resource.save()
            resource.set_state_terminated()
            resource.save()
            invoice_item = invoices_models.InvoiceItem.objects.filter(
                resource=resource
            ).last()
            self.assertEqual(
                parse_datetime(
                    invoice_item.details['resource_limit_periods'][-1]['end']
                ),
                timezone.now(),
            )
            self.assertEqual(
                invoice_item.quantity,
                24,  # From 2019-09-18 to 2019-09-10 => 8 days, 3 gb of storage per day
            )


class StorageModeInvoiceTest(BaseTenantInvoiceTest):
    def setUp(self):
        # Arrange
        super().setUp()
        fixture = OpenStackFixture()
        tenant = fixture.openstack_tenant
        offering_component = marketplace_models.OfferingComponent.objects.create(
            offering=self.offering,
            type='gigabytes_gpfs',
            billing_type=marketplace_models.OfferingComponent.BillingTypes.LIMIT,
        )

        plan = self.create_plan(self.prices)
        marketplace_models.PlanComponent.objects.create(
            component=offering_component,
            plan=plan,
            price=10,
        )
        self.resource = marketplace_factories.ResourceFactory(
            offering=self.offering,
            plan=plan,
            limits=self.limits,
            state=marketplace_models.Resource.States.CREATING,
        )

        callbacks.resource_creation_succeeded(self.resource)
        self.resource.scope = tenant
        self.resource.save()
        tenant.set_quota_limit('vcpu', 6)
        tenant.set_quota_limit('ram', 10 * 1024)
        tenant.set_quota_usage('storage', 30 * 1024)
        tenant.set_quota_usage('gigabytes_gpfs', 100 * 1024)

    def test_when_storage_mode_is_switched_to_dynamic_limits_are_updated(self):
        # Act
        with freeze_time('2019-09-20'):
            self.offering.plugin_options['storage_mode'] = STORAGE_MODE_DYNAMIC
            self.offering.save()

        # Assert
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.limits.get('cores'), 6)
        self.assertEqual(self.resource.limits.get('ram'), 10 * 1024)
        self.assertEqual(self.resource.limits.get('storage'), None)
        self.assertEqual(self.resource.limits.get('gigabytes_gpfs'), 100 * 1024)

        invoice_item = invoices_models.InvoiceItem.objects.filter(
            resource=self.resource, details__offering_component_type='gigabytes_gpfs'
        ).get()
        last_period = invoice_item.details['resource_limit_periods'][-1]
        self.assertEqual(last_period['quantity'], 100 * 1024)

    def test_when_storage_mode_is_switched_to_fixed_limits_are_updated(self):
        # Act
        with freeze_time('2019-09-20'):
            self.offering.plugin_options['storage_mode'] = STORAGE_MODE_FIXED
            self.offering.save()

        # Assert
        self.resource.refresh_from_db()
        self.assertEqual(self.resource.limits.get('cores'), 6)
        self.assertEqual(self.resource.limits.get('ram'), 10 * 1024)
        self.assertEqual(self.resource.limits.get('storage'), 30 * 1024)
        self.assertEqual(self.resource.limits.get('gigabytes_gpfs'), None)

        invoice_item = invoices_models.InvoiceItem.objects.filter(
            resource=self.resource
        ).last()
        last_period = invoice_item.details['resource_limit_periods'][-1]
        self.assertEqual(last_period['quantity'], 30)

    @mock.patch(
        'waldur_mastermind.marketplace_openstack.utils.import_limits_when_storage_mode_is_switched'
    )
    def test_when_storage_mode_is_not_switched_limits_are_not_updated(
        self, mocked_utils
    ):
        # Act
        with freeze_time('2019-09-20'):
            self.offering.plugin_options['FOO'] = 'BAR'
            self.offering.save()

        # Assert
        self.assertEqual(mocked_utils.call_count, 0)


class SharedInstanceTest(test.APITransactionTestCase):
    def test_when_instance_is_created_component_usage_is_imported(self):
        offering = marketplace_factories.OfferingFactory(type=SHARED_INSTANCE_TYPE)
        for ct in [RAM_TYPE, CORES_TYPE, STORAGE_TYPE]:
            marketplace_factories.OfferingComponentFactory(
                offering=offering,
                type=ct,
                billing_type=marketplace_models.OfferingComponent.BillingTypes.USAGE,
            )

        fixture = OpenStackTenantFixture()
        resource = marketplace_factories.ResourceFactory(
            offering=offering,
            attributes={
                'flavor': FlavorFactory.get_url(fixture.flavor),
                'data_volume_size': 1024 * 4,
            },
        )
        plan = marketplace_factories.PlanFactory(offering=offering)
        marketplace_models.ResourcePlanPeriod.objects.create(
            resource=resource,
            plan=plan,
        )
        resource.attributes['system_volume_size'] = 1024 * 2
        resource.save()

        self.assertEqual(
            3,
            marketplace_models.ComponentUsage.objects.filter(resource=resource).count(),
        )
