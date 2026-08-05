"""Bestaande berichten een editienummer geven.

Op volgorde van aanmaken: het oudste bericht wordt #1. Nieuwe berichten krijgen
hun nummer bij het opslaan, maar wat er al staat moet hier eenmalig gevuld —
anders staat er bij vier bestaande edities vier keer niets.
"""

from django.db import migrations


def nummeren(apps, schema_editor):
    Bericht = apps.get_model("vkvnieuws", "Bericht")
    nummer = 0
    for bericht in Bericht.objects.filter(nummer__isnull=True).order_by("aangemaakt", "pk"):
        nummer += 1
        bericht.nummer = nummer
        bericht.save(update_fields=["nummer"])


def leegmaken(apps, schema_editor):
    """Omkeerbaar: de nummers er weer af."""
    apps.get_model("vkvnieuws", "Bericht").objects.update(nummer=None)


class Migration(migrations.Migration):

    dependencies = [
        ("vkvnieuws", "0002_bericht_nummer"),
    ]

    operations = [
        migrations.RunPython(nummeren, leegmaken),
    ]
