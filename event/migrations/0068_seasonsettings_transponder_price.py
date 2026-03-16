from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0067_merge_livestream_into_youtube_link"),
    ]

    operations = [
        migrations.AddField(
            model_name="seasonsettings",
            name="transponder_price",
            field=models.IntegerField(default=1900),
        ),
    ]
