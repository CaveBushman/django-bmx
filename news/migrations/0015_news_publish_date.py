# Generated by Django 3.2 on 2021-05-08 08:01

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0014_news_created'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='publish_date',
            field=models.DateField(default=datetime.date.today),
        ),
    ]
