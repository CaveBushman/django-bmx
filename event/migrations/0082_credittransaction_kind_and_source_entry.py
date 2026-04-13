from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0081_event_reg_cancel_to"),
    ]

    operations = [
        migrations.AddField(
            model_name="credittransaction",
            name="kind",
            field=models.CharField(
                choices=[
                    ("topup", "Dobití kreditu"),
                    ("checkout_refund", "Vrácení startovného po checkoutu"),
                ],
                default="topup",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="credittransaction",
            name="source_entry",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="credit_transactions",
                to="event.entry",
            ),
        ),
        migrations.AddIndex(
            model_name="credittransaction",
            index=models.Index(fields=["source_entry", "kind"], name="event_credit_entry_kind"),
        ),
        migrations.AddIndex(
            model_name="credittransaction",
            index=models.Index(fields=["kind", "payment_complete"], name="event_credit_kind_pay"),
        ),
        migrations.AddConstraint(
            model_name="credittransaction",
            constraint=models.UniqueConstraint(
                condition=Q(kind="checkout_refund", source_entry__isnull=False),
                fields=("source_entry", "kind"),
                name="event_credit_unique_checkout_refund_per_entry",
            ),
        ),
    ]
