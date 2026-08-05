"""De pilotenlinks die er al staan omkleuren van magenta naar lichtblauw.

Zonder dit blijft alles wat vóór deze versie geschreven is roze, terwijl nieuwe
berichten lichtblauw worden — en dan betekent de kleur niets meer.
"""

from django.db import migrations

OUD = "#fff078d8"
NIEUW = "#ff5cc8ff"


def omkleuren(apps, schema_editor):
    Bericht = apps.get_model("vkvnieuws", "Bericht")
    for bericht in Bericht.objects.filter(tekst__contains=OUD):
        bericht.tekst = bericht.tekst.replace(OUD, NIEUW)
        bericht.save(update_fields=["tekst"])


def terug(apps, schema_editor):
    Bericht = apps.get_model("vkvnieuws", "Bericht")
    for bericht in Bericht.objects.filter(tekst__contains=NIEUW):
        bericht.tekst = bericht.tekst.replace(NIEUW, OUD)
        bericht.save(update_fields=["tekst"])


class Migration(migrations.Migration):

    dependencies = [
        ("vkvnieuws", "0004_piloot_bericht_link_piloten"),
    ]

    operations = [
        migrations.RunPython(omkleuren, terug),
    ]
