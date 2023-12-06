import base64
import json
import logging

from rest_framework import serializers

from waldur_mastermind.marketplace import processors

from .utils import ContainerExecutorMixin

"""
It is expected that offering plugin_options field is dict with following structure:

language: python

environ:
    USERNAME: admin
    PASSWORD: secret

create:
    import os
    print("Creating resource ", os.environ.get('RESOURCE_NAME'))

update:
    import os
    print("Updating resource ", os.environ.get('RESOURCE_NAME'))

delete:
    import os
    print("Deleting resource ", os.environ.get('RESOURCE_NAME'))

pull:
    import os
    print("Pulling resource ", os.environ.get('RESOURCE_NAME'))
"""

logger = logging.getLogger(__name__)


class CreateProcessor(
    ContainerExecutorMixin, processors.AbstractCreateResourceProcessor
):
    hook_type = 'create'

    def send_request(self, user):
        output = super().send_request(user)
        if output:
            last_line = output.splitlines()[-1].split()
            if len(last_line) == 1:
                # return the last line of the output as a backend_id of a created resource
                return last_line[0]
            elif len(last_line) == 2:
                # expecting space separated backend_id and base64-encoded metadata in json format
                result = {'response_type': 'metadata'}
                if str(last_line[0]) == 'null':
                    raise ValueError('Backend id returned as null, will not proceed.')
                result['backend_id'] = str(last_line[0])
                decoded_metadata = base64.b64decode(last_line[1])
                try:
                    metadata_dict = json.loads(decoded_metadata)
                    if 'backend_metadata' in metadata_dict:
                        result['backend_metadata'] = metadata_dict['backend_metadata']

                    if 'endpoints' in metadata_dict:
                        result['endpoints'] = metadata_dict['endpoints']
                except ValueError:
                    logger.error(
                        f'Failed to encode as json metadata: {decoded_metadata}'
                    )
                    raise
                return result
            else:
                raise serializers.ValidationError(
                    'Unexpected structure of output', last_line
                )


class UpdateProcessor(
    ContainerExecutorMixin, processors.AbstractUpdateResourceProcessor
):
    hook_type = 'update'

    def send_request(self, user):
        self.order.resource.set_state_updating()
        self.order.resource.save(update_fields=['state'])
        super().send_request(user)
        return True

    def update_limits_process(self, user):
        super().send_request(user)
        return True


class DeleteProcessor(
    ContainerExecutorMixin, processors.AbstractDeleteResourceProcessor
):
    hook_type = 'terminate'

    def send_request(self, user, resource):
        resource.set_state_terminating()
        resource.save(update_fields=['state'])
        super().send_request(user, resource)
        return True
