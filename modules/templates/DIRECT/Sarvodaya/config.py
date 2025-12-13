"""
    DIRECT/Sarvodaya: sub-template for Sarvodaya / Sri Lanka

    License: MIT
"""

from collections import OrderedDict

from gluon import current
from gluon.storage import Storage

# =============================================================================
def config(settings):

    T = current.T

    settings.base.system_name = "Disaster Response Coordination"
    settings.base.system_name_short = "Sarvodaya DIRECT"

    # PrePopulate data
    settings.base.prepopulate += ("DIRECT/Sarvodaya",)
    settings.base.prepopulate_demo.append("DIRECT/Sarvodaya/Demo")

    # Restrict the Location Selector to just certain countries
    # NB This can also be over-ridden for specific contexts later
    # e.g. Activities filtered to those of parent Project
    settings.gis.countries = ("LK",)
    #gis_levels = ("L1", "L2", "L3")
    # Uncomment to display the Map Legend as a floating DIV, so that it is visible on Summary Map
    settings.gis.legend = "float"
    # Uncomment to Disable the Postcode selector in the LocationSelector
    #settings.gis.postcode_selector = False # @ToDo: Vary by country (include in the gis_config!)
    # Uncomment to show the Print control:
    # http://eden.sahanafoundation.org/wiki/UserGuidelines/Admin/MapPrinting
    #settings.gis.print_button = True

    # L10n settings
    # Languages used in the deployment (used for Language Toolbar, GIS Locations, etc)
    # http://www.loc.gov/standards/iso639-2/php/code_list.php
    settings.L10n.languages = OrderedDict([
       ("en", "English"),
       ("si", "Sinhala"),
       ("ta", "Tamil"),
    ])
    # Default language for Language Toolbar (& GIS Locations in future)
    settings.L10n.default_language = "en"
    # Uncomment to Hide the language toolbar
    #settings.L10n.display_toolbar = False
    # Default timezone for users
    settings.L10n.timezone = "Asia/Colombo"
    # Default date/time formats
    settings.L10n.date_format = "%d.%m.%Y"
    settings.L10n.time_format = "%H:%M"
    # Number formats (defaults to ISO 31-0)
    # Decimal separator for numbers (defaults to ,)
    settings.L10n.decimal_separator = "."
    # Thousands separator for numbers (defaults to space)
    settings.L10n.thousands_separator = " "
    # Uncomment this to Translate Layer Names
    #settings.L10n.translate_gis_layer = True
    # Uncomment this to Translate Location Names
    #settings.L10n.translate_gis_location = True
    # Uncomment this to Translate Organisation Names/Acronyms
    #settings.L10n.translate_org_organisation = True
    # Finance settings
    settings.fin.currencies = {
        "EUR" : "Euros",
    }
    settings.fin.currency_default = "EUR"
    settings.fin.currency_writable = False

    # Do not require international phone number format
    settings.msg.require_international_phone_numbers = False

    # -------------------------------------------------------------------------
    # Overrides for custom settings
    #
    settings.custom.context_org_name = "Sarvodaya"

    settings.custom.org_menu_logo = ("Sarvodaya", "img", "logo_small.png")
    settings.custom.homepage_logo = ("Sarvodaya", "img", "logo_large.png")

# END =========================================================================
