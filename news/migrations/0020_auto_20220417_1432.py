# Generated by Django 3.2.12 on 2022-04-17 12:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0019_news_time_to_read'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='news',
            options={'verbose_name': 'Článek', 'verbose_name_plural': 'Články'},
        ),
        migrations.AlterField(
            model_name='news',
            name='photo_01',
            field=models.ImageField(blank=True, default='static/images/news/AKBMX.jpg', null=True, upload_to='static/images/news'),
        ),
    ]
