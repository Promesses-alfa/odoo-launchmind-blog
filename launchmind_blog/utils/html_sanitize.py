# -*- coding: utf-8 -*-
"""HTML-sanitatiebarriere voor de Odoo-connector (milestone M3).

Het platform levert artikel-HTML nooit gesaneerd aan de connectors (zie
``docs/content-allowlist.md`` sectie 7). Elke surface legt daarom zijn eigen
barriere op de grens waar hij de feed ontvangt. Voor Odoo is dat core's eigen
``odoo.tools.html_sanitize`` (Odoo 18), een bewezen en onderhouden sanitizer.

Deze module is de ENIGE plek in de connector die hem aanroept. Daardoor is
elke plek die artikel-HTML verwerkt greppebaar op ``sanitize_article_html`` en
is een call-site die de barriere vergeet zichtbaar als een ontbrekende
referentie. De controller roept de wrapper aan voordat ``post_vals`` wordt
gebouwd, zodat zowel het create- als het update-pad de gesaneerde waarde krijgt.

Beperking van de omgeving: er staat lokaal geen Odoo-instantie, dus
``odoo.tools.html_sanitize`` kan hier niet echt draaien. De bewijsverplichting
is de BEDRADING (deze wrapper wordt voor de ``blog.post``-write aangeroepen op
beide paden), en die bewijst ``test/test_sanitize.py`` met een gemockte import.
De werking van de sanitizer zelf is geteste Odoo-kerncode.
"""

import html
import re

from odoo.tools import html_sanitize


def sanitize_article_html(content):
    """Sanitize artikel-HTML met Odoo's core-sanitizer.

    Lege of ontbrekende invoer blijft ongewijzigd: ``None`` en ``''`` zijn geen
    HTML en hoeven niet door de sanitizer. Alles wat wel tekst is gaat door
    ``odoo.tools.html_sanitize``; de teruggegeven waarde is de enige die in
    ``post_vals`` (en in de daaruit afgeleide velden) mag belanden.
    """
    if not content:
        return content
    return html_sanitize(content)


_TAG = re.compile(r'<[^>]*>')
_WIT = re.compile(r'\s+')


def excerpt_as_text(excerpt):
    """Maak van de excerpt platte tekst voor ``subtitle`` en de meta description.

    Die velden zijn tekstvelden die Odoo bij het renderen zelf escapet. Een
    HTML-sanitizer is daar het verkeerde gereedschap: die laat entities
    (``&amp;``) en wrapper-tags achter die dan letterlijk op de pagina en in
    de zoekresultaten staan. We halen daarom alle tags weg, decoderen
    entities en vouwen witruimte samen. Doordat Odoo escapet bij het
    renderen, kan er geen markup meer uit deze waarde ontstaan.
    """
    if not excerpt:
        return excerpt
    tekst = html.unescape(_TAG.sub(' ', excerpt))
    # Een tweede ronde: gecodeerde tags (&lt;img ...&gt;) worden na het
    # decoderen echte tags en mogen ook niet als tekst blijven staan.
    tekst = _TAG.sub(' ', tekst)
    return _WIT.sub(' ', tekst).strip()
