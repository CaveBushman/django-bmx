from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0004_eventinvoiceoverride"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventinvoiceoverride",
            name="manual_amounts",
            field=models.TextField(blank=True),
        ),
    ]
