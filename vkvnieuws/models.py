"""Modellen — Blog.

Eén bericht, dat je naar twee kanalen kunt sturen: EVE-mail en Discord. Wat er
verstuurd is wordt per kanaal vastgelegd, zodat je achteraf ziet wat er wél en
niet aankwam — en zodat je niet per ongeluk twee keer dezelfde mail rondstuurt.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _

# CCP's grenzen op /characters/{id}/mail/.
#
# LET OP: de ESI-spec zegt maxLength 10000 voor de body, maar dat klopt niet.
# De server weigert boven de 8000: "Maximum body length is 8000" (HTTP 400).
# Dat is dezelfde 8000 als de teller in het mailvenster van de game. Afgaan op de
# spec kostte hier een mislukte verzending, dus: 8000.
MAX_ONDERWERP = 1000
MAX_BODY = 8000
MAX_ONTVANGERS = 50
# De teller telt zichtbare tekens; de 8000 hierboven geldt inclusief opmaak.
MAX_ZICHTBAAR = 8000

LETTERGROOTTES = (10, 11, 12, 13, 14, 16, 18, 20, 24)


class Soort(models.TextChoices):
    """De ontvangersoorten die ESI kent."""

    CORPORATION = "corporation", _("Corporatie")
    ALLIANCE = "alliance", _("Alliantie")
    CHARACTER = "character", _("Character")
    MAILING_LIST = "mailing_list", _("Mailinglijst")


class General(models.Model):
    """Bestaat alleen om de permissies aan op te hangen."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", _("Kan VKV Nieuws lezen")),
            ("schrijven", _("Kan berichten schrijven en bewerken")),
            ("verzenden", _("Kan berichten naar EVE-mail en Discord sturen")),
        )


class Instellingen(models.Model):
    """De instellingen, als één rij in de admin.

    Waarom in de database en niet alleen in local.py: een webhook wisselen hoort
    geen serverherstart te kosten, en niet iedereen die de blog beheert komt bij
    het instellingenbestand. De waarde uit local.py blijft werken als terugval,
    zodat een bestaande installatie niets merkt.
    """

    class DiscordStijl(models.TextChoices):
        VOORBEELD = "voorbeeld", _("Voorbeeldkaart met link naar de site")
        TEKST = "tekst", _("De hele nieuwsbrief als tekst")
        TEKST_PLAATJE = "tekst_plaatje", _("De hele nieuwsbrief plus een "
                                           "gekleurde afbeelding")

    discord_webhook = models.URLField(
        max_length=500, blank=True,
        verbose_name=_("Discord-webhook"),
        help_text=_("De webhook-URL van het kanaal waar de berichten in moeten "
                    "komen. Leeg laten zet Discord uit."))
    logo = models.ImageField(
        upload_to="vkvnieuws/", blank=True, verbose_name=_("Logo"),
        help_text=_("Komt op de kaarten en op de voorbeeldkaart voor Discord. "
                    "Vierkant werkt het best; een PNG met doorzichtige "
                    "achtergrond is het mooist."))
    logo_url = models.URLField(
        max_length=500, blank=True, verbose_name=_("Logo-adres"),
        help_text=_("Staat je logo al ergens op internet, vul dan hier het "
                    "adres in in plaats van te uploaden. Handig als de "
                    "mediamap van de server niet publiek is — dan blijft een "
                    "upload namelijk een gebroken plaatje."))
    discord_stijl = models.CharField(
        max_length=20, choices=DiscordStijl.choices,
        default=DiscordStijl.VOORBEELD,
        verbose_name=_("Wat er op Discord komt"),
        help_text=_("Een voorbeeldkaart is een aankondiging: titel, de eerste "
                    "zinnen en een link naar de site. De hele nieuwsbrief kan "
                    "ook, maar die wordt opgeknipt — Discord staat maar 2.000 "
                    "tekens per bericht toe."))
    bijgewerkt = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("instellingen")
        verbose_name_plural = _("instellingen")

    def __str__(self):
        return str(_("Instellingen van VKV Nieuws"))

    def save(self, *args, **kwargs):
        # Altijd dezelfde rij: zo kan er nooit een tweede set instellingen
        # ontstaan waarvan je je afvraagt welke nou geldt.
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def haal(cls):
        return cls.objects.get_or_create(pk=1)[0]

    def logo_pad(self):
        """Een pad op schijf naar het logo, om de Discord-omslag te tekenen.

        Pillow kan geen adres openen, dus een ingevuld logo-adres wordt één keer
        opgehaald en bewaard. Zelfde volgorde als op de site: adres, upload, en
        anders het embleem dat in de plugin meekomt. Geeft None als er niets
        bruikbaars is; de omslag wordt dan zonder embleem getekend.
        """
        import hashlib
        import os
        import tempfile

        if self.logo_url:
            naam = hashlib.sha256(self.logo_url.encode()).hexdigest()[:16]
            pad = os.path.join(tempfile.gettempdir(), f"vkvnieuws-logo-{naam}.img")
            if not os.path.exists(pad):
                import requests

                try:
                    antwoord = requests.get(self.logo_url, timeout=20)
                    antwoord.raise_for_status()
                    with open(pad, "wb") as bestand:
                        bestand.write(antwoord.content)
                except Exception:  # noqa: BLE001 — dan de volgende bron
                    pad = None
            if pad:
                return pad

        if self.logo:
            return self.logo.path

        from django.contrib.staticfiles import finders

        return finders.find("vkvnieuws/logo.png")


class Auteur(models.Model):
    """Onder welke naam een bericht ondertekend wordt.

    Los van de AA-gebruiker: die heet "admin", en dat wil je niet onder een
    nieuwsbrief hebben staan. Hier zet je bijvoorbeeld je characternaam of
    gewoon "Dutch Legions".
    """

    naam = models.CharField(
        max_length=255, unique=True, verbose_name=_("Naam"),
        help_text=_("Bijvoorbeeld je characternaam."))
    kleur = models.CharField(
        max_length=7, default="#ffe400", verbose_name=_("Kleur van de naam"),
        help_text=_("Waarin de naam in de EVE-mail komt te staan."))

    organisatie = models.CharField(
        max_length=255, blank=True, verbose_name=_("Organisatie"),
        help_text=_("Komt achter de naam met een streepje ertussen. Mag leeg."))
    kleur_organisatie = models.CharField(
        max_length=7, default="#ff8c00", verbose_name=_("Kleur van de organisatie"))

    standaard = models.BooleanField(
        default=False, verbose_name=_("standaard"),
        help_text=_("Staat vast voorgeselecteerd bij een nieuw bericht."))

    class Meta:
        ordering = ("-standaard", "naam")
        verbose_name = _("auteur")
        verbose_name_plural = _("auteurs")

    def __str__(self):
        return f"{self.naam} - {self.organisatie}" if self.organisatie else self.naam

    @property
    def html(self):
        """De ondertekening in EVE-opmaak, elk deel in z'n eigen kleur.

        De kleuren staan als #RRGGBB in de database — dat is wat een kleurkiezer
        in de browser teruggeeft. EVE wil #AARRGGBB met de doorzichtigheid
        vóóraan, dus daar zetten we ff voor.
        """
        def vak(tekst, kleur):
            kleur = (kleur or "").strip() or "#ffffff"
            return f'<font color="#ff{kleur.lstrip("#")}">{tekst}</font>'

        uit = vak(self.naam, self.kleur)
        if self.organisatie:
            uit += f' - {vak(self.organisatie, self.kleur_organisatie)}'
        return uit

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Er kan er maar één de standaard zijn; anders is het willekeurig welke
        # er straks voorgeselecteerd staat.
        if self.standaard:
            Auteur.objects.exclude(pk=self.pk).update(standaard=False)


class StandaardOntvanger(models.Model):
    """Adresboek: ontvangers die je vaker gebruikt.

    Zonder dit tik je bij elk bericht dezelfde corp of mailinglijst opnieuw over,
    en één cijfer verkeerd betekent dat je mail bij een vreemde aankomt.
    """

    soort = models.CharField(max_length=20, choices=Soort.choices,
                             default=Soort.CORPORATION)
    eve_id = models.BigIntegerField()
    naam = models.CharField(max_length=255)
    standaard = models.BooleanField(
        default=False, verbose_name=_("standaard"),
        help_text=_("Staat aangevinkt bij een nieuw bericht."))

    class Meta:
        unique_together = ("soort", "eve_id")
        ordering = ("-standaard", "naam")
        verbose_name = _("vaste ontvanger")
        verbose_name_plural = _("vaste ontvangers")

    def __str__(self):
        return f"{self.naam} ({self.get_soort_display()})"


class Piloot(models.Model):
    """Namen die in de tekst een link naar het karakter mogen worden.

    **Waarom een lijst en niet gewoon opzoeken.** Namen uit de tekst vissen en
    aan EVE vragen "kennen jullie die?" klinkt makkelijk maar loopt stuk: van de
    927 losse woorden in vier nieuwsbrieven bleken er **60 ook een bestaand
    character** — *Trein*, *Toen*, *Twee*, *Vrijdag*, *Week*, *Waar*, *Weg*.
    Woordparen zijn niet veel beter: *Death clone*, *Cap Pilot*, *Sov Hub*,
    *Titan Bridge* en zelfs *En de* bestaan allemaal als piloot. Zo zou de halve
    nieuwsbrief oplichten.

    Met een ledenlijst is er niets te raden: alleen namen die hier staan worden
    gelinkt. De lijst vult zichzelf uit de corp-roster en uit de characters die
    in Alliance Auth gekoppeld zijn (`vkvnieuws_piloten`); wie daarbuiten valt —
    een FC van een andere alliantie — zet je er zelf bij.
    """

    class Bron(models.TextChoices):
        CORP = "corp", _("Ledenlijst van de corp")
        AUTH = "auth", _("Gekoppeld in Alliance Auth")
        HAND = "hand", _("Zelf toegevoegd")

    eve_id = models.BigIntegerField(unique=True, verbose_name=_("Character-id"))
    naam = models.CharField(max_length=255, verbose_name=_("Naam"))
    bron = models.CharField(max_length=10, choices=Bron.choices,
                            default=Bron.HAND, verbose_name=_("Herkomst"))
    linken = models.BooleanField(
        default=True, verbose_name=_("Automatisch linken"),
        help_text=_("Uitzetten voor een naam die ook een gewoon woord is; die "
                    "zou anders midden in een zin oplichten."))
    bijgewerkt = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("naam",)
        verbose_name = _("piloot")
        verbose_name_plural = _("piloten")

    def __str__(self):
        return self.naam


class Bericht(models.Model):
    """Een blogbericht."""

    nummer = models.PositiveIntegerField(
        null=True, blank=True, unique=True, verbose_name=_("Editie"),
        help_text=_("Het nummer van deze editie. Laat leeg bij een nieuw "
                    "bericht; dan pakt de plugin het eerstvolgende."))

    onderwerp = models.CharField(max_length=MAX_ONDERWERP)
    tekst = models.TextField(
        help_text=_("Opgemaakte tekst in de opmaak die EVE-mail kent."))

    link_systemen = models.BooleanField(
        default=True, verbose_name=_("Systeemnamen klikbaar maken"),
        help_text=_("Namen als HB-5L3 worden in de EVE-mail een link naar het "
                    "systeem."))
    link_piloten = models.BooleanField(
        default=True, verbose_name=_("Pilotennamen klikbaar maken"),
        help_text=_("Namen uit de pilotenlijst worden een link naar het "
                    "karakter."))

    # Twee verschillende dingen, dus ook twee verschillende labels: wie het in
    # Alliance Auth heeft ingetikt, en welke naam er onder de mail komt. Allebei
    # "Auteur" noemen leverde twee identieke labels op in het beheerscherm.
    auteur = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True,
        related_name="vkvberichten", verbose_name=_("Aangemaakt door"),
        help_text=_("De Alliance Auth-gebruiker die dit bericht schreef. Wordt "
                    "vanzelf ingevuld."))
    ondertekend_door = models.ForeignKey(
        Auteur, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name=_("Ondertekend door"),
        help_text=_("De naam die onder het bericht komt te staan. Leeg laten "
                    "gebruikt de gebruikersnaam hierboven."))
    aangemaakt = models.DateTimeField(auto_now_add=True)
    bijgewerkt = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-aangemaakt",)
        verbose_name = _("bericht")
        verbose_name_plural = _("berichten")

    def __str__(self):
        return f"#{self.nummer} {self.onderwerp}" if self.nummer else self.onderwerp

    def save(self, *args, **kwargs):
        # Nummer één keer toekennen en daarna laten staan. Niet afleiden uit de
        # volgorde in de lijst: dan verspringen alle nummers zodra je er eentje
        # weggooit, en dan klopt #3 in de mail niet meer met #3 op de site.
        if self.nummer is None:
            hoogste = Bericht.objects.aggregate(models.Max("nummer"))["nummer__max"]
            self.nummer = (hoogste or 0) + 1
        super().save(*args, **kwargs)

    @property
    def html(self):
        """Wat er op het scherm hoort te komen.

        Niet zomaar de opgeslagen tekst: die staat in EVE-opmaak, en die tekent
        een browser verkeerd. `size="18"` is in HTML de oude schaal van 1 t/m 7
        (dus reusachtig) en `#ff00a99d` leest een browser als een heel andere
        kleur. Vandaar de omrekening.

        Veilig om zo te tonen: bij het opslaan is alles langs de opschoner
        geweest. Oudere berichten van vóór de opmaakbalk zijn platte tekst.
        """
        from django.utils.safestring import mark_safe

        from vkvnieuws import opmaak

        # Mét ondertekening, zodat de pagina laat zien wat er echt verstuurd
        # wordt — anders zie je pas in je inbox dat er een naam onder staat.
        ruw = self.tekst or ""
        if "<" not in ruw:
            # Oud bericht van vóór de opmaakbalk: eerst platte tekst omzetten.
            ondertekening = self.ondertekening_html
            ruw = opmaak.van_platte_tekst(ruw)
            if ondertekening:
                ruw = f"{ruw}<br><br>{ondertekening}"
        else:
            ruw = self.tekst_met_ondertekening
        return mark_safe(opmaak.naar_browser(ruw))

    @property
    def ondertekening_web(self):
        """De ondertekening voor op een webpagina.

        Dezelfde kleuren als onder de mail, maar omgerekend: EVE's `#AARRGGBB`
        en `<font>` tekent een browser verkeerd.
        """
        from django.utils.safestring import mark_safe

        from vkvnieuws import opmaak

        return mark_safe(opmaak.naar_browser(self.ondertekening_html))

    @property
    def inleiding(self):
        """De eerste echte zinnen, voor de voorbeeldkaart op Discord.

        Scheidingslijnen en kopjes eruit: die zeggen een lezer niets als
        aankondiging, en een rij streepjes is als voorproefje ronduit lelijk.
        """
        import re

        stukken = []
        for regel in self.platte_tekst.split("\n"):
            regel = regel.strip(" *_")
            if not regel:
                continue
            if re.fullmatch(r"[─-╿_=~-]{3,}", regel):
                continue                    # scheidingslijn
            if regel == regel.upper() and len(regel) < 60:
                continue                    # kopje als DE WEEK / NIET DOEN
            stukken.append(regel)
            if sum(len(s) for s in stukken) > 260:
                break
        return " ".join(stukken)

    @property
    def platte_tekst(self):
        """Zonder opmaak — voor Discord en voor het fragment in de lijst."""
        from vkvnieuws import opmaak

        return opmaak.naar_tekst(self.tekst)

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("vkvnieuws:detail", args=[self.pk])

    @property
    def auteur_weergave(self):
        """De naam die eronder komt te staan.

        De gekozen auteur wint; anders de AA-gebruikersnaam, want die is er
        altijd — al is "admin" onder een nieuwsbrief niet mooi.
        """
        if self.ondertekend_door:
            # str(), niet .naam: sinds de auteur uit twee stukken bestaat zou
            # .naam alleen "CosmicCarrot" geven en de organisatie wegvallen.
            return str(self.ondertekend_door)
        return self.auteur.username if self.auteur else ""

    @property
    def tekst_met_ondertekening(self):
        """De tekst zoals hij de deur uit gaat, met de naam eronder.

        De ondertekening zit met opzet NIET in het opgeslagen bericht: dan zou er
        bij elke keer opslaan een regel bij komen. Hij wordt er hier pas
        aangeplakt, bij het versturen en bij het tonen.
        """
        import re

        tekst = self.tekst or ""
        ondertekening = self.ondertekening_html
        if not ondertekening:
            return tekst
        # Witregels aan het eind eraf, anders komt er bij een tekst die al op
        # lege regels eindigt een gat van vier regels boven de naam.
        tekst = re.sub(r"(?i)(?:<br\s*/?>|\s)+$", "", tekst)
        return f"{tekst}<br><br>{ondertekening}"

    @property
    def ondertekening_html(self):
        """De naam eronder, in EVE-opmaak.

        Met de kleuren van de gekozen auteur. Is er geen auteur gekozen, dan de
        AA-gebruikersnaam in grijs — die is er altijd, maar hoeft niet op te
        vallen.
        """
        if self.ondertekend_door:
            return self.ondertekend_door.html
        if self.auteur:
            return f'<font color="#ff999999">{self.auteur.username}</font>'
        return ""

    @property
    def is_verzonden(self):
        return self.verzendingen.filter(gelukt=True).exists()

    def gelukte_kanalen(self):
        return sorted({v.get_kanaal_display()
                       for v in self.verzendingen.filter(gelukt=True)})


class Ontvanger(models.Model):
    """Naar wie de EVE-mail gaat.

    Los model en geen vast veld: één bericht mag naar meerdere adressen, en de
    soorten die ESI kent (character, corporation, alliance, mailing_list) hebben
    allemaal hun eigen id-ruimte.
    """

    # De keuzelijst staat bovenaan het bestand: StandaardOntvanger gebruikt 'm
    # ook, en die staat hierboven.
    Soort = Soort

    bericht = models.ForeignKey(Bericht, on_delete=models.CASCADE,
                                related_name="ontvangers")
    soort = models.CharField(max_length=20, choices=Soort.choices,
                             default=Soort.CORPORATION)
    eve_id = models.BigIntegerField()
    naam = models.CharField(max_length=255, blank=True,
                            help_text=_("Alleen om te tonen; ESI werkt op id."))

    class Meta:
        unique_together = ("bericht", "soort", "eve_id")
        verbose_name = _("ontvanger")
        verbose_name_plural = _("ontvangers")

    def __str__(self):
        return self.naam or f"{self.get_soort_display()} #{self.eve_id}"


class Verzending(models.Model):
    """Wat er per kanaal gebeurd is, gelukt of niet.

    Ook mislukte pogingen bewaren: anders sta je bij een 403 of een rate limit
    met lege handen en weet je niet of het bericht half is aangekomen.
    """

    class Kanaal(models.TextChoices):
        EVEMAIL = "evemail", _("EVE-mail")
        DISCORD = "discord", _("Discord")

    bericht = models.ForeignKey(Bericht, on_delete=models.CASCADE,
                                related_name="verzendingen")
    kanaal = models.CharField(max_length=20, choices=Kanaal.choices)
    gelukt = models.BooleanField(default=False)
    tijdstip = models.DateTimeField(auto_now_add=True)

    # Bij EVE-mail: het character dat als afzender optrad. ESI kent geen
    # corp-afzender — mail komt altijd van een character.
    afzender = models.CharField(max_length=255, blank=True)
    toelichting = models.TextField(blank=True)

    class Meta:
        ordering = ("-tijdstip",)
        verbose_name = _("verzending")
        verbose_name_plural = _("verzendingen")

    def __str__(self):
        stand = "gelukt" if self.gelukt else "mislukt"
        return f"{self.get_kanaal_display()} — {stand}"
