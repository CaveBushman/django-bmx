# Generated by Django 5.0.2 on 2024-02-08 16:01

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0030_remove_entry_confirmed'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Order',
        ),
    ]