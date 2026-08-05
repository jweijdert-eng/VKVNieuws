"""Opmaak — Blog.

EVE-mail is HTML, maar een heel kleine variant. Wat hier staat is niet gegokt:
het komt uit echte mails, gelezen via /characters/{id}/mail/{id}/. Daar gebruikt
EVE zelf `<font size="12" color="#ff00a99d">`, `<br>`, `<a href="...">` (ook voor
in-game links als `contract:30004333//234233628`) en `<loc>`.

De opschoner hier is de baas, niet de opmaakbalk in de browser. Alles wat via
het formulier binnenkomt gaat hier doorheen: wat niet op de lijst staat vliegt
eruit, de tekst blijft. Dat houdt de mail geldig voor EVE én voorkomt dat er via
een blogbericht scripts in Alliance Auth belanden.
"""

import re
from html import escape
from html.parser import HTMLParser

from vkvnieuws import compact

# Kleur in EVE is #AARRGGBB — doorzichtigheid eerst. Zes tekens vullen we aan
# met ff (helemaal dekkend), anders leest EVE de rood-waarde als alpha en wordt
# alles doorzichtig.
KLEUR = re.compile(r"^#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

TOEGESTAAN = {
    "b": (),
    "span": ("style",),
    "u": (),
    "i": (),
    "br": (),
    "loc": (),
    "font": ("size", "color"),
    "a": ("href",),
}
LEEG = {"br"}
# Van deze tags gooien we ook de inhoud weg. Bij de rest houden we de tekst,
# maar "alert(1)" uit een script hoort niet als zinnetje in de mail te belanden.
NEGEER_INHOUD = {"script", "style", "title", "head"}

# http(s) plus de schema's die EVE zelf in mails zet.
SCHEMAS = ("http://", "https://", "showinfo:", "contract:", "killreport:",
           "fleet:", "joinchannel:", "evemail:", "bookmark:", "localsvc:")

MIN_GROOTTE, MAX_GROOTTE = 8, 36


RGB_FUNCTIE = re.compile(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)")


def _kleur(waarde):
    """Wat de browser ook aanlevert, eruit komt EVE's #AARRGGBB."""
    waarde = (waarde or "").strip()
    m = RGB_FUNCTIE.match(waarde)
    if m:
        r, g, b = (min(255, int(x)) for x in m.groups())
        return f"#ff{r:02x}{g:02x}{b:02x}"
    if re.fullmatch(r"#[0-9a-fA-F]{3}", waarde):        # #abc → #aabbcc
        waarde = "#" + "".join(c * 2 for c in waarde[1:])
    if not KLEUR.match(waarde):
        return None
    return waarde if len(waarde) == 9 else f"#ff{waarde[1:]}"


def _grootte(waarde):
    try:
        n = int(str(waarde).strip())
    except (TypeError, ValueError):
        return None
    return str(max(MIN_GROOTTE, min(MAX_GROOTTE, n)))


def _href(waarde):
    waarde = (waarde or "").strip()
    if not waarde or not waarde.lower().startswith(SCHEMAS):
        return None
    # Aanhalingstekens en punthaken eruit: die zouden het attribuut afbreken.
    return escape(waarde, quote=True)


class _Opschoner(HTMLParser):
    """Houdt alleen de toegestane tags over; de rest wordt platte tekst."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stukken = []
        self.open = []
        self.negeren = 0

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in NEGEER_INHOUD:
            self.negeren += 1
            return
        if tag not in TOEGESTAAN:
            return
        if tag == "br":
            self.stukken.append("<br>")
            return

        # Een contenteditable levert opmaak vaak als style aan. EVE kent geen
        # CSS, dus dat vertalen we naar <font size> en <font color>.
        attrs = list(attrs)
        if tag == "span":
            stijl = dict(attrs).get("style") or ""
            vervang = []
            m = re.search(r"font-size\s*:\s*([\d.]+)\s*(px|pt)?", stijl, re.I)
            if m:
                vervang.append(("size", str(round(float(m.group(1))))))
            m = re.search(r"(?<!-)color\s*:\s*([^;]+)", stijl, re.I)
            if m:
                vervang.append(("color", m.group(1).strip()))
            if not vervang:
                return                      # niets bruikbaars: span weglaten
            tag, attrs = "font", vervang

        bewaard = []
        for naam, waarde in attrs:
            naam = (naam or "").lower()
            if naam not in TOEGESTAAN[tag]:
                continue
            schoon = {"color": _kleur, "size": _grootte, "href": _href}[naam](waarde)
            if schoon:
                bewaard.append(f' {naam}="{schoon}"')

        # Een <font> zonder bruikbaar attribuut of een <a> zonder adres voegt
        # niets toe; die laten we weg in plaats van hem leeg mee te sturen.
        if tag in ("font", "a") and not bewaard:
            return

        self.stukken.append(f"<{tag}{''.join(bewaard)}>")
        self.open.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "span":
            tag = "font"                   # is bij het openen ook font geworden
        if tag in NEGEER_INHOUD:
            self.negeren = max(0, self.negeren - 1)
            return
        if tag in LEEG or tag not in TOEGESTAAN:
            return
        if tag in self.open:
            # Alles sluiten tot en met deze tag, zodat er nooit een tag open
            # blijft staan die EVE dan over de rest van de mail uitsmeert.
            while self.open:
                laatste = self.open.pop()
                self.stukken.append(f"</{laatste}>")
                if laatste == tag:
                    break

    def handle_data(self, data):
        if self.negeren:
            return
        self.stukken.append(escape(data, quote=False))

    def resultaat(self):
        while self.open:
            self.stukken.append(f"</{self.open.pop()}>")
        return "".join(self.stukken)


def schoon(html):
    """Opgemaakte tekst uit het formulier naar geldige EVE-mailopmaak."""
    if not html:
        return ""
    # <div> en </p> zijn regelovergangen in een contenteditable; die wil EVE als
    # <br> zien, anders plakt alles aan elkaar.
    html = re.sub(r"(?i)<\s*/\s*(div|p|li)\s*>", "<br>", html)
    html = re.sub(r"(?i)<\s*(div|p|li|tr)\b[^>]*>", "", html)
    html = html.replace("\r\n", "\n").replace("\r", "\n")

    o = _Opschoner()
    o.feed(html)
    o.close()
    uit = compact.compacteer(o.resultaat())
    # Losse regeleindes die nog als \n binnenkwamen alsnog omzetten.
    uit = uit.replace("\n", "<br>")
    # Meer dan twee lege regels achter elkaar leest niemand.
    return re.sub(r"(?:<br>\s*){4,}", "<br><br><br>", uit).strip()


# EVE kent naast <font> ook de Unity-schrijfwijze, die je in bio's en
# omschrijvingen tegenkomt. In echte mails staat hij niet, maar wie markup van
# elders plakt heeft 'm zo te pakken — dus vertalen we hem in plaats van hem weg
# te gooien. Anders verdween de kleur zonder dat je zag waarom.
UNITY_KLEUR = re.compile(r"(?i)<\s*color\s*=\s*(?:0x|#)?([0-9a-f]{6,8})\s*>")
UNITY_KLEUR_EIND = re.compile(r"(?i)<\s*/\s*color\s*>")
UNITY_GROOTTE = re.compile(r"(?i)<\s*fontsize\s*=\s*(\d{1,2})\s*>")
UNITY_GROOTTE_EIND = re.compile(r"(?i)<\s*/\s*fontsize\s*>")

# Een regeleinde dat tegen een tag aan ligt is inspringing, geen lege regel.
# Twee gevallen, want tekst kan aan beide kanten staan:
#     <font ...>\n  Fly o7\n</font>   ->   <font ...>Fly o7</font>
# Een regeleinde tússen twee stukken tekst blijft wél een regelovergang; anders
# zou je in de bronweergave geen alinea meer kunnen typen.
NA_TAG = re.compile(r"(?<=>)[ \t]*\n[ \t\n]*")
VOOR_TAG = re.compile(r"[ \t]*\n[ \t\n]*(?=<)")


def uit_bron(bron):
    """Ruwe EVE-markup uit de bronweergave omzetten naar wat we bewaren.

    Twee dingen die anders misgaan bij geplakte markup:

    1. **Inspringing wordt geen lege regel.** Zet je de tags onder elkaar met
       spaties ervoor — zoals in elk voorbeeld op internet — dan zou elke
       regelovergang een `<br>` worden en staat je mail vol gaten. Een
       regeleinde dat alleen maar tússen twee tags staat gooien we dus weg;
       een regeleinde middenin tekst blijft gewoon een regelovergang.
    2. **De Unity-schrijfwijze wordt vertaald** naar `<font>`, in plaats van
       eruit gegooid.
    """
    if not bron:
        return ""
    bron = bron.replace("\r\n", "\n").replace("\r", "\n")
    bron = UNITY_KLEUR.sub(lambda m: f'<font color="{_unity_kleur(m.group(1))}">', bron)
    bron = UNITY_KLEUR_EIND.sub("</font>", bron)
    bron = UNITY_GROOTTE.sub(r'<font size="\1">', bron)
    bron = UNITY_GROOTTE_EIND.sub("</font>", bron)
    bron = NA_TAG.sub("", bron)
    bron = VOOR_TAG.sub("", bron)
    return schoon(bron)


def _unity_kleur(hex_waarde):
    """`0xffffa600` of `ffa600` -> `#ffffa600`."""
    return _kleur("#" + hex_waarde) or "#ffffffff"


def van_platte_tekst(tekst):
    """Oude berichten zonder opmaak alsnog netjes tonen."""
    return escape(tekst or "", quote=False).replace("\n", "<br>")


def naar_tekst(html):
    """Opmaak eraf voor Discord en voor het fragment in de lijst.

    Discord kent geen HTML; daar is markdown de opmaak. Vet en onderstreept
    zetten we om, de rest verdwijnt gewoon.
    """
    if not html:
        return ""
    tekst = re.sub(r"(?i)<\s*br\s*/?>", "\n", html)
    tekst = re.sub(r"(?i)</?\s*b\s*>", "**", tekst)
    tekst = re.sub(r"(?i)</?\s*u\s*>", "__", tekst)
    tekst = re.sub(r"(?i)</?\s*i\s*>", "*", tekst)
    tekst = re.sub(r"<[^>]+>", "", tekst)
    from html import unescape

    return re.sub(r"\n{3,}", "\n\n", unescape(tekst)).strip()


def zichtbare_lengte(html):
    """Hoeveel tekens de lezer ziet — de teller in de game telt zo ook."""
    return len(naar_tekst(html).replace("\n", ""))


# Wat EVE begrijpt is niet wat een browser begrijpt, en dat is geen detail:
# `size="18"` is in HTML de oude schaal van 1 t/m 7, dus dat wordt reusachtig,
# en `#ff00a99d` leest een browser als een heel andere kleur. Voor het scherm
# rekenen we het daarom om; in de database blijft de EVE-vorm staan.
_FONT = re.compile(r"(?i)<font([^>]*)>")
_ATTR = re.compile(r"(?i)(size|color)\s*=\s*\"([^\"]*)\"")


def naar_browser(html):
    """EVE-opmaak omzetten naar iets dat een browser goed tekent."""
    if not html:
        return ""

    def vervang(m):
        stijl = []
        for naam, waarde in _ATTR.findall(m.group(1)):
            if naam.lower() == "size":
                stijl.append(f"font-size:{waarde}px")
            elif len(waarde) == 9:          # #AARRGGBB → #RRGGBB
                stijl.append(f"color:#{waarde[3:]}")
            else:
                stijl.append(f"color:{waarde}")
        if not stijl:
            return "<span>"
        return f'<span style="{";".join(stijl)}">'

    return _FONT.sub(vervang, html).replace("</font>", "</span>")
