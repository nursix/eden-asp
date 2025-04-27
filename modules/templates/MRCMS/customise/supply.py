"""
    SUPPLY module customisations for MRCMS

    License: MIT
"""

from collections import OrderedDict

from gluon import current, URL

from core import CustomController, IS_ONE_OF, \
                 DateFilter, OptionsFilter, TextFilter, \
                 CustomForm, InlineLink

# -------------------------------------------------------------------------
def supply_distribution_set_controller(**attr):

    T = current.T
    db = current.db
    s3db = current.s3db

    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        if not r.component:

            # Organisation is required
            from ..helpers import permitted_orgs
            organisations = permitted_orgs("update", "supply_distribution_set")

            otable = s3db.org_organisation
            dbset = db(otable.id.belongs(organisations))

            field = table.organisation_id
            field.requires = IS_ONE_OF(dbset, "org_organisation.id",
                                       field.represent,
                                       sort = True,
                                       zero = None,
                                       )

            if len(organisations) == 1:
                field.default = organisations[0]
                field.readable = field.writable = False

                ftable = s3db.dvr_case_flag
                dbset = db(ftable.organisation_id == organisations[0])

                for alias in ("flag_required", "flag_debarring"):
                    component = resource.components.get(alias)
                    ltable = component.link.table
                    field = ltable.flag_id
                    field.requires = IS_ONE_OF(dbset, "dvr_case_flag.id",
                                               field.represent,
                                               sort=True,
                                               )
            else:
                field.default = None
                field.readable = field.writable = True

                # Multiple organisations
                # => must filter flag options dynamically (not ideal UX-wise)
                jquery_ready = s3.jquery_ready
                filter_opts = lambda alias: '''
$.filterOptionsS3({
 'trigger':'organisation_id',
 'target':{'name':'flag_id','alias':'%s','inlineType':'link'},
 'lookupPrefix':'dvr',
 'lookupResource':'case_flag',
 'showEmptyField':false
})''' % alias
                for alias in ("flag_required", "flag_debarring"):
                    script = filter_opts(alias)
                    if script not in jquery_ready:
                        jquery_ready.append(script)

            # Embed flags_required/flags_debarring in CRUD form
            crud_form = CustomForm("organisation_id",
                                   "name",
                                   "max_per_day",
                                   "min_interval",
                                   "residents_only",
                                   InlineLink("flag_required",
                                              label = T("Case Flags Required"),
                                              field = "flag_id",
                                              render_list = True,
                                              ),
                                   InlineLink("flag_debarring",
                                              label = T("Case Flags Debarring"),
                                              field = "flag_id",
                                              render_list = True,
                                              ),
                                   "active",
                                   "comments",
                                   )

            # Custom list fields
            list_fields = ["name",
                           "active",
                           "max_per_day",
                           "min_interval",
                           "residents_only",
                           "comments",
                           ]
            if table.organisation_id.readable:
                list_fields.insert(0, "organisation_id")

            resource.configure(crud_form = crud_form,
                               list_fields = list_fields,
                               )

        return result
    s3.prep = prep

    return attr

# -------------------------------------------------------------------------
def supply_distribution_resource(r, tablename):

    s3db = current.s3db

    # Read-only (except via registration UI)
    s3db.configure("supply_distribution",
                   insertable = False,
                   editable = False,
                   deletable = False,
                   )

# -------------------------------------------------------------------------
def supply_distribution_controller(**attr):

    auth = current.auth
    s3 = current.response.s3

    # Custom postp
    standard_postp = s3.postp
    def custom_postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.interactive and \
           r.method == "register":
            if isinstance(output, dict):
                if auth.permission.has_permission("read", c="supply", f="distribution_item"):
                    output["return_url"] = URL(c="supply", f="distribution_item")
                else:
                    output["return_url"] = URL(c="default", f="index")
            CustomController._view("MRCMS", "register_distribution.html")
        return output
    s3.postp = custom_postp

    return attr

# -------------------------------------------------------------------------
def supply_distribution_item_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    resource = r.resource

    table = s3db.supply_distribution_item
    field = table.item_id
    field.represent = s3db.supply_ItemRepresent(show_link=False)

    text_filter_fields = ["item_id$name"]

    # If distributions of multiple organisations accessible
    # => include organisation in list_fields and filters
    from ..helpers import permitted_orgs
    if len(permitted_orgs("read", "supply_distribution")) > 1:
        organisation_id = "distribution_id$organisation_id"
        org_filter = OptionsFilter(organisation_id, hidden=True)
    else:
        organisation_id = org_filter = None

    # If in primary distribution item controller
    # => include beneficiary in list fields and filters
    if resource.tablename == "supply_distribution_item":
        pe_label = (T("ID"), "person_id$pe_label")
        person_id = (T("Name"), "person_id")
        # Show person name as link to case file (supply perspective)
        field = table.person_id
        field.represent = s3db.pr_PersonRepresent(show_link = True,
                                                  linkto = URL(c = "supply",
                                                               f = "person",
                                                               args = ["[id]", "distribution_item"],
                                                               extension = "",
                                                               ),
                                                  )
        text_filter_fields.extend(["person_id$pe_label",
                                   "person_id$last_name",
                                   "person_id$first_name",
                                   ])
    else:
        pe_label = person_id = None

    # Filter widgets
    # - filterable by mode, distribution date and site
    try:
        filter_options = OrderedDict(table.mode.requires.options())
        filter_options.pop(None, None)
    except AttributeError:
        filter_options = None
    filter_widgets = [TextFilter(text_filter_fields,
                                 label = T("Search"),
                                 ),
                      OptionsFilter("mode",
                                    options = filter_options,
                                    cols = 4,
                                    sort = False,
                                    hidden = True,
                                    ),
                      DateFilter("distribution_id$date",
                                 hidden = True,
                                 ),
                      org_filter,
                      OptionsFilter("distribution_id$site_id",
                                    hidden = True,
                                    ),
                      ]

    # List fields
    # - include distribution date and site
    list_fields = ["distribution_id$date",
                   organisation_id,
                   "distribution_id$site_id",
                   pe_label,
                   person_id,
                   "mode",
                   "item_id",
                   "quantity",
                   "item_pack_id",
                   "distribution_id$human_resource_id",
                   ]

    # Update table configuration
    s3db.configure("supply_distribution_item",
                   filter_widgets = filter_widgets,
                   list_fields = list_fields,
                   # Read-only (except via registration UI)
                   insertable = False,
                   editable = False,
                   deletable = False,
                   )

    if resource.tablename == "supply_distribution_item":
        # Install report method
        from ..reports import GrantsTotalReport
        s3db.set_method("supply_distribution_item",
                        method = "grants_total",
                        action = GrantsTotalReport,
                        )

        # Update CRUD strings for perspective
        crud_strings = current.response.s3.crud_strings
        crud_strings["supply_distribution_item"].update({
            "title_list": T("Distributed Items"),
            "title_display": T("Distributed Item"),
            "label_list_button": T("List Distributed Items"),
            })

# -------------------------------------------------------------------------
def supply_item_resource(r, tablename):

    db = current.db
    s3db = current.s3db
    auth = current.auth

    # Filter to items linked to accessible catalogs
    # => special multi-tenancy with catalog separation (TODO make this a generic option?)
    for resource in (r.resource, r.component):
        if resource and resource.tablename == "supply_item":

            citable = s3db.supply_catalog_item
            accessible = auth.s3_accessible_query("read", citable)
            permitted_items = db(accessible)._select(citable.item_id, distinct=True)

            table = resource.table
            query = table.id.belongs(permitted_items)
            resource.add_filter(query)

            break

# -------------------------------------------------------------------------
def supply_item_controller(**attr):

    s3db = current.s3db

    s3 = current.response.s3

    # Custom postp
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        from ..helpers import permitted_orgs
        organisation_ids = permitted_orgs("read", "supply_catalog")
        if len(organisation_ids) > 1:
            # Include organisation_id in list_fields
            organisation_id = "catalog_id$organisation_id"
        else:
            organisation_id = None

        if r.interactive:
            # Add organisation filter if organisation_id is shown
            filter_widgets = r.resource.get_config("filter_widgets")
            if filter_widgets and organisation_id:
                ctable = s3db.supply_catalog
                filter_opts = ctable.organisation_id.represent.bulk(organisation_ids)
                filter_opts.pop(None, None)
                filter_widgets.append(OptionsFilter(organisation_id,
                                                    options = filter_opts,
                                                    hidden = True,
                                                    ))

        # Custom list fields
        list_fields = ["name",
                       "code",
                       "um",
                       "item_category_id",
                       "catalog_id",
                       organisation_id,
                       ]

        s3db.configure("supply_item",
                       list_fields = list_fields,
                       )

        return result
    s3.prep = prep

    return attr

# END =========================================================================
