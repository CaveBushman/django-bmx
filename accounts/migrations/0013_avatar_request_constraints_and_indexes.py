from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_pendingavatarchangerequest"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="avatarchangerequest",
            index=models.Index(fields=["status", "-created"], name="avatar_req_status_created_idx"),
        ),
        migrations.AddConstraint(
            model_name="avatarchangerequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="pending", target_account__isnull=False),
                fields=("target_account",),
                name="unique_pending_avatar_request_per_account",
            ),
        ),
        migrations.AddConstraint(
            model_name="avatarchangerequest",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="pending", target_rider__isnull=False),
                fields=("target_rider",),
                name="unique_pending_avatar_request_per_rider",
            ),
        ),
    ]
