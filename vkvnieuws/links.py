"""Systeem- en regionamen klikbaar maken — Blog.

EVE-mail kent in-game links: `<a href="showinfo:5//30000142">Jita</a>` opent het
infovenster van dat systeem, `showinfo:3//10000058` dat van een region. Type 5 is
Solar System, type 3 is Region; beide vormen komen in echte mails voor.

Om de link staat `<font color="#ffd98d00">`, de amber die EVE zelf gebruikt. Dat
is geen smaak: in 16 systeemlinks uit een echte inbox staat exact die kleur, en
zonder ziet een lezer niet dat het klikbaar is.

**Waarom niet gewoon alles linken.** Er bestaan systemen die *Van*, *Hier*,
*Lang*, *Toon*, *Rand* en *Zet* heten. In een Nederlandse tekst zou "Van" aan het
begin van elke zin een link worden. Die staan daarom op UITZONDERINGEN. Regions
als *Fountain*, *Delve* en *Branch* botsen alleen met Engelse woorden en blijven
dus wél linkbaar.
"""

import re

SYSTEEM_TYPE = 5
REGION_TYPE = 3

# De kleur die EVE zelf om zo'n link zet. Nagekeken in 16 echte systeemlinks in
# de inbox: altijd exact deze amber.
LINKKLEUR = "#ffd98d00"

# Systeemnamen die ook gewone Nederlandse woorden of voornamen zijn. Gevonden
# door alle 8.490 systeemnamen tegen een woordenlijst te houden, niet op het oog.
# Regions staan er bewust niet bij: die botsen alleen met Engelse woorden.
UITZONDERINGEN = {
    "Ala", "Alf", "Ami", "Ana", "Bar", "Cat", "Col", "Dal", "Exit", "Gens",
    "Half", "Ham", "Hare", "Hier", "Ides", "Iro", "Jan", "Lang", "Loes",
    "Mies", "Mod", "Moh", "Mora", "Ned", "Nein", "Obe", "Odin", "Olo", "Ono",
    "Pain", "Raa", "Rand", "Sist", "Stou", "Tar", "Tew", "Toon", "Vale",
    "Van", "Weld", "Zet",
}

# Een naam zoals EVE ze schrijft: letters en cijfers, eventueel met streepjes.
TOKEN = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
TAG = re.compile(r"(<[^>]+>)")

_enkel = None            # namen van één woord: naam -> (type, id)
_meerwoord = None        # namen met spaties: één regex, langste eerst


def _kaarten():
    """De sterrenkaart uit django-eveuniverse, één keer opgebouwd.

    Namen met spaties ("Cloud Ring", "Old Man Star") kunnen niet per woord
    gevonden worden, dus die gaan in een eigen regex die éérst draait — anders
    zou "Cloud" los al matchen.
    """
    global _enkel, _meerwoord
    if _enkel is not None:
        return _enkel, _meerwoord
    try:
        from eveuniverse.models import EveRegion, EveSolarSystem
    except ImportError:
        _enkel, _meerwoord = {}, None
        return _enkel, _meerwoord

    _enkel = {}
    met_spatie = []
    for model, soort in ((EveSolarSystem, SYSTEEM_TYPE), (EveRegion, REGION_TYPE)):
        for pk, naam in model.objects.values_list("id", "name"):
            if soort == SYSTEEM_TYPE and naam in UITZONDERINGEN:
                continue
            if " " in naam:
                met_spatie.append((naam, soort, pk))
            else:
                _enkel[naam] = (soort, pk)

    if met_spatie:
        met_spatie.sort(key=lambda r: -len(r[0]))     # langste eerst
        _meerwoord = (
            re.compile(r"\b(" + "|".join(re.escape(n) for n, _, _ in met_spatie) + r")\b"),
            {n: (s, pk) for n, s, pk in met_spatie},
        )
    return _enkel, _meerwoord


def _link(naam, soort, pk):
    return (f'<font color="{LINKKLEUR}">'
            f'<a href="showinfo:{soort}//{pk}">{naam}</a></font>')


def _zet_links(tekst):
    enkel, meerwoord = _kaarten()
    if not enkel:
        return tekst

    # Eerst de namen met spaties, anders pakt de losse-woordronde het eerste
    # woord ervan al af.
    if meerwoord:
        patroon, kaart = meerwoord
        tekst = patroon.sub(lambda m: _link(m.group(1), *kaart[m.group(1)]), tekst)

    stukken, laatste = [], 0
    for m in TOKEN.finditer(tekst):
        gevonden = enkel.get(m.group(0))
        if not gevonden:
            continue
        # Niet binnen een net gemaakte link opnieuw beginnen.
        if "<a " in tekst[laatste:m.start()] and "</a>" not in tekst[laatste:m.start()]:
            continue
        stukken.append(tekst[laatste:m.start()])
        stukken.append(_link(m.group(0), *gevonden))
        laatste = m.end()
    stukken.append(tekst[laatste:])
    return "".join(stukken)


def link_systemen(html):
    """Systeem- en regionamen omzetten naar in-game links.

    Tekst die al in een `<a>` staat blijft met rust: anders krijg je een link in
    een link zodra je het bericht een tweede keer opslaat.
    """
    if not html:
        return ""
    uit, in_link = [], 0
    for deel in TAG.split(html):
        if deel.startswith("<") and deel.endswith(">"):
            soort = deel[1:].lstrip("/").split(" ")[0].split(">")[0].lower()
            if soort == "a":
                in_link += -1 if deel.startswith("</") else 1
                in_link = max(0, in_link)
            uit.append(deel)
        elif in_link:
            uit.append(deel)
        else:
            uit.append(_zet_links(deel))
    return "".join(uit)


# Ook de kleur eromheen weghalen, anders blijft er een losse <font> staan.
LOSHALEN = re.compile(
    r'(?i)(?:<font color="%s">)?<a href="showinfo:(?:%d|%d)//\d+">([^<]*)</a>(?:</font>)?'
    % (re.escape(LINKKLEUR), SYSTEEM_TYPE, REGION_TYPE))


def haal_links_weg(html):
    """De links er weer af, als je het vinkje uitzet."""
    return LOSHALEN.sub(r"\1", html or "")
