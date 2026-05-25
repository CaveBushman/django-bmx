from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('news', '0043_news_multilang_audio'),
    ]

    operations = [
        migrations.AddField(model_name='news', name='prefix_en', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='prefix_de', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='prefix_sk', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='prefix_es', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='prefix_it', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='prefix_fr', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_en', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_de', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_sk', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_es', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_it', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='news', name='content_fr', field=models.TextField(blank=True, default='')),
    ]
