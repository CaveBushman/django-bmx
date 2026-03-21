from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("todo", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="commissiontask",
            name="event",
        ),
    ]
