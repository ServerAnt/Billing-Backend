# Generated by Django 2.2.13 on 2021-01-13 13:07

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0019_servicesettings_remove_deprecated_fields'),
    ]

    operations = [
        migrations.RemoveField(model_name='project', name='certifications',),
        migrations.DeleteModel(name='ServiceCertification',),
    ]
