from unittest import mock

from constance.test.pytest import override_config
from rest_framework import status, test
from rest_framework.reverse import reverse

from waldur_core.permissions.fixtures import ProjectRole
from waldur_core.structure.exceptions import ServiceBackendError
from waldur_core.structure.tests.factories import CustomerFactory, UserFactory
from waldur_mastermind.marketplace.models import Offering
from waldur_mastermind.marketplace.tests.factories import OfferingFactory, PlanFactory
from waldur_mastermind.marketplace_flows.models import (
    CustomerCreateRequest,
    FlowTracker,
    OfferingStateRequest,
    ProjectCreateRequest,
    ResourceCreateRequest,
)
from waldur_mastermind.marketplace_support.tests.fixtures import SupportFixture
from waldur_mastermind.support import models as support_models
from waldur_mastermind.support.tests import factories as support_factories

from . import factories


class CreateResourceFlowTest(test.APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.list_url = reverse('marketplace-resource-creation-flow-list')
        self.fixture = SupportFixture()
        self.offering = self.fixture.offering
        self.offering.state = Offering.States.ACTIVE
        self.offering.save()
        self.plan = self.fixture.plan
        self.user = UserFactory()
        self.payload = {
            'customer_create_request': {'name': 'XYZ corp'},
            'project_create_request': {'name': 'First project'},
            'resource_create_request': {
                'name': 'Test VM',
                'offering': OfferingFactory.get_public_url(self.offering),
                'plan': PlanFactory.get_public_url(self.plan),
                'attributes': {},
            },
        }

    def test_user_can_create_submission(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        flow = FlowTracker.objects.get(uuid=response.data['uuid'])
        self.assertEqual(flow.requested_by, self.user)
        self.assertEqual(flow.customer_create_request.name, 'XYZ corp')
        self.assertEqual(flow.project_create_request.name, 'First project')
        self.assertEqual(flow.resource_create_request.name, 'Test VM')
        self.assertEqual(flow.resource_create_request.offering, self.offering)
        self.assertEqual(flow.resource_create_request.plan, self.plan)

    def test_user_can_create_submission_for_existing_customer(self):
        self.client.force_authenticate(self.user)

        del self.payload['customer_create_request']
        self.payload['customer'] = CustomerFactory.get_url(self.fixture.customer)
        self.fixture.project.add_user(self.user, ProjectRole.MEMBER)

        response = self.client.post(self.list_url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        flow = FlowTracker.objects.get(uuid=response.data['uuid'])
        self.assertEqual(flow.customer_create_request, None)
        self.assertEqual(flow.customer, self.fixture.customer)

    def test_user_can_not_create_submission_for_unrelated_customer(self):
        self.client.force_authenticate(self.user)

        del self.payload['customer_create_request']
        self.payload['customer'] = CustomerFactory.get_url(self.fixture.customer)

        response = self.client.post(self.list_url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_active_offering_is_allowed(self):
        self.offering.state = Offering.States.DRAFT
        self.offering.save()
        self.client.force_authenticate(self.user)
        response = self.client.post(self.list_url, self.payload)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FlowOperationsTest(test.APITransactionTestCase):
    def setUp(self):
        super().setUp()
        self.fixture = SupportFixture()
        self.flow = FlowTracker.objects.create(
            requested_by=self.fixture.manager,
            customer=self.fixture.customer,
            project_create_request=ProjectCreateRequest.objects.create(
                name='First project'
            ),
            resource_create_request=ResourceCreateRequest.objects.create(
                name='First project',
                offering=self.fixture.offering,
                plan=self.fixture.plan,
            ),
        )


class ListResourceFlowTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.list_url = reverse('marketplace-resource-creation-flow-list')

    def test_user_can_see_his_own_flow(self):
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 1)

    def test_staff_can_see_his_any_flow(self):
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 1)

    def test_other_user_can_not_see_flow(self):
        self.client.force_authenticate(self.fixture.user)
        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 0)


class FlowSubmitTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.detail_url = (
            reverse(
                'marketplace-resource-creation-flow-detail',
                kwargs={'uuid': self.flow.uuid.hex},
            )
            + 'submit/'
        )

    def test_user_can_submit_his_own_flow(self):
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_can_not_submit_flow_of_other_user(self):
        self.client.force_authenticate(self.fixture.user)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_not_submit_pending_flow(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class FlowCancelTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.detail_url = (
            reverse(
                'marketplace-resource-creation-flow-detail',
                kwargs={'uuid': self.flow.uuid.hex},
            )
            + 'cancel/'
        )

    def test_user_can_cancel_his_own_flow(self):
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_user_can_not_cancel_flow_of_other_user(self):
        self.client.force_authenticate(self.fixture.user)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_not_cancel_pending_flow(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)


class CustomerCreationApproveTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.flow.customer_create_request = CustomerCreateRequest.objects.create(
            name='XYZ corp'
        )
        self.flow.save()

        self.detail_url = (
            reverse(
                'marketplace-customer-creation-request-detail',
                kwargs={'flow__uuid': self.flow.uuid.hex},
            )
            + 'approve/'
        )

    def test_staff_can_approve_pending_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.flow.refresh_from_db()
        self.assertEqual(
            self.flow.customer_create_request.state,
            CustomerCreateRequest.States.APPROVED,
        )
        self.assertEqual(
            self.flow.customer_create_request.reviewed_by, self.fixture.staff
        )

    def test_reviewer_may_attach_comment(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url, {'comment': 'Test comment'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.flow.refresh_from_db()
        self.assertEqual(
            self.flow.customer_create_request.review_comment, 'Test comment'
        )

    def test_staff_can_not_approve_draft_request(self):
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_non_staff_can_not_approve_request(self):
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CustomerCreationRejectTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.flow.customer_create_request = CustomerCreateRequest.objects.create(
            name='XYZ corp'
        )
        self.flow.save()

        self.detail_url = (
            reverse(
                'marketplace-customer-creation-request-detail',
                kwargs={'flow__uuid': self.flow.uuid.hex},
            )
            + 'reject/'
        )

    def test_staff_can_reject_pending_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.flow.refresh_from_db()
        self.assertEqual(
            self.flow.customer_create_request.state,
            CustomerCreateRequest.States.REJECTED,
        )
        self.assertEqual(self.flow.state, CustomerCreateRequest.States.REJECTED)
        self.assertEqual(
            self.flow.customer_create_request.reviewed_by, self.fixture.staff
        )

    def test_staff_can_not_reject_draft_request(self):
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_non_staff_can_not_reject_request(self):
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectCreationApproveTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.detail_url = (
            reverse(
                'marketplace-project-creation-request-detail',
                kwargs={'flow__uuid': self.flow.uuid.hex},
            )
            + 'approve/'
        )

    def test_staff_can_approve_project_creation_request_even_if_customer_is_not_defined(
        self,
    ):
        self.flow.customer_create_request = CustomerCreateRequest.objects.create(
            name='XYZ corp'
        )
        self.flow.save()
        self.flow.submit()
        self.client.force_authenticate(self.fixture.staff)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_customer_owner_can_approve_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.owner)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.flow.project_create_request.refresh_from_db()
        self.assertEqual(
            self.flow.project_create_request.state,
            ProjectCreateRequest.States.APPROVED,
        )
        self.assertEqual(
            self.flow.project_create_request.reviewed_by, self.fixture.owner
        )

    def test_unauthorized_user_can_not_approve_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ProjectCreationRejectTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.detail_url = (
            reverse(
                'marketplace-project-creation-request-detail',
                kwargs={'flow__uuid': self.flow.uuid.hex},
            )
            + 'reject/'
        )

    def test_customer_owner_can_reject_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.owner)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.flow.refresh_from_db()
        self.assertEqual(
            self.flow.state,
            ProjectCreateRequest.States.REJECTED,
        )

    def test_unauthorized_user_can_not_reject_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ResourceCreationApproveTest(FlowOperationsTest):
    def setUp(self):
        super().setUp()
        self.detail_url = (
            reverse(
                'marketplace-resource-creation-request-detail',
                kwargs={'flow__uuid': self.flow.uuid.hex},
            )
            + 'approve/'
        )

    def test_service_owner_can_approve_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.service_owner)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.flow.resource_create_request.refresh_from_db()
        self.assertEqual(
            self.flow.resource_create_request.state,
            ResourceCreateRequest.States.APPROVED,
        )
        self.assertEqual(
            self.flow.resource_create_request.reviewed_by, self.fixture.service_owner
        )

    def test_service_owner_can_not_approve_draft_request(self):
        self.client.force_authenticate(self.fixture.service_owner)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_unauthorized_user_can_not_approve_request(self):
        self.flow.submit()
        self.client.force_authenticate(self.fixture.manager)
        response = self.client.post(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FlowApproveTest(FlowOperationsTest):
    def test_when_all_requests_are_approved_flow_is_approved_too(self):
        self.flow.submit()
        self.flow.project_create_request.approve(self.fixture.owner)
        self.flow.resource_create_request.approve(self.fixture.service_owner)
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, FlowTracker.States.APPROVED)
        self.assertEqual(
            self.flow.order.offering, self.flow.resource_create_request.offering
        )
        self.assertEqual(self.flow.order.project.customer, self.flow.customer)
        self.assertTrue(self.flow.order.project.has_user(self.flow.requested_by))


@override_config(WALDUR_SUPPORT_ENABLED=False)
class CreateOfferingStateRequestTest(test.APITransactionTestCase):
    def setUp(self):
        self.list_url = reverse('marketplace-offering-activate-request-list')
        self.fixture = SupportFixture()
        self.offering = self.fixture.offering
        self.offering.state = Offering.States.DRAFT
        self.offering.save()
        self.plan = self.fixture.plan
        self.user = UserFactory()
        self.offering_url = OfferingFactory.get_url(self.offering)

    def test_user_can_create_request(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            OfferingStateRequest.objects.filter(requested_by=self.user).exists()
        )

    def test_user_cannot_create_request_if_offering_state_is_not_draft(self):
        self.client.force_authenticate(self.user)
        self.offering.state = Offering.States.ACTIVE
        self.offering.save()
        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_create_request_twice(self):
        self.client.force_authenticate(self.user)
        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_can_get_only_his_requests(self):
        factories.OfferingStateRequestFactory(requested_by=self.user)
        factories.OfferingStateRequestFactory()

        self.client.force_authenticate(self.user)
        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 1)

        self.client.force_authenticate(self.fixture.staff)
        response = self.client.get(self.list_url)
        self.assertEqual(len(response.data), 2)

    def test_staff_can_approve_request(self):
        offering_request = factories.OfferingStateRequestFactory(
            requested_by=self.user,
            state=OfferingStateRequest.States.PENDING,
            offering=self.offering,
        )
        approve_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'approve'
        )
        self.client.force_authenticate(self.fixture.staff)

        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.state, Offering.States.ACTIVE)
        offering_request.refresh_from_db()
        self.assertEqual(offering_request.state, OfferingStateRequest.States.APPROVED)

        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_staff_can_reject_request(self):
        offering_request = factories.OfferingStateRequestFactory(
            requested_by=self.user,
            state=OfferingStateRequest.States.PENDING,
            offering=self.offering,
        )
        reject_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'reject'
        )
        self.client.force_authenticate(self.fixture.staff)

        response = self.client.post(reject_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.state, Offering.States.DRAFT)
        offering_request.refresh_from_db()
        self.assertEqual(offering_request.state, OfferingStateRequest.States.REJECTED)

        response = self.client.post(reject_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_user_cannot_approve_or_reject_request(self):
        offering_request = factories.OfferingStateRequestFactory(
            requested_by=self.user,
            state=OfferingStateRequest.States.PENDING,
            offering=self.offering,
        )

        self.client.force_authenticate(self.user)

        approve_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'approve'
        )
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        approve_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'reject'
        )
        response = self.client.post(approve_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_submit_request(self):
        offering_request = factories.OfferingStateRequestFactory(
            requested_by=self.user,
            state=OfferingStateRequest.States.DRAFT,
            offering=self.offering,
        )

        self.client.force_authenticate(self.user)

        submit_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'submit'
        )
        response = self.client.post(submit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offering_request.refresh_from_db()
        self.assertEqual(offering_request.state, OfferingStateRequest.States.PENDING)

        response = self.client.post(submit_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    def test_user_can_cancel_request(self):
        offering_request = factories.OfferingStateRequestFactory(
            requested_by=self.user,
            state=OfferingStateRequest.States.DRAFT,
            offering=self.offering,
        )

        self.client.force_authenticate(self.user)

        cancel_url = factories.OfferingStateRequestFactory.get_url(
            offering_request, 'cancel'
        )
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        offering_request.refresh_from_db()
        self.assertEqual(offering_request.state, OfferingStateRequest.States.CANCELED)

        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    @mock.patch('waldur_mastermind.support.views.backend')
    @override_config(WALDUR_SUPPORT_ENABLED=True)
    def test_create_related_issue(self, mock_backend):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            OfferingStateRequest.objects.filter(requested_by=self.user).count(), 1
        )
        offering_request = OfferingStateRequest.objects.get(requested_by=self.user)
        self.assertEqual(offering_request.state, OfferingStateRequest.States.PENDING)
        self.assertTrue(offering_request.issue)
        mock_backend.get_active_backend().create_issue.assert_called_once()

    def test_do_not_create_issue_if_support_extension_is_not_enabled(self):
        self.client.force_authenticate(self.user)

        response = self.client.post(self.list_url, {'offering': self.offering_url})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            OfferingStateRequest.objects.filter(requested_by=self.user).count(), 1
        )
        offering_request = OfferingStateRequest.objects.get(requested_by=self.user)
        self.assertEqual(offering_request.state, OfferingStateRequest.States.DRAFT)
        self.assertFalse(offering_request.issue)

    @mock.patch('waldur_mastermind.support.views.backend')
    @override_config(WALDUR_SUPPORT_ENABLED=True)
    def test_do_not_create_request_if_related_jira_issue_has_not_been_created(
        self, mock_backend
    ):
        self.client.force_authenticate(self.user)

        def create_issue(*args, **kwargs):
            raise ServiceBackendError()

        mock_backend.get_active_backend().create_issue = create_issue
        self.assertRaises(
            ServiceBackendError,
            self.client.post,
            self.list_url,
            {'offering': self.offering_url},
        )


class IssueTest(test.APITransactionTestCase):
    def setUp(self):
        self.issue = support_factories.IssueFactory()
        support_factories.IssueStatusFactory(
            name='RESOLVED', type=support_models.IssueStatus.Types.RESOLVED
        )
        support_factories.IssueStatusFactory(
            name='CANCELED', type=support_models.IssueStatus.Types.CANCELED
        )
        self.offering_request = factories.OfferingStateRequestFactory(issue=self.issue)
        PlanFactory(offering=self.offering_request.offering)
        self.offering_request.submit()

    def test_request_will_be_approved_if_issue_has_been_resolved(self):
        self.issue.set_resolved()
        self.offering_request.refresh_from_db()
        self.assertEqual(
            self.offering_request.state, OfferingStateRequest.States.APPROVED
        )

    def test_request_will_be_rejected_if_issue_has_been_canceled(self):
        self.issue.set_canceled()
        self.offering_request.refresh_from_db()
        self.assertEqual(
            self.offering_request.state, OfferingStateRequest.States.REJECTED
        )

    def test_request_does_not_change_if_issue_has_not_been_resolved(self):
        self.issue.status = 'OTHER'
        self.issue.save()
        self.offering_request.refresh_from_db()
        self.assertEqual(
            self.offering_request.state, OfferingStateRequest.States.PENDING
        )
