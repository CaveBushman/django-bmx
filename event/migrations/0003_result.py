# Generated by Django 3.1.7 on 2021-03-19 12:27

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0002_auto_20210318_1940'),
    ]

    operations = [
        migrations.CreateModel(
            name='Result',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rider', models.IntegerField()),
                ('points', models.IntegerField()),
                ('event', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='event.event')),
            ],
            options={
                'verbose_name': 'Výsledek',
                'verbose_name_plural': 'Výsledky',
            },
        ),
    ]
