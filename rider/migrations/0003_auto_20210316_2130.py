# Generated by Django 3.1.7 on 2021-03-16 21:30

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rider', '0002_auto_20210316_2128'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rider',
            name='path_to_photo',
            field=models.ImageField(blank=True, null=True, upload_to='static/images/riders/'),
        ),
    ]
