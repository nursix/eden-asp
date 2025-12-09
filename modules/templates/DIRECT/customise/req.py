"""
    REQ module customisations for DIRECT

    License: MIT
"""

from gluon import current

from core import LocationSelector

# =============================================================================
def req_need_resource(r, tablename):

    pass

# -----------------------------------------------------------------------------
def req_need_controller(**attr):

    T = current.T
    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        if not r.component:
            from core import CustomForm

            table = resource.table
            field = table.contact_organisation_id
            field.readable = field.writable = True

            # field = table.location_id
            # field.widget = LocationSelector(levels = ("L1", "L2", "L3"),
            #                         required_levels = ("L1", "L2"),
            #                         show_address = True,
            #                         show_postcode = False,
            #                         address_required = False,
            #                         postcode_required = False,
            #                         show_map = True,
            #                         points = True
            #                         )

            crud_fields = [# --- Contact ---
                           "contact_organisation_id",
                           "contact_name",
                           "contact_phone",

                           # --- Location ---
                           "location_id",

                           # --- Situation ---
                           "refno",
                           "date",
                           "name",
                           "description",

                           # --- Response Management ---
                           "organisation_id",
                           "priority",
                           "status",

                           "comments",
                           ]

            subheadings = {"author_organisation_id": T("Contact"),
                           "location_id": T("Location"),
                           "date": T("Situation"),
                           "organisation_id": T("Response Management"),
                           }

            list_fields = ["date",
                           "priority",
                           "refno",
                           "location_id",
                           "name",
                           "contact_organisation_id",
                           "contact_name",
                           "contact_phone",
                           "status",
                           "comments",
                           ]

            resource.configure(crud_form = CustomForm(*crud_fields),
                               subheadings = subheadings,
                               list_fields = list_fields,
                               )

        return result
    s3.prep = prep

    from ..rheaders import req_rheader
    attr["rheader"] = req_rheader

    return attr

# END =========================================================================
