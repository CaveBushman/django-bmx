from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('event', '0090_entryforeign_rider'),
    ]

    operations = [
        migrations.CreateModel(
            name='EventPhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('photo', models.ImageField(upload_to='images/events/gallery/')),
                ('caption', models.CharField(blank=True, default='', max_length=255)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('event', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='photos',
                    to='event.event',
                )),
            ],
            options={
                'verbose_name': 'Foto závodu',
                'verbose_name_plural': 'Fotogalerie závodů',
                'ordering': ['order', 'id'],
            },
        ),
    ]
