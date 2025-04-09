"""
    CR module customisations for GIMS

    License: MIT
"""

from collections import OrderedDict

from gluon import current, URL, \
                  A, DIV, H4, IS_EMPTY_OR, SPAN, TABLE, TD, TR

from core import FS

from ..helpers import restrict_data_formats

# =============================================================================
def shelter_map_popup(record):
    """
        Custom map popup for shelters

        Args:
            record: the shelter record (Row)

        Returns:
            the shelter popup contents as DIV
    """

    db = current.db
    s3db = current.s3db

    T = current.T

    table = s3db.cr_shelter

    # Custom Map Popup
    title = A(H4(record.name, _class="map-popup-title"),
              _href = URL(c="cr", f="shelter", args=[record.id]),
              _title = T("Open"),
              )

    details = TABLE(_class="map-popup-details")
    append = details.append

    def formrow(label, value, represent=None):
        return TR(TD("%s:" % label, _class="map-popup-label"),
                  TD(represent(value) if represent else value),
                  )

    # Organisation
    organisation_id = record.organisation_id
    if organisation_id:
        append(formrow(table.organisation_id.label,
                       A(table.organisation_id.represent(organisation_id),
                         _href = URL("org", "organisation", args=[organisation_id]),
                         ),
                       ))

    # Address
    gtable = s3db.gis_location
    query = (gtable.id == record.location_id)
    location = db(query).select(gtable.addr_street,
                                gtable.addr_postcode,
                                gtable.L4,
                                gtable.L3,
                                limitby = (0, 1),
                                ).first()

    if location.addr_street:
        append(formrow(gtable.addr_street.label, location.addr_street))
    place = location.L4 or location.L3 or "?"
    if location.addr_postcode:
        place = "%s %s" % (location.addr_postcode, place)
    append(formrow(T("Place"), place))

    # Phone number
    phone = record.phone
    if phone:
        append(formrow(T("Phone"), phone))

    # Email address (as hyperlink)
    email = record.email
    if email:
        append(formrow(table.email.label, A(email, _href="mailto:%s" % email)))

    # Capacity / available capacity
    capacity = record.capacity
    append(formrow(table.capacity.label, capacity))
    available_capacity = record.available_capacity
    append(formrow(table.available_capacity.label, available_capacity))

    # Status
    append(formrow(table.status.label,
                   table.status.represent(record.status),
                   ))

    # Comments
    if record.comments:
        append(formrow(table.comments.label,
                       record.comments,
                       represent = table.comments.represent,
                       ))

    return DIV(title, details, _class="map-popup")

# -------------------------------------------------------------------------
def available_capacity_represent(value, row=None):
    """ Color-coded representation of available shelter capacities """

    if value is None:
        return "-"

    if value == 0:
        css = "shelter-full"
    elif value < 4:
        css = "shelter-low"
    else:
        css = "shelter-available"

    return SPAN(value, _class=css)

# -------------------------------------------------------------------------
def cr_shelter_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.cr_shelter

    shelter_status_opts = OrderedDict(((2, T("Open##status")),
                                       (1, T("Closed")),
                                       ))

    from core import LocationFilter, \
                     OptionsFilter, \
                     RangeFilter, \
                     LocationSelector, \
                     S3PriorityRepresent, \
                     S3SQLCustomForm, \
                     S3SQLInlineComponent, \
                     S3SQLInlineLink, \
                     TextFilter, \
                     get_filter_options, \
                     s3_fieldmethod

    from ..helpers import ShelterDetails, ServiceListRepresent

    # Field methods for a more compact representation
    # of place/contact information
    table.place = s3_fieldmethod("place",
                                 ShelterDetails.place,
                                 represent = ShelterDetails.place_represent,
                                 )

    table.contact = s3_fieldmethod("contact",
                                   ShelterDetails.contact,
                                   represent = ShelterDetails.contact_represent,
                                   )

    # No add-link for organisation
    field = table.organisation_id
    field.requires = s3db.org_organisation_requires(required = True,
                                                    updateable = True,
                                                    )
    field.comment = None

    # Custom label for population_children
    field = table.population_children
    field.label = T("Current Population (Minors)")

    # Enable contact name and website fields
    field = table.contact_name
    field.readable = field.writable = True
    field = table.website
    field.readable = field.writable = True

    # Shelter type is required
    field = table.shelter_type_id
    requires = field.requires
    if isinstance(requires, IS_EMPTY_OR):
        field.requires = requires.other

    # Configure location selector
    field = table.location_id
    requires = field.requires
    if isinstance(requires, IS_EMPTY_OR):
        field.requires = requires.other
    field.widget = LocationSelector(levels = ("L1", "L2", "L3", "L4"),
                                    required_levels = ("L1", "L2", "L3"),
                                    show_address = True,
                                    show_postcode = True,
                                    show_map = True,
                                    )
    current.response.s3.scripts.append("/%s/static/themes/RLP/js/geocoderPlugin.js" % r.application)

    # Color-coded status representation
    field = table.status
    requires = field.requires
    if isinstance(requires, IS_EMPTY_OR):
        field.requires = requires.other
    field.represent = S3PriorityRepresent(shelter_status_opts,
                                          {1: "red",
                                           2: "green",
                                           }).represent

    field = table.available_capacity
    field.represent = available_capacity_represent

    ltable = s3db.cr_shelter_service_shelter
    field = ltable.service_id
    field.label = T("Services")
    field.represent = ServiceListRepresent(lookup = "cr_shelter_service",
                                           )

    # CRUD Form
    crud_fields = [# ----- Shelter -----
                   "organisation_id",
                   "name",
                   "shelter_type_id",
                   S3SQLInlineLink(
                        "shelter_service",
                        field = "service_id",
                        label = T("Services"),
                        cols = 3,
                        render_list = True,
                        ),
                   "status",
                   # ----- Address -----
                   "location_id",
                   # ----- Contact -----
                   "website",
                   "contact_name",
                   "phone",
                   "email",
                   # ----- Capacity and Population -----
                   "capacity",
                   S3SQLInlineComponent("population",
                                        label = T("Current Population##shelter"),
                                        fields = ["type_id",
                                                  "population_adults",
                                                  (T("Population (Minors)"), "population_children"),
                                                  ],
                                        ),
                   "population",
                   "population_adults",
                   "population_children",
                   # ----- Other Details -----
                   "comments"
                   ]

    subheadings = {"organisation_id": T("Facility"),
                   "location_id": T("Address"),
                   "website": T("Contact Information"),
                   "capacity": T("Capacity / Occupancy"),
                   "comments": T("Administrative"),
                   }

    # Filter widgets
    is_report = r.method == "report"
    filter_widgets = [TextFilter(["name",
                                  ],
                                 label = T("Search"),
                                 ),
                      OptionsFilter("status",
                                    options = shelter_status_opts,
                                    default = 2,
                                    cols = 2,
                                    sort = False,
                                    ),
                      RangeFilter("available_capacity",
                                  hidden = is_report,
                                  ),
                      OptionsFilter("shelter_service__link.service_id",
                                    options = lambda: get_filter_options("cr_shelter_service"),
                                    hidden = True,
                                    ),
                      LocationFilter("location_id",
                                     levels = ["L2", "L3"],
                                     hidden = True,
                                     ),
                      OptionsFilter("shelter_type_id",
                                    options = lambda: get_filter_options("cr_shelter_type"),
                                    hidden = True,
                                    ),
                      OptionsFilter("organisation_id",
                                    hidden = True,
                                    ),
                      ]

    # List fields
    list_fields = ["organisation_id",
                   "name",
                   "shelter_type_id",
                   "status",
                   (T("Capacity"), "capacity"),
                   (T("Current Population##shelter"), "population"),
                   (T("Available Capacity"), "available_capacity"),
                   (T("Place"), "place"),
                   (T("Contact"), "contact"),
                   #"website",
                   #"shelter_service__link.service_id",
                   ]
    if r.representation in ("xlsx", "xls"):
        list_fields.append("shelter_service__link.service_id")

    s3db.configure("cr_shelter",
                   crud_form = S3SQLCustomForm(*crud_fields),
                   subheadings = subheadings,
                   extra_fields = ["contact_name",
                                   "phone",
                                   "email",
                                   "location_id$L3",
                                   "location_id$L2",
                                   "location_id$L1",
                                   "population",
                                   "capacity",
                                   ],
                  filter_widgets = filter_widgets,
                  list_fields = list_fields,
                  )

    if is_report:
        axes = ["location_id$L3",
                "location_id$L2",
                "location_id$L1",
                "shelter_type_id",
                (T("Organization Group"), "organisation_id$group_membership.group_id"),
                "organisation_id$organisation_type__link.organisation_type_id",
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Available Capacity"), "sum(available_capacity)"),
                     (T("Total Capacity"), "sum(capacity)"),
                     (T("Current Population##shelter"), "sum(population)"),
                     (T("Number of Facilities"), "count(id)"),
                     ],
            "defaults": {"rows": "location_id$L2",
                         "cols": None,
                         "fact": "sum(available_capacity)",
                         "totals": True,
                         },
            }

        s3db.configure("cr_shelter",
                       report_options = report_options,
                       )

# -------------------------------------------------------------------------
def cr_shelter_controller(**attr):

    settings = current.deployment_settings
    s3 = current.response.s3

    auth = current.auth

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Restrict data formats
        restrict_data_formats(r)

        # Enable catalog layers in map views
        settings.gis.widget_catalogue_layers = True

        # Hide last update except for own records
        record = r.record
        if not record or \
           not auth.s3_has_permission("update", r.table, record_id=record.id):
            s3.hide_last_update = True

        if record and r.representation == "plain":
            # Bypass REST method, return map popup directly
            result = {"bypass": True,
                      "output": shelter_map_popup(r.record),
                      }
        return result
    s3.prep = prep

    # Custom rheader
    from ..rheaders import cr_rheader
    attr["rheader"] = cr_rheader

    return attr

# -------------------------------------------------------------------------
def cr_shelter_status_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    current.deployment_settings.base.bigtable = True

    table = s3db.cr_shelter_status
    field = table.population_children
    field.label = T("Population (Minors)")

    # Timeplot options
    # TODO need end date for proper timeplot report
    #facts = [(T("Current Population (Total)"), "sum(population)"),
    #         (T("Current Population (Adults)"), "sum(population_adults)"),
    #         (T("Current Population (Children)"), "sum(population_children)"),
    #         (T("Total Capacity"), "sum(capacity)"),
    #         ]
    #timeplot_options = {
    #    "facts": facts,
    #    "timestamp": (#(T("per interval"), "date,date"),
    #                  (T("cumulative"), "date"),
    #                  ),
    #    "defaults": {"fact": facts[0],
    #                 "timestamp": "date",
    #                 "time": "<-0 months||days",
    #                 },
    #    }
    #
    #s3db.configure("cr_shelter_status",
    #               timeplot_options = timeplot_options,
    #               )

# -------------------------------------------------------------------------
def cr_shelter_population_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.cr_shelter_population
    field = table.population_children
    field.label = T("Population (Minors)")

    from core import LocationFilter, \
                     OptionsFilter, \
                     get_filter_options

    filter_widgets = [OptionsFilter("shelter_id$organisation_id$group_membership.group_id",
                                    label = T("Organization Group"),
                                    options = get_filter_options("org_group"),
                                    ),
                      OptionsFilter("type_id",
                                    options = get_filter_options("cr_population_type"),
                                    hidden = True,
                                    ),
                      LocationFilter("shelter_id$location_id",
                                     levels = ("L2", "L3"),
                                     translate = False,
                                     hidden = True,
                                     ),
                      ]
    if current.auth.s3_has_role("ADMIN"):
        shelter_status_opts = OrderedDict(((2, T("Open##status")),
                                           (1, T("Closed")),
                                           ))
        filter_widgets.insert(1, OptionsFilter("shelter_id$status",
                                               label = T("Shelter Status"),
                                               options = shelter_status_opts,
                                               sort = False,
                                               default = 2,
                                               cols = 2,
                                               ))

    s3db.configure("cr_shelter_population",
                   filter_widgets = filter_widgets,
                   insertable = False,
                   editable = False,
                   deletable = False,
                   )

    if r.method == "report":

        axes = ["type_id",
                "shelter_id$location_id$L3",
                "shelter_id$location_id$L2",
                "shelter_id$location_id$L1",
                "shelter_id$shelter_type_id",
                (T("Organization Group"), "shelter_id$organisation_id$group_membership.group_id"),
                "shelter_id$organisation_id$organisation_type__link.organisation_type_id",
                "shelter_id$organisation_id",
                ]

        report_options = {
            "rows": axes,
            "cols": axes,
            "fact": [(T("Current Population (Total)"), "sum(population)"),
                     (T("Population (Adults)"), "sum(population_adults)"),
                     (T("Population (Minors)"), "sum(population_children)"),
                     ],
            "defaults": {"rows": "shelter_id$location_id$L2",
                         "cols": "type_id",
                         "fact": "sum(population)",
                         "totals": True,
                         },
            }

        s3db.configure("cr_shelter_population",
                       report_options = report_options,
                       )

# -------------------------------------------------------------------------
def cr_shelter_population_controller(**attr):

    s3 = current.response.s3

    current.deployment_settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Restrict data formats
        restrict_data_formats(r)

        # Exclude closed shelters
        if not current.auth.s3_has_role("ADMIN"):
            r.resource.add_filter(FS("shelter_id$status") == 2)

        return result
    s3.prep = prep

    return attr

# -------------------------------------------------------------------------
def occupancy_rate_estimate(row):
    """
        Field method for reception centers to calculate the occupancy
        rate relative to the estimated allocable capacity
    """

    if hasattr(row, "cr_reception_center"):
        row = row.cr_reception_center
    try:
        population = row.population
        capacity = row.allocable_capacity_estimate
    except AttributeError:
        return None

    if population is None or population < 0:
        population = 0

    rate = (population * 100 // capacity) if capacity else 100

    return rate

# -------------------------------------------------------------------------
def free_capacity_estimate(row):
    """
        Field method for reception centers to calculate the free
        capacity relative to the estimated allocable capacity
    """

    if hasattr(row, "cr_reception_center"):
        row = row.cr_reception_center
    try:
        population = row.population
        capacity = row.allocable_capacity_estimate
    except AttributeError:
        return None

    if population is None or population < 0:
        population = 0
    if capacity is None or capacity < 0:
        capacity = 0
    free_capacity = max(0, capacity - population)

    return free_capacity

# -------------------------------------------------------------------------
def cr_reception_center_resource(r, tablename):

    has_role = current.auth.s3_has_role

    table = current.s3db.cr_reception_center

    # Field methods for computed values by estimated capacity
    from core import s3_fieldmethod, represent_occupancy
    table.occupancy_rate_estimate = s3_fieldmethod("occupancy_rate_estimate",
                                                   occupancy_rate_estimate,
                                                   represent = represent_occupancy,
                                                   )
    table.free_capacity_estimate = s3_fieldmethod("free_capacity_estimate",
                                                  free_capacity_estimate,
                                                  represent = lambda v, row=None: v if v is not None else "-",
                                                  )

    record = r.record if r.resource.tablename == "cr_reception_center" else None

    # Restrict modifications field-wise by role
    if record:
        is_manager = has_role("AFA_MANAGER", for_pe=record.realm_entity) or \
                     has_role("AFA_MANAGER", for_pe=0)
        is_coordinator = has_role("AFA_COORDINATOR")

        for fn in table.fields:
            field = table[fn]
            if fn in ("capacity", "allocable_capacity_estimate"):
                field.writable = is_coordinator
            else:
                field.writable = is_manager

# -------------------------------------------------------------------------
def cr_reception_center_controller(**attr):

    from ..rheaders import cr_rheader
    attr["rheader"] = cr_rheader

    return attr

# -------------------------------------------------------------------------
def cr_reception_center_type_controller(**attr):

    import os
    xslt_path = os.path.join("..", "..", "..", "modules", "templates", "GIMS", "formats")

    attr.update(csv_stylesheet = (xslt_path, "cr", "reception_center_type.xsl"),
                )

    return attr

# END =========================================================================
