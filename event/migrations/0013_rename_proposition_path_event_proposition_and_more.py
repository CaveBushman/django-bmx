# Generated by Django 4.0.3 on 2022-04-25 19:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0012_rename_bem_backup_path_event_bem_backup_and_more'),
    ]

    operations = [
        migrations.RenameField(
            model_name='event',
            old_name='proposition_path',
            new_name='proposition',
        ),
        migrations.RenameField(
            model_name='event',
            old_name='series_path',
            new_name='series',
        ),
        migrations.AlterField(
            model_name='entryclasses',
            name='is_enabled',
            field=models.BooleanField(default=True),
        ),
    ]