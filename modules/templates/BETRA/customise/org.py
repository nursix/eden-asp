"""
    ORG module customisations for BETRA

    License: MIT
"""

from gluon import current

# -------------------------------------------------------------------------
def org_group_controller(**attr):

    s3 = current.response.s3

    standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource

        # Cannot create new groups unless Admin or site-wide OrgGroupAdmin
        from ..helpers import get_role_realms
        if not current.auth.s3_has_role("ADMIN") and \
           get_role_realms("ORG_GROUP_ADMIN") is not None:
            resource.configure(insertable = False)

        if r.interactive:
            if not r.component:
                from core import CustomForm
                crud_form = CustomForm("name", "comments")
                resource.configure(crud_form = crud_form)
            elif r.component_name == "organisation":
                r.component.configure(insertable = False,
                                      editable = False,
                                      deletable = False,
                                      )

        list_fields = ["name", "comments"]
        resource.configure(list_fields = list_fields)

        # TODO filter form
        # TODO CRUD string translations

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import org_rheader
    attr["rheader"] = org_rheader

    return attr

# -------------------------------------------------------------------------
def org_organisation_filter_widgets(is_org_group_admin=False):
    """
        Determine filter widgets for organisations view

        Args:
            is_org_group_admin: user is ORG_GROUP_ADMIN

        Returns:
            list of filter widgets
    """

    from core import OptionsFilter, TextFilter, get_filter_options

    T = current.T

    text_fields = ["name", "acronym", "email.value"]
    filter_widgets = [TextFilter(
                        text_fields,
                        label = T("Search"),
                        ),
                      OptionsFilter(
                        "organisation_type__link.organisation_type_id",
                        label = T("Type"),
                        options = lambda: get_filter_options("org_organisation_type"),
                        hidden = True,
                        ),
                      OptionsFilter(
                        "group__link.group_id",
                        label = T("Group"),
                        options = lambda: get_filter_options("org_group"),
                        hidden = True,
                        ),
                      OptionsFilter(
                        "sector__link.sector_id",
                        label = T("Sector"),
                        options = lambda: get_filter_options("org_sector"),
                        hidden = True,
                        ),
                      ]

    return filter_widgets

# -------------------------------------------------------------------------
def configure_org_components():

    s3db = current.s3db

    # Make sure default model is loaded first
    s3db.table("org_organisation")

    # Configure filtered components document/template
    s3db.add_components("org_organisation",
                        doc_document = ({"name": "document",
                                         "joinby": "organisation_id",
                                         "filterby": {"is_template": False,
                                                      "doc_id": None,
                                                      },
                                         },
                                        {"name": "template",
                                         "joinby": "organisation_id",
                                         "filterby": {"is_template": True,
                                                      "doc_id": None,
                                                      },
                                         },
                                        ),
                        )

# -------------------------------------------------------------------------
def org_organisation_controller(**attr):

    T = current.T
    auth = current.auth

    s3 = current.response.s3
    settings = current.deployment_settings

    configure_org_components()

    is_org_group_admin = auth.s3_has_role("ORG_GROUP_ADMIN")

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        record = r.record

        if not r.component:

            from core import CustomForm, \
                             InlineComponent, \
                             InlineLink

            # Show organisation type(s)
            types = InlineLink("organisation_type",
                               field = "organisation_type_id",
                               search = False,
                               label = T("Type"),
                               multiple = False,
                               widget = "multiselect",
                               readonly = not is_org_group_admin,
                               )

            # Show organisation sectors (=commission types)
            sectors = InlineLink("sector",
                                 field = "sector_id",
                                 search = False,
                                 label = T("Sectors"),
                                 widget = "multiselect",
                                 readonly = not is_org_group_admin,
                                 )

            if is_org_group_admin:

                # Show org groups
                if record:
                    groups_readonly = True
                    user = auth.user
                    if user:
                        # Only OrgGroupAdmins managing this organisation can
                        # change its group memberships
                        realm = user.realms.get(auth.get_system_roles().ORG_GROUP_ADMIN)
                        groups_readonly = realm is not None and record.pe_id not in realm
                else:
                    groups_readonly = False

                groups = InlineLink("group",
                                    field = "group_id",
                                    label = T("Organization Group"),
                                    multiple = False,
                                    readonly = groups_readonly,
                                    )

            else:

                groups = None

            crud_fields = ["name",
                           "acronym",
                           groups,
                           types,
                           sectors,
                           "phone",
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
                           "logo",
                           "comments",
                           ]

            subheadings = {"name": T("Organization"),
                           "phone": T("Contact Information"),
                           "logo": T("Other Details"),
                           }

            # Add post-process to add/update verification
            crud_form = CustomForm(*crud_fields)

            list_fields = ["name",
                           "acronym",
                           (T("Organization Group"), "group__link.group_id"),
                           (T("Type"), "organisation_type__link.organisation_type_id"),
                           (T("Sectors"), "sector__link.sector_id"),
                           (T("Email"), "email.value"),
                           ]

            # Filter widgets
            filter_widgets = org_organisation_filter_widgets(
                                   is_org_group_admin = is_org_group_admin,
                                   )

            resource.configure(crud_form = crud_form,
                               subheadings = subheadings,
                               filter_widgets = filter_widgets,
                               list_fields = list_fields,
                               )


        elif r.component_name == "human_resource":

            phone_label = settings.get_ui_label_mobile_phone()
            list_fields = ["person_id",
                           "job_title_id",
                           (T("Email"), "person_id$email.value"),
                           (phone_label, "person_id$phone.value"),
                           "status",
                           ]
            r.component.configure(list_fields = list_fields,
                                  open_read_first = True,
                                  )

        elif r.component_name in ("document", "template"):

            from .doc import doc_customise_documents
            doc_customise_documents(r, r.component.table)

        return result
    s3.prep = prep

    standard_postp = s3.postp
    def postp(r, output):

        if not auth.s3_has_permission("read", "pr_person", c="hrm", f="person"):
            if callable(standard_postp):
                output = standard_postp(r, output)

        return output
    s3.postp = postp

    # Custom rheader
    from ..rheaders import org_rheader
    attr["rheader"] = org_rheader

    if is_org_group_admin:
        # Show all records by default
        settings.ui.datatables_pagelength = -1

    return attr

# END =========================================================================
