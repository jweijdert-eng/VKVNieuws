"""Het bericht als afbeelding — Blog.

Discord kent geen kleuren in gewone tekst. Alleen een `ansi`-codeblok kan dat, en
dat maakt alles monospace en zet de rest van de opmaak uit. Een plaatje wél: dan
komt de nieuwsbrief er precies zo uit als in de EVE-mail, met kleuren en al.

Getekend met Pillow en niet met een browser. Pillow zit al in Alliance Auth, een
headless browser is een installatie van honderden megabytes op de server. Dat kan
hier omdat de opmaak klein is: vet, cursief, onderstreept, kleur, lettergrootte
en regeleindes, meer niet.
"""

import io
import logging
import os
import re
from html import unescape
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# Kleuren van het EVE-mailvenster, zodat het plaatje er hetzelfde uitziet.
ACHTERGROND = (13, 17, 23)
TEKSTKLEUR = (220, 224, 232)

BREEDTE = 900
RAND = 28
BASIS_GROOTTE = 15
REGELAFSTAND = 1.45

# Segoe UI op Windows, DejaVu op Linux. Pillow's eigen bitmapfont kan geen
# formaten, dus zonder een van deze wordt het plaatje onleesbaar klein.
FONTS = {
    "gewoon": ("C:/Windows/Fonts/segoeui.ttf",
               "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    "vet": ("C:/Windows/Fonts/segoeuib.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    "cursief": ("C:/Windows/Fonts/segoeuii.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf"),
    # Voor de scheidingslijnen. Segoe UI kent U+2550 (dubbele streep) NIET en
    # tekent er blokjes voor; nagemeten door het teken te renderen en te
    # vergelijken met een teken dat zeker niet bestaat. Consolas en DejaVu Mono
    # hebben het wel, en monospace sluit ook netjes aan tot één doorlopende lijn.
    "lijn": ("C:/Windows/Fonts/consola.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf"),
}

# De tekens waarmee mensen een scheidingslijn tikken.
LIJNTEKENS = re.compile(r"^[─-╿_\-=~]{3,}$")


class GeenLettertype(Exception):
    """Zonder schaalbaar lettertype heeft tekenen geen zin."""


def _fontpad(soort):
    for pad in FONTS[soort]:
        if os.path.exists(pad):
            return pad
    return None


def _soort(tekst, vet, cursief):
    """Welk lettertype voor dit stukje tekst."""
    if LIJNTEKENS.match(tekst.strip()):
        return "lijn"
    return "vet" if vet else ("cursief" if cursief else "gewoon")


_cache = {}


def _font(soort, grootte):
    sleutel = (soort, grootte)
    if sleutel not in _cache:
        from PIL import ImageFont

        pad = _fontpad(soort) or _fontpad("gewoon")
        if not pad:
            raise GeenLettertype(
                "Geen schaalbaar lettertype gevonden. Installeer bijvoorbeeld "
                "fonts-dejavu-core.")
        _cache[sleutel] = ImageFont.truetype(pad, grootte)
    return _cache[sleutel]


def _kleur(waarde, terugval=TEKSTKLEUR):
    """EVE's #AARRGGBB (of #RRGGBB) naar een RGB-drietal."""
    h = (waarde or "").strip().lstrip("#")
    if len(h) == 8:
        h = h[2:]                       # doorzichtigheid negeren; wij tekenen dekkend
    if len(h) != 6:
        return terugval
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return terugval


class _Stukjes(HTMLParser):
    """Zet de EVE-opmaak om in stukjes tekst met elk hun eigen stijl."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stukjes = []               # (tekst, vet, cursief, streep, kleur, grootte)
        self.vet = self.cursief = self.streep = 0
        self.kleuren = []
        self.groottes = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "b":
            self.vet += 1
        elif tag == "i":
            self.cursief += 1
        elif tag in ("u", "a"):
            self.streep += 1
        elif tag == "font":
            a = dict(attrs)
            self.kleuren.append(_kleur(a.get("color")) if a.get("color")
                                else (self.kleuren[-1] if self.kleuren else TEKSTKLEUR))
            try:
                self.groottes.append(int(a.get("size") or 0) or self._grootte())
            except ValueError:
                self.groottes.append(self._grootte())
        elif tag == "br":
            self.stukjes.append(None)   # regeleinde

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.stukjes.append(None)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "b":
            self.vet = max(0, self.vet - 1)
        elif tag == "i":
            self.cursief = max(0, self.cursief - 1)
        elif tag in ("u", "a"):
            self.streep = max(0, self.streep - 1)
        elif tag == "font":
            if self.kleuren:
                self.kleuren.pop()
            if self.groottes:
                self.groottes.pop()

    def _grootte(self):
        return self.groottes[-1] if self.groottes else BASIS_GROOTTE

    def handle_data(self, data):
        if not data:
            return
        self.stukjes.append((
            unescape(data),
            bool(self.vet), bool(self.cursief), bool(self.streep),
            self.kleuren[-1] if self.kleuren else TEKSTKLEUR,
            self._grootte(),
        ))


def _woorden(stukjes, meet, maxbreedte):
    """Stukjes in regels breken, mét woordafbreking binnen een stukje."""
    regels, huidig, breedte = [], [], 0

    def nieuweregel():
        nonlocal huidig, breedte
        regels.append(huidig)
        huidig, breedte = [], 0

    for stuk in stukjes:
        if stuk is None:
            nieuweregel()
            continue
        tekst, vet, cursief, streep, kleur, grootte = stuk
        # Op spaties splitsen maar ze bewaren, anders plakken woorden aan elkaar.
        for woord in re.split(r"(\s+)", tekst):
            if not woord:
                continue
            w = meet(woord, vet, cursief, grootte)
            if breedte + w > maxbreedte and huidig and woord.strip():
                nieuweregel()
            huidig.append((woord, vet, cursief, streep, kleur, grootte, w))
            breedte += w
    regels.append(huidig)
    return regels


# ── Voorbeeldbanner ──────────────────────────────────────────────────────
# Een aparte, brede afbeelding speciaal voor Discord. De hele nieuwsbrief als
# plaatje werkt daar niet: die is ~2000px hoog en Discord schaalt af op 350px,
# dus je krijgt een postzegel van 17%. Een banner van 1200x430 komt uit op
# 550x197 en blijft leesbaar.
BANNER_BREEDTE = 1200
BANNER_HOOGTE = 430
ACCENT = (240, 192, 64)


def _teken_opmaak(teken, x, y, html, grootte, terugval):
    """Eén regel opgemaakte tekst tekenen, met de kleuren die erin staan.

    Voor de ondertekening op de banner: die bestaat uit twee stukjes met elk hun
    eigen kleur, en die moeten hier net zo staan als onder de mail.
    """
    ontleder = _Stukjes()
    ontleder.feed(html or "")
    ontleder.close()
    for stuk in ontleder.stukjes:
        if stuk is None:
            continue
        tekst, vet, cursief, _streep, kleur, _grootte = stuk
        font = _font("vet" if vet else ("cursief" if cursief else "gewoon"), grootte)
        teken.text((x, y), tekst, font=font,
                   fill=kleur if kleur != TEKSTKLEUR else terugval)
        x += teken.textlength(tekst, font=font)
    return x


OMSLAG_BREEDTE = 1200
OMSLAG_HOOGTE = 400
OMSLAG_LOGO = 250


def omslag(onderwerp, logo=None, bijschrift=""):
    """Een omslagplaat: het embleem groot, met de titel ernaast.

    Bedoeld om ín een Discord-kaart te hangen, naast de tekst — dus zonder de
    inleiding erop. Anders staat alles er twee keer: één keer als tekst in de
    kaart en één keer als plaatje eronder.
    """
    from PIL import Image, ImageDraw

    plaat = Image.new("RGB", (OMSLAG_BREEDTE, OMSLAG_HOOGTE), ACHTERGROND)
    teken = ImageDraw.Draw(plaat)

    # Schuine accentband achter het embleem: geeft diepte zonder af te leiden.
    teken.polygon([(0, OMSLAG_HOOGTE), (0, 40), (430, 0),
                   (330, OMSLAG_HOOGTE)], fill=(18, 24, 34))
    teken.rectangle((0, 0, 6, OMSLAG_HOOGTE), fill=ACCENT)

    embleem = _logo(logo, OMSLAG_LOGO)
    tekst_x = 90
    if embleem:
        plaat.paste(embleem, (70, (OMSLAG_HOOGTE - OMSLAG_LOGO) // 2), embleem)
        tekst_x = 70 + OMSLAG_LOGO + 60

    binnen = OMSLAG_BREEDTE - tekst_x - 60

    def regels(tekst, font, maxregels):
        uit, huidig = [], ""
        for woord in (tekst or "").split():
            proef = f"{huidig} {woord}".strip()
            if teken.textlength(proef, font=font) > binnen and huidig:
                uit.append(huidig)
                huidig = woord
                if len(uit) == maxregels:
                    return uit, True
            else:
                huidig = proef
        if huidig:
            uit.append(huidig)
        return uit, False

    # Titel zo groot mogelijk, maar hij moet wel op drie regels passen.
    for grootte in (44, 40, 36, 32, 28):
        titelfont = _font("vet", grootte)
        titelregels, meer = regels(onderwerp, titelfont, 3)
        if not meer:
            break

    klein = _font("gewoon", 17)
    hoog = len(titelregels) * int(grootte * 1.24) + (34 if bijschrift else 0)
    y = (OMSLAG_HOOGTE - hoog) // 2

    teken.text((tekst_x, y - 30), "NIEUWSBRIEF", font=_font("vet", 15),
               fill=(120, 128, 150))
    for i, r in enumerate(titelregels):
        laatste = i == len(titelregels) - 1
        teken.text((tekst_x, y), r + ("…" if meer and laatste else ""),
                   font=titelfont, fill=ACCENT)
        y += int(grootte * 1.24)

    if bijschrift:
        y += 10
        _teken_opmaak(teken, tekst_x, y, bijschrift, 17, (150, 158, 178))

    uit = io.BytesIO()
    plaat.save(uit, format="PNG", optimize=True)
    return uit.getvalue()


LOGO_MAAT = 150


def _logo(pad=None, maat=None):
    """Het logo voor op de banner, of None.

    Zonder eigen upload het meegeleverde VKV-embleem. Het wordt rond
    bijgesneden: de bron heeft een donkere vierkante achtergrond en die zou als
    een blokje op de banner staan.
    """
    from PIL import Image, ImageDraw

    if not pad:
        pad = os.path.join(os.path.dirname(__file__), "static", "vkvnieuws", "logo.png")
    if not os.path.exists(pad):
        return None
    try:
        bron = Image.open(pad).convert("RGBA")
    except Exception:  # noqa: BLE001 — geen geldige afbeelding
        logger.info("Blog: logo %s kon niet geopend worden", pad)
        return None

    # Vierkant maken rond het midden, anders wordt de cirkel een ovaal.
    zijde = max(bron.size)
    doek = Image.new("RGBA", (zijde, zijde), (0, 0, 0, 0))
    doek.paste(bron, ((zijde - bron.size[0]) // 2, (zijde - bron.size[1]) // 2))

    maat = maat or LOGO_MAAT
    # Vier keer zo groot maskeren en dan verkleinen: dat geeft een vloeiende rand.
    groot = doek.resize((maat * 4, maat * 4), Image.LANCZOS)
    masker = Image.new("L", groot.size, 0)
    ImageDraw.Draw(masker).ellipse((0, 0, groot.size[0] - 1, groot.size[1] - 1),
                                   fill=255)
    # Bestaande doorzichtigheid meenemen, anders verdwijnt die bij het maskeren.
    if groot.mode == "RGBA":
        masker = Image.composite(groot.split()[3], Image.new("L", groot.size, 0),
                                 masker)
    groot.putalpha(masker)
    return groot.resize((maat, maat), Image.LANCZOS)


def voorbeeld(onderwerp, inleiding, ondertekening="", oproep="", logo=None):
    """Een brede voorbeeldkaart voor Discord.

    Alleen de titel en de eerste zinnen: het is een aankondiging, geen kopie.
    Wie verder wil leest het op de site.

    De hoogte past zich aan de inhoud aan. Een vaste hoogte gaf bij een korte
    inleiding een half leeg vlak, en dat oogt als een fout.

    `logo` is een pad naar een afbeelding; die komt rechts te staan en de tekst
    krijgt dan een smallere kolom.
    """
    from PIL import Image, ImageDraw

    logoplaat = _logo(logo)
    marge = 46
    rechts = 40 + (LOGO_MAAT + 34 if logoplaat else 0)
    binnen = BANNER_BREEDTE - marge - rechts
    meten = ImageDraw.Draw(Image.new("RGB", (1, 1)))

    def regels(tekst, font, maxregels):
        uit, huidig = [], ""
        for woord in (tekst or "").split():
            proef = f"{huidig} {woord}".strip()
            if meten.textlength(proef, font=font) > binnen and huidig:
                uit.append(huidig)
                huidig = woord
                if len(uit) == maxregels:
                    return uit, True
            else:
                huidig = proef
        if huidig:
            uit.append(huidig)
        return uit, False

    klein = _font("gewoon", 15)
    titelfont = _font("vet", 34)
    tekstfont = _font("gewoon", 19)

    titelregels, titel_meer = regels(onderwerp, titelfont, 2)
    tekstregels, tekst_meer = regels(inleiding, tekstfont, 5)

    # Eerst uitrekenen hoe hoog het wordt, dan pas het doek maken.
    y = 44 + 30 + len(titelregels) * 44 + 18 + len(tekstregels) * 30
    if tekst_meer:
        y += 8
    hoogte = y + 34 + 44
    if logoplaat:
        # Nooit lager dan het logo: anders steekt dat er boven en onder uit.
        hoogte = max(hoogte, LOGO_MAAT + 56)

    plaat = Image.new("RGB", (BANNER_BREEDTE, hoogte), ACHTERGROND)
    teken = ImageDraw.Draw(plaat)
    # Accentbalk links, zoals de streep van een embed maar dan van onszelf.
    teken.rectangle((0, 0, 7, hoogte), fill=ACCENT)

    y = 44
    teken.text((marge, y), "NIEUWSBRIEF", font=klein, fill=(120, 128, 150))
    y += 30

    for i, r in enumerate(titelregels):
        laatste = i == len(titelregels) - 1
        teken.text((marge, y), r + ("…" if titel_meer and laatste else ""),
                   font=titelfont, fill=ACCENT)
        y += 44
    y += 18

    for i, r in enumerate(tekstregels):
        laatste = i == len(tekstregels) - 1
        teken.text((marge, y), r + ("…" if tekst_meer and laatste else ""),
                   font=tekstfont, fill=TEKSTKLEUR)
        y += 30

    # Onderaan: wie het schreef, en rechts de uitnodiging om door te klikken.
    voet = hoogte - 44
    teken.line((marge, voet - 20, BANNER_BREEDTE - 40, voet - 20), fill=(38, 44, 56))
    if ondertekening:
        # Met de kleuren van de auteur, net als onder de mail: daar is
        # CosmicCarrot geel en Dutch Legions oranje. Vlak grijs zou dat verschil
        # juist wegpoetsen.
        _teken_opmaak(teken, marge, voet, ondertekening, 15, (150, 158, 178))
    if oproep:
        vetklein = _font("vet", 15)
        breedte = teken.textlength(oproep, font=vetklein)
        teken.text((BANNER_BREEDTE - 40 - breedte, voet), oproep,
                   font=vetklein, fill=ACCENT)

    if logoplaat:
        # Het doek is RGB, dus plakken met het logo zelf als masker: dan loopt de
        # ronde rand netjes over in de achtergrond.
        plaat.paste(logoplaat,
                    (BANNER_BREEDTE - 40 - LOGO_MAAT, (hoogte - LOGO_MAAT) // 2),
                    logoplaat)

    uit = io.BytesIO()
    plaat.save(uit, format="PNG", optimize=True)
    return uit.getvalue()


def maak(html, onderwerp=""):
    """Het bericht tekenen. Geeft PNG-bytes terug."""
    from PIL import Image, ImageDraw

    ontleder = _Stukjes()
    ontleder.feed(html or "")
    ontleder.close()

    tijdelijk = Image.new("RGB", (1, 1))
    teken = ImageDraw.Draw(tijdelijk)

    def meet(tekst, vet, cursief, grootte):
        return teken.textlength(tekst, font=_font(_soort(tekst, vet, cursief), grootte))

    binnen = BREEDTE - 2 * RAND
    regels = _woorden(ontleder.stukjes, meet, binnen)

    # Hoogte vooraf uitrekenen: een lege regel telt als een gewone regel mee,
    # anders klapt de witruimte van de nieuwsbrief dicht.
    kop_h = int(BASIS_GROOTTE * 1.6 * REGELAFSTAND) + 14 if onderwerp else 0
    hoogtes = [int(max((s[5] for s in r), default=BASIS_GROOTTE) * REGELAFSTAND)
               for r in regels]
    hoogte = RAND * 2 + kop_h + sum(hoogtes)

    plaat = Image.new("RGB", (BREEDTE, hoogte), ACHTERGROND)
    teken = ImageDraw.Draw(plaat)

    y = RAND
    if onderwerp:
        font = _font("vet", int(BASIS_GROOTTE * 1.6))
        teken.text((RAND, y), onderwerp, font=font, fill=(240, 192, 64))
        y += kop_h

    for regel, regelhoogte in zip(regels, hoogtes):
        x = RAND
        for tekst, vet, cursief, streep, kleur, grootte, w in regel:
            font = _font(_soort(tekst, vet, cursief), grootte)
            # Op de onderkant uitlijnen, anders dansen grote en kleine letters
            # binnen dezelfde regel.
            basis = y + regelhoogte - int(grootte * 0.32)
            teken.text((x, basis), tekst, font=font, fill=kleur, anchor="ls")
            if streep and tekst.strip():
                onder = basis + max(1, grootte // 10)
                teken.line((x, onder, x + w, onder), fill=kleur, width=1)
            x += w
        y += regelhoogte

    uit = io.BytesIO()
    plaat.save(uit, format="PNG", optimize=True)
    logger.info("Blog: plaatje gemaakt, %sx%s, %s kB",
                BREEDTE, hoogte, len(uit.getvalue()) // 1024)
    return uit.getvalue()
