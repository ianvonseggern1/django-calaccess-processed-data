# -*- coding: utf-8 -*-
# Generated by Django 1.10.5 on 2017-01-30 22:48
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('calaccess_processed', '0021_auto_20170130_2042'),
    ]

    operations = [
        migrations.CreateModel(
            name='BallotMeasureContestIdentifier',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('identifier', models.CharField(max_length=300)),
                ('scheme', models.CharField(max_length=300)),
                ('contest', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='identifiers', to='calaccess_processed.BallotMeasureContest')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
