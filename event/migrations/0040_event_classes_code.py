# Generated by Django 3.2 on 2021-04-16 07:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0039_event_reg_open'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='classes_code',
            field=models.IntegerField(default=3),
        ),
    ]
