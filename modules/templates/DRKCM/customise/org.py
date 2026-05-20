"""
    ORG module customisations for DRKCM

    License: MIT
"""

from gluon import current

from core import FS

# -------------------------------------------------------------------------
def org_organisation_controller(**attr):

    T = current.T
    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Disable creation of new root orgs unless user is ORG_GROUP_ADMIN
        if r.method != "hierarchy" and \
            (r.representation != "popup" or not r.get_vars.get("hierarchy")):
            auth = current.auth
            sysroles = sysroles = auth.get_system_roles()
            insertable = auth.s3_has_roles((sysroles.ADMIN,
                                            sysroles.ORG_GROUP_ADMIN,
                                            ))
            r.resource.configure(insertable = insertable)

        if r.component_name == "document":
            s3.crud_strings["doc_document"].label_create = T("Add Document Template")
            # Done in doc_document_resource
            #f = current.s3db.doc_document.url
            #f.readable = f.writable = False
            current.s3db.doc_document.is_template.default = True
            r.resource.add_component_filter("document", FS("is_template") == True)

        return result

    s3.prep = custom_prep

    # Customr header
    from ..rheaders import org_rheader
    attr["rheader"] = org_rheader

    return attr

# -------------------------------------------------------------------------
def org_site_check(site_id):
    """ Custom tasks for scheduled site checks """

    # Tasks which are not site-specific
    if site_id == "all":

        # Update all shelter populations
        # NB will be db.committed by org_site_check in models/tasks.py
        current.log.info("Updating all shelter populations")
        from .cr import cr_shelter_population
        cr_shelter_population()

# -------------------------------------------------------------------------
def org_facility_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    # Hide "code" field (not needed)
    table = s3db.org_facility
    field = table.code
    field.readable = field.writable = False

    # Location selector just needs country + address
    from core import LocationSelector
    field = table.location_id
    field.widget = LocationSelector(levels = ["L0"],
                                    show_address=True,
                                    show_map = False,
                                    )

    field = table.obsolete
    field.label = T("Inactive")
    field.represent = lambda opt: T("Inactive") if opt else current.messages["NONE"]

    # Custom list fields
    list_fields = ["name",
                   "site_facility_type.facility_type_id",
                   "organisation_id",
                   "location_id",
                   "contact",
                   "phone1",
                   "phone2",
                   "email",
                   #"website",
                   "obsolete",
                   "comments",
                   ]

    # Custom filter widgets
    from core import TextFilter, OptionsFilter, get_filter_options
    filter_widgets = [TextFilter(["name",
                                  "organisation_id$name",
                                  "organisation_id$acronym",
                                  "comments",
                                  ],
                                 label = T("Search"),
                                 ),
                      OptionsFilter("site_facility_type.facility_type_id",
                                    options = get_filter_options("org_facility_type",
                                                                 translate = True,
                                                                 ),
                                     ),
                      OptionsFilter("organisation_id",
                                    ),
                      OptionsFilter("obsolete",
                                    options = {False: T("No"),
                                               True: T("Yes"),
                                               },
                                    default = [False],
                                    cols = 2,
                                    )
                      ]

    s3db.configure("org_facility",
                   #deletable = False,
                   filter_widgets = filter_widgets,
                   list_fields = list_fields,
                   )

# -------------------------------------------------------------------------
def org_facility_controller(**attr):

    # Allow selection of all countries
    current.deployment_settings.gis.countries = []

    # Custom rheader+tabs
    if current.request.controller == "org":
        from ..rheaders import org_rheader
        attr["rheader"] = org_rheader

    return attr

# END =========================================================================
