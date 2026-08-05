"""Formulieren — VKV Nieuws."""

from django import forms
from django.utils.translation import gettext_lazy as _

from vkvnieuws import esi, links, opmaak
from vkvnieuws.models import (MAX_BODY, MAX_ONDERWERP, MAX_ZICHTBAAR, Auteur,
                         Bericht, Ontvanger, StandaardOntvanger)


class BerichtForm(forms.ModelForm):
    # Vaste ontvangers om aan te vinken. Los van het formset eronder, dat voor
    # eenmalige adressen is.
    vaste_ontvangers = forms.ModelMultipleChoiceField(
        queryset=StandaardOntvanger.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple, label=_("Vaste ontvangers"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ondertekend_door"].queryset = Auteur.objects.all()
        self.fields["ondertekend_door"].empty_label = _("— je gebruikersnaam —")
        self.fields["ondertekend_door"].widget.attrs["class"] = "vkv-invoer vkv-smal"

        # Bij bewerken de browser-vorm in het veld zetten, anders staat er in de
        # opmaakbalk reuzentekst in de verkeerde kleur. Opslaan zet het weer om.
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["tekst"] = opmaak.naar_browser(self.instance.tekst)
            # Aanvinken wat er al aan hangt, zodat het beeld klopt.
            bestaand = {(o.soort, o.eve_id) for o in self.instance.ontvangers.all()}
            self.initial["vaste_ontvangers"] = [
                v.pk for v in StandaardOntvanger.objects.all()
                if (v.soort, v.eve_id) in bestaand]
        elif not self.is_bound:
            standaard = Auteur.objects.filter(standaard=True).first()
            if standaard:
                self.initial["ondertekend_door"] = standaard.pk
            self.initial["vaste_ontvangers"] = list(
                StandaardOntvanger.objects.filter(standaard=True)
                .values_list("pk", flat=True))

    class Meta:
        model = Bericht
        fields = ("onderwerp", "tekst", "link_systemen", "link_piloten",
                  "ondertekend_door")
        widgets = {
            "onderwerp": forms.TextInput(attrs={
                "class": "vkv-invoer", "maxlength": MAX_ONDERWERP,
                "placeholder": _("Waar gaat het over?"), "autofocus": True}),
            "tekst": forms.Textarea(attrs={
                "class": "vkv-invoer vkv-tekstvak", "rows": 16,
                "placeholder": _("Schrijf hier je bericht.")}),
        }

    def clean(self):
        """Systeemlinks pas hier, want beide velden moeten bekend zijn.

        Ook weer weghalen als het vinkje uitgaat: anders blijven links staan die
        je net hebt uitgezet.
        """
        gegevens = super().clean()
        tekst = gegevens.get("tekst")
        if tekst is None:
            return gegevens
        tekst = (links.link_systemen(tekst) if gegevens.get("link_systemen")
                 else links.haal_links_weg(tekst))
        tekst = (links.link_piloten(tekst) if gegevens.get("link_piloten")
                 else links.haal_piloten_weg(tekst))
        # Webadressen altijd: een kaal adres in een mail is voor niemand handig,
        # en anders dan bij systeemnamen valt hier niets te gokken.
        gegevens["tekst"] = links.link_adressen(tekst)
        return gegevens

    def clean_tekst(self):
        """Opschonen en pas daarna meten.

        De opschoner is hier de baas: wat de browser aanlevert kan van alles
        bevatten, en alleen wat op de lijst staat mag door. Meten gebeurt ná het
        opschonen, want anders keur je iets goed dat straks toch anders is.
        """
        # Uit de bronweergave komt ruwe EVE-markup; die heeft een eigen route,
        # want daar is een regeleinde tussen twee tags inspringing en geen lege
        # regel.
        if self.data.get("bronmodus"):
            schoon = opmaak.uit_bron(self.cleaned_data["tekst"])
        else:
            schoon = opmaak.schoon(self.cleaned_data["tekst"])
        if not opmaak.naar_tekst(schoon).strip():
            raise forms.ValidationError(_("Een bericht zonder tekst heeft geen zin."))

        zichtbaar = opmaak.zichtbare_lengte(schoon)
        if zichtbaar > MAX_ZICHTBAAR:
            raise forms.ValidationError(
                _("Te lang: %(nu)s zichtbare tekens, en EVE staat er %(max)s toe.")
                % {"nu": f"{zichtbaar:,}".replace(",", "."),
                   "max": f"{MAX_ZICHTBAAR:,}".replace(",", ".")})

        # Opmaak telt mee voor de grens die ESI hanteert, dus die ook nakijken:
        # veel kleurtjes kunnen de body opblazen zonder dat je meer tekst ziet.
        if len(schoon) > MAX_BODY:
            raise forms.ValidationError(
                _("Met opmaak erbij is dit %(nu)s tekens, en EVE weigert boven "
                  "de %(max)s. Kort de tekst in of gebruik minder kleur en "
                  "lettergroottes.")
                % {"nu": f"{len(schoon):,}".replace(",", "."),
                   "max": f"{MAX_BODY:,}".replace(",", ".")})
        return schoon


class OntvangerForm(forms.ModelForm):
    """Naam óf id invullen is genoeg; EVE zoekt de rest erbij.

    Wordt gebruikt door de inline in het beheerscherm. Losse ontvangers stonden
    ook in het schrijfscherm, maar dat waren twee plekken voor hetzelfde.
    """

    class Meta:
        model = Ontvanger
        fields = ("soort", "eve_id", "naam")
        widgets = {
            "soort": forms.Select(attrs={"class": "vkv-invoer"}),
            "eve_id": forms.NumberInput(attrs={
                "class": "vkv-invoer", "placeholder": _("laat leeg")}),
            "naam": forms.TextInput(attrs={
                "class": "vkv-invoer",
                "placeholder": _("bv. Dutch Legions of je eigen naam")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Het id mag leeg blijven zolang er een naam staat; dat vullen we zelf.
        self.fields["eve_id"].required = False

    def clean(self):
        """Naam en id bij elkaar zoeken, en nakijken of ze kloppen.

        Waarom dit hier gebeurt: een EVE-id is niets waar iemand zomaar over
        beschikt, en één cijfer verkeerd betekent dat je mail bij een vreemde
        aankomt. Nu vul je een naam in en zoekt de plugin het id erbij — of
        andersom, en dan zie je meteen wie het is.
        """
        gegevens = super().clean()
        if gegevens.get("DELETE"):
            return gegevens

        naam = (gegevens.get("naam") or "").strip()
        eve_id = gegevens.get("eve_id")
        soort = gegevens.get("soort")

        if not naam and not eve_id:
            return gegevens                 # lege rij: gewoon overslaan

        # Mailinglijsten staan niet in de publieke opzoeklijst; daar is het id
        # het enige houvast.
        if soort == Ontvanger.Soort.MAILING_LIST:
            if not eve_id:
                raise forms.ValidationError(
                    _("Voor een mailinglijst is het id nodig; de naam ervan is "
                      "niet publiek op te zoeken."))
            return gegevens

        if eve_id:
            gevonden_soort, gevonden_naam = esi.zoek_op_id(eve_id)
            if not gevonden_soort:
                raise forms.ValidationError(
                    _("EVE kent id %(id)s niet als character, corporatie of "
                      "alliantie. Is het een mailinglijst? Kies dan "
                      "Mailinglijst als soort — die staan niet in de publieke "
                      "opzoeklijst van EVE en zijn dus niet te controleren.")
                    % {"id": eve_id})
            gegevens["soort"] = gevonden_soort
            gegevens["naam"] = gevonden_naam
            return gegevens

        gevonden_soort, gevonden_id = esi.zoek_op_naam(naam)
        if not gevonden_id:
            raise forms.ValidationError(
                _("EVE kent “%(naam)s” niet. Let op dat de naam exact klopt; "
                  "hoofdletters maken niet uit.") % {"naam": naam})
        gegevens["soort"] = gevonden_soort
        gegevens["eve_id"] = gevonden_id
        return gegevens


