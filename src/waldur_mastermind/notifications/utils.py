import collections

from django.contrib.auth import get_user_model
from django.db.models import Q

from waldur_core.structure import models as structure_models
from waldur_mastermind.marketplace.models import Offering, Resource

User = get_user_model()


def get_users_for_query(query):
    users, _, _ = get_mapping(query)
    return users.values()


def get_mapping(query):
    users = {}
    user_offerings = collections.defaultdict(set)
    user_customers = collections.defaultdict(set)

    all_users = query.get("all_users")
    if all_users:
        users = {
            user.id: user
            for user in User.objects.filter(is_active=True).exclude(email="")
        }
    else:
        customers = query.get("customers", [])
        offerings = query.get("offerings", [])

        if offerings:
            resources = Resource.objects.filter(
                Q(offering__in=offerings) | Q(offering__parent__in=offerings)
            ).exclude(state=Resource.States.TERMINATED)

            # Drop resources from non-whitelisted customers
            if customers:
                resources = resources.filter(
                    project__customer_id__in=[customer.id for customer in customers]
                )

            # Use only unique customers
            resource_customer_ids = (
                resources.values_list("project__customer_id", flat=True)
                .distinct()
                .order_by()
            )

            filtered_customers = structure_models.Customer.objects.filter(
                id__in=resource_customer_ids
            )
            for customer in filtered_customers:
                customer_offering_ids = set(
                    resources.filter(project__customer=customer)
                    .values_list("offering", flat=True)
                    .distinct()
                    .order_by()
                )
                customer_offerings = Offering.objects.filter(
                    id__in=customer_offering_ids
                )
                for user in customer.get_users():
                    users[user.id] = user
                    user_offerings[user.id] = user_offerings[user.id] | set(
                        customer_offerings
                    )
                    user_customers[user.id].add(customer)

        for customer in customers:
            for user in customer.get_users():
                users[user.id] = user
                user_customers[user.id].add(customer)
    return users, user_offerings, user_customers


def get_recipients_for_query(query):
    users, user_offerings, user_customers = get_mapping(query)

    result = []
    for user_id, user in users.items():
        result.append(
            {
                "full_name": user.full_name,
                "email": user.email,
                "offerings": [
                    {"uuid": offering.uuid, "name": offering.name}
                    for offering in user_offerings[user_id]
                ],
                "customers": [
                    {"uuid": customer.uuid, "name": customer.name}
                    for customer in user_customers[user_id]
                ],
            }
        )
    return sorted(result, key=lambda row: row["full_name"])
