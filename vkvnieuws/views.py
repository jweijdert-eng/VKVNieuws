"""Views — Blog."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.handlers.wsgi import WSGIRequest
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from esi.decorators import token_required

from vkvnieuws import discord, esi, plaatje
from vkvnieuws.forms import BerichtForm
from vkvnieuws.models import (LETTERGROOTTES, MAX_ZICHTBAAR, Bericht, Ontvanger,
                         StandaardOntvanger, Verzending)

SCOPES = [esi.SEND_SCOPE]


def _basis():
    """Wat elke pagina wil weten over de inrichting."""
    from django.templatetags.static import static

    from vkvnieuws.models import Instellingen

    afzenders = esi.verzend_tokens()
    # Volgorde: een ingevuld adres wint van een upload, want dat vul je juist in
    # als de mediamap niet publiek is en de upload dus een gebroken plaatje
    # oplevert. Staat er niets, dan het embleem dat in de plugin meekomt — dat
    # vraagt wel dat er ooit `collectstatic` gedraaid is.
    try:
        instellingen = Instellingen.haal()
        logo = (instellingen.logo_url
                or (instellingen.logo.url if instellingen.logo else "")
                or static("vkvnieuws/logo.png"))
    except Exception:  # noqa: BLE001 — tabel bestaat nog niet
        logo = static("vkvnieuws/logo.png")

    return {
        "afzenders": [{"id": cid, "naam": naam} for cid, naam, _t in afzenders],
        "kan_mailen": bool(afzenders),
        "kan_discord": discord.is_ingericht(),
        "discord_instelling": discord.INSTELLING,
        "logo_url": logo,
    }


@login_required
@permission_required("vkvnieuws.basic_access")
def lijst(request: WSGIRequest) -> HttpResponse:
    """Alle berichten, nieuwste eerst."""
    berichten = (Bericht.objects
                 .prefetch_related("verzendingen", "ontvangers")
                 .select_related("auteur", "ondertekend_door"))
    ctx = _basis()
    ctx["berichten"] = berichten
    # Hoeveel er de deur uit zijn: de rest is nog concept.
    ctx["verstuurd"] = sum(1 for b in berichten if b.is_verzonden)
    return render(request, "vkvnieuws/lijst.html", ctx)


@login_required
@permission_required("vkvnieuws.basic_access")
def detail(request: WSGIRequest, pk: int) -> HttpResponse:
    """Eén bericht met z'n verzendgeschiedenis."""
    ctx = _basis()
    ctx["bericht"] = get_object_or_404(
        Bericht.objects.prefetch_related("verzendingen", "ontvangers"), pk=pk)
    return render(request, "vkvnieuws/detail.html", ctx)


@login_required
@permission_required("vkvnieuws.schrijven")
def schrijven(request: WSGIRequest, pk: int = None) -> HttpResponse:
    """Nieuw bericht schrijven of een bestaand bewerken."""
    bericht = get_object_or_404(Bericht, pk=pk) if pk else None

    if request.method == "POST":
        form = BerichtForm(request.POST, instance=bericht)
        if form.is_valid():
            # In één transactie, want de ontvangers hangen aan een bericht dat
            # er eerst moet zijn: gaat het tweede deel mis, dan blijft er anders
            # een bericht zonder ontvangers achter dat niemand besteld heeft.
            with transaction.atomic():
                nieuw = form.save(commit=False)
                if not nieuw.auteur_id:
                    nieuw.auteur = request.user
                nieuw.save()
                _vaste_ontvangers(nieuw, form.cleaned_data.get("vaste_ontvangers"))
            messages.success(request, _("Bericht opgeslagen."))
            return redirect("vkvnieuws:detail", pk=nieuw.pk)
    else:
        form = BerichtForm(instance=bericht)

    ctx = _basis()
    ctx.update({"form": form, "bericht": bericht,
                "groottes": LETTERGROOTTES, "max_zichtbaar": MAX_ZICHTBAAR,
                "losse_ontvangers": _losse_ontvangers(bericht)})
    return render(request, "vkvnieuws/schrijven.html", ctx)


def _losse_ontvangers(bericht):
    """Ontvangers die niet uit het adresboek komen.

    Die zijn hier niet te bewerken — dat doe je in de admin — maar wel te zien,
    anders zou zo iemand ongemerkt meegaan met elke volgende verzending.
    """
    if not bericht:
        return []
    adresboek = set(StandaardOntvanger.objects.values_list("soort", "eve_id"))
    return [o for o in bericht.ontvangers.all()
            if (o.soort, o.eve_id) not in adresboek]


def _vaste_ontvangers(bericht, gekozen):
    """De aangevinkte adresboek-regels gelijktrekken met het bericht.

    Alleen regels die uit het adresboek komen worden weggehaald als je ze
    uitvinkt; eenmalige adressen die je zelf hebt ingetikt blijven staan.
    """
    gekozen = list(gekozen or [])
    for v in gekozen:
        Ontvanger.objects.get_or_create(
            bericht=bericht, soort=v.soort, eve_id=v.eve_id,
            defaults={"naam": v.naam})

    aangevinkt = {(v.soort, v.eve_id) for v in gekozen}
    adresboek = set(StandaardOntvanger.objects.values_list("soort", "eve_id"))
    for o in bericht.ontvangers.all():
        sleutel = (o.soort, o.eve_id)
        if sleutel in adresboek and sleutel not in aangevinkt:
            o.delete()


@login_required
@permission_required("vkvnieuws.verzenden")
@require_POST
def verzenden(request: WSGIRequest, pk: int) -> HttpResponse:
    """Naar EVE-mail, naar Discord, of allebei."""
    bericht = get_object_or_404(Bericht, pk=pk)
    kanalen = request.POST.getlist("kanaal")
    if not kanalen:
        messages.warning(request, _("Geen kanaal aangevinkt."))
        return redirect("vkvnieuws:detail", pk=pk)

    if "evemail" in kanalen:
        _stuur_mail(request, bericht)
    if "discord" in kanalen:
        _stuur_discord(request, bericht)

    return redirect("vkvnieuws:detail", pk=pk)


def _stuur_mail(request, bericht):
    ontvangers = [(o.soort, o.eve_id) for o in bericht.ontvangers.all()]
    if not ontvangers:
        messages.error(request, _("Dit bericht heeft nog geen ontvangers."))
        return

    gekozen = request.POST.get("afzender") or None
    try:
        _cid, naam = esi.stuur_mail(bericht.onderwerp,
                                    bericht.tekst_met_ondertekening, ontvangers,
                                    character_id=int(gekozen) if gekozen else None)
    except esi.MailFout as fout:
        Verzending.objects.create(bericht=bericht, kanaal=Verzending.Kanaal.EVEMAIL,
                                  gelukt=False, toelichting=str(fout))
        messages.error(request, _("EVE-mail mislukt: %(fout)s") % {"fout": fout})
        return

    Verzending.objects.create(bericht=bericht, kanaal=Verzending.Kanaal.EVEMAIL,
                              gelukt=True, afzender=naam,
                              toelichting=f"{len(ontvangers)} ontvanger(s)")
    messages.success(
        request,
        _("EVE-mail verstuurd door %(naam)s naar %(aantal)s ontvanger(s).")
        % {"naam": naam, "aantal": len(ontvangers)})


def _stuur_discord(request, bericht):
    from vkvnieuws.models import Instellingen

    instellingen = Instellingen.haal()
    stijl = instellingen.discord_stijl
    adres = request.build_absolute_uri(bericht.get_absolute_url())
    logo = instellingen.logo_pad()

    def teken(maker, *args):
        """Tekenen mag nooit het verzenden tegenhouden."""
        try:
            return maker(*args)
        except Exception as fout:  # noqa: BLE001 — lettertype of tekenfout
            messages.warning(
                request,
                _("Afbeelding maken lukte niet (%(fout)s); zonder verstuurd.")
                % {"fout": fout})
            return None

    try:
        if stijl == Instellingen.DiscordStijl.VOORBEELD:
            # De omslag draagt alleen het embleem en de titel; de inleiding
            # staat in de kaart zelf, anders zie je alles twee keer.
            plaat = teken(plaatje.omslag, bericht.onderwerp, logo,
                          bericht.ondertekening_html)
            discord.voorbeeld(bericht.onderwerp, bericht.inleiding,
                              omslag=plaat, url=adres,
                              auteur=bericht.auteur_weergave,
                              oproep=str(_("Lees de hele nieuwsbrief →")))
            Verzending.objects.create(
                bericht=bericht, kanaal=Verzending.Kanaal.DISCORD, gelukt=True,
                toelichting="voorbeeldkaart")
            messages.success(request, _("Op Discord gezet."))
            return

        plaat = None
        if stijl == Instellingen.DiscordStijl.TEKST_PLAATJE:
            plaat = teken(plaatje.maak, bericht.tekst_met_ondertekening,
                          bericht.onderwerp)
        discord.post(bericht.onderwerp, bericht.platte_tekst,
                     auteur=bericht.auteur_weergave, url=adres, afbeelding=plaat)
    except discord.DiscordFout as fout:
        Verzending.objects.create(bericht=bericht, kanaal=Verzending.Kanaal.DISCORD,
                                  gelukt=False, toelichting=str(fout))
        messages.error(request, _("Discord mislukt: %(fout)s") % {"fout": fout})
        return

    Verzending.objects.create(bericht=bericht, kanaal=Verzending.Kanaal.DISCORD,
                              gelukt=True)
    messages.success(request, _("Op Discord gezet."))


@login_required
@permission_required("vkvnieuws.schrijven")
@require_POST
def verwijderen(request: WSGIRequest, pk: int) -> HttpResponse:
    bericht = get_object_or_404(Bericht, pk=pk)
    onderwerp = bericht.onderwerp
    bericht.delete()
    messages.success(request, _("“%(onderwerp)s” verwijderd.")
                     % {"onderwerp": onderwerp})
    return redirect("vkvnieuws:index")


@login_required
@permission_required("vkvnieuws.verzenden")
@token_required(scopes=SCOPES)
def koppelen(request: WSGIRequest, token) -> HttpResponse:
    """Een character aanwijzen dat de mail mag versturen."""
    messages.success(
        request,
        _("%(naam)s kan nu mail versturen. Let op: EVE toont dit character als "
          "afzender — ESI kent geen corp-afzender.")
        % {"naam": token.character_name})
    return redirect("vkvnieuws:index")
