from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("commissar", "0007_commissar_created_commissar_is_active_and_more"),
        ("event", "0060_result_rider_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="start_commissar",
            field=models.ForeignKey(
                blank=True,
                help_text="Start commissar",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="start_commissar_events",
                to="commissar.commissar",
            ),
        ),
    ]
