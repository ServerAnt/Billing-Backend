# Generated by Django 4.2.10 on 2024-07-24 13:35

import django.db.models.deletion
import django.utils.timezone
import model_utils.fields
from django.conf import settings
from django.db import migrations, models

import waldur_core.core.fields


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("structure", "0045_customer_slug_project_slug"),
        ("marketplace", "0132_offering_slug_resource_slug"),
        ("policy", "0005_rename_customer_customerestimatedcostpolicy_scope_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OfferingEstimatedCostPolicy",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="created",
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name="modified",
                    ),
                ),
                ("uuid", waldur_core.core.fields.UUIDField()),
                ("has_fired", models.BooleanField(default=False)),
                (
                    "fired_datetime",
                    models.DateTimeField(blank=True, editable=False, null=True),
                ),
                ("limit_cost", models.IntegerField()),
                ("actions", models.CharField(max_length=255)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization_groups",
                    models.ManyToManyField(to="structure.organizationgroup"),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="marketplace.offering",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Offering estimated cost policies",
            },
        ),
    ]
