# Generated by Django 4.1.2 on 2023-02-26 17:37

import ckeditor.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0033_alter_news_prefix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='news',
            name='prefix',
            field=ckeditor.fields.RichTextField(blank=True, default='', max_length=4000, null=True),
        ),
    ]