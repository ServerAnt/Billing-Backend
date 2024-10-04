import datetime
import decimal
import uuid

from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.db.models import F, Sum
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import exceptions, status
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from waldur_core.core import validators as core_validators
from waldur_core.core import views as core_views
from waldur_core.structure import filters as structure_filters
from waldur_core.structure import models as structure_models
from waldur_core.structure import permissions as structure_permissions
from waldur_core.structure.permissions import IsStaffOrSupportUser
from waldur_mastermind.common.utils import quantize_price
from waldur_mastermind.invoices.models import InvoiceItem

from . import filters, log, models, serializers, tasks, utils


class InvoiceViewSet(core_views.ReadOnlyActionsViewSet):
    queryset = models.Invoice.objects.order_by("-year", "-month")
    serializer_class = serializers.InvoiceSerializer
    lookup_field = "uuid"
    filter_backends = (
        structure_filters.GenericRoleFilter,
        structure_filters.CustomerAccountingStartDateFilter,
        DjangoFilterBackend,
    )
    filterset_class = filters.InvoiceFilter

    def _is_invoice_created(invoice):
        if invoice.state != models.Invoice.States.CREATED:
            raise exceptions.ValidationError(
                _("Notification only for the created invoice can be sent.")
            )

    @action(detail=True, methods=["post"])
    def send_notification(self, request, uuid=None):
        invoice = self.get_object()
        tasks.send_invoice_notification.delay(invoice.uuid.hex)

        return Response(
            {
                "detail": _(
                    "Invoice notification sending has been successfully scheduled."
                )
            },
            status=status.HTTP_200_OK,
        )

    send_notification_permissions = [structure_permissions.is_staff]
    send_notification_validators = [_is_invoice_created]

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def paid(self, request, uuid=None):
        invoice = self.get_object()

        if request.data:
            serializer = serializers.PaidSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            try:
                profile = models.PaymentProfile.objects.get(
                    is_active=True, organization=invoice.customer
                )
            except models.PaymentProfile.DoesNotExist:
                raise exceptions.ValidationError(
                    _("The active profile for this customer does not exist.")
                )

            payment = models.Payment.objects.create(
                date_of_payment=serializer.validated_data["date"],
                sum=invoice.total_current,
                profile=profile,
                invoice=invoice,
            )

            proof = serializer.validated_data.get("proof")

            if proof:
                payment.proof = proof

            payment.save()

            log.event_logger.invoice.info(
                'Payment for invoice ({month}/{year}) has been added."',
                event_type="payment_created",
                event_context={
                    "month": invoice.month,
                    "year": invoice.year,
                    "customer": invoice.customer,
                },
            )

        invoice.state = models.Invoice.States.PAID
        invoice.save(update_fields=["state"])
        return Response(status=status.HTTP_200_OK)

    paid_permissions = [structure_permissions.is_staff]
    paid_validators = [core_validators.StateValidator(models.Invoice.States.CREATED)]

    @action(detail=True)
    def stats(self, request, uuid=None):
        invoice = self.get_object()
        offerings = {}

        for item in invoice.items.all():
            if not item.resource:
                continue

            resource = item.resource
            offering = resource.offering
            customer = offering.customer
            service_category_title = offering.category.title
            service_provider_name = customer.name
            service_provider_uuid = customer.serviceprovider.uuid.hex

            if offering.uuid.hex not in offerings.keys():
                offerings[offering.uuid.hex] = {
                    "offering_name": offering.name,
                    "aggregated_price": item.price,
                    "aggregated_tax": item.tax,
                    "aggregated_total": item.total,
                    "service_category_title": service_category_title,
                    "service_provider_name": service_provider_name,
                    "service_provider_uuid": service_provider_uuid,
                }
            else:
                offerings[offering.uuid.hex]["aggregated_price"] += item.price
                offerings[offering.uuid.hex]["aggregated_tax"] += item.tax
                offerings[offering.uuid.hex]["aggregated_total"] += item.total

        queryset = [dict(uuid=key, **details) for (key, details) in offerings.items()]

        for item in queryset:
            item["aggregated_price"] = quantize_price(
                decimal.Decimal(item["aggregated_price"])
            )
            item["aggregated_tax"] = quantize_price(
                decimal.Decimal(item["aggregated_tax"])
            )
            item["aggregated_total"] = quantize_price(
                decimal.Decimal(item["aggregated_total"])
            )

        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(page)

    @action(detail=False)
    def growth(self, request):
        if not self.request.user.is_staff and not request.user.is_support:
            raise exceptions.PermissionDenied()

        customers = structure_models.Customer.objects.all()
        customers = structure_filters.AccountingStartDateFilter().filter_queryset(
            request, customers, self
        )

        customers_count = 4
        if "customers_count" in request.query_params:
            try:
                customers_count = int(request.query_params["customers_count"])
            except ValueError:
                raise exceptions.ValidationError("customers_count is not a number")

        if customers_count > 20:
            raise exceptions.ValidationError(
                "customers_count should not be greater than 20"
            )

        is_accounting_mode = request.query_params.get("accounting_mode") == "accounting"

        today = datetime.date.today()
        year_ago = today - relativedelta(months=12)

        majors = list(
            models.Invoice.objects.filter(customer__in=customers, created__gte=year_ago)
            .values("customer_id")
            .annotate(total_value=Sum("total_cost"))
            .order_by("-total_value")
            .values_list("customer_id", flat=True)[:customers_count]
        )

        minors = customers.exclude(id__in=majors)

        periods = []
        for i in range(13):
            month = year_ago + relativedelta(months=i)
            periods.append(f"{month.year}-{month.month}")

        field = is_accounting_mode and "total_price" or "total_cost"
        total_values = {
            f"{row['year']}-{row['month']}": row["total_value"]
            for row in models.Invoice.objects.values("year", "month").annotate(
                total_value=Sum(field)
            )
        }
        other_values = {
            f"{row['year']}-{row['month']}": row["total_value"]
            for row in models.Invoice.objects.filter(customer__in=minors)
            .values("year", "month")
            .annotate(total_value=Sum(field))
        }
        customer_periods = {
            f"{row.customer_id}-{row.year}-{row.month}": getattr(row, field)
            for row in models.Invoice.objects.filter(customer__in=majors)
        }
        customer_periods = [
            {
                "name": customer.name,
                "periods": [
                    customer_periods.get(f"{customer.id}-{period}", 0)
                    for period in periods
                ],
            }
            for customer in structure_models.Customer.objects.filter(id__in=majors)
        ]

        result = {
            "periods": periods,
            "total_periods": [total_values.get(period, 0) for period in periods],
            "other_periods": [other_values.get(period, 0) for period in periods],
            "customer_periods": customer_periods,
        }

        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def set_backend_id(self, request, uuid=None):
        serializer = self.get_serializer(instance=self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK)

    set_backend_id_permissions = [structure_permissions.is_staff]
    set_backend_id_serializer_class = serializers.BackendIdSerializer

    @action(detail=True, methods=["post"])
    def set_payment_url(self, request, uuid=None):
        serializer = self.get_serializer(instance=self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK)

    set_payment_url_permissions = [structure_permissions.is_staff]
    set_payment_url_serializer_class = serializers.PaymentURLSerializer

    @action(detail=True, methods=["post"])
    def set_reference_number(self, request, uuid=None):
        serializer = self.get_serializer(instance=self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_200_OK)

    set_reference_number_permissions = [structure_permissions.is_staff]
    set_reference_number_serializer_class = serializers.ReferenceNumberSerializer


class InvoiceItemViewSet(core_views.ActionsViewSet):
    disabled_actions = ["create"]
    queryset = models.InvoiceItem.objects.all().order_by("start")
    serializer_class = serializers.InvoiceItemDetailSerializer
    lookup_field = "uuid"
    filter_backends = (structure_filters.GenericRoleFilter, DjangoFilterBackend)
    filterset_class = filters.InvoiceItemFilter

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def create_compensation(self, request, **kwargs):
        invoice_item = self.get_object()

        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)
        offering_component_name = serializer.validated_data["offering_component_name"]

        if invoice_item.unit_price < 0:
            return Response(
                "Can not create compensation for invoice item with negative unit price.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        year, month = utils.get_current_year(), utils.get_current_month()
        invoice, _ = models.Invoice.objects.get_or_create(
            customer=invoice_item.invoice.customer,
            month=month,
            year=year,
        )

        # Fill new invoice item details
        if not invoice_item.details:
            invoice_item.details = {}
        invoice_item.details["original_invoice_item_uuid"] = invoice_item.uuid.hex
        invoice_item.details["offering_component_name"] = offering_component_name

        # Save new invoice item to database
        invoice_item.invoice = invoice
        invoice_item.pk = None
        invoice_item.uuid = uuid.uuid4()
        invoice_item.unit_price *= -1
        invoice_item.save()

        log.event_logger.invoice_item.info(
            f"Invoice item {invoice_item.name} has been created.",
            event_type="invoice_item_created",
            event_context={
                "customer": invoice_item.invoice.customer,
            },
        )

        return Response(
            {"invoice_item_uuid": invoice_item.uuid.hex},
            status=status.HTTP_201_CREATED,
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        old_values = {
            field: getattr(instance, field.attname) for field in instance._meta.fields
        }
        invoice_item = serializer.save()
        diff = ", ".join(
            [
                f"{field.name}: {old_values.get(field.name)} -> {getattr(invoice_item, field.name, None)}"
                for field, value in old_values.items()
                if value != getattr(invoice_item, field.attname, None)
            ]
        )
        log.event_logger.invoice_item.info(
            f"Invoice item {invoice_item.name} has been updated. Details: {diff}.",
            event_type="invoice_item_updated",
            event_context={
                "customer": invoice_item.invoice.customer,
            },
        )
        return invoice_item

    def perform_destroy(self, instance):
        invoice_item = instance
        log.event_logger.invoice_item.info(
            f"Invoice item {invoice_item.name} has been deleted.",
            event_type="invoice_item_deleted",
            event_context={
                "customer": invoice_item.invoice.customer,
            },
        )
        invoice_item.delete()

    @action(detail=True, methods=["post"])
    def migrate_to(self, request, **kwargs):
        invoice_item = self.get_object()
        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data["invoice"]

        if invoice.customer != invoice_item.invoice.customer:
            raise exceptions.ValidationError(
                _(
                    "Moving of items is possible only between invoices of same the customer."
                )
            )

        if invoice == invoice_item.invoice:
            raise exceptions.ValidationError(
                _("Invoice item is already in the target invoice.")
            )

        old_invoice = invoice_item.invoice
        invoice_item.invoice = invoice
        invoice_item.save()

        log.event_logger.invoice_item.info(
            f"Invoice item has been migrated from {old_invoice} to {invoice}",
            event_type="invoice_item_updated",
            event_context={
                "customer": invoice.customer,
            },
        )

        return Response(
            {"invoice_item_uuid": invoice_item.uuid.hex},
            status=status.HTTP_200_OK,
        )

    def _get_costs_data(self, paginated_invoices):
        result_list = []
        for invoice in paginated_invoices:
            data = {
                "price": "{:.2f}".format(invoice["price"]),
                "year": invoice["invoice__year"],
                "month": invoice["invoice__month"],
            }
            result_list.append(data)
        return result_list

    @action(detail=False, methods=["get"], filterset_class=filters.InvoiceItemFilter)
    def costs(self, request, *args, **kwargs):
        project_uuid = request.GET.get("project_uuid", "")
        invoices = (
            InvoiceItem.objects.filter(project_uuid=project_uuid)
            .values("invoice__year", "invoice__month")
            .annotate(price=Sum(F("unit_price") * F("quantity")))
            .values("invoice__year", "invoice__month", "price")
            .order_by("-invoice__year", "-invoice__month")
        )
        page = self.paginate_queryset(invoices)
        if page is not None:
            data = self._get_costs_data(page)
            return self.get_paginated_response(data)
        data = self._get_costs_data(invoices)
        return Response(data)

    create_compensation_serializer_class = serializers.InvoiceItemCompensationSerializer

    update_serializer_class = serializers.InvoiceItemUpdateSerializer

    partial_update_serializer_class = serializers.InvoiceItemUpdateSerializer

    migrate_to_serializer_class = serializers.InvoiceItemMigrateToSerializer

    create_compensation_permissions = update_permissions = (
        partial_update_permissions
    ) = destroy_permissions = migrate_to_permissions = [structure_permissions.is_staff]


class PaymentProfileViewSet(core_views.ActionsViewSet):
    lookup_field = "uuid"
    filter_backends = (
        structure_filters.GenericRoleFilter,
        DjangoFilterBackend,
        filters.PaymentProfileFilterBackend,
    )
    filterset_class = filters.PaymentProfileFilter
    create_permissions = update_permissions = partial_update_permissions = (
        destroy_permissions
    ) = enable_permissions = [structure_permissions.is_staff]
    queryset = models.PaymentProfile.objects.all().order_by("name")
    serializer_class = serializers.PaymentProfileSerializer

    @action(detail=True, methods=["post"])
    def enable(self, request, uuid=None):
        profile = self.get_object()
        profile.is_active = True
        profile.save(update_fields=["is_active"])

        return Response(
            {"detail": _("Payment profile has been enabled.")},
            status=status.HTTP_200_OK,
        )


class PaymentViewSet(core_views.ActionsViewSet):
    lookup_field = "uuid"
    filter_backends = (
        structure_filters.GenericRoleFilter,
        DjangoFilterBackend,
    )
    filterset_class = filters.PaymentFilter
    create_permissions = update_permissions = partial_update_permissions = (
        destroy_permissions
    ) = link_to_invoice_permissions = unlink_from_invoice_permissions = [
        structure_permissions.is_staff
    ]
    queryset = models.Payment.objects.all().order_by("created")
    serializer_class = serializers.PaymentSerializer

    @action(detail=True, methods=["post"])
    def link_to_invoice(self, request, uuid=None):
        payment = self.get_object()
        serializer = self.get_serializer_class()(data=request.data)
        serializer.is_valid(raise_exception=True)
        invoice = serializer.validated_data["invoice"]

        if invoice.customer != payment.profile.organization:
            raise exceptions.ValidationError(
                _("The passed invoice does not belong to the selected customer.")
            )

        payment.invoice = invoice
        payment.save(update_fields=["invoice"])

        log.event_logger.invoice.info(
            "Payment for invoice ({month}/{year}) has been added.",
            event_type="payment_created",
            event_context={
                "month": invoice.month,
                "year": invoice.year,
                "customer": invoice.customer,
            },
        )

        return Response(
            {"detail": _("An invoice has been linked to payment.")},
            status=status.HTTP_200_OK,
        )

    def _link_to_invoice_exists(payment):
        if payment.invoice:
            raise exceptions.ValidationError(_("Link to an invoice exists."))

    link_to_invoice_validators = [_link_to_invoice_exists]
    link_to_invoice_serializer_class = serializers.LinkToInvoiceSerializer

    def _link_to_invoice_does_not_exist(payment):
        if not payment.invoice:
            raise exceptions.ValidationError(_("Link to an invoice does not exist."))

    @action(detail=True, methods=["post"])
    def unlink_from_invoice(self, request, uuid=None):
        payment = self.get_object()
        invoice = payment.invoice
        payment.invoice = None
        payment.save(update_fields=["invoice"])

        log.event_logger.invoice.info(
            "Payment for invoice ({month}/{year}) has been removed.",
            event_type="payment_removed",
            event_context={
                "month": invoice.month,
                "year": invoice.year,
                "customer": invoice.customer,
            },
        )

        return Response(
            {"detail": _("An invoice has been unlinked from payment.")},
            status=status.HTTP_200_OK,
        )

    unlink_from_invoice_validators = [_link_to_invoice_does_not_exist]

    def perform_create(self, serializer):
        super().perform_create(serializer)
        payment = serializer.instance
        log.event_logger.payment.info(
            "Payment for {customer_name} in the amount of {amount} has been added.",
            event_type="payment_added",
            event_context={
                "amount": payment.sum,
                "customer": payment.profile.organization,
            },
        )

    def perform_destroy(self, instance):
        customer = instance.profile.organization
        amount = instance.sum
        super().perform_destroy(instance)

        log.event_logger.payment.info(
            "Payment for {customer_name} in the amount of {amount} has been removed.",
            event_type="payment_removed",
            event_context={
                "amount": amount,
                "customer": customer,
            },
        )


@api_view(["POST"])
@permission_classes((IsStaffOrSupportUser,))
def send_financial_report_by_mail(request):
    serializer = serializers.FinancialReportEmailSerializer(data=request.data)
    if serializer.is_valid():
        year = serializer.data["year"]
        month = serializer.data["month"]
        emails = serializer.data["emails"]
        tasks.send_invoice_report.delay(year, month, emails, False)
        return Response(
            {"status": _("The dispatch of reports has been scheduled.")},
            status=status.HTTP_202_ACCEPTED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomerCreditViewSet(core_views.ActionsViewSet):
    lookup_field = "uuid"
    filter_backends = (
        structure_filters.GenericRoleFilter,
        DjangoFilterBackend,
    )
    create_permissions = update_permissions = partial_update_permissions = (
        destroy_permissions
    ) = [structure_permissions.is_staff]
    queryset = models.CustomerCredit.objects.all().order_by("created")
    serializer_class = serializers.CustomerCreditSerializer
    create_serializer_class = update_serializer_class = (
        partial_update_serializer_class
    ) = serializers.CreateCustomerCreditSerializer


class ProjectCreditViewSet(core_views.ActionsViewSet):
    lookup_field = "uuid"
    filter_backends = (
        structure_filters.GenericRoleFilter,
        DjangoFilterBackend,
    )
    update_permissions = partial_update_permissions = destroy_permissions = [
        structure_permissions.is_owner
    ]
    queryset = models.ProjectCredit.objects.all().order_by("created")
    serializer_class = serializers.ProjectCreditSerializer
