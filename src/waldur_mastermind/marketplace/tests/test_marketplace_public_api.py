import datetime

from freezegun import freeze_time
from rest_framework import status, test

from waldur_core.core import utils as core_utils
from waldur_core.structure.tests import factories as structure_factories
from waldur_mastermind.common.mixins import UnitPriceMixin
from waldur_mastermind.marketplace import utils
from waldur_mastermind.marketplace.tests import factories
from waldur_mastermind.marketplace import models
from waldur_mastermind.invoices import models as invoices_models


@freeze_time('2017-01-10 00:00:00')
class TestPublicComponentUsageApi(test.APITransactionTestCase):
    def setUp(self):
        self.service_provider = factories.ServiceProviderFactory()
        self.secret_code = self.service_provider.api_secret_code
        self.plan = factories.PlanFactory(unit=UnitPriceMixin.Units.PER_DAY)
        self.offering_component = factories.OfferingComponentFactory(
            offering=self.plan.offering, billing_type=models.OfferingComponent.BillingTypes.USAGE)
        self.component = factories.PlanComponentFactory(plan=self.plan, component=self.offering_component)
        self.resource = models.Resource.objects.create(
            offering=self.plan.offering,
            plan=self.plan,
            project=structure_factories.ProjectFactory()
        )

    def test_validate_correct_signature(self):
        payload = self.get_valid_payload()
        response = self.client.post('/api/marketplace-public-api/check_signature/', payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_validate_not_correct_signature(self):
        response = self.submit_usage(data='wrong_signature')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_usage(self):
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.ComponentUsage.objects.filter(resource=self.resource,
                                                             component=self.offering_component,
                                                             date=datetime.date.today()).exists())

    def test_total_amount_exceeds_month_limit(self):
        self.offering_component.limit_period = models.OfferingComponent.LimitPeriods.MONTH
        self.offering_component.limit_amount = 1
        self.offering_component.save()
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_total_amount_does_not_exceed_month_limit(self):
        self.offering_component.limit_period = models.OfferingComponent.LimitPeriods.MONTH
        self.offering_component.limit_amount = 10
        self.offering_component.save()
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_total_amount_exceeds_total_limit(self):
        self.offering_component.limit_period = models.OfferingComponent.LimitPeriods.TOTAL
        self.offering_component.limit_amount = 7
        self.offering_component.save()

        models.ComponentUsage.objects.create(
            resource=self.resource,
            component=self.offering_component,
            date=core_utils.month_start(datetime.date.today()),
            usage=5,
        )
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_total_amount_does_not_exceed_total_limit(self):
        self.offering_component.limit_period = models.OfferingComponent.LimitPeriods.TOTAL
        self.offering_component.limit_amount = 15
        self.offering_component.save()

        models.ComponentUsage.objects.create(
            resource=self.resource,
            component=self.offering_component,
            date=core_utils.month_start(datetime.date.today()),
            usage=5,
        )
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_not_create_usage_if_component_not_exists(self):
        response = self.submit_usage(**self.get_valid_payload(component_type='ram'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_usage_if_usage_exists(self):
        self.submit_usage()
        response = self.submit_usage(**self.get_valid_payload(amount=15))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        usage = models.ComponentUsage.objects.first()
        self.assertEqual(usage.usage, 15)

    @freeze_time('2017-01-18 00:00:00')
    def test_not_update_usage_if_billing_period_closed(self):
        invoices_models.Invoice.objects.create(
            customer=self.resource.project.customer,
            year=2017,
            month=1,
            state=invoices_models.Invoice.States.PENDING
        )
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @freeze_time('2017-01-18 00:00:00')
    def test_update_usage_if_billing_period_not_closed(self):
        invoices_models.Invoice.objects.create(
            customer=self.resource.project.customer,
            year=2017,
            month=1,
            state=invoices_models.Invoice.States.CREATED
        )
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @freeze_time('2017-01-18 00:00:00')
    def test_round_date_if_unit_is_per_half_month(self):
        self.plan.unit = UnitPriceMixin.Units.PER_HALF_MONTH
        self.plan.save()
        response = self.submit_usage()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(models.ComponentUsage.objects.filter().exists())
        usage = models.ComponentUsage.objects.first()
        self.assertEqual(usage.date.day, 16)

    def test_dry_run_mode(self):
        response = self.submit_usage(dry_run=True)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(models.ComponentUsage.objects.filter().exists())

    def submit_usage(self, **extra):
        payload = self.get_valid_payload()
        payload.update(extra)
        return self.client.post('/api/marketplace-public-api/set_usage/', payload)

    def get_valid_payload(self, component_type='cpu', amount=5):
        data = {
            'date': datetime.date.today(),
            'resource': self.resource.uuid,
            'usages': [{
                'type': component_type,
                'amount': amount
            }]
        }

        payload = dict(
            customer=self.service_provider.customer.uuid,
            data=utils.encode_api_data(data, self.secret_code)
        )
        return payload
