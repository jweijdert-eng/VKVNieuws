"""Menu- en URL-haken."""

from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, UrlHook

import vkvnieuws.urls


class BlogMenuItem(MenuItemHook):
    """Eén menu-item; de onderdelen zijn tabbladen in de pagina zelf.

    VALKUIL: AA bepaalt de identiteit van een menu-item met
    sha256("<module>.<klassenaam>"), dus niet met de tekst of de URL. Twee hooks
    die dezelfde klasse teruggeven worden tot één item samengevouwen. Elk item
    hoort dus een eigen klasse te zijn.
    """

    def __init__(self):
        MenuItemHook.__init__(
            self,
            _("VKV Nieuws"),
            "fas fa-newspaper fa-fw",
            "vkvnieuws:index",
            navactive=["vkvnieuws:"],
        )

    def render(self, request):
        if request.user.has_perm("vkvnieuws.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    return BlogMenuItem()


@hooks.register("url_hook")
def register_urls():
    return UrlHook(vkvnieuws.urls, "vkvnieuws", r"^vkvnieuws/")
