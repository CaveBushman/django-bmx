from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0002_eventinvoice_delete_invoice"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventinvoice",
            name="created",
            field=models.DateTimeField(auto_now_add=True, null=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="eventinvoice",
            name="email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="eventinvoice",
            name="email_sent_to",
            field=models.EmailField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="eventinvoice",
            name="updated",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.AddField(
            model_name="eventinvoice",
            name="xml_export",
            field=models.FileField(blank=True, null=True, upload_to="invoices/xml/"),
        ),
        migrations.AlterField(
            model_name="eventinvoice",
            name="word",
            field=models.FileField(blank=True, null=True, upload_to="invoices/word/"),
        ),
        migrations.AddConstraint(
            model_name="eventinvoice",
            constraint=models.UniqueConstraint(fields=("event", "club"), name="finance_invoice_event_club_unique"),
        ),
    ]
