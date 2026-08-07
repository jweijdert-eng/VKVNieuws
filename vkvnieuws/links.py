"""Links in de tekst — VKV Nieuws.

Systeemnamen, regionamen, webadressen en pilotennamen klikbaar maken.

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

# ── Piloten ──────────────────────────────────────────────────────────────
# Het typenummer hoort bij de bloedlijn (1374 t/m 1386 komen alle voor), maar de
# client trekt zich er niets van aan: in de inbox staat brandweer denhelder
# (1831618559) in de ene mail als showinfo:1375 en in de andere als 1377. Het id
# doet het werk, dus één vast nummer volstaat.
PILOOT_TYPE = 1377

# EVE zet zelf géén kleur om een pilotenlink (14 stuks in de inbox, allemaal
# kaal). Deze is dus zelfgekozen. Alles wat de nieuwsbrief al gebruikt is warm —
# amber voor systemen, geel voor adressen, oranje voor de ondertekening — dus is
# de koele kant vrij. Lichtblauw haalt 9,4:1 op de donkere mailachtergrond en
# ligt met 29 het verst van die warme kleuren af.
PILOOTKLEUR = "#ff5cc8ff"

_enkel = None            # namen van één woord: naam -> (type, id)
_meerwoord = None        # namen met spaties: één regex, langste eerst
_piloten = None          # één regex over alle namen, langste eerst


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


def _pilotenkaart():
    """De pilotenlijst als één regex, langste naam eerst.

    Langste eerst is nodig omdat `TheMarf` en `TheMarf03` allebei bestaan; zonder
    die volgorde linkt de korte de eerste zeven letters van de lange weg.
    """
    global _piloten
    if _piloten is not None:
        return _piloten
    from vkvnieuws.models import Piloot

    rijen = list(Piloot.objects.filter(linken=True).values_list("naam", "eve_id"))
    if not rijen:
        _piloten = ()
        return _piloten
    rijen.sort(key=lambda r: -len(r[0]))
    # Eigen randen in plaats van \b: namen bevatten apostrofs, streepjes en
    # cijfers (MC'SAKE, General-suk-mai-diek, 5corpi0), en daar rekent \b anders
    # mee dan je wilt.
    #
    # De apostrof telt bewust NIET als rand, anders valt "Rudy's grote QnA" af —
    # en die bezitsvorm staat gewoon in de nieuwsbrief. Dat een naam als MC'SAKE
    # daardoor niet halverwege wordt gepakt komt door de volgorde: de langste
    # naam staat vooraan in de reeks en wint op dezelfde plek altijd.
    patroon = re.compile(r"(?<![\w-])(" +
                         "|".join(re.escape(n) for n, _ in rijen) +
                         r")(?![\w-])")
    _piloten = (patroon, dict(rijen))
    return _piloten


def vergeet_piloten():
    """De opgebouwde regex weggooien; na het bijwerken van de lijst."""
    global _piloten
    _piloten = None


def _zet_piloten(tekst):
    kaart = _pilotenkaart()
    if not kaart:
        return tekst
    patroon, ids = kaart
    return patroon.sub(
        lambda m: (f'<font color="{PILOOTKLEUR}">'
                   f'<a href="showinfo:{PILOOT_TYPE}//{ids[m.group(1)]}">'
                   f'{m.group(1)}</a></font>'),
        tekst)


def link_piloten(html):
    """Namen uit de pilotenlijst omzetten naar een link naar het karakter."""
    return _buiten_links(html, _zet_piloten)


def _buiten_links(html, doe):
    """`doe` op de tekst loslaten, maar niet op wat al in een `<a>` staat.

    Zonder dit krijg je een link in een link zodra je een bericht een tweede keer
    opslaat, en dat is precies wat de drie linkers hieronder gemeen hebben: ze
    verschillen alleen in wát ze met een stuk tekst doen.
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
            uit.append(doe(deel))
    return "".join(uit)


def link_adressen(html):
    """Webadressen in de tekst klikbaar maken."""
    return _buiten_links(html, _zet_adressen)


def link_systemen(html):
    """Systeem- en regionamen omzetten naar in-game links."""
    return _buiten_links(html, _zet_links)


# Ook de kleur eromheen weghalen, anders blijft er een losse <font> staan.
LOSHALEN = re.compile(
    r'(?i)(?:<font color="%s">)?<a href="showinfo:(?:%d|%d)//\d+">([^<]*)</a>(?:</font>)?'
    % (re.escape(LINKKLEUR), SYSTEEM_TYPE, REGION_TYPE))

PILOOT_LOSHALEN = re.compile(
    r'(?i)(?:<font color="%s">)?<a href="showinfo:1(?:37[3-9]|38[0-6])//\d+">'
    r'([^<]*)</a>(?:</font>)?' % re.escape(PILOOTKLEUR))


# Iets dat eruitziet als een nullsec-systeem: hoofdletters/cijfers, een streepje,
# en érgens een cijfer. Dat laatste sluit gewone woorden als "Non-CS" uit.
LIJKT_SYSTEEM = re.compile(r"(?<![\w-])([A-Z0-9]{1,4}-[A-Z0-9]{1,5})(?![\w-])")


def verdachte_systemen(html):
    """Namen die op een systeem lijken maar er geen zijn — meestal een typefout.

    Waarom dit bestaat: in een nieuwsbrief stond `SF-XSQ` terwijl het systeem
    `SF-XJS` heet. De linker sloeg 'm over en niemand die het zag; pas toen alle
    ándere namen wél een link kregen viel die ene op.

    Alleen op de vorm afgaan werkt niet: `DL-SRP` en `Jita 4-4` zien er net zo
    uit en zijn allebei goed. Daarom melden we er pas iets over als er een
    échte systeemnaam bestaat die er sterk op lijkt — dan is het bijna zeker
    een tikfout en geen afkorting.
    """
    import difflib

    if not html:
        return []
    enkel, _ = _kaarten()
    if not enkel:
        return []
    tekst = TAG.sub(" ", html)
    bekend, gezien, uit = set(enkel), set(), []
    for m in LIJKT_SYSTEEM.finditer(tekst):
        naam = m.group(1)
        if naam in bekend or naam in gezien:
            continue
        gezien.add(naam)
        buren = difflib.get_close_matches(naam, bekend, n=3, cutoff=0.75)
        if buren:
            uit.append((naam, buren))
    return uit


def haal_links_weg(html):
    """De systeemlinks er weer af, als je het vinkje uitzet."""
    return LOSHALEN.sub(r"\1", html or "")


def haal_piloten_weg(html):
    """De pilotenlinks er weer af.

    Alle bloedlijn-nummers eruit en niet alleen het onze: een naam die je uit de
    game hebt gesleept komt binnen als 1384 of 1375, en die moet ook loskomen.
    """
    return PILOOT_LOSHALEN.sub(r"\1", html or "")
