from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_account_is_trainer_account_trainer_clubs"),
        ("finance", "0008_eventcashreceipt_customer_address"),
        ("rider", "0051_trainerclubsubscription_trainerclubcharge"),
    ]

    operations = [
        migrations.CreateModel(
            name="SubscriptionInvoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=255, unique=True)),
                ("issue_date", models.DateField()),
                ("due_date", models.DateField()),
                ("invoice_type", models.CharField(choices=[("rider_stats", "Individuální předplatné"), ("trainer_club_stats", "Klubové předplatné trenéra"), ("trainer_extended", "Rozšířené předplatné trenéra")], db_index=True, max_length=40)),
                ("description", models.CharField(max_length=255)),
                ("customer_name", models.CharField(max_length=255)),
                ("customer_email", models.EmailField(blank=True, max_length=255)),
                ("total_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("pdf", models.FileField(blank=True, null=True, upload_to="subscription-invoices/pdf/")),
                ("xml_export", models.FileField(blank=True, null=True, upload_to="subscription-invoices/xml/")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                ("rider_charge", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoice", to="rider.riderstatscharge")),
                ("trainer_charge", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invoice", to="rider.trainerclubcharge")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscription_invoices", to="accounts.account")),
            ],
            options={
                "verbose_name": "Faktura za předplatné",
                "verbose_name_plural": "Faktury za předplatná",
                "ordering": ["-issue_date", "-created"],
            },
        ),
        migrations.AddIndex(
            model_name="subscriptioninvoice",
            index=models.Index(fields=["user", "issue_date"], name="subinv_user_issue_idx"),
        ),
        migrations.AddIndex(
            model_name="subscriptioninvoice",
            index=models.Index(fields=["invoice_type", "issue_date"], name="subinv_type_issue_idx"),
        ),
    ]
