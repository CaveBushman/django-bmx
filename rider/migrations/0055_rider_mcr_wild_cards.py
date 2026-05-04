from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rider", "0054_rider_search_text_normalized"),
    ]

    operations = [
        migrations.AddField(
            model_name="rider",
            name="mcr_wild_card_20",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="rider",
            name="mcr_wild_card_24",
            field=models.BooleanField(default=False),
        ),
    ]
