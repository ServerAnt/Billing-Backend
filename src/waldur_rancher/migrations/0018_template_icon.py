# Generated by Django 2.2.10 on 2020-03-02 15:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('waldur_rancher', '0017_pull_settings'),
    ]

    operations = [
        migrations.AddField(
            model_name='template',
            name='icon',
            field=models.FileField(blank=True, null=True, upload_to='rancher_icons'),
        ),
    ]