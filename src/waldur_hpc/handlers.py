import logging
import re

from django.conf import settings
from django.db import transaction

from waldur_core.core.utils import is_uuid_like
from waldur_core.permissions.fixtures import ProjectRole
from waldur_core.structure.models import Customer, Project
from waldur_core.structure.utils import move_project
from waldur_mastermind.marketplace.models import Offering, Order, Plan, Resource
from waldur_mastermind.marketplace.tasks import (
    notify_consumer_about_pending_order,
    process_order_on_commit,
)
from waldur_slurm.utils import sanitize_allocation_name

logger = logging.getLogger(__name__)


def get_internal_customer():
    customer_uuid = settings.WALDUR_HPC['INTERNAL_CUSTOMER_UUID']
    if not customer_uuid:
        logger.debug('Internal customer is not specified.')
        return
    if not is_uuid_like(customer_uuid):
        logger.warning('Internal customer UUID is invalid.')
        return
    try:
        return Customer.objects.get(uuid=customer_uuid)
    except Customer.DoesNotExist:
        logger.warning('Customer with UUID %s is not found', customer_uuid)
        return


def get_external_customer():
    customer_uuid = settings.WALDUR_HPC['EXTERNAL_CUSTOMER_UUID']
    if not customer_uuid:
        logger.debug('External customer is not specified.')
        return
    if not is_uuid_like(customer_uuid):
        logger.warning('External customer UUID is invalid.')
        return
    try:
        return Customer.objects.get(uuid=customer_uuid)
    except Customer.DoesNotExist:
        logger.warning('Customer with UUID %s is not found', customer_uuid)
        return


def get_offering():
    offering_uuid = settings.WALDUR_HPC['OFFERING_UUID']
    if not offering_uuid:
        logger.debug('Offering is not specified.')
        return
    if not is_uuid_like(offering_uuid):
        logger.warning('Offering UUID is invalid.')
        return
    try:
        offering = Offering.objects.get(uuid=offering_uuid)
    except Offering.DoesNotExist:
        logger.warning('Offering UUID %s is not found', offering_uuid)
        return

    if not offering.shared:
        logger.warning('Offering is not shared.')
        return

    return offering


def get_plan():
    plan_uuid = settings.WALDUR_HPC['PLAN_UUID']
    if not plan_uuid:
        logger.debug('Plan is not specified.')
        return
    if not is_uuid_like(plan_uuid):
        logger.warning('Plan UUID is invalid.')
        return
    try:
        return Plan.objects.get(uuid=plan_uuid)
    except Plan.DoesNotExist:
        logger.warning('Plan UUID %s is not found', plan_uuid)
        return


def get_or_create_project(customer, user, wrong_customer):
    try:
        return Project.objects.get(name=user.username, customer=customer)
    except Project.MultipleObjectsReturned:
        logger.warning('Multiple projects with the same name %s exist.', user.username)
        return
    except Project.DoesNotExist:
        try:
            # user has changed and has led to a change in INTERNAL/EXTERNAL decision
            project = Project.objects.get(name=user.username, customer=wrong_customer)
            move_project(project, customer)
            return project
        except Project.DoesNotExist:
            pass

        project = Project.objects.create(customer=customer, name=user.username)
        project.add_user(user, ProjectRole.ADMIN)
        return project
    else:
        logger.warning('Projects with name %s already exists.', user.username)
        return


def get_or_create_order(project: Project, user, offering, plan, limits=None):
    limits = limits or {}

    order_ids = Order.objects.filter(offering=offering).values_list('id', flat=True)

    order = (
        Order.objects.filter(
            project=project,
            created_by=user,
            state__in=(
                Order.States.DONE,
                Order.States.PENDING_CONSUMER,
                Order.States.PENDING_PROVIDER,
                Order.States.EXECUTING,
            ),
            id__in=order_ids,
        )
        .order_by('created')
        .last()
    )
    if order:
        if order.state in [
            Order.States.PENDING_CONSUMER,
            Order.States.PENDING_PROVIDER,
            Order.States.EXECUTING,
        ]:
            return order, False
        if order.state == Order.States.DONE:
            if order.resource.state != Resource.States.ERRED:
                return order, False

    name = sanitize_allocation_name(user.username)

    with transaction.atomic():
        resource = Resource(
            project=project,
            offering=offering,
            plan=plan,
            limits=limits,
            attributes={'name': name},
            name=name,
            state=Resource.States.CREATING,
        )
        resource.init_cost()
        resource.save()

        order = Order(
            resource=resource,
            project=project,
            created_by=user,
            offering=offering,
            plan=plan,
            limits=limits,
            attributes={'name': name},
            state=Order.States.EXECUTING,
        )

        order.init_cost()
        order.save()

    return order, True


def check_user(user, affiliations, email_patterns):
    logger.info(
        "Checking user %s for internal/external belonging. "
        "User's affiliations: %s, affiliations: %s, email patterns: %s",
        user,
        user.affiliations,
        affiliations,
        email_patterns,
    )
    if set(user.affiliations or []) & set(affiliations):
        return True

    return any(re.match(pattern, user.email) for pattern in email_patterns)


def is_internal_user(user):
    is_internal = check_user(
        user,
        settings.WALDUR_HPC['INTERNAL_AFFILIATIONS'],
        settings.WALDUR_HPC['INTERNAL_EMAIL_PATTERNS'],
    )

    if is_internal:
        logger.info('The user %s is internal one', user)

    return is_internal


def is_external_user(user):
    if is_internal_user(user):
        return False

    is_external = check_user(
        user,
        settings.WALDUR_HPC['EXTERNAL_AFFILIATIONS'],
        settings.WALDUR_HPC['EXTERNAL_EMAIL_PATTERNS'],
    )

    if is_external:
        logger.info('The user %s is external one', user)

    return is_external


def handle_new_user(sender, instance, created=False, **kwargs):
    if not settings.WALDUR_HPC['ENABLED']:
        return

    user = instance

    internal_customer = get_internal_customer()
    if not internal_customer:
        return

    external_customer = get_external_customer()
    if not external_customer:
        return

    offering = get_offering()
    if not offering:
        return

    plan = get_plan()
    if not plan:
        return

    if plan.offering != offering:
        logger.warning('Plan does not match offering.')
        return

    if is_internal_user(user):
        project = get_or_create_project(internal_customer, user, external_customer)

        if not project:
            return
        # assure that user has permissions connected with the project
        project.add_user(user, ProjectRole.ADMIN)

        order, order_created = get_or_create_order(
            project,
            user,
            offering,
            plan,
            limits=settings.WALDUR_HPC['INTERNAL_LIMITS'],
        )

        if not order or not order_created:
            return
        process_order_on_commit(order, user)
        return

    if is_external_user(user):
        project = get_or_create_project(external_customer, user, internal_customer)

        if not project:
            return

        # assure that user has permissions connected with the project
        project.add_user(user, ProjectRole.ADMIN)

        order, order_created = get_or_create_order(
            project,
            user,
            offering,
            plan,
            limits=settings.WALDUR_HPC['EXTERNAL_LIMITS'],
        )

        if not order or not order_created:
            return

        transaction.on_commit(
            lambda: notify_consumer_about_pending_order.delay(order.uuid)
        )
