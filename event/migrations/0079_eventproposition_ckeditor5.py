from django.db import migrations
import django_ckeditor_5.fields


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0078_align_uci_field_metadata"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventproposition",
            name="summary",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=4000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="schedule",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=8000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="categories",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=6000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="registration_info",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=6000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="awards",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=4000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="accommodation",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=4000, null=True),
        ),
        migrations.AlterField(
            model_name="eventproposition",
            name="additional_info",
            field=django_ckeditor_5.fields.CKEditor5Field(blank=True, config_name="event_proposition", default="", max_length=6000, null=True),
        ),
    ]
