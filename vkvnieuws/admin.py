"""Beheerscherm — Blog."""

from django import forms
from django.contrib import admin, messages
from django.db import models
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

from vkvnieuws import discord, opmaak
from vkvnieuws.models import (Auteur, Bericht, Instellingen, Ontvanger,
                         StandaardOntvanger, Verzending)


class OntvangerInline(admin.TabularInline):
    model = Ontvanger
    extra = 1


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


@admin.register(Bericht)
class BerichtAdmin(admin.ModelAdmin):
    list_display = ("onderwerp", "auteur_weergave", "aangemaakt", "is_verzonden")
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
