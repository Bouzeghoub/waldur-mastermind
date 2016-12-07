# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django.utils.timezone
from django.conf import settings
import model_utils.fields
import nodeconductor.core.fields
import nodeconductor.structure.models


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('structure', '0037_remove_customer_billing_backend_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='Issue',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, verbose_name='created', editable=False)),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, verbose_name='modified', editable=False)),
                ('uuid', nodeconductor.core.fields.UUIDField()),
                ('key', models.CharField(max_length=255)),
                ('type', models.SmallIntegerField(default=0, choices=[(0, 'Informational'), (1, 'Service request'), (2, 'Change request'), (3, 'Incident')])),
                ('summary', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('status', models.CharField(max_length=255)),
                ('resolution', models.CharField(max_length=255, blank=True)),
                ('object_id', models.PositiveIntegerField(null=True)),
                ('assignee', models.ForeignKey(related_name='assigned_issues', to=settings.AUTH_USER_MODEL, blank=True, null=True)),
                ('content_type', models.ForeignKey(to='contenttypes.ContentType', null=True)),
                ('creator', models.ForeignKey(related_name='created_issues', to=settings.AUTH_USER_MODEL)),
                ('customer', models.ForeignKey(related_name='issues', blank=True, to='structure.Customer', null=True)),
                ('project', models.ForeignKey(related_name='issues', blank=True, to='structure.Project', null=True)),
                ('reporter', models.ForeignKey(related_name='reported_issues', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-modified'],
            },
            bases=(models.Model, nodeconductor.structure.models.StructureLoggableMixin),
        ),
    ]
