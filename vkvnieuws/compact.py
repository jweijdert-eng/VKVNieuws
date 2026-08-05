"""Opmaak inkorten — Blog.

Een contenteditable strooit met tags. Eén lege regel wordt zomaar
`<font color="#ff00a99d"><font size="18"><b><br></b></font></font>`: zestig
tekens markup voor niets. Bij een echt bericht liep dat op tot 8.765 tekens voor
3.958 tekens tekst, en dan weigert ESI het.

Wat hier gebeurt kost geen enkele zichtbare opmaak:
- geneste `<font>`-tags worden er één, met de attributen bij elkaar
- opmaak om iets wat geen tekst bevat (`<b><br></b>`) gaat eraf
- dezelfde tag twee keer achter elkaar wordt er één
"""


from html import escape
from html.parser import HTMLParser

OPMAAK = {"b", "u", "i", "font", "loc"}
LEEG = {"br"}


class _Knoop:
    __slots__ = ("tag", "attrs", "kinderen")

    def __init__(self, tag, attrs=None):
        self.tag = tag
        self.attrs = list(attrs or [])
        self.kinderen = []

    def sleutel(self):
        return (self.tag, tuple(sorted(self.attrs)))


class _Boom(HTMLParser):
    """Bouwt een boom van de al opgeschoonde HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.wortel = _Knoop(None)
        self.stapel = [self.wortel]

    def handle_starttag(self, tag, attrs):
        if tag in LEEG:
            self.stapel[-1].kinderen.append(_Knoop(tag))
            return
        knoop = _Knoop(tag, attrs)
        self.stapel[-1].kinderen.append(knoop)
        self.stapel.append(knoop)

    def handle_startendtag(self, tag, attrs):
        self.stapel[-1].kinderen.append(_Knoop(tag))

    def handle_endtag(self, tag):
        for i in range(len(self.stapel) - 1, 0, -1):
            if self.stapel[i].tag == tag:
                del self.stapel[i:]
                return

    def handle_data(self, data):
        self.stapel[-1].kinderen.append(data)


def _heeft_tekst(knoop):
    """Zit er iets in dat je kunt lézen? Een <br> telt niet mee."""
    if isinstance(knoop, str):
        return bool(knoop.strip())
    if knoop.tag in LEEG:
        return False
    return any(_heeft_tekst(k) for k in knoop.kinderen)


def _knip(knopen):
    uit = []
    for knoop in knopen:
        if isinstance(knoop, str):
            uit.append(knoop)
            continue

        knoop.kinderen = _knip(knoop.kinderen)

        # Opmaak om iets zonder tekst is verspilling: <b><br></b> is gewoon <br>.
        if knoop.tag in OPMAAK and not _heeft_tekst(knoop):
            uit.extend(knoop.kinderen)
            continue

        # <font a><font b>…</font></font> wordt één tag. De binnenste wint bij
        # hetzelfde attribuut, want die staat er het dichtst omheen.
        while (knoop.tag == "font" and len(knoop.kinderen) == 1
               and isinstance(knoop.kinderen[0], _Knoop)
               and knoop.kinderen[0].tag == "font"):
            binnen = knoop.kinderen[0]
            samen = dict(knoop.attrs)
            samen.update(dict(binnen.attrs))
            knoop.attrs = list(samen.items())
            knoop.kinderen = binnen.kinderen

        # Dezelfde tag twee keer achter elkaar: samenvoegen.
        if (uit and isinstance(uit[-1], _Knoop) and knoop.tag not in LEEG
                and uit[-1].sleutel() == knoop.sleutel()):
            uit[-1].kinderen.extend(knoop.kinderen)
            continue

        uit.append(knoop)
    return uit


def _schrijf(knopen):
    stukken = []
    for knoop in knopen:
        if isinstance(knoop, str):
            stukken.append(escape(knoop, quote=False))
        elif knoop.tag in LEEG:
            stukken.append(f"<{knoop.tag}>")
        else:
            attrs = "".join(f' {n}="{w}"' for n, w in knoop.attrs)
            stukken.append(f"<{knoop.tag}{attrs}>")
            stukken.append(_schrijf(knoop.kinderen))
            stukken.append(f"</{knoop.tag}>")
    return "".join(stukken)


def compacteer(html):
    """Zelfde opmaak, minder tekens. Herhaalt tot er niets meer afgaat."""
    if not html:
        return ""
    vorige = None
    uit = html
    for _ in range(5):                      # normaal is twee rondes genoeg
        if uit == vorige:
            break
        vorige = uit
        boom = _Boom()
        boom.feed(uit)
        boom.close()
        uit = _schrijf(_knip(boom.wortel.kinderen))
    # Met opzet géén lege regels weghalen: dat zou de indeling van het bericht
    # veranderen, en inkorten mag alleen markup schelen.
    return uit
