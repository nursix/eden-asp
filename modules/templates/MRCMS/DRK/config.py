"""
    MRCMS: Migrant Reception Center and Case Management System

    License: MIT
"""

from collections import OrderedDict

# from gluon import current
# from gluon.storage import Storage

# =============================================================================
def config(settings):

    # T = current.T

    settings.base.system_name = "Village"
    settings.base.system_name_short = "Village"

    # PrePopulate data
    settings.base.prepopulate += ("MRCMS/DRK",)
    settings.base.prepopulate_demo += ("MRCMS/DRK/Demo",)

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "DRK"
    settings.base.theme_config = "MRCMS/DRK"

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
    # Scenario-specific custom settings
    #
    settings.custom.autogenerate_case_ids = True
    settings.custom.manage_work_orders = True

    settings.custom.context_org_name = "Deutsches Rotes Kreuz"

    settings.custom.org_menu_logo = ("DRK", "img", "logo_small.png")
    settings.custom.homepage_logo = ("DRK", "img", "logo_small.png")
    settings.custom.idcard_default_logo = ("DRK", "img", "logo_small.png")

# END =========================================================================
