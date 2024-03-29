# Generated by Django 4.2.6 on 2023-10-28 21:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0021_entry_class_beginner_entry_fee_beginner_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='class_beginner',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='fee_beginner',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='order',
            name='is_beinner',
            field=models.BooleanField(default=False),
        ),
    ]
