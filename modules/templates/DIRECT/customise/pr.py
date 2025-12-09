"""
    PR module customisations for DIRECT

    License: MIT
"""

from gluon import current, IS_NOT_EMPTY

from core import CustomForm, InlineComponent, InlineLink, StringTemplateParser

# -----------------------------------------------------------------------------
def pr_group_controller(**attr):

    s3 = current.response.s3

    T = current.T

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.controller == "hrm":
            # Teams
            crud_form = CustomForm("name",
                                   "description",
                                   # TODO limit to organisations the user can
                                   #      create teams for (using helpers/permitted_orgs)
                                   InlineComponent("organisation_team",
                                                   label = T("Organization"),
                                                   fields = [("", "organisation_id")],
                                                   multiple = False,
                                                   ),
                                   InlineLink("service",
                                              field = "service_id",
                                              label = T("Capabilities"),
                                              ),
                                   # TODO contact name
                                   # TODO contact phone#
                                   "comments",
                                   )
            r.resource.configure(crud_form=crud_form)

        return result
    s3.prep = prep

    # TODO Custom rheader exposing status, needs assignments and deployments (hrm/group only)

    return attr

# -----------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    s3db = current.s3db

    # Configure components to inherit realm_entity from person
    s3db.configure("pr_person",
                    realm_components = ("person_details",
                                        "contact",
                                        "address",
                                        ),
                    )

# -----------------------------------------------------------------------------
def pr_person_controller(**attr):

    s3 = current.response.s3
    settings = current.deployment_settings

    T = current.T

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Determine order of name fields
        NAMES = ("first_name", "middle_name", "last_name")
        keys = StringTemplateParser.keys(settings.get_pr_name_format())
        name_fields = [fn for fn in keys if fn in NAMES]

        controller = r.controller
        if controller in ("default", "hrm") and not r.component:
            # Personal profile (default/person) or staff
            resource = r.resource

            # Last name is required
            table = resource.table
            table.last_name.requires = IS_NOT_EMPTY()

            # Make place of birth accessible
            details = resource.components.get("person_details")
            if details:
                field = details.table.place_of_birth
                field.readable = field.writable = True

            # Custom Form
            crud_fields = name_fields + ["date_of_birth",
                                         "person_details.place_of_birth",
                                         "gender",
                                         ]

            r.resource.configure(crud_form = CustomForm(*crud_fields),
                                 deletable = False,
                                 )

        if r.component_name == "address":
            ctable = r.component.table

            # Configure location selector and geocoder
            from core import LocationSelector
            field = ctable.location_id
            field.widget = LocationSelector(levels = ("L1", "L2"),
                                            required_levels = ("L1", "L2"),
                                            show_address = True,
                                            show_postcode = True,
                                            show_map = True,
                                            )

        elif r.component_name == "human_resource":

            phone_label = settings.get_ui_label_mobile_phone()
            r.component.configure(list_fields= ["job_title_id",
                                                "site_id",
                                                (T("Email"), "person_id$email.value"),
                                                (phone_label, "person_id$phone.value"),
                                                "status",
                                                ],
                                  deletable = False,
                                  )
            s3.crud_strings["hrm_human_resource"]["label_list_button"] = T("List Staff Records")

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import profile_rheader, hr_rheader
    controller = current.request.controller
    if controller == "default":
        attr["rheader"] = profile_rheader
    elif controller == "hrm":
        attr["rheader"] = hr_rheader

    return attr

# END =========================================================================
