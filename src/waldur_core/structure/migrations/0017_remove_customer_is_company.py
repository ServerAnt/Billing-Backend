# Generated by Django 2.2.13 on 2020-12-14 11:05

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0016_customerpermissionreview'),
    ]

    operations = [
        migrations.RemoveField(model_name='customer', name='is_company',),
    ]
