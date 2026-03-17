from django.db import migrations, models
import django.db.models.deletion
import ckeditor.fields


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_account_club_account_is_club_manager"),
        ("event", "0069_seasonsettings_bmx_rules_link"),
    ]

    operations = [
        migrations.CreateModel(
            name="EventProposition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("venue_name", models.CharField(blank=True, default="", max_length=255)),
                ("venue_address", models.CharField(blank=True, default="", max_length=255)),
                ("office_hours", models.CharField(blank=True, default="", max_length=255)),
                ("contact_name", models.CharField(blank=True, default="", max_length=255)),
                ("contact_email", models.EmailField(blank=True, default="", max_length=254)),
                ("contact_phone", models.CharField(blank=True, default="", max_length=100)),
                ("summary", ckeditor.fields.RichTextField(blank=True, default="", max_length=4000, null=True)),
                ("schedule", ckeditor.fields.RichTextField(blank=True, default="", max_length=8000, null=True)),
                ("categories", ckeditor.fields.RichTextField(blank=True, default="", max_length=6000, null=True)),
                ("registration_info", ckeditor.fields.RichTextField(blank=True, default="", max_length=6000, null=True)),
                ("awards", ckeditor.fields.RichTextField(blank=True, default="", max_length=4000, null=True)),
                ("accommodation", ckeditor.fields.RichTextField(blank=True, default="", max_length=4000, null=True)),
                ("additional_info", ckeditor.fields.RichTextField(blank=True, default="", max_length=6000, null=True)),
                ("is_published", models.BooleanField(default=False)),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                ("updated", models.DateTimeField(auto_now=True, null=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_event_propositions", to="accounts.account")),
                ("event", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="structured_proposition", to="event.event")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_event_propositions", to="accounts.account")),
            ],
            options={
                "verbose_name": "Formulářová propozice",
                "verbose_name_plural": "Formulářové propozice",
                "ordering": ["-updated", "-created"],
            },
        ),
    ]
