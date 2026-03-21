from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0075_racerun_qualified_to_next_round"),
        ("todo", "0002_remove_commissiontask_event"),
    ]

    operations = [
        migrations.AddField(
            model_name="commissiontask",
            name="event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="commission_tasks",
                to="event.event",
                verbose_name="Souvisejici zavod",
            ),
        ),
    ]
