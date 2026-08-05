# VKV Nieuws

Plugin voor **Alliance Auth 5.2**. Je schrijft één nieuwsbrief en stuurt die met
één knop naar **EVE-mail** en **Discord**. Wat er verstuurd is wordt bijgehouden, ook
als het misging.

## Wat je moet weten voordat je begint

**EVE kent geen corp-afzender.** Een mail komt altijd van het character wiens
token gebruikt wordt — CCP's API biedt geen manier om namens een corporatie te
verzenden. Wat wél kan is een mail *aan* een corporatie: die valt bij alle leden
in de inbox, met dat ene character als afzender. Wijs daarvoor bijvoorbeeld je
CEO of een director aan.

Voor een mail aan een hele corporatie of alliantie heb je in de game bovendien de
rol **Communications Officer** nodig. Zonder die rol geeft ESI een 403; de plugin
laat dat dan als zodanig zien.

CCP's grenzen, rechtstreeks uit de ESI-spec:

| | grens |
|---|---|
| onderwerp | 1.000 tekens |
| tekst | 8.000 tekens, inclusief opmaak |
| ontvangers | 50 per mail |

**De ESI-spec liegt hier.** Die geeft `maxLength: 10000` voor de body, maar de
server weigert boven de 8.000 met "Maximum body length is 8000". Dat is dezelfde
8.000 als de teller in het mailvenster van de game.

Die 8.000 geldt **inclusief opmaak**, en dat telt harder aan dan je denkt: een
contenteditable maakt van één lege regel al gauw
`<font color="#ff00a99d"><font size="18"><b><br></b></font></font>`. Daarom
wordt de opmaak bij het opslaan én bij het verzenden ingekort — geneste
font-tags worden er één, opmaak om iets zonder tekst gaat eraf. Bij een echte
nieuwsbrief scheelde dat 31%: van 8.765 naar 6.039 tekens, met exact dezelfde
tekst en alle 113 regels intact.

## Opmaak

Dezelfde knoppen als de mail in de game: **vet**, onderstreept, schuin, kleur,
lettergrootte en links. Wat je opmaakt wordt opgeslagen in EVE's eigen vorm,
zoals `<font size="12" color="#ff00a99d">` — acht hex-tekens met de
doorzichtigheid vóóraan. Dat is niet gegokt maar afgelezen uit echte mails.

Let op dat dit *geen* browser-opmaak is: `size="18"` betekent in HTML de oude
schaal van 1 t/m 7 en wordt dus reusachtig, en `#ff00a99d` leest een browser als
een heel andere kleur. Op het scherm wordt het daarom omgerekend; in de database
staat de EVE-vorm.

Wat het formulier binnenkrijgt gaat altijd door een opschoner aan de serverkant.
Alleen `b`, `u`, `i`, `br`, `font`, `a` en `loc` blijven staan, links moeten
http(s) of een EVE-schema zijn (`showinfo:`, `contract:`, …), en de rest wordt
platte tekst. Dat houdt de mail geldig voor EVE en voorkomt dat er via een
nieuwsbrief scripts in Alliance Auth belanden.

Er zit ook een limiet op hóéveel mail je per tijdseenheid mag sturen. Loop je
daar tegenaan, dan geeft ESI een 520 en is wachten het enige dat helpt.

## Installeren

```bash
pip install aa-vkvnieuws
```

In `local.py`:

```python
INSTALLED_APPS += ["vkvnieuws"]
```

Daarna migreren en de statische bestanden verzamelen:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

## Discord instellen

In de admin onder **VKV Nieuws → instellingen** vul je de webhook-URL van het kanaal
in. Daar zit ook een actie **Testbericht naar Discord sturen**, zodat je meteen
ziet of hij klopt in plaats van daar bij een echt bericht achter te komen. Het
overzicht toont alleen het staartje van de URL — wie de hele URL heeft kan in
dat kanaal posten.

Wisselen kan zonder de server te herstarten. Staat het veld leeg, dan valt de
plugin terug op `VKVNIEUWS_DISCORD_WEBHOOK` in `local.py`, zodat een bestaande
installatie niets merkt van het bijwerken. Zijn ze allebei leeg, dan staat
Discord gewoon uit en blijft EVE-mail werken.

### Tekst en een gekleurde afbeelding

De tekst komt altijd in de embed. Daaronder gaat optioneel een **afbeelding** mee
met de kleuren zoals in de EVE-mail — Discord kent namelijk geen kleur in gewone
tekst; alleen een `ansi`-codeblok kan dat, en dat maakt alles monospace en zet de
rest van de opmaak uit.

**Waarom de tekst leidend is en niet het plaatje.** Discord schaalt afbeeldingen
terug tot maximaal 350px hoog. Een nieuwsbrief is al gauw 2.000px, dus die komt
op ~17% in beeld en is onleesbaar tot je erop klikt. Nagemeten op 900, 1200, 1600
en 2000px breed: breder tekenen helpt niet, want de hoogte blijft.

Het plaatje wordt getekend met Pillow, niet met een browser: Pillow zit al in
Alliance Auth, een headless browser is honderden megabytes op de server. Dat kan
omdat de opmaak klein is — vet, cursief, onderstreept, kleur, grootte en
regeleindes.

Uit te zetten bij **VKV Nieuws → instellingen**. Lukt het tekenen niet, bijvoorbeeld
omdat er geen schaalbaar lettertype op de server staat, dan gaat het bericht
alsnog weg met een waarschuwing. Op Linux volstaat `fonts-dejavu-core`.

Let op: boven de 4.096 tekens kapt Discord de tekst af.

## Systeem- en regionamen klikbaar

Standaard aan, per bericht uit te zetten. `Olettiers` wordt in de EVE-mail
`<a href="showinfo:5//30002686">Olettiers</a>` en `Fountain` wordt
`showinfo:3//10000058`; in de game opent dan het infovenster. Type 5 is Solar
System, type 3 is Region — beide vormen komen in echte mails voor.

Om de link staat `<font color="#ffd98d00">`, de amber die EVE zelf gebruikt. In
16 systeemlinks uit een echte inbox staat exact die kleur, en zonder ziet een
lezer niet dat het klikbaar is.

**Alle 8.490 systemen en 114 regions, op 41 namen na.** Er bestaan systemen die
*Van*, *Hier*, *Lang*, *Toon*, *Rand* en *Zet* heten, en in een Nederlandse tekst
zou "Van" aan het begin van elke zin een link worden. Die staan op een
uitzonderingslijst, gevonden door alle namen tegen een woordenlijst te houden.

Regions staan er niet bij: *Fountain*, *Delve*, *Branch*, *Catch* en *Curse*
botsen alleen met Engelse woorden, en die komen in een Nederlandse nieuwsbrief
niet als gewoon woord voor.

Namen met spaties (*Cloud Ring*, *Vale of the Silent*, *Old Man Star*) worden als
geheel herkend, en wel vóór de losse woorden — anders zou "Cloud" er los al
uitgepikt worden.

De namen komen uit django-eveuniverse, dat de sterrenkaart lokaal heeft staan;
er is geen ESI-call voor nodig. Reken op ongeveer 66 tekens per link van je
8.000.

## Rechten

| Recht | Wat het mag |
|---|---|
| `vkvnieuws.basic_access` | VKV Nieuws lezen |
| `vkvnieuws.schrijven` | berichten schrijven, bewerken en verwijderen |
| `vkvnieuws.verzenden` | naar EVE-mail en Discord sturen |

## Verzend-character koppelen

Iemand met `vkvnieuws.verzenden` koppelt één keer een character via de knop op de
nieuwspagina. Dat vraagt de scope `esi-mail.send_mail.v1` — de losse scope voor
mail versturen, die je waarschijnlijk nog niet hebt want de meeste plugins vragen
alleen leesrechten.

## Ontvangers

Per bericht geef je op naar wie de mail gaat. ESI kent vier soorten:

- **corporation** — alle leden van die corp
- **alliance** — alle leden van die alliantie
- **character** — één iemand
- **mailing_list** — een in-game mailinglijst

Je hoeft maar één van de twee in te vullen: bij een naam zoekt de plugin het id
erbij, bij een id de naam. Dan zie je meteen of het de juiste is, en of EVE 'm
überhaupt kent. De soort wordt daarbij ook rechtgezet — vul je een character in
terwijl er "alliantie" staat, dan wordt het alsnog character.

Alleen voor een **mailinglijst** is het id nodig; die staan niet in de publieke
opzoeklijst van EVE en zijn dus ook niet te controleren. De lijsten waar je
characters zelf in zitten worden onder de tabel getoond, mét hun id, zodat je
dat nummer niet ergens vandaan hoeft te halen.
