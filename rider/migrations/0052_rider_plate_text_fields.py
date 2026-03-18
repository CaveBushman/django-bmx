from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rider", "0051_trainerclubsubscription_trainerclubcharge"),
    ]

    operations = [
        migrations.AddField(
            model_name="rider",
            name="plate_text",
            field=models.CharField(blank=True, default="", max_length=10, null=True),
        ),
        migrations.AddField(
            model_name="foreignrider",
            name="plate_text",
            field=models.CharField(blank=True, default="", max_length=10, null=True),
        ),
    ]
