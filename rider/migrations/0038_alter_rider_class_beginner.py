# Generated by Django 5.0.2 on 2024-02-09 19:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rider', '0037_alter_rider_class_beginner'),
    ]

    operations = [
        migrations.AlterField(
            model_name='rider',
            name='class_beginner',
            field=models.CharField(blank=True, choices=[('Beginners 1', 'Beginners 1'), ('Beginners 2', 'Beginners 2'), ('Beginners 3', 'Beginners 3'), ('', '')], default='', max_length=50, null=True),
        ),
    ]
