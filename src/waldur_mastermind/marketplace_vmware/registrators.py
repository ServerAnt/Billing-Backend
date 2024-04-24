import logging

from waldur_core.core import utils as core_utils
from waldur_core.structure.permissions import _get_project
from waldur_mastermind.common.utils import mb_to_gb
from waldur_mastermind.invoices import models as invoices_models
from waldur_mastermind.marketplace import models as marketplace_models
from waldur_mastermind.marketplace import utils as marketplace_utils
from waldur_mastermind.marketplace.registrators import MarketplaceRegistrator
from waldur_vmware import models as vmware_models

logger = logging.getLogger(__name__)


class VirtualMachineRegistrator(MarketplaceRegistrator):
    def get_customer(self, source):
        return source.project.customer

    def get_sources(self, customer):
        return (
            vmware_models.VirtualMachine.objects.filter(project__customer=customer)
            .exclude(
                state__in=[
                    vmware_models.VirtualMachine.States.CREATING,
                    vmware_models.VirtualMachine.States.DELETING,
                ]
            )
            .distinct()
        )

    def _create_item(self, source, invoice, start, end, **kwargs):
        try:
            resource = marketplace_models.Resource.objects.get(scope=source)
            plan = resource.plan
            if not plan:
                logger.warning(
                    "Skipping VMware item invoice creation because "
                    "billing plan is not defined for resource. "
                    "Resource ID: %s",
                    resource.id,
                )
                return
        except marketplace_models.Resource.DoesNotExist:
            logger.warning(
                "Skipping VMware item invoice creation because "
                "marketplace resource is not available for VMware resource. "
                "Resource ID: %s",
                source.id,
            )
            return

        components_map = {
            plan_component.component.type: plan_component.price
            for plan_component in plan.components.all()
        }

        missing_components = {"cpu", "ram", "disk"} - set(components_map.keys())
        if missing_components:
            logger.warning(
                "Skipping VMware item invoice creation because plan components are missing. "
                "Plan ID: %s. Missing components: %s",
                plan.id,
                ", ".join(missing_components),
            )
            return

        cores_price = components_map["cpu"] * source.cores
        ram_price = components_map["ram"] * mb_to_gb(source.ram)
        disk_price = components_map["disk"] * mb_to_gb(source.total_disk)
        total_price = cores_price + ram_price + disk_price

        details = self.get_details(source)
        invoices_models.InvoiceItem.objects.create(
            resource=resource,
            project=_get_project(source),
            unit_price=total_price,
            unit=plan.unit,
            article_code=plan.article_code,
            invoice=invoice,
            start=start,
            end=end,
            details=details,
        )

    def get_name(self, source):
        return f"{source.name} ({source.cores} CPU, {mb_to_gb(source.ram)} GB RAM, {mb_to_gb(source.total_disk)} GB disk)"

    def get_details(self, source):
        details = {
            "cpu": source.cores,
            "ram": source.ram,
            "disk": source.total_disk,
        }
        service_provider_info = marketplace_utils.get_service_provider_info(source)
        details.update(service_provider_info)
        return details

    def _find_item(self, source, now):
        resource = marketplace_models.Resource.objects.get(scope=source)
        return list(
            invoices_models.InvoiceItem.objects.filter(
                resource=resource,
                invoice__customer=self.get_customer(source),
                invoice__state=invoices_models.Invoice.States.PENDING,
                invoice__year=now.year,
                invoice__month=now.month,
                end=core_utils.month_end(now),
            )
        )
