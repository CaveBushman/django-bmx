from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0013_avatar_request_constraints_and_indexes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="avatarchangerequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Čeká na schválení"),
                    ("approved", "Schváleno"),
                    ("rejected", "Zamítnuto"),
                    ("expired", "Expirováno"),
                ],
                db_index=True,
                default="pending",
                max_length=20,
            ),
        ),
    ]
