# Generated by Django 3.2.20 on 2023-09-01 06:44

from django.db import migrations, models

import waldur_core.core.validators


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace_checklist', '0001_squashed_0012_alter_answer_value'),
    ]

    operations = [
        migrations.RunSQL(
            [
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_da;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_de;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_es;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_fr;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_it;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_lt;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_lv;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_nb;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_ru;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS description_sv;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_da;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_de;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_es;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_fr;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_it;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_lt;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_lv;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_nb;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_ru;',
                'ALTER TABLE marketplace_checklist_checklist DROP COLUMN IF EXISTS name_sv;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_da;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_de;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_es;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_fr;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_it;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_lt;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_lv;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_nb;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_ru;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS description_sv;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_da;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_de;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_es;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_fr;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_it;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_lt;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_lv;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_nb;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_ru;',
                'ALTER TABLE marketplace_checklist_question DROP COLUMN IF EXISTS solution_sv;',
            ]
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_da',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_de',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_es',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_fr',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_it',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_lt',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_lv',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_nb',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_ru',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='description_sv',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_da',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_de',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_es',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_fr',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_it',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_lt',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_lv',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_nb',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_ru',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='checklist',
            name='name_sv',
            field=models.CharField(
                max_length=150,
                null=True,
                validators=[waldur_core.core.validators.validate_name],
                verbose_name='name',
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_da',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_de',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_es',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_fr',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_it',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_lt',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_lv',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_nb',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_ru',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='description_sv',
            field=models.CharField(
                blank=True, max_length=2000, null=True, verbose_name='description'
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_da',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_de',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_es',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_fr',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_it',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_lt',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_lv',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_nb',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_ru',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='question',
            name='solution_sv',
            field=models.TextField(
                blank=True,
                help_text='It is shown when incorrect or N/A answer is chosen',
                null=True,
            ),
        ),
    ]
