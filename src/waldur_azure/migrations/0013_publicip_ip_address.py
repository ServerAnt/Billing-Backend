# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-02-08 13:41
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('waldur_azure', '0012_network_security_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='publicip',
            name='ip_address',
            field=models.GenericIPAddressField(
                blank=True, default=None, null=True, protocol='IPv4'
            ),
        ),
    ]
