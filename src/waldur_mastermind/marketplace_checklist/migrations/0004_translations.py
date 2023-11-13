# Generated by Django 3.2.20 on 2023-11-13 09:17

from django.db import migrations, models

import waldur_core.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace_checklist', '0003_translations'),
    ]

    operations = [
        migrations.AddField(
            model_name='checklist',
            name='description_cs',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_cs',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_cs',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_cs',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
    ]
