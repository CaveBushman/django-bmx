# Generated by Django 4.0.4 on 2022-05-23 20:27

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0025_remove_downloads_tag_downloads_tag'),
    ]

    operations = [
        migrations.RenameField(
            model_name='downloads',
            old_name='tag',
            new_name='tags',
        ),
    ]