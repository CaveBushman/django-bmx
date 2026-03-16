from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admin_stats", "0003_visit_device_type_visit_location"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["timestamp"], name="admin_visit_timestamp"),
        ),
        migrations.AddIndex(
            model_name="visit",
            index=models.Index(fields=["ip_address", "timestamp"], name="admin_visit_ip_timestamp"),
        ),
    ]
