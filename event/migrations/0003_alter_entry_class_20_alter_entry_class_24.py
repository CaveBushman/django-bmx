# Generated by Django 4.0.4 on 2022-05-15 10:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0002_alter_entry_class_20_alter_entry_class_24_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entry',
            name='class_20',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='entry',
            name='class_24',
            field=models.CharField(blank=True, default='', max_length=255, null=True),
        ),
    ]