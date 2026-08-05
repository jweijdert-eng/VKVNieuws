/* Opmaakbalk voor het blogbericht — dezelfde knoppen als de mail in de game:
   vet, onderstreept, schuin, kleur, lettergrootte, link en een tekenteller.

   Werkt als aanvulling, niet als vervanging: zonder JavaScript blijft het gewone
   tekstvak staan en werkt het formulier nog. De opschoner aan de serverkant
   bepaalt wat er echt verstuurd wordt; wat hier gebeurt is puur gemak.

   Twee dingen waar dit eerder op stukliep:

   1. Grootte gaat als `style="font-size:NNpx"` en niet als `<font size="NN">`.
      Dat size-attribuut is in HTML de oude schaal van 1 t/m 7, dus alles boven
      de 7 tekende de browser als reuzenletters. De opschoner maakt er bij het
      opslaan alsnog EVE's `<font size>` van.
   2. De selectie moet bewaard en teruggezet worden. Klik je op het keuzelijstje
      of het kleurvakje, dan raakt het bewerkvlak de aandacht kwijt en valt de
      selectie weg — dan deed een tweede keer kiezen niets. */
(function () {
    var vak = document.querySelector('#id_tekst');
    var balk = document.querySelector('#vkv-balk');
    if (!vak || !balk) { return; }

    var vlak = document.createElement('div');
    vlak.className = 'vkv-invoer vkv-bewerkvlak';
    vlak.contentEditable = 'true';
    vlak.spellcheck = true;
    vlak.innerHTML = vak.value || '';
    vak.parentNode.insertBefore(vlak, vak);
    vak.style.display = 'none';
    balk.hidden = false;

    // Opmaak als tags in plaats van style-attributen waar dat kan; EVE-mail
    // kent geen CSS. Voor grootte doen we het bewust wél met style, zie boven.
    try { document.execCommand('styleWithCSS', false, false); } catch (e) { /* oud */ }

    var teller = document.querySelector('#vkv-teller');
    var GRENS = parseInt(balk.dataset.grens || '8000', 10);

    // In bronweergave is het tekstvak zelf waar je in typt; dan mag `tel` er
    // niet overheen schrijven met de inhoud van het bewerkvlak.
    var inBron = false;

    function tel() {
        var n;
        if (inBron) {
            n = vak.value.replace(/<[^>]*>/g, '').replace(/\s/g, '').length;
        } else {
            n = (vlak.innerText || '').replace(/\n/g, '').length;
            vak.value = vlak.innerHTML;
        }
        if (teller) {
            teller.textContent = n + '/' + GRENS;
            teller.classList.toggle('vkv-teveel', n > GRENS);
        }
    }

    /* ── Selectie onthouden ──────────────────────────────────────────────── */
    var bewaard = null;

    function onthoud() {
        var sel = window.getSelection();
        if (!sel.rangeCount) { return; }
        var r = sel.getRangeAt(0);
        if (vlak.contains(r.commonAncestorContainer)) { bewaard = r.cloneRange(); }
    }

    function herstel() {
        vlak.focus();
        if (!bewaard) { return; }
        var sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(bewaard);
    }

    document.addEventListener('selectionchange', function () {
        if (document.activeElement === vlak) { onthoud(); }
    });
    vlak.addEventListener('keyup', onthoud);
    vlak.addEventListener('mouseup', onthoud);

    vlak.addEventListener('input', tel);
    vlak.addEventListener('blur', tel);
    vlak.closest('form').addEventListener('submit', tel);
    tel();

    function doe(commando, waarde) {
        herstel();
        document.execCommand(commando, false, waarde || null);
        onthoud();
        tel();
    }

    /* ── Knoppen ─────────────────────────────────────────────────────────── */
    // preventDefault op mousedown: dan verliest het bewerkvlak de aandacht niet
    // en blijft de selectie staan.
    balk.addEventListener('mousedown', function (e) {
        if (e.target.closest('[data-doe]')) { e.preventDefault(); }
    });

    balk.addEventListener('click', function (e) {
        var knop = e.target.closest('[data-doe]');
        if (!knop) { return; }
        e.preventDefault();
        if (knop.dataset.doe === 'link') {
            var adres = window.prompt(balk.dataset.linkvraag ||
                'Adres (https://… of showinfo:…)', 'https://');
            if (adres) { doe('createLink', adres); }
            return;
        }
        if (knop.dataset.doe === 'geenlink') { doe('unlink'); return; }
        doe(knop.dataset.doe);
    });

    /* ── Kleur ───────────────────────────────────────────────────────────── */
    var kleur = document.querySelector('#vkv-kleur');
    if (kleur) {
        kleur.addEventListener('input', function () { doe('foreColor', kleur.value); });
    }

    /* ── Lettergrootte ───────────────────────────────────────────────────── */
    function zetBestaandeGrootte(px) {
        // Alle spans met een eigen font-size die helemaal binnen de selectie
        // vallen, plus de span waar de selectie zelf in zit.
        var sel = window.getSelection();
        if (!sel.rangeCount) { return; }
        var r = sel.getRangeAt(0);

        var geraakt = [];
        vlak.querySelectorAll('span[style*="font-size"]').forEach(function (s) {
            if (r.intersectsNode(s)) { geraakt.push(s); }
        });
        var omhoog = r.commonAncestorContainer;
        while (omhoog && omhoog !== vlak) {
            if (omhoog.nodeType === 1 && omhoog.style && omhoog.style.fontSize) {
                if (geraakt.indexOf(omhoog) === -1) { geraakt.push(omhoog); }
            }
            omhoog = omhoog.parentNode;
        }
        geraakt.forEach(function (s) { s.style.fontSize = px + 'px'; });
    }

    var grootte = document.querySelector('#vkv-grootte');
    if (grootte) {
        grootte.addEventListener('change', function () {
            herstel();
            // execCommand kent alleen 1 t/m 7. We zetten 7 als merkteken en
            // vervangen die elementen daarna door een span met de echte maat in
            // pixels — anders tekent de browser er reuzenletters van.
            document.execCommand('fontSize', false, '7');

            var nieuw = [];
            vlak.querySelectorAll('font[size="7"]').forEach(function (f) {
                var span = document.createElement('span');
                span.style.fontSize = grootte.value + 'px';
                // Een kleur die op hetzelfde element stond mag niet verdwijnen.
                if (f.getAttribute('color')) { span.style.color = f.getAttribute('color'); }
                while (f.firstChild) { span.appendChild(f.firstChild); }
                f.parentNode.replaceChild(span, f);
                nieuw.push(span);
            });

            if (nieuw.length) {
                // Opnieuw selecteren, want de bewaarde selectie wees naar de
                // elementen die we net vervangen hebben. Zonder dit doet een
                // tweede keer kiezen niets: het bereik is dan losgekoppeld.
                var r = document.createRange();
                r.setStartBefore(nieuw[0]);
                r.setEndAfter(nieuw[nieuw.length - 1]);
                var sel = window.getSelection();
                sel.removeAllRanges();
                sel.addRange(r);
            } else {
                // Chrome maakt geen merkteken als de selectie al een eigen
                // font-size heeft; die passen we dan rechtstreeks aan.
                zetBestaandeGrootte(grootte.value);
            }
            onthoud();
            tel();
        });
    }

    // Plakken als platte tekst: anders komt de halve opmaak van een website mee
    // en gooit de opschoner dat er straks toch weer uit. Wil je wél markup
    // plakken, dan is daar de bronweergave voor.
    vlak.addEventListener('paste', function (e) {
        e.preventDefault();
        var tekst = (e.clipboardData || window.clipboardData).getData('text');
        document.execCommand('insertText', false, tekst);
    });

    /* ── Bronweergave ────────────────────────────────────────────────────────
       Het omzetten gebeurt aan de serverkant. Dat is één netwerkrondje per klik,
       maar het alternatief is de hele opschoner nóg een keer in JavaScript
       naschrijven — en dan heb je twee versies die na de eerste wijziging al uit
       elkaar lopen. */
    var bronknop = balk.querySelector('[data-doe="bron"]');
    var bronvlag = document.querySelector('#vkv-bronmodus');
    var form = vak.closest('form');

    function csrf() {
        var el = form && form.querySelector('[name=csrfmiddlewaretoken]');
        return el ? el.value : '';
    }

    function omzetten(tekst, naar) {
        return fetch(balk.dataset.bronurl, {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
            body: JSON.stringify({tekst: tekst, naar: naar})
        }).then(function (r) {
            if (!r.ok) { throw new Error('HTTP ' + r.status); }
            return r.json();
        }).then(function (a) { return a.tekst; });
    }

    function zetBron(aan) {
        inBron = aan;
        vlak.style.display = aan ? 'none' : '';
        vak.style.display = aan ? '' : 'none';
        vak.classList.toggle('vkv-bronvlak', aan);
        if (bronvlag) { bronvlag.value = aan ? '1' : ''; }
        if (bronknop) { bronknop.setAttribute('aria-pressed', aan ? 'true' : 'false'); }
        // De opmaakknoppen doen niets op ruwe tekst; grijs ze uit in plaats van
        // ze te laten klikken zonder gevolg.
        [].forEach.call(balk.querySelectorAll('.vkv-balkknop, .vkv-balkkeuze, .vkv-kleurknop'),
            function (el) {
                if (el === bronknop) { return; }
                el.classList.toggle('vkv-balk-uit', aan);
                if ('disabled' in el) { el.disabled = aan; }
            });
        tel();
    }

    if (bronknop && balk.dataset.bronurl) {
        bronknop.addEventListener('click', function () {
            bronknop.disabled = true;
            if (!inBron) {
                omzetten(vlak.innerHTML, 'bron').then(function (t) {
                    vak.value = t; zetBron(true);
                }).catch(function () {
                    window.alert(balk.dataset.bronfout || 'Omzetten mislukte.');
                }).then(function () { bronknop.disabled = false; });
            } else {
                omzetten(vak.value, 'editor').then(function (t) {
                    vlak.innerHTML = t; zetBron(false);
                }).catch(function () {
                    window.alert(balk.dataset.bronfout || 'Omzetten mislukte.');
                }).then(function () { bronknop.disabled = false; });
            }
        });
        vak.addEventListener('input', function () { if (inBron) { tel(); } });
    }
})();
