# Generated by Django 3.1.7 on 2021-04-04 10:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0014_event_results_uploaded'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='result_file_path',
        ),
    ]
