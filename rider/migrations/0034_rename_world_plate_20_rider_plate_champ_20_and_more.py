# Generated by Django 4.0.4 on 2023-03-29 06:37

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rider', '0033_rename_world_plate_rider_world_plate_20_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='rider',
            old_name='world_plate_20',
            new_name='plate_champ_20',
        ),
        migrations.RenameField(
            model_name='rider',
            old_name='world_plate_24',
            new_name='plate_champ_24',
        ),
    ]