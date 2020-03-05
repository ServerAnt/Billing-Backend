# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2017-12-16 09:48
import django.db.models.deletion
import django.utils.timezone
import django_fsm
import model_utils.fields
from django.db import migrations, models

import waldur_core.core.fields
import waldur_core.core.models
import waldur_core.core.shims
import waldur_core.core.validators
import waldur_core.logging.loggers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('taggit', '0002_auto_20150616_2121'),
        ('contenttypes', '0002_remove_content_type_name'),
        ('structure', '0001_squashed_0054'),
    ]

    operations = [
        migrations.CreateModel(
            name='Host',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name='created',
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name='modified',
                    ),
                ),
                (
                    'description',
                    models.CharField(
                        blank=True, max_length=500, verbose_name='description'
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=64,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('error_message', models.TextField(blank=True)),
                (
                    'state',
                    django_fsm.FSMIntegerField(
                        choices=[
                            (5, 'Creation Scheduled'),
                            (6, 'Creating'),
                            (1, 'Update Scheduled'),
                            (2, 'Updating'),
                            (7, 'Deletion Scheduled'),
                            (8, 'Deleting'),
                            (3, 'OK'),
                            (4, 'Erred'),
                        ],
                        default=5,
                    ),
                ),
                ('backend_id', models.CharField(blank=True, max_length=255)),
                (
                    'visible_name',
                    models.CharField(max_length=64, verbose_name='visible name'),
                ),
                ('interface_parameters', waldur_core.core.fields.JSONField(blank=True)),
                (
                    'host_group_name',
                    models.CharField(
                        blank=True, max_length=64, verbose_name='host group name'
                    ),
                ),
                (
                    'error',
                    models.CharField(
                        blank=True,
                        help_text='Error text if Zabbix agent is unavailable.',
                        max_length=500,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[('0', 'monitored'), ('1', 'unmonitored')],
                        default='0',
                        max_length=30,
                    ),
                ),
                ('object_id', models.PositiveIntegerField(null=True)),
                (
                    'content_type',
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to='contenttypes.ContentType',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(
                waldur_core.core.models.DescendantMixin,
                waldur_core.core.models.BackendModelMixin,
                waldur_core.logging.loggers.LoggableMixin,
                models.Model,
            ),
        ),
        migrations.CreateModel(
            name='Item',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('key', models.CharField(max_length=255)),
                ('name', models.CharField(max_length=255)),
                ('backend_id', models.CharField(max_length=64)),
                (
                    'value_type',
                    models.IntegerField(
                        choices=[
                            (0, 'Numeric (float)'),
                            (1, 'Character'),
                            (2, 'Log'),
                            (3, 'Numeric (unsigned)'),
                            (4, 'Text'),
                        ]
                    ),
                ),
                ('units', models.CharField(max_length=255)),
                ('history', models.IntegerField()),
                ('delay', models.IntegerField()),
            ],
        ),
        migrations.CreateModel(
            name='ITService',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'created',
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name='created',
                    ),
                ),
                (
                    'modified',
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now,
                        editable=False,
                        verbose_name='modified',
                    ),
                ),
                (
                    'description',
                    models.CharField(
                        blank=True, max_length=500, verbose_name='description'
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=150,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('error_message', models.TextField(blank=True)),
                (
                    'state',
                    django_fsm.FSMIntegerField(
                        choices=[
                            (5, 'Creation Scheduled'),
                            (6, 'Creating'),
                            (1, 'Update Scheduled'),
                            (2, 'Updating'),
                            (7, 'Deletion Scheduled'),
                            (8, 'Deleting'),
                            (3, 'OK'),
                            (4, 'Erred'),
                        ],
                        default=5,
                    ),
                ),
                ('backend_id', models.CharField(blank=True, max_length=255)),
                (
                    'is_main',
                    models.BooleanField(
                        default=True,
                        help_text='Main IT service SLA will be added to hosts resource as monitoring item.',
                    ),
                ),
                (
                    'algorithm',
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, 'do not calculate'),
                            (1, 'problem, if at least one child has a problem'),
                            (2, 'problem, if all children have problems'),
                        ],
                        default=0,
                    ),
                ),
                ('sort_order', models.PositiveSmallIntegerField(default=1)),
                (
                    'agreed_sla',
                    models.DecimalField(
                        blank=True, decimal_places=4, max_digits=6, null=True
                    ),
                ),
                (
                    'backend_trigger_id',
                    models.CharField(blank=True, max_length=64, null=True),
                ),
                (
                    'host',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='itservices',
                        to='waldur_zabbix.Host',
                    ),
                ),
            ],
            bases=(
                waldur_core.core.models.DescendantMixin,
                waldur_core.core.models.BackendModelMixin,
                waldur_core.logging.loggers.LoggableMixin,
                models.Model,
            ),
        ),
        migrations.CreateModel(
            name='SlaHistory',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('period', models.CharField(max_length=10)),
                (
                    'value',
                    models.DecimalField(
                        blank=True, decimal_places=4, max_digits=11, null=True
                    ),
                ),
                (
                    'itservice',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='waldur_zabbix.ITService',
                    ),
                ),
            ],
            options={
                'verbose_name': 'SLA history',
                'verbose_name_plural': 'SLA histories',
            },
        ),
        migrations.CreateModel(
            name='SlaHistoryEvent',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('timestamp', models.IntegerField()),
                (
                    'state',
                    models.CharField(
                        choices=[('U', 'DOWN'), ('D', 'UP')], max_length=1
                    ),
                ),
                (
                    'history',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='events',
                        to='waldur_zabbix.SlaHistory',
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name='Template',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=150,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('backend_id', models.CharField(db_index=True, max_length=255)),
                (
                    'parents',
                    models.ManyToManyField(
                        related_name='children', to='waldur_zabbix.Template'
                    ),
                ),
                (
                    'settings',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='+',
                        to='structure.ServiceSettings',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(waldur_core.core.models.BackendModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='Trigger',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=255,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('backend_id', models.CharField(db_index=True, max_length=255)),
                (
                    'settings',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='+',
                        to='structure.ServiceSettings',
                    ),
                ),
                (
                    'template',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='triggers',
                        to='waldur_zabbix.Template',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(waldur_core.core.models.BackendModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='User',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=150,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('error_message', models.TextField(blank=True)),
                (
                    'state',
                    django_fsm.FSMIntegerField(
                        choices=[
                            (5, 'Creation Scheduled'),
                            (6, 'Creating'),
                            (1, 'Update Scheduled'),
                            (2, 'Updating'),
                            (7, 'Deletion Scheduled'),
                            (8, 'Deleting'),
                            (3, 'OK'),
                            (4, 'Erred'),
                        ],
                        default=5,
                    ),
                ),
                ('backend_id', models.CharField(db_index=True, max_length=255)),
                ('alias', models.CharField(max_length=150)),
                ('surname', models.CharField(max_length=150)),
                (
                    'type',
                    models.CharField(
                        choices=[('1', 'default'), ('2', 'admin'), ('3', 'superadmin')],
                        default='1',
                        max_length=30,
                    ),
                ),
                ('password', models.CharField(blank=True, max_length=150)),
                ('phone', models.CharField(blank=True, max_length=30)),
            ],
            bases=(waldur_core.core.models.BackendModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='UserGroup',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'name',
                    models.CharField(
                        max_length=150,
                        validators=[waldur_core.core.validators.validate_name],
                        verbose_name='name',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                ('backend_id', models.CharField(db_index=True, max_length=255)),
                (
                    'settings',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='+',
                        to='structure.ServiceSettings',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(waldur_core.core.models.BackendModelMixin, models.Model),
        ),
        migrations.CreateModel(
            name='ZabbixService',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('uuid', waldur_core.core.fields.UUIDField()),
                (
                    'available_for_all',
                    models.BooleanField(
                        default=False,
                        help_text='Service will be automatically added to all customers projects if it is available for all',
                    ),
                ),
                (
                    'customer',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='structure.Customer',
                        verbose_name='organization',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(
                waldur_core.core.models.DescendantMixin,
                waldur_core.logging.loggers.LoggableMixin,
                models.Model,
            ),
        ),
        migrations.CreateModel(
            name='ZabbixServiceProjectLink',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'project',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='structure.Project',
                    ),
                ),
                (
                    'service',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='waldur_zabbix.ZabbixService',
                    ),
                ),
            ],
            options={'abstract': False,},
            bases=(
                waldur_core.core.models.DescendantMixin,
                waldur_core.logging.loggers.LoggableMixin,
                models.Model,
            ),
        ),
        migrations.AddField(
            model_name='zabbixservice',
            name='projects',
            field=models.ManyToManyField(
                related_name='zabbix_services',
                through='waldur_zabbix.ZabbixServiceProjectLink',
                to='structure.Project',
            ),
        ),
        migrations.AddField(
            model_name='zabbixservice',
            name='settings',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='structure.ServiceSettings',
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(
                related_name='users', to='waldur_zabbix.UserGroup'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='settings',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                to='structure.ServiceSettings',
            ),
        ),
        migrations.AddField(
            model_name='itservice',
            name='service_project_link',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='itservices',
                to='waldur_zabbix.ZabbixServiceProjectLink',
            ),
        ),
        migrations.AddField(
            model_name='itservice',
            name='tags',
            field=waldur_core.core.shims.TaggableManager(
                related_name='+',
                blank=True,
                help_text='A comma-separated list of tags.',
                through='taggit.TaggedItem',
                to='taggit.Tag',
                verbose_name='Tags',
            ),
        ),
        migrations.AddField(
            model_name='itservice',
            name='trigger',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='waldur_zabbix.Trigger',
            ),
        ),
        migrations.AddField(
            model_name='item',
            name='template',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='items',
                to='waldur_zabbix.Template',
            ),
        ),
        migrations.AddField(
            model_name='host',
            name='service_project_link',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='hosts',
                to='waldur_zabbix.ZabbixServiceProjectLink',
            ),
        ),
        migrations.AddField(
            model_name='host',
            name='tags',
            field=waldur_core.core.shims.TaggableManager(
                related_name='+',
                blank=True,
                help_text='A comma-separated list of tags.',
                through='taggit.TaggedItem',
                to='taggit.Tag',
                verbose_name='Tags',
            ),
        ),
        migrations.AddField(
            model_name='host',
            name='templates',
            field=models.ManyToManyField(
                related_name='hosts', to='waldur_zabbix.Template'
            ),
        ),
        migrations.AlterUniqueTogether(
            name='zabbixserviceprojectlink',
            unique_together=set([('service', 'project')]),
        ),
        migrations.AlterUniqueTogether(
            name='zabbixservice', unique_together=set([('customer', 'settings')]),
        ),
        migrations.AlterUniqueTogether(
            name='usergroup', unique_together=set([('settings', 'backend_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='user', unique_together=set([('alias', 'settings')]),
        ),
        migrations.AlterUniqueTogether(
            name='trigger', unique_together=set([('settings', 'backend_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='template', unique_together=set([('settings', 'backend_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='slahistory', unique_together=set([('itservice', 'period')]),
        ),
        migrations.AlterUniqueTogether(
            name='itservice', unique_together=set([('host', 'is_main')]),
        ),
    ]
