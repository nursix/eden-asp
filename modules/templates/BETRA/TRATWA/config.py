"""
    TRATWA Configuration for BETRA

    License: MIT
"""

from collections import OrderedDict

from gluon import current
from gluon.storage import Storage

# =============================================================================
def config(settings):

    T = current.T

    settings.base.system_name = "Beneficiary Tracking and Assistance Coordination"
    settings.base.system_name_short = "BETRA"

    # PrePopulate data
    settings.base.prepopulate += ("BETRA/TRATWA",)
    settings.base.prepopulate_demo += ("BETRA/TRATWA/Demo",)

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "TRATWA"
    settings.base.theme_config = "BETRA/TRATWA"

    # Restrict the Location Selector to just certain countries
    settings.gis.countries = ("PL",)

    # Languages used in the deployment (used for Language Toolbar & GIS Locations)
    settings.L10n.languages = OrderedDict([
       ("pl", "Polish"),
       ("en", "English"),
       ("de", "German"),
    ])
    # Default language for Language Toolbar (& GIS Locations in future)
    settings.L10n.default_language = "pl"
    # Default timezone for users
    settings.L10n.timezone = "Europe/Warszawa"

    # -------------------------------------------------------------------------
    # Defaults for custom settings
    #
    settings.custom.autogenerate_case_ids = True

    settings.custom.context_org_name = "Tratwa"

    settings.custom.org_menu_logo = ("TRATWA", "img", "logo_small.png")
    settings.custom.homepage_logo = ("TRATWA", "img", "logo_large.png")
    settings.custom.idcard_default_logo = ("TRATWA", "img", "logo_small.png")

# END =========================================================================
