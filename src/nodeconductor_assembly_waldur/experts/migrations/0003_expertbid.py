# -*- coding: utf-8 -*-
# Generated by Django 1.11.1 on 2017-07-07 15:09
from __future__ import unicode_literals

from decimal import Decimal
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import nodeconductor.core.fields


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0052_customer_subnets'),
        ('experts', '0002_expertrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpertBid',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', nodeconductor.core.fields.UUIDField()),
                ('price', models.DecimalField(decimal_places=7, default=0, max_digits=22, validators=[django.core.validators.MinValueValidator(Decimal('0'))])),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='experts.ExpertRequest')),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='structure.Project')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
