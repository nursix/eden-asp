"""
    ORG module customisations for GIMS

    License: MIT
"""

from gluon import current

from ..helpers import restrict_data_formats

# -------------------------------------------------------------------------
def add_org_tags():
    """
        Adds organisation tags as filtered components,
        for embedding in form, filtering and as report axis
    """

    s3db = current.s3db

    s3db.add_components("org_organisation",
                        org_organisation_tag = ({"name": "district_id",
                                                 "joinby": "organisation_id",
                                                 "filterby": {"tag": "DistrictID"},
                                                 "multiple": False,
                                                 },
                                                ),
                        )

# -------------------------------------------------------------------------
def org_organisation_resource(r, tablename):

    # Add organisation tags
    add_org_tags()

# -------------------------------------------------------------------------
def org_organisation_controller(**attr):

    T = current.T
    settings = current.deployment_settings
    s3 = current.response.s3

    # Enable bigtable features
    settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        auth = current.auth
        s3db = current.s3db

        resource = r.resource
        record = r.record

        is_org_group_admin = auth.s3_has_role("ORG_GROUP_ADMIN")

        # Add invite-method for ORG_GROUP_ADMIN role
        from templates.RLPPTM.helpers import InviteUserOrg
        s3db.set_method("org_organisation",
                        method = "invite",
                        action = InviteUserOrg,
                        )

        mine = False
        if not is_org_group_admin:

            if r.get_vars.get("mine") == "1":
                mine = True
                # Filter to those the user can update
                aquery = current.auth.s3_accessible_query("update", "org_organisation")
                if aquery:
                    resource.add_filter(aquery)

            # Restrict data formats
            restrict_data_formats(r)

        if not r.component:
            from core import CustomForm, \
                             InlineComponent, \
                             InlineLink, \
                             OptionsFilter, \
                             TextFilter, \
                             get_filter_options

            # Custom form
            if is_org_group_admin:
                user = auth.user
                if record and user:
                    # Only OrgGroupAdmins managing this organisation can change
                    # its org group membership (=organisation must be within realm):
                    realm = user.realms.get(auth.get_system_roles().ORG_GROUP_ADMIN)
                    groups_readonly = realm is not None and record.pe_id not in realm
                else:
                    groups_readonly = False

                # Show organisation types
                types = InlineLink("organisation_type",
                                   field = "organisation_type_id",
                                   search = False,
                                   label = T("Type"),
                                   multiple = settings.get_org_organisation_types_multiple(),
                                   widget = "multiselect",
                                   )
                # Show org groups and projects
                groups = InlineLink("group",
                                    field = "group_id",
                                    label = T("Organization Group"),
                                    multiple = False,
                                    readonly = groups_readonly,
                                    )

            else:
                types = groups = None

            if auth.s3_has_role("ADMIN"):
                # Show district ID
                component = resource.components["district_id"]
                ctable = component.table
                field = ctable.value
                field.label = T("District ID")
                field.writable = auth.s3_has_role("ADMIN")
                district_id = "district_id.value"
            else:
                district_id = None

            crud_fields = [# ---- Organisation ----
                           "name",
                           "acronym",
                           types,
                           groups,
                           district_id,
                           "logo",
                           # ---- Contact Information ----
                           InlineComponent(
                                "contact",
                                fields = [("", "value")],
                                filterby = {"field": "contact_method",
                                            "options": "EMAIL",
                                            },
                                label = T("Email"),
                                multiple = False,
                                name = "email",
                                ),
                           "phone",
                           "website",
                           # ---- Comments ----
                           "comments",
                           ]
            subheadings = {"name": T("Organization"),
                           "emailcontact": T("Contact Information"),
                           "comments": T("Comments"),
                           }
            # Filters
            text_fields = ["name",
                           "acronym",
                           "website",
                           "phone",
                           ]
            if is_org_group_admin:
                text_fields.extend(["email.value",
                                    "district_id.value",
                                    ])
            if not mine:
                text_fields.extend(["office.location_id$L3",
                                    "office.location_id$L1",
                                    ])
            filter_widgets = [TextFilter(
                                    text_fields,
                                    label = T("Search"),
                                    ),
                              OptionsFilter(
                                    "organisation_type__link.organisation_type_id",
                                    label = T("Type"),
                                    options = lambda: get_filter_options("org_organisation_type"),
                                    ),
                              ]
            if is_org_group_admin:
                filter_widgets.extend([
                    OptionsFilter(
                        "group__link.group_id",
                        label = T("Group"),
                        options = lambda: get_filter_options("org_group"),
                        ),
                    ])

            # Custom list fields
            if is_org_group_admin:
                list_fields = ["name",
                               "organisation_type__link.organisation_type_id",
                               (T("Organization Group"), "group__link.group_id"),
                               district_id,
                               "office.location_id$L3",
                               "office.location_id$L1",
                               "website",
                               "phone",
                               (T("Email"), "email.value"),
                               ]
            elif not mine:
                list_fields = ["name",
                               "organisation_type__link.organisation_type_id",
                               "office.location_id$L3",
                               "office.location_id$L1",
                               "website",
                               "phone",
                               ]
            else:
                list_fields = ["name",
                               "website",
                               "phone",
                               (T("Email"), "email.value"),
                               ]

            resource.configure(crud_form = CustomForm(*crud_fields),
                               filter_widgets = filter_widgets,
                               list_fields = list_fields,
                               subheadings = subheadings,
                               )

        elif r.component_name == "office":

            ctable = r.component.table

            field = ctable.phone1
            field.label = T("Phone #")

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import org_rheader
    attr["rheader"] = org_rheader

    return attr

# END =========================================================================
