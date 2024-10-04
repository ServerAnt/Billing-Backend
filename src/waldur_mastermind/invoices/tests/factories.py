import factory
from django.utils import timezone
from rest_framework.reverse import reverse

from waldur_core.structure.tests import factories as structure_factories
from waldur_mastermind.invoices import models


class InvoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Invoice

    customer = factory.SubFactory(structure_factories.CustomerFactory)
    invoice_date = factory.fuzzy.FuzzyDateTime(start_dt=timezone.now())

    @classmethod
    def get_url(cls, invoice=None, action=None):
        if invoice is None:
            invoice = InvoiceFactory()
        url = "http://testserver" + reverse(
            "invoice-detail", kwargs={"uuid": invoice.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("invoice-list")


class InvoiceItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.InvoiceItem

    invoice = factory.SubFactory(InvoiceFactory)
    project = factory.SubFactory(structure_factories.ProjectFactory)

    @classmethod
    def get_url(cls, invoice=None, action=None):
        if invoice is None:
            invoice = InvoiceItemFactory()
        url = "http://testserver" + reverse(
            "invoice-item-detail", kwargs={"uuid": invoice.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("invoice-item-list")


class PaymentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.PaymentProfile

    organization = factory.SubFactory(structure_factories.CustomerFactory)
    payment_type = models.PaymentType.MONTHLY_INVOICES

    @classmethod
    def get_url(cls, profile=None, action=None):
        if profile is None:
            profile = cls()
        url = "http://testserver" + reverse(
            "payment-profile-detail", kwargs={"uuid": profile.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("payment-profile-list")


class PaymentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.Payment

    profile = factory.SubFactory(PaymentProfileFactory)
    sum = 100
    date_of_payment = factory.fuzzy.FuzzyDateTime(start_dt=timezone.now())

    @classmethod
    def get_url(cls, payment=None, action=None):
        if payment is None:
            payment = cls()
        url = "http://testserver" + reverse(
            "payment-detail", kwargs={"uuid": payment.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("payment-list")


class CustomerCreditFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.CustomerCredit

    customer = factory.SubFactory(structure_factories.CustomerFactory)
    value = 100

    @classmethod
    def get_url(cls, credit=None, action=None):
        if credit is None:
            credit = cls()
        url = "http://testserver" + reverse(
            "customer-credit-detail", kwargs={"uuid": credit.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("customer-credit-list")


class ProjectCreditFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = models.ProjectCredit

    project = factory.SubFactory(structure_factories.ProjectFactory)
    value = 50

    @classmethod
    def get_url(cls, credit=None, action=None):
        if credit is None:
            credit = cls()
        url = "http://testserver" + reverse(
            "project-credit-detail", kwargs={"uuid": credit.uuid.hex}
        )
        return url if action is None else url + action + "/"

    @classmethod
    def get_list_url(cls):
        return "http://testserver" + reverse("project-credit-list")
