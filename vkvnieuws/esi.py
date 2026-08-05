"""EVE-mail versturen — Blog.

Belangrijk om te weten: **ESI kent geen corp-afzender**. Een mail komt altijd
van het character wiens token je gebruikt. Wat wél kan is een mail *naar* een
corporatie sturen; die valt dan bij alle leden in de inbox, met dat ene
character als afzender. Vandaar dat je hier een verzend-character aanwijst.
"""

import logging
import time

import requests
from vkvnieuws.models import MAX_BODY, MAX_ONDERWERP, MAX_ONTVANGERS

logger = logging.getLogger(__name__)

ESI = "https://esi.evetech.net/latest"
UA = {"User-Agent": "aa-vkvrijdag (Alliance Auth plugin; maintainer: Dutch Legions)"}

SEND_SCOPE = "esi-mail.send_mail.v1"

_session = requests.Session()


class MailFout(Exception):
    """Verzenden lukte niet; de tekst is bedoeld om aan de gebruiker te tonen."""


def verzend_tokens():
    """Alle geldige tokens die mail mogen versturen, nieuwste eerst."""
    from esi.models import Token

    uit = []
    for token in (Token.objects.filter(scopes__name=SEND_SCOPE)
                  .order_by("-created")):
        try:
            uit.append((token.character_id, token.character_name,
                        token.valid_access_token()))
        except Exception:  # noqa: BLE001 — verlopen of ingetrokken
            continue
    return uit


# ESI's categorie -> onze soort. Mailinglijsten staan er niet bij: die zijn niet
# publiek op te zoeken, daar moet je het id van weten.
CATEGORIE = {
    "character": "character",
    "characters": "character",
    "corporation": "corporation",
    "corporations": "corporation",
    "alliance": "alliance",
    "alliances": "alliance",
}


def zoek_op_naam(naam):
    """Naam -> (soort, id). Geeft (None, None) als EVE 'm niet kent.

    /universe/ids/ vraagt een exacte naam maar trekt zich niets aan van
    hoofdletters. Publiek, dus geen token nodig.
    """
    naam = (naam or "").strip()
    if not naam:
        return None, None
    try:
        r = _session.post(f"{ESI}/universe/ids/", headers=UA,
                          params={"datasource": "tranquility"},
                          json=[naam], timeout=20)
        if r.status_code != 200:
            return None, None
        gevonden = r.json() or {}
    except (requests.RequestException, ValueError):
        return None, None

    for sleutel in ("characters", "corporations", "alliances"):
        for rij in gevonden.get(sleutel) or []:
            return CATEGORIE[sleutel], rij["id"]
    return None, None


def zoek_op_id(eve_id):
    """Id -> (soort, naam). Geeft (None, None) als EVE 'm niet kent."""
    try:
        eve_id = int(eve_id)
    except (TypeError, ValueError):
        return None, None
    try:
        r = _session.post(f"{ESI}/universe/names/", headers=UA,
                          params={"datasource": "tranquility"},
                          json=[eve_id], timeout=20)
        if r.status_code != 200:
            return None, None
        rijen = r.json() or []
    except (requests.RequestException, ValueError):
        return None, None

    for rij in rijen:
        soort = CATEGORIE.get((rij.get("category") or "").lower())
        if soort:
            return soort, rij.get("name") or ""
    return None, None


def character_ids(user):
    """De character-ids van een gebruiker."""
    try:
        from allianceauth.eveonline.models import EveCharacter

        return list(EveCharacter.objects
                    .filter(character_ownership__user=user)
                    .values_list("character_id", flat=True))
    except Exception:  # noqa: BLE001
        return []


def mailinglijsten(ids):
    """De mailinglijsten waar deze characters in zitten.

    Een mailinglijst-id is nergens publiek op te zoeken — /universe/names kent
    ze niet. Dit is de enige manier om er een naam bij te krijgen, en het scheelt
    dat je zo'n nummer niet hoeft over te tikken.
    """
    uit = {}
    for cid in ids:
        token = token_voor(cid, "esi-mail.read_mail.v1")
        if not token:
            continue
        rijen = _lees(f"/characters/{cid}/mail/lists/", token) or []
        for rij in rijen:
            uit[rij["mailing_list_id"]] = rij.get("name") or ""
    return sorted(uit.items(), key=lambda p: p[1].lower())


def token_voor(character_id, scope):
    """Een geldig token van dit character met deze scope, of None."""
    from esi.models import Token

    for token in (Token.objects.filter(character_id=character_id,
                                       scopes__name=scope).order_by("-created")):
        try:
            return token.valid_access_token()
        except Exception:  # noqa: BLE001 — verlopen of ingetrokken
            continue
    return None


def _lees(pad, token):
    """Eén GET met token; None bij een fout."""
    try:
        r = _session.get(f"{ESI}{pad}", headers={**UA, "Authorization": f"Bearer {token}"},
                         params={"datasource": "tranquility"}, timeout=20)
        return r.json() if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def naar_eve_opmaak(tekst):
    """Klaarmaken voor verzending.

    De tekst is bij het opslaan al door de opschoner gegaan en is dus geldige
    EVE-opmaak. Alleen berichten van vóór de opmaakbalk zijn nog platte tekst;
    die krijgen alsnog hun <br>'s en escaping.
    """
    from vkvnieuws import compact, opmaak

    tekst = tekst or ""
    if "<" not in tekst:
        return opmaak.van_platte_tekst(tekst)
    # Ook hier inkorten: berichten van vóór deze versie staan nog met alle
    # overbodige tags in de database en zouden anders geweigerd worden.
    return compact.compacteer(tekst)


def _kort(tekst, grens):
    """Afkappen op een grens, met een teken dat er meer was."""
    if len(tekst) <= grens:
        return tekst
    return tekst[: grens - 1] + "…"


def stuur_mail(onderwerp, tekst, ontvangers, character_id=None):
    """Stuur één mail. Geeft (character_id, character_name) van de afzender terug.

    `ontvangers` is een lijst van (soort, eve_id) zoals ESI ze kent:
    character / corporation / alliance / mailing_list.
    """
    if not ontvangers:
        raise MailFout("Geen ontvangers opgegeven.")
    if len(ontvangers) > MAX_ONTVANGERS:
        raise MailFout(
            f"ESI staat hoogstens {MAX_ONTVANGERS} ontvangers per mail toe; "
            f"dit bericht heeft er {len(ontvangers)}.")

    tokens = verzend_tokens()
    if character_id:
        tokens = [t for t in tokens if t[0] == character_id]
    if not tokens:
        raise MailFout(
            "Geen character gekoppeld dat mail mag versturen. Koppel er eerst "
            f"één met de scope {SEND_SCOPE}.")

    cid, naam, token = tokens[0]
    inhoud = naar_eve_opmaak(tekst)
    if len(inhoud) > MAX_BODY:
        # Niet afkappen: een half verstuurde nieuwsbrief is erger dan geen.
        raise MailFout(
            f"Te lang voor EVE: {len(inhoud):,} tekens inclusief opmaak, en de "
            f"grens is {MAX_BODY:,}. Kort de tekst in of gebruik minder kleur "
            f"en lettergroottes.".replace(",", "."))

    body = {
        "subject": _kort(onderwerp, MAX_ONDERWERP),
        "body": inhoud,
        "recipients": [{"recipient_type": soort, "recipient_id": int(eve_id)}
                       for soort, eve_id in ontvangers],
        "approved_cost": 0,
    }

    for poging in (1, 2, 3):
        try:
            r = _session.post(
                f"{ESI}/characters/{cid}/mail/",
                headers={**UA, "Authorization": f"Bearer {token}",
                         "Content-Type": "application/json"},
                params={"datasource": "tranquility"},
                json=body, timeout=30)
        except requests.RequestException as exc:
            if poging == 3:
                raise MailFout(f"ESI niet bereikbaar: {exc}") from exc
            time.sleep(2 ** poging)
            continue

        if r.status_code in (200, 201):
            logger.info("Blog: mail verstuurd door %s naar %s ontvangers",
                        naam, len(ontvangers))
            return cid, naam

        # Alleen bij een tijdelijke storing opnieuw proberen. Een 403 verandert
        # niet door het nog eens te doen, en bij 520 (rate limit) maak je het
        # juist erger.
        if r.status_code in (500, 502, 503, 504) and poging < 3:
            time.sleep(2 ** poging)
            continue

        raise MailFout(_uitleg(r, naam))

    raise MailFout("Verzenden lukte niet na drie pogingen.")


def _uitleg(respons, afzender):
    """Van een ESI-foutcode iets maken waar je wat aan hebt."""
    try:
        melding = respons.json().get("error", "")
    except ValueError:
        melding = (respons.text or "")[:200]

    uitleg = {
        400: "ESI weigerde het bericht. Meestal een ontvanger die niet bestaat, "
             "een lege tekst, of een body boven de 8000 tekens.",
        401: "Het token is verlopen of ingetrokken. Koppel het "
             "verzend-character opnieuw.",
        403: f"{afzender} mag deze mail niet versturen. Voor een mail aan een "
             "hele corporatie of alliantie heb je in de game de rol "
             "Communications Officer nodig.",
        420: "ESI-foutlimiet bereikt. Even wachten en het daarna opnieuw proberen.",
        520: "EVE's eigen limiet op mail versturen is bereikt. Dit is een limiet "
             "van CCP op het aantal mails per tijdseenheid — wachten is het enige "
             "dat helpt.",
    }.get(respons.status_code,
          f"ESI gaf {respons.status_code} terug.")

    return f"{uitleg} ({melding})" if melding else uitleg
