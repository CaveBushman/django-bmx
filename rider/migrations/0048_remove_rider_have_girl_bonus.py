from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rider", "0047_result_rider_fk"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rider",
            name="have_girl_bonus",
        ),
    ]
