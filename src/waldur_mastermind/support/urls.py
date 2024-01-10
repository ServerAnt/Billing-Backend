from django.urls import re_path

from waldur_mastermind.support import views


def register_in(router):
    router.register(r"support-issues", views.IssueViewSet, basename="support-issue")
    router.register(
        r"support-priorities", views.PriorityViewSet, basename="support-priority"
    )
    router.register(
        r"support-comments", views.CommentViewSet, basename="support-comment"
    )
    router.register(r"support-users", views.SupportUserViewSet, basename="support-user")
    router.register(
        r"support-attachments", views.AttachmentViewSet, basename="support-attachment"
    )
    router.register(
        r"support-templates", views.TemplateViewSet, basename="support-template"
    )
    router.register(
        r"support-feedbacks",
        views.FeedbackViewSet,
        basename="support-feedback",
    )


urlpatterns = [
    re_path(
        r"^api/support-jira-webhook/$",
        views.WebHookReceiverView.as_view(),
        name="web-hook-receiver",
    ),
    re_path(
        r"^api/support-feedback-report/$",
        views.FeedbackReportViewSet.as_view(),
        name="support-feedback-report",
    ),
    re_path(
        r"^api/support-feedback-average-report/$",
        views.FeedbackAverageReportViewSet.as_view(),
        name="support-feedback-average-report",
    ),
    re_path(
        r"^api/support-zammad-webhook/$",
        views.ZammadWebHookReceiverView.as_view(),
        name="zammad-web-hook-receiver",
    ),
    re_path(
        r"^api/support-statistics/$",
        views.SupportStatsViewSet.as_view(),
        name="support-statistics",
    ),
]
