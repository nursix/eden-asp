"""
    DRKCM: Case Management, German Red Cross

    License: MIT
"""

from collections import OrderedDict

from gluon import current
from gluon.storage import Storage

from .helpers import user_mailmerge_fields
from .uioptions import get_ui_option

# =============================================================================
def config(settings):

    T = current.T

    settings.base.system_name = "RefuScope"
    settings.base.system_name_short = "RefuScope"

    # PrePopulate data
    settings.base.prepopulate.append("DRKCM")
    settings.base.prepopulate_demo.append("DRKCM/Demo")

    # Theme (folder to use for views/layout.html)
    settings.base.theme = "DRK"
    settings.base.theme_layouts = "DRKCM"
    settings.base.theme_config = "DRKCM"

    # Custom models/controllers
    settings.base.models = "templates.DRKCM.models"
    settings.base.rest_controllers = {("dvr", "diagnosis"): ("dvr", "diagnosis"),
                                      }

    # Authentication settings
    # Should users be allowed to register themselves?
    settings.security.self_registration = False
    # Do new users need to verify their email address?
    #settings.auth.registration_requires_verification = True
    # Do new users need to be approved by an administrator prior to being able to login?
    #settings.auth.registration_requires_approval = True
    # Disable welcome-emails to newly registered users
    settings.auth.registration_welcome_email = False

    # Request Organisation during user registration
    settings.auth.registration_requests_organisation = True
    # Suppress popup-link for creating organisations during user registration
    settings.auth.registration_organisation_link_create = False

    settings.auth.registration_link_user_to = {"staff": T("Staff"),
                                               #"volunteer": T("Volunteer"),
                                               }
    # Don't show alternatives, just default
    settings.auth.registration_link_user_to_default = ["staff"]

    # Assign all new users the STAFF role for their default realm
    settings.auth.registration_roles = {None: ("STAFF",)}

    # Disable password-retrieval feature
    settings.auth.password_retrieval = False

    # Define which entity types to use as realm entities in role manager
    settings.auth.realm_entity_types = ("org_organisation",)

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
       ("de", "German"),
       ("en", "English"),
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

    # Do not require international phone number format
    settings.msg.require_international_phone_numbers = False

    # Security Policy
    # http://eden.sahanafoundation.org/wiki/S3AAA#System-widePolicy
    # 1: Simple (default): Global as Reader, Authenticated as Editor
    # 2: Editor role required for Update/Delete, unless record owned by session
    # 3: Apply Controller ACLs
    # 4: Apply both Controller & Function ACLs
    # 5: Apply Controller, Function & Table ACLs
    # 6: Apply Controller, Function, Table ACLs and Entity Realm
    # 7: Apply Controller, Function, Table ACLs and Entity Realm + Hierarchy
    settings.security.policy = 7 # Hierarchical Realms

    # Version details on About-page require login
    settings.security.version_info_requires_login = True

    # -------------------------------------------------------------------------
    # General UI settings
    #
    settings.ui.calendar_clear_icon = True

    settings.ui.auto_open_update = False
    #settings.ui.inline_cancel_edit = "submit"

    #settings.ui.organizer_snap_duration = "00:10:00"

    settings.ui.custom_icons = {"eraser": "fa-remove",
                                "file-pdf": "fa-file-pdf-o",
                                "file-doc": "fa-file-word-o",
                                "file-xls": "fa-file-excel-o",
                                "file-text": "fa-file-text-o",
                                "file-image": "fa-file-image-o",
                                "file-generic": "fa-file-o",
                                "_base": "fa",
                                }

    # -------------------------------------------------------------------------
    # Auth settings
    #
    from .customise.auth import drk_realm_entity

    settings.auth.realm_entity = drk_realm_entity

    # -------------------------------------------------------------------------
    # CMS Module Settings
    #
    settings.cms.hide_index = True

    # -------------------------------------------------------------------------
    # Shelter Registry Settings
    #
    settings.cr.shelter_registration = False

    from .customise.cr import cr_shelter_resource, \
                              cr_shelter_controller

    settings.customise_cr_shelter_resource = cr_shelter_resource
    settings.customise_cr_shelter_controller = cr_shelter_controller

    # -------------------------------------------------------------------------
    # Document settings
    #
    settings.doc.mailmerge_fields = {"ID": "pe_label",
                                     "Vorname": "first_name",
                                     "Name": "last_name",
                                     "Geburtsdatum": "date_of_birth",
                                     "Geburtsort": "pr_person_details.place_of_birth",
                                     "Adresse": "dvr_case.site_id$location_id$addr_street",
                                     "PLZ": "dvr_case.site_id$location_id$addr_postcode",
                                     "Wohnort": "dvr_case.site_id$location_id$L3",
                                     "Land": "pr_person_details.nationality",
                                     "Registrierungsdatum": "case_details.arrival_date",
                                     "AKN-Datum": "case_details.arrival_date",
                                     "Falldatum": "dvr_case.date",
                                     "BAMF-Az": "bamf.value",
                                     "Benutzername": "current_user.name",
                                     "Berater": user_mailmerge_fields,
                                     }

    from .customise.doc import doc_document_resource, \
                               doc_document_controller

    settings.customise_doc_document_controller = doc_document_controller
    settings.customise_doc_document_resource = doc_document_resource

    # -------------------------------------------------------------------------
    # DVR Settings
    #
    # Enable features to manage case flags
    settings.dvr.case_flags = True
    # Beneficiary documents-tab includes case activity attachments
    settings.dvr.case_include_activity_docs = True
    # Beneficiary documents-tab includes case group attachments
    settings.dvr.case_include_group_docs = True

    # Enable household size in cases, "auto" for automatic counting
    settings.dvr.household_size = "auto"

    # Manage vulnerabilities
    settings.dvr.vulnerabilities = get_ui_option("case_use_vulnerabilities")

    # Case activity subject type
    settings.dvr.case_activity_subject_type = get_ui_option("activity_subject_type")
    # Group/Case activities per sector
    settings.dvr.case_activity_sectors = True
    # Do not link case activities to individual vulnerabilities
    settings.dvr.case_activity_vulnerabilities = False
    # Case activities use follow-up fields
    settings.dvr.case_activity_follow_up = get_ui_option("activity_follow_up")
    # Case activities use status
    settings.dvr.case_activity_status = get_ui_option("activity_closure")
    # Do not documents achievement level per case activity
    settings.dvr.case_activity_achievement = False
    # Allow upload if documents to case activities
    settings.dvr.case_activity_documents = True
    # Use additional comments field in case activities
    settings.dvr.case_activity_comments = get_ui_option("activity_comments")

    # Manage individual response actions in case activities
    settings.dvr.manage_response_actions = True
    # Use response types
    settings.dvr.response_types = get_ui_option("response_types")
    # Response types hierarchical
    settings.dvr.response_types_hierarchical = True
    # Planning response actions, or just documenting them?
    settings.dvr.response_planning = get_ui_option("response_planning")
    # Responses use date+time
    settings.dvr.response_use_time = get_ui_option("response_use_time")
    # Response planning uses separate due-date
    settings.dvr.response_due_date = get_ui_option("response_due_date")
    # Use response themes
    settings.dvr.response_themes = get_ui_option("response_use_theme")
    # Response themes are org-specific
    settings.dvr.response_themes_org_specific = True
    # Response themes organized by sectors
    settings.dvr.response_themes_sectors = get_ui_option("response_themes_sectors")
    # Response themes linked to needs
    settings.dvr.response_themes_needs = get_ui_option("response_themes_needs")
    # Document response details per theme
    settings.dvr.response_themes_details = get_ui_option("response_themes_details")
    # Document response efforts per theme
    settings.dvr.response_themes_efforts = get_ui_option("response_themes_efforts")
    # Link response actions to vulnerabilities
    settings.dvr.response_vulnerabilities = get_ui_option("case_use_vulnerabilities")
    # Auto-link responses to case activities
    settings.dvr.response_activity_autolink = get_ui_option("response_activity_autolink")

    # Expose flags to mark appointment types as mandatory
    settings.dvr.mandatory_appointments = False
    # Appointments with personal presence update last_seen_on
    settings.dvr.appointments_update_last_seen_on = False
    # Automatically update the case status when appointments are completed
    settings.dvr.appointments_update_case_status = True
    # Automatically close appointments when registering certain case events
    settings.dvr.case_events_close_appointments = True

    # Allowance payments update last_seen_on
    #settings.dvr.payments_update_last_seen_on = True

    # Configure a regular expression pattern for ID Codes (QR Codes)
    #settings.dvr.id_code_pattern = "(?P<label>[^,]*),(?P<family>[^,]*),(?P<last_name>[^,]*),(?P<first_name>[^,]*),(?P<date_of_birth>[^,]*),.*"
    # Issue a "not checked-in" warning in case event registration
    #settings.dvr.event_registration_checkin_warning = True

    from .customise.dvr import dvr_home, \
                               dvr_case_resource, \
                               dvr_note_resource, \
                               dvr_case_activity_resource, \
                               dvr_case_activity_controller, \
                               dvr_case_appointment_resource, \
                               dvr_case_appointment_controller, \
                               dvr_case_flag_resource, \
                               dvr_need_resource, \
                               dvr_response_action_resource, \
                               dvr_response_action_controller, \
                               dvr_response_theme_resource, \
                               dvr_response_type_resource, \
                               dvr_service_contact_resource, \
                               dvr_vulnerability_resource

    settings.customise_dvr_home = dvr_home
    settings.customise_dvr_need_resource = dvr_need_resource

    settings.customise_dvr_case_resource = dvr_case_resource
    settings.customise_dvr_case_flag_resource = dvr_case_flag_resource

    settings.customise_dvr_case_activity_resource = dvr_case_activity_resource
    settings.customise_dvr_case_activity_controller = dvr_case_activity_controller

    settings.customise_dvr_case_appointment_resource = dvr_case_appointment_resource
    settings.customise_dvr_case_appointment_controller = dvr_case_appointment_controller

    settings.customise_dvr_note_resource = dvr_note_resource

    settings.customise_dvr_response_action_resource = dvr_response_action_resource
    settings.customise_dvr_response_action_controller = dvr_response_action_controller
    settings.customise_dvr_response_theme_resource = dvr_response_theme_resource
    settings.customise_dvr_response_type_resource = dvr_response_type_resource

    settings.customise_dvr_service_contact_resource = dvr_service_contact_resource

    settings.customise_dvr_vulnerability_resource = dvr_vulnerability_resource

    # -------------------------------------------------------------------------
    # Human Resource Module Settings
    #
    settings.hrm.teams_orgs = True
    settings.hrm.staff_departments = False

    settings.hrm.use_id = False
    settings.hrm.use_address = True
    settings.hrm.use_description = False

    settings.hrm.use_trainings = False
    settings.hrm.use_certificates = False
    settings.hrm.use_credentials = False
    settings.hrm.use_awards = False

    settings.hrm.use_skills = False
    settings.hrm.staff_experience = False
    settings.hrm.vol_experience = False

    # -------------------------------------------------------------------------
    # Organisations Module Settings
    #
    settings.org.sector = True
    # But hide it from the rheader
    settings.org.sector_rheader = False
    settings.org.branches = True
    settings.org.offices_tab = False
    settings.org.country = False

    from .customise.org import org_organisation_controller, \
                               org_site_check, \
                               org_facility_resource, \
                               org_facility_controller

    settings.customise_org_organisation_controller = org_organisation_controller
    settings.org.site_check = org_site_check
    settings.customise_org_facility_resource = org_facility_resource
    settings.customise_org_facility_controller = org_facility_controller

    # -------------------------------------------------------------------------
    # Persons Module Settings
    #
    settings.pr.hide_third_gender = False
    settings.pr.separate_name_fields = 2
    settings.pr.name_format= "%(last_name)s, %(first_name)s"

    settings.pr.contacts_tabs = {"all": "Contact Info"}

    from .customise.pr import pr_address_resource, \
                              pr_contact_resource, \
                              pr_person_resource, \
                              pr_person_controller, \
                              pr_group_controller, \
                              pr_group_membership_controller

    settings.customise_pr_address_resource = pr_address_resource
    settings.customise_pr_contact_resource = pr_contact_resource
    settings.customise_pr_person_resource = pr_person_resource
    settings.customise_pr_person_controller = pr_person_controller
    settings.customise_pr_group_controller = pr_group_controller
    settings.customise_pr_group_membership_controller = pr_group_membership_controller

    # -------------------------------------------------------------------------
    # Project Module Settings
    #
    settings.project.mode_task = True
    settings.project.projects = False
    settings.project.sectors = False

    # NB should not add or remove options, but just comment/uncomment
    settings.project.task_status_opts = {#1: T("Draft"),
                                         2: T("New"),
                                         3: T("Assigned"),
                                         #4: T("Feedback"),
                                         #5: T("Blocked"),
                                         6: T("On Hold"),
                                         7: T("Canceled"),
                                         #8: T("Duplicate"),
                                         #9: T("Ready"),
                                         #10: T("Verified"),
                                         #11: T("Reopened"),
                                         12: T("Completed"),
                                         }

    settings.project.task_time = False
    settings.project.my_tasks_include_team_tasks = True

    from .customise.project import project_task_resource

    #settings.customise_project_home = project_home
    settings.customise_project_task_resource = project_task_resource

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
        #("sync", Storage(
        #    name_nice = T("Synchronization"),
        #    #description = "Synchronization",
        #    restricted = True,
        #    access = "|1|",     # Only Administrators can see this module in the default menu & access the controller
        #    module_type = None  # This item is handled separately for the menu
        #)),
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
        ("msg", Storage(
          name_nice = T("Messaging"),
          #description = "Sends & Receives Alerts via Email & SMS",
          restricted = True,
          # The user-visible functionality of this module isn't normally required. Rather it's main purpose is to be accessed from other modules.
          module_type = None,
        )),
        ("project", Storage(
           name_nice = T("Projects"),
           #description = "Tracking of Projects, Activities and Tasks",
           restricted = True,
           module_type = 2
        )),
        ("cr", Storage(
            name_nice = T("Shelters"),
            #description = "Tracks the location, capacity and breakdown of victims in Shelters",
            restricted = True,
            module_type = 10
        )),
        ("dvr", Storage(
          name_nice = T("Case Management"),
          #description = "Allow affected individuals & households to register to receive compensation and distributions",
          restricted = True,
          module_type = 10,
        )),
        ("stats", Storage(
           name_nice = T("Statistics"),
           #description = "Manages statistics",
           restricted = True,
           module_type = None,
        )),
    ])

# END =========================================================================
