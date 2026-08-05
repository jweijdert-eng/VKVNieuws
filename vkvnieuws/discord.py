"""Discord-webhook — VKV Nieuws.

Een webhook en niet de bot: er is geen extra dienst voor nodig, hij werkt ook
als de Discord-service in AA niet ingericht is, en de URL zet je gewoon in de
instellingen — hetzelfde patroon als CHARACTERSCAN_DISCORD_WEBHOOK.
"""

import json
import logging
import re

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Discord's eigen grenzen.
MAX_TITEL = 256
MAX_TEKST = 4096            # in een embed
MAX_BERICHT = 2000          # in een gewoon bericht — een stuk krapper

INSTELLING = "VKVNIEUWS_DISCORD_WEBHOOK"
BESTANDSNAAM = "nieuwsbrief.png"


class DiscordFout(Exception):
    """Posten lukte niet; de tekst is bedoeld om aan de gebruiker te tonen."""


def webhook_url():
    """De webhook: eerst uit de admin, anders uit local.py.

    De admin wint, zodat je hem kunt wisselen zonder de server te herstarten.
    Blijft die leeg, dan geldt nog steeds wat er in local.py staat — anders zou
    een bestaande installatie na het bijwerken opeens stil vallen.
    """
    from vkvnieuws.models import Instellingen

    try:
        uit_admin = (Instellingen.haal().discord_webhook or "").strip()
    except Exception:  # noqa: BLE001 — tabel bestaat nog niet (vóór migrate)
        uit_admin = ""
    return uit_admin or (getattr(settings, INSTELLING, "") or "").strip()


def is_ingericht():
    return webhook_url().startswith("https://")


def _kort(tekst, grens):
    return tekst if len(tekst) <= grens else tekst[: grens - 1] + "…"


def _stukken(tekst, grens=MAX_BERICHT):
    """De tekst opknippen in berichten van hoogstens `grens` tekens.

    Liefst op een lege regel, anders op een regeleinde, en pas als het niet
    anders kan midden in een regel. Zo valt een opsomming niet uit elkaar.
    """
    tekst = (tekst or "").strip()
    if len(tekst) <= grens:
        return [tekst] if tekst else []

    # Liefst vlak vóór een scheidingslijn afbreken. Anders eindigt een bericht op
    # het kopje van een kop-je en staat de inhoud ervan in het volgende.
    scheiding = re.compile(r"\n\s*[─-╿_=-]{3,}\s*\n")

    uit = []
    while len(tekst) > grens:
        venster = tekst[:grens]
        knip = -1
        for m in scheiding.finditer(venster):
            knip = m.start()
        if knip < grens // 3:
            knip = venster.rfind("\n\n")
        if knip < grens // 3:
            knip = venster.rfind("\n")
        if knip < grens // 3:
            knip = venster.rfind(" ")
        if knip <= 0:
            knip = grens
        uit.append(tekst[:knip].rstrip())
        tekst = tekst[knip:].lstrip("\n ")
    if tekst:
        uit.append(tekst)
    return uit


def vermelding_tekst(soort):
    """`@everyone` of `@here`, of niets.

    Let op: in een embed doet zo'n vermelding **niets** — Discord tikt alleen
    aan wat in de gewone berichttekst staat. Vandaar dat hij hieronder altijd in
    `content` belandt en niet in de kaart.
    """
    from vkvnieuws.models import Instellingen

    return {Instellingen.Vermelding.EVERYONE: "@everyone",
            Instellingen.Vermelding.HERE: "@here"}.get(soort, "")


def _mag_aantikken(inhoud):
    """Discord alleen laten aantikken als we daar zelf om vragen.

    Zonder dit zou een `@everyone` die iemand middenin zijn nieuwsbrief typt
    ook de hele server wakker maken.
    """
    if inhoud.startswith("@everyone"):
        return {"parse": ["everyone"]}
    if inhoud.startswith("@here"):
        return {"parse": ["everyone"]}     # @here valt onder dezelfde sleutel
    return {"parse": []}


def voorbeeld(onderwerp, inleiding, omslag=None, url="", auteur="", oproep="",
              vermelding=""):
    """Een aankondiging als kaart: titel, de eerste zinnen en een omslagplaat.

    Wél een embed hier. Bij een lap tekst oogt zo'n kaart benauwd, maar met een
    afbeelding erin is het juist wat je wilt: een aankondiging die eruit springt.
    De titel is de link naar de site.
    """
    haak = _haak()
    embed = {
        "title": _kort(onderwerp, MAX_TITEL),
        "description": _kort(inleiding, 400),
        "color": 0xF0C040,
    }
    if url:
        embed["url"] = url
        if oproep:
            embed["description"] += f"\n\n**[{oproep}]({url})**"
    if auteur:
        embed["footer"] = {"text": auteur}
    if omslag:
        embed["image"] = {"url": f"attachment://{BESTANDSNAAM}"}

    _verstuur_embed(haak, embed, omslag, vermelding)
    logger.info("VKV Nieuws: voorbeeldkaart op Discord gezet — %s", onderwerp)
    return True


def _verstuur_embed(haak, embed, afbeelding=None, vermelding=""):
    """Eén kaart naar de webhook, eventueel met een afbeelding erin.

    De vermelding gaat als gewone berichttekst boven de kaart: in een embed
    tikt Discord niemand aan.
    """
    lading = {"embeds": [embed]}
    if vermelding:
        lading["content"] = vermelding
        lading["allowed_mentions"] = _mag_aantikken(vermelding)
    try:
        if afbeelding:
            r = requests.post(
                haak, timeout=40, params={"wait": "true"},
                data={"payload_json": json.dumps(lading)},
                files={"files[0]": (BESTANDSNAAM, afbeelding, "image/png")})
        else:
            r = requests.post(haak, json=lading, timeout=20,
                              params={"wait": "true"})
    except requests.RequestException as exc:
        raise DiscordFout(f"Discord niet bereikbaar: {exc}") from exc
    _controleer(r)


def _haak():
    haak = webhook_url()
    if not haak:
        raise DiscordFout(
            f"Geen webhook ingesteld. Vul hem in bij VKV Nieuws → instellingen, of zet "
            f"{INSTELLING} in local.py.")
    if not haak.startswith("https://"):
        raise DiscordFout("De ingestelde webhook is geen geldige https-URL.")
    return haak


def post(onderwerp, tekst, auteur="", url="", afbeelding=None, vermelding=""):
    """Zet het bericht op Discord als gewone berichten.

    Geen embed: dat zet alles in een kaart met een streep ernaast, en een
    nieuwsbrief hoort te lezen als een bericht, niet als een kaartje. Wel wat
    krapper — een gewoon bericht mag 2.000 tekens tegen 4.096 in een embed —
    dus lange nieuwsbrieven worden opgeknipt, liefst op een lege regel.

    Met `afbeelding` (PNG-bytes) gaat de gekleurde versie als bijlage mee bij het
    láátste stuk, zodat hij onderaan staat en niet boven de tekst.
    """
    haak = _haak()

    # De vermelding op een eigen regel bovenaan, vóór de kop.
    kop = f"{vermelding}\n" if vermelding else ""
    kop += f"## {_kort(onderwerp, MAX_TITEL)}"
    if url:
        # Punthaken eromheen: anders plakt Discord er een linkvoorbeeld onder,
        # en dan staat er alsnog een kaart in beeld.
        kop += f"\n<{url}>"

    romp = tekst or ""
    if auteur:
        # -# is Discords opmaak voor kleine tekst; past bij een ondertekening.
        romp = f"{romp}\n\n-# {auteur}"

    stukken = _stukken(romp)
    if not stukken:
        stukken = [""]
    # De kop hoort bij het eerste stuk; past dat niet meer, dan wordt het een
    # bericht op zich.
    if len(kop) + 2 + len(stukken[0]) <= MAX_BERICHT:
        stukken[0] = f"{kop}\n\n{stukken[0]}".strip()
    else:
        stukken.insert(0, kop)

    for nummer, stuk in enumerate(stukken, start=1):
        laatste = nummer == len(stukken)
        _verstuur(haak, stuk, afbeelding if (laatste and afbeelding) else None)

    logger.info("VKV Nieuws: op Discord gezet in %s bericht(en) — %s",
                len(stukken), onderwerp)
    return True


def _verstuur(haak, inhoud, afbeelding=None):
    """Eén bericht naar de webhook."""
    lading = {"content": inhoud, "allowed_mentions": _mag_aantikken(inhoud)}
    try:
        if afbeelding:
            r = requests.post(
                haak, timeout=40, params={"wait": "true"},
                data={"payload_json": json.dumps(lading)},
                files={"files[0]": (BESTANDSNAAM, afbeelding, "image/png")})
        else:
            r = requests.post(haak, json=lading, timeout=20,
                              params={"wait": "true"})
    except requests.RequestException as exc:
        raise DiscordFout(f"Discord niet bereikbaar: {exc}") from exc
    _controleer(r)


def _controleer(r):
    """Van een antwoord van Discord iets maken waar je wat aan hebt."""
    if r.status_code in (200, 204):
        return
    if r.status_code == 413:
        raise DiscordFout("Het plaatje is te groot voor Discord (8 MB). Kort het "
                          "bericht in.")
    if r.status_code == 404:
        raise DiscordFout("Discord kent deze webhook niet (404). Is hij "
                          "verwijderd of staat er een typefout in de URL?")
    if r.status_code == 429:
        raise DiscordFout("Discord houdt je even tegen (rate limit). Zo weer "
                          "proberen.")
    raise DiscordFout(f"Discord gaf {r.status_code} terug: {(r.text or '')[:200]}")
