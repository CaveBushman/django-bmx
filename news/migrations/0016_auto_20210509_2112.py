# Generated by Django 3.2 on 2021-05-09 19:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0015_news_publish_date'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='news',
            name='perex',
        ),
        migrations.AlterField(
            model_name='news',
            name='photo_01',
            field=models.ImageField(blank=True, null=True, upload_to='static/images/news'),
        ),
        migrations.AlterField(
            model_name='news',
            name='photo_02',
            field=models.ImageField(blank=True, null=True, upload_to='static/images/news'),
        ),
        migrations.AlterField(
            model_name='news',
            name='photo_03',
            field=models.ImageField(blank=True, null=True, upload_to='static/images/news'),
        ),
    ]
