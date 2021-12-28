# Generated by Django 2.2.25 on 2021-12-27 15:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('openstack', '0024_securitygrouprule_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='port',
            name='port_security_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='port',
            name='security_groups',
            field=models.ManyToManyField(
                related_name='ports', to='openstack.SecurityGroup'
            ),
        ),
    ]
