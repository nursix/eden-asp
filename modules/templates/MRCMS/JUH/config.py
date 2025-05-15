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

    #settings.base.system_name = "MRCMS"
    #settings.base.system_name_short = "MRCMS"

    # PrePopulate data
    settings.base.prepopulate += ("MRCMS/JUH",)
    settings.base.prepopulate_demo += ("MRCMS/JUH/Demo",)

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "JUH"
    settings.base.theme_config = "MRCMS/JUH"

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
    settings.custom.manage_work_orders = False

    settings.custom.context_org_name = "Johanniter-Unfall-Hilfe"

    settings.custom.org_menu_logo = ("JUH", "img", "logo_smaller.png")
    settings.custom.homepage_logo = ("JUH", "img", "logo_small.svg")
    settings.custom.idcard_default_logo = ("JUH", "img", "logo_small.png")

    # -------------------------------------------------------------------------
    # Hide IssueReporter role while not using work order management
    # TODO remove when approved
    #
    privileged_roles = settings.get_auth_privileged_roles()
    privileged_roles["ISSUE_REPORTER"] = "ADMIN"
    settings.auth.privileged_roles = privileged_roles

# END =========================================================================
