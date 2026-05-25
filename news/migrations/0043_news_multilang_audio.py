from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0042_news_publish_in_app'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='audio_file_en',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
        migrations.AddField(
            model_name='news',
            name='audio_file_de',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
        migrations.AddField(
            model_name='news',
            name='audio_file_sk',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
        migrations.AddField(
            model_name='news',
            name='audio_file_es',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
        migrations.AddField(
            model_name='news',
            name='audio_file_it',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
        migrations.AddField(
            model_name='news',
            name='audio_file_fr',
            field=models.FileField(blank=True, null=True, upload_to='audio/news/'),
        ),
    ]
