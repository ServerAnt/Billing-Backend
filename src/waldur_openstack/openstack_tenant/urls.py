from django.urls import re_path

from . import views


def register_in(router):
    router.register(
        r"openstacktenant-images", views.ImageViewSet, basename="openstacktenant-image"
    )
    router.register(
        r"openstacktenant-flavors",
        views.FlavorViewSet,
        basename="openstacktenant-flavor",
    )
    router.register(
        r"openstacktenant-volumes",
        views.VolumeViewSet,
        basename="openstacktenant-volume",
    )
    router.register(
        r"openstacktenant-snapshots",
        views.SnapshotViewSet,
        basename="openstacktenant-snapshot",
    )
    router.register(
        r"openstacktenant-instance-availability-zones",
        views.InstanceAvailabilityZoneViewSet,
        basename="openstacktenant-instance-availability-zone",
    )
    router.register(
        r"openstacktenant-instances",
        views.InstanceViewSet,
        basename="openstacktenant-instance",
    )
    router.register(
        r"openstacktenant-backups",
        views.BackupViewSet,
        basename="openstacktenant-backup",
    )
    router.register(
        r"openstacktenant-backup-schedules",
        views.BackupScheduleViewSet,
        basename="openstacktenant-backup-schedule",
    )
    router.register(
        r"openstacktenant-snapshot-schedules",
        views.SnapshotScheduleViewSet,
        basename="openstacktenant-snapshot-schedule",
    )
    router.register(
        r"openstacktenant-volume-types",
        views.VolumeTypeViewSet,
        basename="openstacktenant-volume-type",
    )
    router.register(
        r"openstacktenant-volume-availability-zones",
        views.VolumeAvailabilityZoneViewSet,
        basename="openstacktenant-volume-availability-zone",
    )


urlpatterns = [
    re_path(
        r"^api/openstack-shared-settings-instances/$",
        views.SharedSettingsInstances.as_view(),
    ),
    re_path(
        r"^api/openstack-shared-settings-customers/$",
        views.SharedSettingsCustomers.as_view(),
    ),
]
