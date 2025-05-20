"""
    PR module customisations for BETRA

    License: MIT
"""

from gluon import current

from core import CustomForm, InlineComponent

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    T = current.T
    s3db = current.s3db

    s3 = current.response.s3

    standard_prep = s3.prep
    def prep(r, **attr):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.controller == "dvr":

            resource = r.resource

            from ..helpers import permitted_orgs
            organisation_ids = permitted_orgs("create", "pr_person")

            case_table = s3db.dvr_case
            if len(organisation_ids) == 1:
                field = case_table.organisation_id
                field.default = organisation_ids[0]
                field.readable = True
                field.writable = False

            crud_form = CustomForm(
                # Case Details ----------------------------
                "dvr_case.date",
                "dvr_case.organisation_id",
                (T("Case Status"), "dvr_case.status_id"),

                # Person Details --------------------------
                (T("ID"), "pe_label"),
                "first_name",
                "last_name",
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
                "comments",
                )

            subheadings = {"dvr_case_date": T("Case Status"),
                           "pe_label": T("Person Details"),
                           "emailemail": T("Contact Information"),
                           "address": T("Address"),
                           "comments": T("Comments"),
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
