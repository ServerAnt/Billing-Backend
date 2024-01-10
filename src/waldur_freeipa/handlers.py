import logging

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from waldur_core.core import utils as core_utils

from . import models, tasks, utils
from .log import event_logger

logger = logging.getLogger(__name__)


def schedule_sync(*args, **kwargs):
    tasks.schedule_sync()


def schedule_sync_on_quota_change(sender, instance, created=False, **kwargs):
    if instance.name != utils.QUOTA_NAME:
        return
    if created and instance.value == -1:
        return
    tasks.schedule_sync()


def log_profile_event(sender, instance, created=False, **kwargs):
    profile = instance

    if created:
        event_logger.freeipa.info(
            "{username} FreeIPA profile has been created.",
            event_type="freeipa_profile_created",
            event_context={
                "user": profile.user,
                "username": profile.username,
            },
        )

    elif profile.tracker.has_changed("is_active") and profile.tracker.previous(
        "is_active"
    ):
        event_logger.freeipa.info(
            "{username} FreeIPA profile has been disabled.",
            event_type="freeipa_profile_disabled",
            event_context={
                "user": profile.user,
                "username": profile.username,
            },
        )

    elif profile.tracker.has_changed("is_active") and not profile.tracker.previous(
        "is_active"
    ):
        event_logger.freeipa.info(
            "{username} FreeIPA profile has been enabled.",
            event_type="freeipa_profile_enabled",
            event_context={
                "user": profile.user,
                "username": profile.username,
            },
        )


def log_profile_deleted(sender, instance, **kwargs):
    profile = instance
    event_logger.freeipa.info(
        "{username} FreeIPA profile has been deleted.",
        event_type="freeipa_profile_deleted",
        event_context={
            "user": profile.user,
            "username": profile.username,
        },
    )


def schedule_ssh_key_sync_when_key_is_created(
    sender, instance, created=False, **kwargs
):
    if created:
        schedule_ssh_key_sync(instance)


def schedule_ssh_key_sync_when_key_is_deleted(sender, instance, **kwargs):
    schedule_ssh_key_sync(instance)


def schedule_ssh_key_sync(ssh_key):
    try:
        profile = models.Profile.objects.get(user=ssh_key.user)
    except ObjectDoesNotExist:
        logger.debug(
            "Skipping SSH key synchronization because "
            "FreeIPA profile does not exist. "
            "User ID: %s",
            ssh_key.user.id,
        )
    else:
        transaction.on_commit(lambda: tasks.sync_profile_ssh_keys.delay(profile.pk))


def enable_profile_when_association_is_created(sender, allocation, **kwargs):
    users = allocation.project.customer.get_users()
    models.Profile.objects.filter(user__in=users, is_active=False).update(
        is_active=True
    )
    tasks.schedule_sync()


def update_user(sender, instance, created=False, **kwargs):
    user = instance

    if created or not set(user.tracker.changed()) & {
        "first_name",
        "last_name",
        "email",
        "organization",
        "job_title",
        "preferred_language",
        "phone_number",
    }:
        return

    try:
        profile = models.Profile.objects.get(is_active=True, user=user)
    except models.Profile.DoesNotExist:
        return

    transaction.on_commit(
        lambda: tasks.update_user.delay(core_utils.serialize_instance(profile))
    )
