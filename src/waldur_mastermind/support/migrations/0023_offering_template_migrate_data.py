# -*- coding: utf-8 -*-
# Generated by Django 1.11.14 on 2018-08-09 10:34
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0022_offering_template'),
    ]

    def migrate_config(apps, schema_editor):
        if settings.DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql_psycopg2':
            return 

        OfferingTemplate = apps.get_model('support', 'OfferingTemplate')
        Offering = apps.get_model('support', 'Offering')
        config = settings.WALDUR_SUPPORT['OFFERINGS']

        for offering in Offering.objects.all():
            try:
                template, created = OfferingTemplate.objects.get_or_create(name=offering.type,
                                                                           defaults={'config': config[offering.type]})
                offering.template = template
                offering.save()
            except KeyError:
                pass

        for template in config.keys():
            OfferingTemplate.objects.get_or_create(name=template,
                                                   defaults={'config': config[template]})

    operations = [
        migrations.RunPython(migrate_config),
        migrations.AlterField(
            model_name='offering',
            name='template',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='support.OfferingTemplate')
        ),
    ]