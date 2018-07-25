# -*- coding: utf-8 -*-
# Generated by Django 1.11.7 on 2018-01-16 08:08
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import model_utils.fields


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0053_add_project_type'),
        ('openstack', '0036_remove_security_group_duplicates'),
    ]

    operations = [
        migrations.CreateModel(
            name='CustomerOpenStack',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', model_utils.fields.AutoCreatedField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('modified', model_utils.fields.AutoLastModifiedField(default=django.utils.timezone.now, editable=False, verbose_name='modified')),
                ('external_network_id', models.CharField(max_length=255, verbose_name='OpenStack external network ID')),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='structure.Customer')),
                ('settings', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='structure.ServiceSettings')),
            ],
            options={
                'verbose_name': 'Organization OpenStack settings',
                'verbose_name_plural': 'Organization OpenStack settings',
            },
        ),
        migrations.AlterUniqueTogether(
            name='customeropenstack',
            unique_together=set([('settings', 'customer')]),
        ),
    ]