# Generated by Django 4.2.6 on 2023-10-28 14:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0020_entryclasses_beginners_1_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='entry',
            name='class_beginner',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='entry',
            name='fee_beginner',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='entry',
            name='is_beginner',
            field=models.BooleanField(default=False),
        ),
    ]
