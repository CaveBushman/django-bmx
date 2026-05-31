from django.db import migrations


MCR_CLUB_CLASSES = {
    "boys_6": "Boys 6",
    "boys_7": "Boys 7",
    "boys_8": "Boys 8",
    "boys_9": "Boys 9",
    "boys_10": "Boys 10",
    "boys_11": "Boys 11",
    "boys_12": "Boys 12",
    "boys_13": "Boys 13-14",
    "boys_14": "Boys 13-14",
    "boys_15": "Boys 15-16",
    "boys_16": "Boys 15-16",
    "men_17_24": "Men 17+",
    "men_25_29": "Men 17+",
    "men_30_34": "Masters 30+",
    "men_35_over": "Masters 30+",
    "girls_6": "Girls 6",
    "girls_7": "Girls 7-8",
    "girls_8": "Girls 7-8",
    "girls_9": "Girls 9-10",
    "girls_10": "Girls 9-10",
    "girls_11": "Girls 11-12",
    "girls_12": "Girls 11-12",
    "girls_13": "Girls 13-15",
    "girls_14": "Girls 13-15",
    "girls_15": "Girls 13-15",
    "girls_16": "Girls 16+",
    "women_17_24": "Girls 16+",
    "women_25_over": "Girls 16+",
    "men_junior": "Men Junior",
    "men_u23": "Men Under 23",
    "men_elite": "Men Elite",
    "women_junior": "Women Junior",
    "women_u23": "Women Under 23",
    "women_elite": "Women Elite",
    "cr_boys_12_and_under": "Cruiser TOP",
    "cr_boys_13_14": "Cruiser TOP",
    "cr_boys_15_16": "Cruiser TOP",
    "cr_men_17_24": "Cruiser TOP",
    "cr_men_25_29": "Cruiser TOP",
    "cr_men_30_34": "Cruiser TOP",
    "cr_men_35_39": "Cruiser TOP",
    "cr_men_40_44": "Cruiser TOP",
    "cr_men_45_49": "Cruiser 45+",
    "cr_men_50_and_over": "Cruiser 45+",
    "cr_girls_12_and_under": "Cruiser TOP",
    "cr_girls_13_16": "Cruiser TOP",
    "cr_women_17_29": "Cruiser TOP",
    "cr_women_30_39": "Cruiser TOP",
    "cr_women_40_and_over": "Cruiser TOP",
}


def populate_mcr_club_entry_classes(apps, schema_editor):
    EntryClasses = apps.get_model("event", "EntryClasses")
    template, _ = EntryClasses.objects.get_or_create(event_name="Mistrovství ČR družstev")
    for field, value in MCR_CLUB_CLASSES.items():
        setattr(template, field, value)
    template.save(update_fields=list(MCR_CLUB_CLASSES.keys()))


class Migration(migrations.Migration):

    dependencies = [
        ("event", "0096_seasonsettings_mcr_club_registration_open"),
    ]

    operations = [
        migrations.RunPython(populate_mcr_club_entry_classes, migrations.RunPython.noop),
    ]
