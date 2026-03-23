from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_avatarchangerequest"),
    ]

    operations = [
        migrations.CreateModel(
            name="PendingAvatarChangeRequest",
            fields=[],
            options={
                "verbose_name": "Čekající avatar",
                "verbose_name_plural": "Čekající avatary",
                "proxy": True,
                "indexes": [],
                "constraints": [],
            },
            bases=("accounts.avatarchangerequest",),
        ),
    ]
