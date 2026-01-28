"""
    Org-specific UI Options for DRKCM

    License: MIT
"""

from gluon import current

# =============================================================================
# Default UI options
#
UI_DEFAULTS = {#"case_arrival_date_label": "Date of Entry",
               "case_collaboration": True,
               "case_document_templates": False,
               "case_header_protection_themes": False,
               "case_hide_default_org": False,
               "case_use_response_tab": True,
               "case_use_photos_tab": False,
               "case_use_bamf": False,
               "case_use_address": True,
               "case_use_appointments": False,
               "case_use_education": False,
               "case_use_flags": False,
               "case_use_tasks": True,
               "case_use_notes": False,
               "case_use_occupation": True,
               "case_use_pe_label": True,
               "case_use_place_of_birth": False,
               "case_use_residence_status": True,
               "case_use_referral": True,
               "case_use_service_contacts": False,
               "case_use_vulnerabilities": False,
               "case_lodging": "site", # "site"|"text"|None
               "case_lodging_dates": True,
               "case_nationality_mandatory": False,
               "case_show_total_consultations": True,

               "activity_use_sector": False,
               "activity_subject_type": "both",
               "activity_need_details": True,
               "activity_priority": False,
               "activity_pss_diagnoses": False,
               "activity_follow_up": False,
               "activity_closure": True,
               "activity_comments": True,

               "appointments_staff_link": False,
               "appointments_use_organizer": False,

               "response_types": False,
               "response_activity_autolink": False,
               "response_use_organizer": False,
               "response_use_time": False,
               "response_due_date": False,
               "response_planning": False,
               "response_effort_required": True,
               "response_use_theme": False,
               "response_themes_optional": False,
               "response_themes_sectors": False,
               "response_themes_needs": False,
               "response_themes_details": False,
               "response_themes_efforts": False,
               "response_tab_need_filter": False,
               "response_performance_indicators": None, # default
               }

# =============================================================================
# Custom options sets
#
UI_OPTIONS = {"LEA": {"case_arrival_date_label": "Date of AKN",
                      "case_collaboration": True,
                      "case_document_templates": True,
                      "case_header_protection_themes": True,
                      "case_hide_default_org": True,
                      "case_use_response_tab": True,
                      "case_use_photos_tab": True,
                      "case_use_bamf": True,
                      "case_use_address": False,
                      "case_use_appointments": False,
                      "case_use_education": True,
                      "case_use_flags": False,
                      "case_use_tasks": False,
                      "case_use_notes": False,
                      "case_use_occupation": False,
                      "case_use_pe_label": True,
                      "case_use_place_of_birth": True,
                      "case_use_residence_status": False,
                      "case_use_referral": False,
                      "case_use_service_contacts": False,
                      "case_use_vulnerabilities": True,
                      "case_lodging": "site",
                      "case_lodging_dates": False,
                      "case_nationality_mandatory": True,
                      "case_show_total_consultations": False,

                      "activity_use_sector": False,
                      "activity_subject_type": "need",
                      "activity_need_details": False,
                      "activity_priority": False,
                      "activity_pss_diagnoses": False,
                      "activity_follow_up": False,
                      "activity_closure": False,
                      "activity_comments": False,

                      "appointments_staff_link": True,
                      "appointments_use_organizer": True,

                      "response_types": True,
                      "response_activity_autolink": True,
                      "response_use_organizer": True,
                      "response_use_time": True,
                      "response_due_date": False,
                      "response_planning": False,
                      "response_effort_required": True,
                      "response_use_theme": True,
                      "response_themes_optional": True,
                      "response_themes_sectors": True,
                      "response_themes_needs": True,
                      "response_themes_details": True,
                      "response_themes_efforts": True,
                      "response_tab_need_filter": True,
                      "response_performance_indicators": ("bamf", "rp"),
                      },
              }

# =============================================================================
# Option sets per Org
#
UI_TYPES = {"LEA Ellwangen": "LEA",
            "Ankunftszentrum Heidelberg": "LEA",
            "eva Heidenheim gGmbH": "LEA",
            }

# =============================================================================
# Getters
#
def get_ui_options():
    """ Get the UI options for the current user's root organisation """

    ui_options = dict(UI_DEFAULTS)
    ui_type = UI_TYPES.get(current.auth.root_org_name())
    if ui_type:
        ui_options.update(UI_OPTIONS[ui_type])
    return ui_options

def get_ui_option(key):
    """ Getter for UI options, for lazy deployment settings """

    def getter(default=None):
        return get_ui_options().get(key, default)
    return getter

# END =========================================================================
