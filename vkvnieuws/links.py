"""Links in de tekst — VKV Nieuws.

Systeemnamen, regionamen en webadressen klikbaar maken.

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

# ── Webadressen ──────────────────────────────────────────────────────────
# Hoe EVE zelf een webadres in een mail zet, afgelezen uit vier echte mails:
#     <font color="#ffffe400"><loc><a href="…">tekst</a></loc></font>
# Geel dus, en niet de amber van een systeemlink — dat scheelt een kleur.
ADRESKLEUR = "#ffffe400"

# Alleen deze uitgangen tellen als webadres. Zonder zo'n lijst wordt "20:00.De"
# of een afkorting met een punt erin ook een link.
TLDS = ("com|org|net|eu|nl|be|de|uk|io|gg|app|dev|info|online|xyz|space|"
        "tv|me|co|nu|fr|it|es|se|no|fi|dk|pl|cz|ru|us|ca|au|nz|jp|cn|gov|edu")

# Met opzet hoofdlettergevoelig: anders leest "om 20:00.De rest volgt" als het
# domein "00.De" en wordt het midden in een zin een link.
ADRES = re.compile(
    r"(?<![\w@/.])("
    r"https?://[^\s<>\"']+"                      # met protocol ervoor
    r"|(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+(?:%s)"   # kale domeinnaam
    r"(?::\d+)?(?:/[^\s<>\"']*)?"
    r")" % TLDS)

# Leestekens aan het eind horen bij de zin, niet bij het adres.
STAART = ".,;:!?)»\"'"

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


def _zet_adressen(tekst):
    """Kale webadressen in een stukje tekst omzetten naar links."""

    def vervang(m):
        adres = m.group(1)
        # Leestekens die bij de zin horen buiten de link laten.
        staart = ""
        while adres and adres[-1] in STAART:
            staart = adres[-1] + staart
            adres = adres[:-1]
        if not adres:
            return m.group(0)
        # De naam vóór de uitgang moet minstens één letter hebben; anders zou
        # "20:00.nl" of een versienummer ook als adres gelden.
        gastheer = re.sub(r"^https?://", "", adres, flags=re.I).split("/")[0]
        if not re.search(r"[A-Za-z]", gastheer.rsplit(".", 1)[0]):
            return m.group(0)
        # Zonder protocol is het geen geldig adres voor de mailclient.
        doel = adres if adres.lower().startswith(("http://", "https://")) else f"https://{adres}"
        return (f'<font color="{ADRESKLEUR}"><loc>'
                f'<a href="{doel}">{adres}</a></loc></font>{staart}')

    return ADRES.sub(vervang, tekst)


def link_adressen(html):
    """Webadressen in de tekst klikbaar maken.

    Zelfde aanpak als bij de systeemnamen: tekst die al in een `<a>` staat blijft
    met rust, anders krijg je een link in een link zodra je nog eens opslaat.
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
            uit.append(_zet_adressen(deel))
    return "".join(uit)


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
