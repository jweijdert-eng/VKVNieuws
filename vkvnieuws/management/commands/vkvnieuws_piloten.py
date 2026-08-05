"""De pilotenlijst bijwerken.

Draai dit af en toe (of zet er een cron op): dan linken nieuwe corpleden vanzelf
mee in de volgende nieuwsbrief.

    python manage.py vkvnieuws_piloten

Namen die je zelf hebt toegevoegd blijven met rust — die staan er juist omdat ze
níét in de corp zitten.
"""

from django.core.management.base import BaseCommand
from vkvnieuws import esi
from vkvnieuws.models import Piloot


class Command(BaseCommand):
    help = "Haalt de corp-ledenlijst op en zet die in de pilotenlijst."

    def add_arguments(self, parser):
        parser.add_argument(
            "--opruimen", action="store_true",
            help="Verwijder opgehaalde piloten die niet meer in de corp zitten.")

    def handle(self, *args, **opties):
        gevonden = {}

        # Wat Alliance Auth al weet: iedereen die een character gekoppeld heeft,
        # ook uit andere corps. Gratis, want het staat lokaal.
        try:
            from allianceauth.eveonline.models import EveCharacter

            for pk, naam in EveCharacter.objects.values_list("character_id",
                                                             "character_name"):
                gevonden[pk] = (naam, Piloot.Bron.AUTH)
        except ImportError:
            pass
        self.stdout.write(f"Alliance Auth kent {len(gevonden)} characters.")

        # En de volledige roster, als er ergens een Director-token is. Die wint,
        # want corpleden zijn de namen die in een corp-nieuwsbrief voorkomen.
        leden = esi.corp_leden()
        for pk, naam in leden.items():
            gevonden[pk] = (naam, Piloot.Bron.CORP)
        self.stdout.write(f"Uit de corp-ledenlijst: {len(leden)}.")

        if not gevonden:
            self.stdout.write(self.style.WARNING(
                "Niets gevonden. Zonder Director-rol geeft ESI 403 op de "
                "ledenlijst; dan blijft alleen wat er in Auth gekoppeld is."))
            return

        nieuw = veranderd = 0
        for pk, (naam, bron) in gevonden.items():
            piloot, gemaakt = Piloot.objects.get_or_create(
                eve_id=pk, defaults={"naam": naam, "bron": bron})
            if gemaakt:
                nieuw += 1
            elif piloot.bron != Piloot.Bron.HAND and (piloot.naam != naam
                                                      or piloot.bron != bron):
                # Naamswijzigingen volgen, maar een zelf toegevoegde piloot niet
                # overschrijven: die staat er met een reden.
                piloot.naam, piloot.bron = naam, bron
                piloot.save(update_fields=["naam", "bron", "bijgewerkt"])
                veranderd += 1

        self.stdout.write(self.style.SUCCESS(
            f"{nieuw} nieuw, {veranderd} bijgewerkt, "
            f"{Piloot.objects.count()} piloten in totaal."))

        if opties["opruimen"] and leden:
            weg = (Piloot.objects.filter(bron=Piloot.Bron.CORP)
                   .exclude(eve_id__in=gevonden))
            aantal = weg.count()
            weg.delete()
            self.stdout.write(f"{aantal} vertrokken corpleden verwijderd.")
