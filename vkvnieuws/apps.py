from django.apps import AppConfig

from vkvnieuws import __version__


class VkvNieuwsConfig(AppConfig):
    name = "vkvnieuws"
    label = "vkvnieuws"
    verbose_name = f"VKV Nieuws v{__version__}"
