# Generated by Django 3.2 on 2021-04-13 05:46

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0033_auto_20210413_0532'),
    ]

    operations = [
        migrations.AddField(
            model_name='entry',
            name='date_of_payment',
            field=models.DateField(auto_now_add=True, null=True),
        ),
        migrations.AlterField(
            model_name='entry',
            name='fee_20',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name='entry',
            name='fee_24',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
    ]
