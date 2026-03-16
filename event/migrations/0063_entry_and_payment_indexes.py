from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0062_entryforeign_details"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="entry",
            index=models.Index(fields=["event", "payment_complete", "checkout"], name="event_entry_evt_pay_chk"),
        ),
        migrations.AddIndex(
            model_name="entry",
            index=models.Index(fields=["user", "payment_complete"], name="event_entry_user_pay"),
        ),
        migrations.AddIndex(
            model_name="entry",
            index=models.Index(fields=["transaction_date"], name="event_entry_tx_date"),
        ),
        migrations.AddIndex(
            model_name="entryforeign",
            index=models.Index(fields=["event", "payment_complete", "checkout"], name="event_entryfor_evt_pay_chk"),
        ),
        migrations.AddIndex(
            model_name="entryforeign",
            index=models.Index(fields=["uci_id"], name="event_entryfor_uci"),
        ),
        migrations.AddIndex(
            model_name="entryforeign",
            index=models.Index(fields=["transaction_date"], name="event_entryfor_tx_date"),
        ),
        migrations.AddIndex(
            model_name="debettransaction",
            index=models.Index(fields=["user", "transaction_date"], name="event_debet_user_date"),
        ),
        migrations.AddIndex(
            model_name="debettransaction",
            index=models.Index(fields=["entry"], name="event_debet_entry"),
        ),
        migrations.AddIndex(
            model_name="credittransaction",
            index=models.Index(fields=["user", "payment_complete", "transaction_date"], name="event_credit_user_pay_date"),
        ),
        migrations.AddIndex(
            model_name="credittransaction",
            index=models.Index(fields=["transaction_id"], name="event_credit_tx_id"),
        ),
        migrations.AddIndex(
            model_name="stripefee",
            index=models.Index(fields=["date"], name="event_stripefee_date"),
        ),
    ]
