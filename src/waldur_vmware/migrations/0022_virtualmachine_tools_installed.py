# -*- coding: utf-8 -*-
# Generated by Django 1.11.21 on 2019-08-28 11:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('waldur_vmware', '0021_virtualmachine_tools_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='virtualmachine',
            name='tools_installed',
            field=models.BooleanField(default=False),
        ),
    ]
