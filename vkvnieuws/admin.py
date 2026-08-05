"""Beheerscherm — VKV Nieuws."""

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from vkvnieuws import discord, esi, links, opmaak
from vkvnieuws.forms import OntvangerForm
from vkvnieuws.models import (Auteur, Bericht, Instellingen, Ontvanger, Piloot,
                         StandaardOntvanger, Verzending)


class OntvangerInline(admin.TabularInline):
    """Wie deze mail krijgt.

    Draait op hetzelfde formulier als vroeger in het schrijfscherm stond: naam
    óf id invullen is genoeg, de ander wordt erbij gezocht en meteen nagekeken.
    Dat scherm had het ook, en twee plekken voor hetzelfde is er één te veel.
    """

    model = Ontvanger
    form = OntvangerForm
    extra = 1

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Een mailinglijst-id is nergens publiek op te zoeken; zonder dit
        # lijstje moet je zo'n nummer maar ergens vandaan zien te toveren.
        # Op het formulier en niet op de inline zelf: die laatste is gedeeld
        # tussen alle verzoeken, dus dan zou jouw lijstje bij een ander opduiken.
        lijsten = _mijn_mailinglijsten(request.user)
        if lijsten:
            formset.form.base_fields["eve_id"].help_text = _(
                "Alleen nodig voor een mailinglijst. Die van jou: %(lijst)s"
            ) % {"lijst": ", ".join(f"{naam} ({pk})" for pk, naam in lijsten)}
        return formset


def _mijn_mailinglijsten(user):
    """De mailinglijsten van deze gebruiker, een uur lang onthouden.

    Het kost één ESI-call per character, en dat wil je niet bij elke keer dat
    iemand een bericht openslaat.
    """
    from django.core.cache import cache

    sleutel = f"vkvnieuws:mailinglijsten:{user.pk}"
    uit = cache.get(sleutel)
    if uit is None:
        uit = esi.mailinglijsten(esi.character_ids(user))
        cache.set(sleutel, uit, 3600)
    return uit


class VerzendingInline(admin.TabularInline):
    model = Verzending
    extra = 0
    readonly_fields = ("kanaal", "gelukt", "tijdstip", "afzender", "toelichting")
    can_delete = False


@admin.register(Auteur)
class AuteurAdmin(admin.ModelAdmin):
    """Onder welke namen je berichten kunt ondertekenen."""

    list_display = ("__str__", "voorbeeld", "standaard")
    list_editable = ("standaard",)
    search_fields = ("naam", "organisatie")
    # Een kleurkiezer in plaats van een hex-code overtikken.
    formfield_overrides = {
        models.CharField: {"widget": forms.TextInput},
    }

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in ("kleur", "kleur_organisatie"):
            kwargs["widget"] = forms.TextInput(attrs={"type": "color"})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description=_("Zo komt het eronder te staan"))
    def voorbeeld(self, obj):
        """Laten zien in plaats van laten raden hoe de kleuren uitpakken."""
        return format_html(
            '<span style="background:#0f0f22;padding:.3rem .6rem;'
            'border-radius:4px;display:inline-block;">{}</span>',
            mark_safe(opmaak.naar_browser(obj.html)))


@admin.register(StandaardOntvanger)
class StandaardOntvangerAdmin(admin.ModelAdmin):
    """Adresboek: wie je vaker mailt, hoef je niet elke keer over te tikken."""

    list_display = ("naam", "soort", "eve_id", "standaard")
    list_editable = ("standaard",)
    list_filter = ("soort", "standaard")
    search_fields = ("naam", "eve_id")


class PilootForm(forms.ModelForm):
    """Naam intikken is genoeg; het id zoekt de plugin erbij."""

    class Meta:
        model = Piloot
        fields = ("naam", "eve_id", "linken")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["eve_id"].required = False
        self.fields["eve_id"].help_text = _(
            "Laat leeg; die wordt bij de naam opgezocht.")

    def clean(self):
        gegevens = super().clean()
        naam = (gegevens.get("naam") or "").strip()
        if naam and not gegevens.get("eve_id"):
            soort, pk = esi.zoek_op_naam(naam)
            if soort != "character":
                raise forms.ValidationError(
                    _("EVE kent “%(naam)s” niet als character. Let op dat de "
                      "naam exact klopt.") % {"naam": naam})
            gegevens["eve_id"] = pk
        return gegevens


@admin.register(Piloot)
class PilootAdmin(admin.ModelAdmin):
    """Welke namen in een bericht een link naar het karakter worden.

    Blind namen uit de tekst vissen kan niet: 60 gewone Nederlandse woorden uit
    de eigen nieuwsbrieven blijken ook een bestaand character te zijn. Vandaar
    een lijst — die zichzelf grotendeels vult.
    """

    form = PilootForm
    change_list_template = "vkvnieuws/admin_piloten.html"
    list_display = ("naam", "eve_id", "bron", "linken", "bijgewerkt")
    list_editable = ("linken",)
    list_filter = ("bron", "linken")
    search_fields = ("naam", "eve_id")
    actions = ("niet_linken", "wel_linken")

    def get_readonly_fields(self, request, obj=None):
        # Een opgehaalde piloot is geen plek om te typen: de volgende
        # bijwerkronde zet 'm toch terug.
        return ("bron",) if obj else ()

    def get_urls(self):
        from django.urls import path

        return [path("ophalen/", self.admin_site.admin_view(self.ophalen),
                     name="vkvnieuws_piloot_ophalen")] + super().get_urls()

    def ophalen(self, request):
        """De ledenlijst ophalen. Alleen op POST: dit verandert gegevens."""
        from io import StringIO

        from django.core.management import call_command
        from django.http import HttpResponseNotAllowed
        from django.shortcuts import redirect

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_add_permission(request):
            self.message_user(request, _("Daar heb je geen recht op."),
                              messages.ERROR)
            return redirect("admin:vkvnieuws_piloot_changelist")

        uit = StringIO()
        try:
            call_command("vkvnieuws_piloten", stdout=uit)
        except Exception as fout:  # noqa: BLE001 — melden, niet omvallen
            self.message_user(request, str(fout), messages.ERROR)
        else:
            links.vergeet_piloten()
            self.message_user(request,
                              uit.getvalue().strip().replace("\n", " · "),
                              messages.SUCCESS)
        return redirect("admin:vkvnieuws_piloot_changelist")

    @admin.action(description=_("Niet automatisch linken"))
    def niet_linken(self, request, queryset):
        queryset.update(linken=False)
        links.vergeet_piloten()

    @admin.action(description=_("Wel automatisch linken"))
    def wel_linken(self, request, queryset):
        queryset.update(linken=True)
        links.vergeet_piloten()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        links.vergeet_piloten()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        links.vergeet_piloten()


@admin.register(Bericht)
class BerichtAdmin(admin.ModelAdmin):
    list_display = ("nummer", "onderwerp", "auteur_weergave", "aangemaakt",
                    "is_verzonden")
    list_filter = ("aangemaakt", "ondertekend_door")
    search_fields = ("onderwerp", "tekst")
    # "Aangemaakt door" vult zichzelf; tonen is nuttig, wijzigen niet.
    readonly_fields = ("auteur", "aangemaakt", "bijgewerkt")
    inlines = (OntvangerInline, VerzendingInline)


@admin.register(Instellingen)
class InstellingenAdmin(admin.ModelAdmin):
    """Eén rij, die je alleen kunt wijzigen — niet toevoegen of weggooien."""

    list_display = ("__str__", "webhook_kort", "bijgewerkt")
    readonly_fields = ("bijgewerkt",)
    actions = ("testbericht",)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "discord_webhook":
            # Een gewoon tekstvak: het standaard URL-veld zet de waarde er als
            # klikbare link boven ("Huidig: https://…"). Wie die URL heeft kan in
            # het kanaal posten, dus die hoort niet voluit in beeld te staan waar
            # iemand overheen kan meekijken.
            kwargs["widget"] = forms.TextInput(attrs={"size": 60})
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def has_add_permission(self, request):
        # super() erbij, anders vervangt deze controle de gewone rechtencheck en
        # zou iedereen met toegang tot de admin de eerste rij mogen aanmaken.
        # Daarna niet meer: er hoort er maar één te zijn.
        return (super().has_add_permission(request)
                and not Instellingen.objects.exists())

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description=_("Discord-webhook"))
    def webhook_kort(self, obj):
        """Alleen het staartje tonen.

        Wie de hele URL heeft kan in dat kanaal posten, dus die hoort niet
        zomaar in een overzicht te staan waar iemand overheen kan meekijken.
        """
        url = obj.discord_webhook or ""
        if not url:
            return _("— staat uit —")
        return f"…{url[-8:]}"

    @admin.action(description=_("Testbericht naar Discord sturen"))
    def testbericht(self, request, queryset):
        """Meteen zien of de webhook klopt, in plaats van daar bij een echt
        bericht achter te komen. Dit zet wél een zichtbaar bericht in het kanaal.
        """
        try:
            discord.post(
                str(_("Testbericht")),
                str(_("Als je dit ziet werkt de webhook. Verstuurd vanuit "
                      "Alliance Auth om de instelling te controleren.")),
                auteur=request.user.username)
        except discord.DiscordFout as fout:
            self.message_user(request, str(fout), level=messages.ERROR)
            return
        self.message_user(request, _("Testbericht geplaatst — kijk in het kanaal."),
                          level=messages.SUCCESS)
