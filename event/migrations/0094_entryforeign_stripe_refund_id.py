from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0093_merge_20260528_0829"),
    ]

    operations = [
        migrations.AddField(
            model_name="entryforeign",
            name="stripe_refund_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Stripe Refund ID po vydání refundu startovného (re_xxx)",
                max_length=255,
                null=True,
            ),
        ),
    ]
