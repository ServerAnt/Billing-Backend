import logging

from celery import shared_task
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator

from waldur_core.core.utils import broadcast_mail, format_homeport_link

logger = logging.getLogger(__name__)


@shared_task(name='waldur_auth_social.send_activation_email')
def send_activation_email(user_uuid):
    user = get_user_model().objects.get(uuid=user_uuid, is_active=False)
    token = default_token_generator.make_token(user)

    url = format_homeport_link(
        'activate/{user_uuid}/{token}/', user_uuid=user_uuid, token=token
    )
    context = {'activation_url': url}

    logger.debug('About to send an activation email to %s' % user.email)
    broadcast_mail('waldur_auth_social', 'activation_email', context, [user.email])
