# Generated by Django 4.1.2 on 2023-02-26 17:16

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0030_news_prefix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='news',
            name='prefix',
            field=models.CharField(default='', max_length=400),
        ),
    ]
