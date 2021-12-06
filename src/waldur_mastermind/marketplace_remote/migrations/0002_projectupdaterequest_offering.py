# Generated by Django 2.2.24 on 2021-12-06 14:20

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('marketplace', '0061_order_item_review'),
        ('marketplace_remote', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='projectupdaterequest',
            name='offering',
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='+',
                to='marketplace.Offering',
            ),
            preserve_default=False,
        ),
    ]
