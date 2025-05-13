"""
    MRCMS: Migrant Reception Center and Case Management System

    License: MIT
"""

from collections import OrderedDict

from gluon import current
from gluon.storage import Storage

# =============================================================================
def config(settings):

    T = current.T

    #settings.base.system_name = "MRCMS"
    #settings.base.system_name_short = "MRCMS"

    # PrePopulate data
    settings.base.prepopulate += ("MRCMS/RLP",)
    settings.base.prepopulate_demo += ("MRCMS/RLP/Demo",)

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "RLP"
    settings.base.theme_config = "MRCMS/RLP"

    # Restrict the Location Selector to just certain countries
    settings.gis.countries = ("DE",)

    # Languages used in the deployment (used for Language Toolbar & GIS Locations)
    settings.L10n.languages = OrderedDict([
       ("en", "English"),
       ("de", "German"),
    ])
    # Default language for Language Toolbar (& GIS Locations in future)
    settings.L10n.default_language = "de"
    # Default timezone for users
    settings.L10n.timezone = "Europe/Berlin"

    # -------------------------------------------------------------------------
    # Defaults for custom settings
    #
    settings.custom.autogenerate_case_ids = True

    settings.custom.context_org_name = "Aufsichts- und Dienstleistungsdirektion"

    settings.custom.org_menu_logo = ("RLP", "img", "logo_rlp.png")
    settings.custom.homepage_logo = ("RLP", "img", "logo_add.svg")
    settings.custom.idcard_default_logo = ("RLP", "img", "logo_rlp.png")

# END =========================================================================
