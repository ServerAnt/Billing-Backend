from datetime import timedelta
from unittest import mock

from ddt import data, ddt
from django.core import mail, signing
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from waldur_core.core import utils as core_utils
from waldur_core.structure.tests import factories as structure_factories
from waldur_mastermind.support import models, tasks
from waldur_mastermind.support.backend.atlassian import ServiceDeskBackend
from waldur_mastermind.support.tests import base, factories


@ddt
class FeedbackCreateTest(base.BaseTest):
    @data(
        "staff",
        "owner",
        "admin",
        "manager",
        "user",
        "",
    )
    def test_user_can_create_feedback(self, user):
        url = factories.FeedbackFactory.get_list_url()
        issue = factories.IssueFactory()
        signer = signing.TimestampSigner()
        token = signer.sign(issue.uuid.hex)

        if user:
            self.client.force_authenticate(getattr(self.fixture, user))

        response = self.client.post(
            url,
            data={"evaluation": 10, "token": token},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_comment_has_been_created_if_feedback_has_been_synchronized(self):
        with mock.patch.object(ServiceDeskBackend, "create_comment"):
            backend = ServiceDeskBackend()
            feedback = factories.FeedbackFactory(comment="Test Feedback", evaluation=0)
            backend.create_feedback(feedback)
            self.assertTrue(
                models.Feedback.objects.filter(issue=feedback.issue).exists()
            )

    def test_user_cannot_create_feedback_if_token_is_wrong(self):
        url = factories.FeedbackFactory.get_list_url()
        token = "token"

        response = self.client.post(
            url,
            data={"evaluation": 10, "token": token},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_cannot_create_feedback_if_it_already_exists(self):
        url = factories.FeedbackFactory.get_list_url()
        feedback = factories.FeedbackFactory()
        issue = feedback.issue
        signer = signing.TimestampSigner()
        token = signer.sign(issue.uuid.hex)

        response = self.client.post(
            url,
            data={"evaluation": 10, "token": token},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FeedbackNotificationTest(base.BaseTest):
    def setUp(self):
        super().setUp()
        factories.IssueStatusFactory(
            name="resolved", type=models.IssueStatus.Types.RESOLVED
        )
        factories.IssueStatusFactory(
            name="closed", type=models.IssueStatus.Types.RESOLVED
        )
        factories.IssueStatusFactory(
            name="canceled", type=models.IssueStatus.Types.CANCELED
        )

    @mock.patch(
        "waldur_mastermind.support.handlers.tasks.send_issue_feedback_notification"
    )
    @override_settings(ISSUE_FEEDBACK_ENABLE=True)
    def test_feedback_notification(self, mock_tasks):
        issue = factories.IssueFactory()
        issue.set_resolved()
        serialized_issue = core_utils.serialize_instance(issue)
        mock_tasks.delay.assert_called_once_with(serialized_issue)

    @mock.patch(
        "waldur_mastermind.support.handlers.tasks.send_issue_feedback_notification"
    )
    @override_settings(ISSUE_FEEDBACK_ENABLE=True)
    def test_feedback_notification_does_not_send_twice(self, mock_tasks):
        issue = factories.IssueFactory(status="resolved")
        issue.status = "closed"
        issue.save()
        mock_tasks.delay.assert_not_called()

    def test_feedback_notification_text(self):
        structure_factories.NotificationFactory(
            key="support.notification_issue_feedback", enabled=True
        )
        issue = factories.IssueFactory()
        serialized_issue = core_utils.serialize_instance(issue)
        tasks.send_issue_feedback_notification(serialized_issue)
        self.assertEqual(len(mail.outbox), 1)


@ddt
class FeedbackReportTest(base.BaseTest):
    def setUp(self):
        super().setUp()
        factories.FeedbackFactory(evaluation=10)
        factories.FeedbackFactory(evaluation=6)
        self.avg = round(
            (10 + 6) / 2,
            2,
        )

    @data(
        "staff",
        "global_support",
    )
    def test_user_can_get_report(self, user):
        if user:
            self.client.force_authenticate(getattr(self.fixture, user))
            url_report = reverse("support-feedback-report")
            response = self.client.get(url_report)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data, {"Positive": 1, "Negative": 1})

            url_average = reverse("support-feedback-average-report")
            response = self.client.get(url_average)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertTrue(response.data, self.avg)

    @data(
        "owner",
        "admin",
        "manager",
        "user",
        "",
    )
    def test_user_can_not_get_report(self, user):
        if user:
            self.client.force_authenticate(getattr(self.fixture, user))
            url_report = reverse("support-feedback-report")
            response = self.client.get(url_report)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            url_average = reverse("support-feedback-average-report")
            response = self.client.get(url_average)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class FeedbackGetTest(base.BaseTest):
    def test_feedback_get(self):
        feedback = self.fixture.feedback

        self.client.force_login(self.fixture.staff)
        response = self.client.get(factories.FeedbackFactory.get_url(feedback))

        self.assertEqual(200, response.status_code)
        self.assertEqual(feedback.uuid.hex, response.data["uuid"])
        self.assertIn("issue_uuid", response.data)
        self.assertIn("issue_key", response.data)
        self.assertIn("user_full_name", response.data)
        self.assertIn("issue_summary", response.data)

    def test_feedback_get_is_not_allowed_for_regular_user(self):
        feedback = self.fixture.feedback

        self.client.force_login(self.fixture.user)
        response = self.client.get(factories.FeedbackFactory.get_url(feedback))

        self.assertEqual(403, response.status_code)

    def test_feedback_filtering_by_issue(self):
        issue = self.fixture.issue
        feedback = self.fixture.feedback

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"issue_uuid": issue.uuid.hex}
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual([feedback.uuid.hex], [item["uuid"] for item in response.data])

    def test_feedback_filtering_by_user(self):
        user = self.fixture.issue.caller
        feedback = self.fixture.feedback

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"user_uuid": user.uuid.hex}
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual([feedback.uuid.hex], [item["uuid"] for item in response.data])

    def test_feedback_filtering_by_evaluation(self):
        feedback = self.fixture.feedback
        feedback.evaluation = 2
        feedback.save()

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"evaluation": "2"}
        )

        self.assertEqual(200, response.status_code)
        self.assertEqual(
            models.Feedback.objects.filter(evaluation=2).count(), len(response.data)
        )
        self.assertIn(feedback.uuid.hex, [item["uuid"] for item in response.data])

    def test_feedback_filtering_by_time(self):
        feedback = self.fixture.feedback
        time = feedback.created + timedelta(days=1)

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(),
            {"created_before": time.strftime("%Y-%m-%d")},
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(feedback.uuid.hex, [item["uuid"] for item in response.data])

    def test_feedback_filtering_by_issue_key(self):
        feedback = self.fixture.feedback
        issue_key = feedback.issue.key

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"issue_key": issue_key}
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(feedback.uuid.hex, [item["uuid"] for item in response.data])

        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"issue_key": "other_key"}
        )

        self.assertEqual(200, response.status_code)
        self.assertNotIn(feedback.uuid.hex, [item["uuid"] for item in response.data])

    def test_feedback_filtering_by_caller_full_name(self):
        feedback = self.fixture.feedback
        full_name = feedback.issue.caller.full_name

        self.client.force_login(self.fixture.staff)
        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"user_full_name": full_name}
        )

        self.assertEqual(200, response.status_code)
        self.assertIn(feedback.uuid.hex, [item["uuid"] for item in response.data])

        response = self.client.get(
            factories.FeedbackFactory.get_list_url(), {"user_full_name": "other_name"}
        )

        self.assertEqual(200, response.status_code)
        self.assertNotIn(feedback.uuid.hex, [item["uuid"] for item in response.data])
