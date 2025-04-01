"""
    BETRA: Beneficiary Tracking and Assistance Coordination

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
    settings.base.prepopulate += ("BETRA",)
    #settings.base.prepopulate_demo += ("BETRA/Demo",)

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "MRCMS"
    settings.base.theme_config = "BETRA"
    settings.base.theme_layouts = "BETRA"

    # Authentication settings
    # Should users be allowed to register themselves?
    settings.security.self_registration = False
    # Do new users need to verify their email address?
    #settings.auth.registration_requires_verification = True
    # Do new users need to be approved by an administrator prior to being able to login?
    #settings.auth.registration_requires_approval = True
    settings.auth.registration_requests_organisation = True
    settings.auth.registration_link_user_to = {"staff": T("Staff"),
                                               #"volunteer": T("Volunteer"),
                                               }
    settings.auth.registration_link_user_to_default = ["staff"]
    # Disable password-retrieval feature
    settings.auth.password_retrieval = False

    # Approval emails get sent to all admins
    settings.mail.approver = "ADMIN"

    # Restrict the Location Selector to just certain countries
    # NB This can also be over-ridden for specific contexts later
    # e.g. Activities filtered to those of parent Project
    settings.gis.countries = ("DE",)
    # Uncomment to display the Map Legend as a floating DIV
    settings.gis.legend = "float"
    # Uncomment to Disable the Postcode selector in the LocationSelector
    #settings.gis.postcode_selector = False # @ToDo: Vary by country (include in the gis_config!)
    # Uncomment to show the Print control:
    # http://eden.sahanafoundation.org/wiki/UserGuidelines/Admin/MapPrinting
    #settings.gis.print_button = True

    # Settings suitable for Housing Units
    # - move into customise fn if also supporting other polygons
    settings.gis.precision = 5
    settings.gis.simplify_tolerance = 0
    settings.gis.bbox_min_size = 0.001
    #settings.gis.bbox_offset = 0.007

    # L10n settings
    # Languages used in the deployment (used for Language Toolbar & GIS Locations)
    # http://www.loc.gov/standards/iso639-2/php/code_list.php
    settings.L10n.languages = OrderedDict([
       ("en", "English"),
       ("de", "German"),
       ("pl", "Polish"),
    ])
    # Default language for Language Toolbar (& GIS Locations in future)
    settings.L10n.default_language = "de"
    # Uncomment to Hide the language toolbar
    #settings.L10n.display_toolbar = False
    # Default timezone for users
    settings.L10n.timezone = "Europe/Berlin"
    # Number formats (defaults to ISO 31-0)
    # Decimal separator for numbers (defaults to ,)
    settings.L10n.decimal_separator = "."
    # Thousands separator for numbers (defaults to space)
    settings.L10n.thousands_separator = ","
    # Uncomment this to Translate Layer Names
    #settings.L10n.translate_gis_layer = True
    # Uncomment this to Translate Location Names
    #settings.L10n.translate_gis_location = True
    # Uncomment this to Translate Organisation Names/Acronyms
    #settings.L10n.translate_org_organisation = True
    # Finance settings
    settings.fin.currencies = {
        "EUR" : "Euros",
    #    "GBP" : "Great British Pounds",
    #    "USD" : "United States Dollars",
    }
    settings.fin.currency_default = "EUR"

    # Security Policy
    # http://eden.sahanafoundation.org/wiki/S3AAA#System-widePolicy
    # 1: Simple (default): Global as Reader, Authenticated as Editor
    # 2: Editor role required for Update/Delete, unless record owned by session
    # 3: Apply Controller ACLs
    # 4: Apply both Controller & Function ACLs
    # 5: Apply Controller, Function & Table ACLs
    # 6: Apply Controller, Function, Table ACLs and Entity Realm
    # 7: Apply Controller, Function, Table ACLs and Entity Realm + Hierarchy
    #
    settings.security.policy = 7 # Controller, Function, Table rules with hierarchical realms

    # Version details on About-page require login
    settings.security.version_info_requires_login = True

    # -------------------------------------------------------------------------
    # Defaults for custom settings
    #
    settings.custom.autogenerate_case_ids = True
    settings.custom.context_org_name = "Eden ASP"

    settings.custom.org_menu_logo = ("default", "img", "eden_asp_small.png")
    settings.custom.homepage_logo = ("default", "img", "eden_asp_large.png")
    settings.custom.idcard_default_logo = ("default", "img", "eden_asp_small.png")

    # -------------------------------------------------------------------------
    # General UI settings
    #
    settings.ui.calendar_clear_icon = True
    settings.ui.auth_user_represent = "name"
    settings.ui.datatables_responsive = False

    # Do not pre-select family members for checkpoint registration
    #settings.ui.checkpoint_multi_preselect_all = False

    # -------------------------------------------------------------------------
    # AUTH Settings
    #
    from .customise.auth import realm_entity, \
                                auth_user_resource

    settings.auth.privileged_roles = {"NEWSLETTER_AUTHOR": "ADMIN",
                                      "STAFF": ("ORG_GROUP_ADMIN", "ORG_ADMIN"),
                                      "CASE_ADMIN": "ORG_ADMIN",
                                      "CASE_MANAGER": "ORG_ADMIN",
                                      "SECURITY": "ORG_ADMIN",
                                      "CATERING": "ORG_ADMIN",
                                      "SHELTER_ADMIN": ("ORG_GROUP_ADMIN", "SHELTER_ADMIN"),
                                      "SHELTER_MANAGER": ("ORG_GROUP_ADMIN", "SHELTER_ADMIN"),
                                      "SUPPLY_ADMIN": ("ORG_GROUP_ADMIN", "SUPPLY_ADMIN"),
                                      "SUPPLY_MANAGER": ("ORG_GROUP_ADMIN", "SUPPLY_ADMIN"),
                                      # These are restricted for now until better-defined
                                      "CASE_ASSISTANT": "ADMIN",
                                      "QUARTERMASTER": "ADMIN",
                                      "JANITOR": "ADMIN",
                                      "CHECKPOINT": "ADMIN",
                                      }

    settings.auth.realm_entity = realm_entity
    settings.auth.registration_roles = {None: ["STAFF"]}
    settings.customise_auth_user_resource = auth_user_resource

    # -------------------------------------------------------------------------
    # CMS Settings and Customizations
    #
    settings.cms.hide_index = True
    settings.cms.newsletter_recipient_types = ("org_organisation",)

    from .customise.cms import cms_newsletter_resource, \
                               cms_newsletter_controller, \
                               cms_post_resource, \
                               cms_post_controller

    settings.customise_cms_newsletter_resource = cms_newsletter_resource
    settings.customise_cms_newsletter_controller = cms_newsletter_controller
    settings.customise_cms_post_resource = cms_post_resource
    settings.customise_cms_post_controller = cms_post_controller

    # -------------------------------------------------------------------------
    # DOC Settings and Customizations
    #
    from .customise.doc import doc_document_resource, \
                               doc_document_controller, \
                               doc_image_resource

    settings.customise_doc_document_resource = doc_document_resource
    settings.customise_doc_document_controller = doc_document_controller
    settings.customise_doc_image_resource = doc_image_resource

    # -------------------------------------------------------------------------
    # DVR Settings and Customizations
    #
    # Configure a regular expression pattern for ID Codes (QR Codes)
    settings.dvr.id_code_pattern = "(?P<label>[^,]*),(?P<family>[^,]*),(?P<last_name>[^,]*),(?P<first_name>[^,]*),(?P<date_of_birth>[^,]*),.*"
    # Uncomment this to enable household size in cases, set to "auto" for automatic counting
    settings.dvr.household_size = "auto"

    # Most commonly documented case languages
    settings.dvr.case_languages = ('aa', 'am', 'anp', 'as', 'az', 'bal', 'bg', 'bho', 'bn',
                                   'bs', 'cs', 'da', 'de', 'el', 'en', 'es', 'et', 'fa',
                                   'fi', 'fil', 'fr', 'ga', 'gu', 'ha', 'hi', 'hmn', 'hr',
                                   'hu', 'hy', 'id', 'ig', 'it', 'ja', 'jv', 'ka', 'km',
                                   'kn', 'ko', 'ku', 'lo', 'lt', 'lv', 'mai', 'mk', 'ml',
                                   'mlt', 'mn', 'mr', 'my', 'nl', 'om', 'pa', 'pl', 'prs',
                                   'ps', 'pt', 'ro', 'rom', 'ru', 'rup', 'sd', 'si', 'sk',
                                   'sl', 'so', 'sq', 'sr', 'sv', 'sw', 'ta', 'te', 'th',
                                   'ti', 'tk', 'tl', 'tr', 'uk', 'ur', 'uz', 'vi', 'yo',
                                   'zh', 'ab', 'af', 'ak', 'an', 'ar', 'bem', 'cop', 'cr',
                                   'dak', 'del', 'din', 'gaa', 'kaw', 'kg', 'kho', 'kpe',
                                   'kru', 'kum', 'kv', 'kw', 'ky', 'lez', 'mdr', 'mis',
                                   'new', 'nso', 'nzi', 'pau', 'pi', 'raj', 'rm', 'rn',
                                   'rw', 'sm', 'sn', 'snk', 'srn', 'su', 'syr', 'tig',
                                   'tog', 'tsi', 'tw', 'umb', 'zza',
                                   )

    settings.dvr.case_include_activity_docs = True
    settings.dvr.case_include_group_docs = True

    # Manage case flags
    settings.dvr.case_flags = True
    # Use org-specific case flags
    settings.dvr.case_flags_org_specific = True

    # Use org-specific case event types
    settings.dvr.case_event_types_org_specific = True
    # Issue a "not checked-in" warning in case event registration
    settings.dvr.event_registration_checkin_warning = True
    # Case events can close appointments
    settings.dvr.case_events_close_appointments = True
    # Case events can register activities
    settings.dvr.case_events_register_activities = True
    # Exclude FOOD and SURPLUS-MEALS events from event registration
    settings.dvr.event_registration_exclude_codes = ("FOOD*",)

    # Use date+time (start/end) in appointments
    settings.dvr.appointments_use_time = True
    # Use org-specific appointment types
    settings.dvr.appointment_types_org_specific = True
    # Appointments can be marked as mandatory
    settings.dvr.mandatory_appointments = False
    # Appointments update last-seen-on when completed
    settings.dvr.appointments_update_last_seen_on = True
    # Appointments update case status when completed
    settings.dvr.appointments_update_case_status = True

    # Register vulnerabilities in case files
    settings.dvr.vulnerabilities = True

    # Which subject type to use for case activities (subject|need|both)
    settings.dvr.case_activity_subject_type = "need"
    # Allow marking case activities as emergencies
    settings.dvr.case_activity_emergency = True
    # Disable recording of free-text need details
    #settings.dvr.case_activity_need_details = False
    # Enable/disable linking of case activities to relevant vulnerabilities
    settings.dvr.case_activity_vulnerabilities = False
    # Enable/disable free-text response details
    #settings.dvr.case_activity_response_details = True
    # Disable case activity inline updates
    #settings.dvr.case_activity_updates = False
    # Enable/disable recording of free-text case activity outcome
    #settings.dvr.case_activity_outcome = True
    # Enable/disable recording of improvement level in case activities
    settings.dvr.case_activity_achievement = False
    # Disable follow-up fields in case activities
    settings.dvr.case_activity_follow_up = False
    # Allow uploading of documents in individual case activities
    settings.dvr.case_activity_documents = True

    # Manage individual response actions in case activities
    settings.dvr.manage_response_actions = True
    # Responses use date+time
    settings.dvr.response_use_time = True
    # Response planning uses separate due-date
    settings.dvr.response_due_date = False
    # Use response themes
    settings.dvr.response_themes = True
    # Document response details per theme
    settings.dvr.response_themes_details = True
    # Document response efforts per theme
    settings.dvr.response_themes_efforts = True
    # Response themes are org-specific
    settings.dvr.response_themes_org_specific = False
    # Use response types
    settings.dvr.response_types = True
    # Link response actions to vulnerabilities addressed
    #settings.dvr.response_vulnerabilities = True
    # Response types hierarchical
    settings.dvr.response_types_hierarchical = True
    # Response themes organized by sectors
    settings.dvr.response_themes_sectors = True
    # Response themes linked to needs
    settings.dvr.response_themes_needs = True
    # Auto-link responses to case activities
    settings.dvr.response_activity_autolink = True

    # Uncomment this to enable tracking of transfer origin/destination sites
    #settings.dvr.track_transfer_sites = True
    # Uncomment this to enable features to manage transferability of cases
    #settings.dvr.manage_transferability = True
    # Uncomment this to have allowance payments update last_seen_on
    #settings.dvr.payments_update_last_seen_on = True
    
    from .customise.dvr import dvr_case_activity_resource, \
                                dvr_task_resource, \
                                dvr_note_resource
                                #dvr_note_type_resource
               
                               
    settings.customise_dvr_note_resource = dvr_note_resource
    settings.customise_dvr_case_activity_resource = dvr_case_activity_resource
    settings.customise_dvr_task_resource = dvr_task_resource
    #settings.customise_dvr_note_type_resource = dvr_note_type_resource
    



    # -------------------------------------------------------------------------
    # Human Resource Module Settings
    #
    settings.hrm.teams_orgs = False
    settings.hrm.staff_departments = False
    settings.hrm.deletable = False

    from .customise.hrm import hrm_human_resource_resource, \
                               hrm_human_resource_controller

    settings.customise_hrm_human_resource_resource = hrm_human_resource_resource
    settings.customise_hrm_human_resource_controller = hrm_human_resource_controller

    # -------------------------------------------------------------------------
    # Organisations Module Settings
    #
    settings.org.branches = False
    settings.org.sector = True

    from .customise.org import org_group_controller, \
                               org_organisation_controller

    settings.customise_org_group_controller = org_group_controller
    settings.customise_org_organisation_controller = org_organisation_controller

    # -------------------------------------------------------------------------
    # Persons Module Settings
    #
    settings.pr.hide_third_gender = False
    settings.pr.separate_name_fields = 2
    settings.pr.name_format= "%(last_name)s, %(first_name)s"
    settings.pr.generate_pe_label = True

    from .customise.pr import pr_person_controller
    settings.customise_pr_person_controller = pr_person_controller

    # -------------------------------------------------------------------------
    # Requests Module Settings
    #
    settings.req.req_type = ("Stock",)
    settings.req.use_commit = False
    settings.req.recurring = False
    #--------------------------------------------------------------------------


    #-------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Supply module settings
    #
    settings.supply.generic_items = True
    settings.supply.kits = False
    settings.supply.track_pack_values = False
    settings.supply.track_pack_dimensions = False

    # -------------------------------------------------------------------------
    # Comment/uncomment modules here to disable/enable them
    # Modules menu is defined in modules/eden/menu.py
    settings.modules = OrderedDict([
        # Core modules which shouldn't be disabled
        ("default", Storage(
            name_nice = T("Home"),
            restricted = False, # Use ACLs to control access to this module
            access = None,      # All Users (inc Anonymous) can see this module in the default menu & access the controller
            module_type = None  # This item is not shown in the menu
        )),
        ("admin", Storage(
            name_nice = T("Administration"),
            #description = "Site Administration",
            restricted = True,
            access = "|1|",     # Only Administrators can see this module in the default menu & access the controller
            module_type = None  # This item is handled separately for the menu
        )),
        ("appadmin", Storage(
            name_nice = T("Administration"),
            #description = "Site Administration",
            restricted = True,
            module_type = None  # No Menu
        )),
        ("errors", Storage(
            name_nice = T("Ticket Viewer"),
            #description = "Needed for Breadcrumbs",
            restricted = False,
            module_type = None  # No Menu
        )),
        ("gis", Storage(
            name_nice = T("Map"),
            #description = "Situation Awareness & Geospatial Analysis",
            restricted = True,
            module_type = 6,     # 6th item in the menu
        )),
        ("pr", Storage(
            name_nice = T("Person Registry"),
            #description = "Central point to record details on People",
            restricted = True,
            access = "|1|",     # Only Administrators can see this module in the default menu (access to controller is possible to all still)
            module_type = 10
        )),
        ("org", Storage(
            name_nice = T("Organizations"),
            #description = 'Lists "who is doing what & where". Allows relief agencies to coordinate their activities',
            restricted = True,
            module_type = 1
        )),
        ("hrm", Storage(
            name_nice = T("Staff"),
            #description = "Human Resources Management",
            restricted = True,
            module_type = 2,
        )),
        #("vol", Storage(
        #   name_nice = T("Volunteers"),
        #   #description = "Human Resources Management",
        #   restricted = True,
        #   module_type = 2,
        #)),
        ("cms", Storage(
            name_nice = T("Content Management"),
            #description = "Content Management System",
            restricted = True,
            module_type = 10,
        )),
        ("doc", Storage(
            name_nice = T("Documents"),
            #description = "A library of digital resources, such as photos, documents and reports",
            restricted = True,
            module_type = 10,
        )),
        #("msg", Storage(
        #   name_nice = T("Messaging"),
        #   #description = "Sends & Receives Alerts via Email & SMS",
        #   restricted = True,
        #   # The user-visible functionality of this module isn't normally required. Rather it's main purpose is to be accessed from other modules.
        #   module_type = None,
        #)),
        ("supply", Storage(
            name_nice = T("Supply Chain Management"),
            #description = "Used within Inventory Management, Request Management and Asset Management",
            restricted = True,
            module_type = None, # Not displayed
        )),
        #("inv", Storage(
        #   name_nice = T("Warehouses"),
        #   #description = "Receiving and Sending Items",
        #   restricted = True,
        #   module_type = 4
        #)),
        ("asset", Storage(
            name_nice = T("Assets"),
            #description = "Recording and Assigning Assets",
            restricted = True,
            module_type = 5,
        )),
        ("req", Storage(
            name_nice = T("Requests"),
            #description = "Manage requests for supplies, assets, staff or other resources. Matches against Inventories where supplies are requested.",
            restricted = True,
            module_type = 10,
        )),
        ("act", Storage(
            name_nice = T("Activities"),
            #description = "Management of Organization Activities",
            restricted = True,
            module_type = 10,
        )),
        #("project", Storage(
        #   name_nice = T("Projects"),
        #   #description = "Tracking of Projects, Activities and Tasks",
        #   restricted = True,
        #   module_type = 2
        #)),
        #("cr", Storage(
        #    name_nice = T("Shelters"),
        #    #description = "Tracks the location, capacity and breakdown of victims in Shelters",
        #    restricted = True,
        #    module_type = 10
        #)),
        ("dvr", Storage(
            name_nice = T("Beneficiaries"),
            restricted = True,
            module_type = 10,
        )),
        #("event", Storage(
        #   name_nice = T("Events"),
        #   #description = "Activate Events (e.g. from Scenario templates) for allocation of appropriate Resources (Human, Assets & Facilities).",
        #   restricted = True,
        #   module_type = 10,
        #)),
        #("security", Storage(
        #    name_nice = T("Security"),
        #    restricted = True,
        #    module_type = 10,
        #)),
        ("stats", Storage(
            name_nice = T("Statistics"),
            #description = "Manages statistics",
            restricted = True,
            module_type = None,
        )),
    ])

# END =========================================================================
