"""
    PROJECT module customisations for RLPPTM

    License: MIT
"""

from gluon import current

# -------------------------------------------------------------------------
def project_project_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    # Expose code field
    table = s3db.project_project
    field = table.code
    field.readable = field.writable = True

    # Tags as filtered components (for embedding in form)
    s3db.add_components("project_project",
                        project_project_tag = ({"name": "apply",
                                                "joinby": "project_id",
                                                "filterby": {"tag": "APPLY"},
                                                "multiple": False,
                                                },
                                               {"name": "stats",
                                                "joinby": "project_id",
                                                "filterby": {"tag": "STATS"},
                                                "multiple": False,
                                                },
                                               ),
                        )

    from core import CustomForm, \
                     TextFilter, \
                     OptionsFilter

    # Custom CRUD Form
    crud_fields = ["organisation_id",
                   "name",
                   (T("Code"), "code"),
                   "description",
                   (T("Provider Self-Registration"), "apply.value"),
                   (T("Test Results Statistics"), "stats.value"),
                   "comments",
                   ]

    # Custom list fields
    list_fields = ["id",
                   "organisation_id",
                   "name",
                   (T("Code"), "code"),
                   ]

    # Custom filters
    filter_widgets = [TextFilter(["name",
                                  "code",
                                  ],
                                 label = T("Search"),
                                 ),
                      OptionsFilter("organisation_id",
                                    ),
                      ]

    s3db.configure("project_project",
                   crud_form = CustomForm(*crud_fields),
                   filter_widgets = filter_widgets,
                   list_fields = list_fields,
                   )

# -------------------------------------------------------------------------
def project_project_controller(**attr):

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource

        # Configure binary tags
        from ..helpers import configure_binary_tags
        configure_binary_tags(resource, ("apply", "stats"))

        if r.component_name == "organisation":

            table = r.component.table
            field = table.amount
            field.readable = field.writable = False

            field = table.currency
            field.readable = field.writable = False

        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import rlpptm_project_rheader
    attr["rheader"] = rlpptm_project_rheader

    return attr

# END =========================================================================
