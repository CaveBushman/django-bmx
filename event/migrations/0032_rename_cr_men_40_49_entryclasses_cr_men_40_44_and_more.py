# Generated by Django 5.0.2 on 2024-02-09 19:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0031_delete_order'),
    ]

    operations = [
        migrations.RenameField(
            model_name='entryclasses',
            old_name='cr_men_40_49',
            new_name='cr_men_40_44',
        ),
        migrations.RenameField(
            model_name='entryclasses',
            old_name='cr_men_40_49_fee',
            new_name='cr_men_40_44_fee',
        ),
        migrations.AddField(
            model_name='entryclasses',
            name='cr_men_45_49',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
        migrations.AddField(
            model_name='entryclasses',
            name='cr_men_45_49_fee',
            field=models.IntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='event',
            name='reg_open_from',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]