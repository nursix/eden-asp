"""
    PR module customisations for BETRA

    License: MIT
"""

from gluon import current

from core import CustomForm, InlineComponent

from ..helpers import permitted_orgs

# -------------------------------------------------------------------------
def configure_case_list_fields(resource, fmt=None):

    list_fields = ["dvr_case.organisation_id",
                   # "pe_label",
                   "last_name",
                   "first_name",
                   "address.location_id$L3",
                   "grant.refno",
                   "dvr_case.date",
                   "dvr_case.status_id",
                   ]

    resource.configure(list_fields=list_fields)

# -------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    T = current.T

    table = current.s3db.pr_person

    field = table.pe_label
    field.label = T("ID")

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    T = current.T
    auth = current.auth

    s3 = current.response.s3

    standard_prep = s3.prep
    def prep(r, **attr):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.controller == "dvr":

            resource = r.resource
            table = resource.table

            cases = resource.components.get("dvr_case")
            case_table = cases.table

            # Default organisation_id if user is permitted for only one organisation
            organisation_ids = permitted_orgs("create", "pr_person")
            if len(organisation_ids) == 1:
                field = case_table.organisation_id
                field.default = organisation_ids[0]
                field.readable = True
                field.writable = False

            # Hide invalid-flag, unless the user is a coordinator
            if not auth.s3_has_role("COORDINATOR"):
                field = case_table.archived
                field.readable = field.writable = False

            # Make pe_label read-only, remove comment
            field = table.pe_label
            field.readable = False # currently unused
            field.writable = False
            field.comment = None

            # Fields for case list
            configure_case_list_fields(resource, fmt=r.representation)

            crud_form = CustomForm(
                # Case Details ----------------------------
                "dvr_case.date",
                "dvr_case.organisation_id",
                (T("Case Status"), "dvr_case.status_id"),

                # Person Details --------------------------
                # (T("ID"), "pe_label"), # currently unused
                "last_name",
                "first_name",
                "person_details.nationality",

                # Contact Information ---------------------
                InlineComponent(
                        "email",
                        fields = [("", "value")],
                        label = T("Email"),
                        multiple = False,
                        name = "email",
                        ),
                InlineComponent(
                        "phone",
                        fields = [("", "value")],
                        label = T("Mobile Phone"),
                        multiple = False,
                        name = "phone",
                        ),
                InlineComponent(
                        "address",
                        label = T("Current Address"),
                        fields = [("", "location_id")],
                        filterby = {"field": "type",
                                    "options": "1",
                                    },
                        link = False,
                        multiple = False,
                        ),

                # Administrative --------------------------
                "case_details.tc_signed",
                "comments",

                # Archived-flag ---------------------------
                (T("Invalid"), "dvr_case.archived"),
                )

            subheadings = {"dvr_case_date": T("Case Status"),
                           "last_name": T("Person Details"),
                           "emailemail": T("Contact Information"),
                           "address": T("Address"),
                           "case_details_tc_signed": T("Administrative"),
                           # "comments": T("Comments"),
                           }
            resource.configure(crud_form = crud_form,
                               subheadings = subheadings,
                               )

        return result
    s3.prep = prep

    # Custom rheader tabs
    from ..rheaders import dvr_rheader, hrm_rheader, default_rheader
    if current.request.controller == "dvr":
        attr["rheader"] = dvr_rheader
    elif current.request.controller == "hrm":
        attr["rheader"] = hrm_rheader
    elif current.request.controller == "default":
        attr["rheader"] = default_rheader

    return attr

# END =========================================================================
