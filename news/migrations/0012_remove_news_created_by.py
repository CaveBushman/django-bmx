# Generated by Django 3.2 on 2021-04-16 21:08

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0011_merge_20210319_1911'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='news',
            name='created_by',
        ),
    ]
