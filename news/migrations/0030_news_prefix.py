# Generated by Django 4.1.2 on 2023-02-26 17:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0029_downloads_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='prefix',
            field=models.CharField(blank=True, max_length=400, null=True),
        ),
    ]