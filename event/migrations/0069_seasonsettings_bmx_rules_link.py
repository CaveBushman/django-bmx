from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0068_seasonsettings_transponder_price"),
    ]

    operations = [
        migrations.AddField(
            model_name="seasonsettings",
            name="bmx_rules_link",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
    ]
