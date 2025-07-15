"""
    DVR module customisations for MRCMS

    License: MIT
"""

import datetime

from gluon import current, URL, A, TAG, IS_EMPTY_OR
from gluon.storage import Storage

from core import CRUDRequest, CustomController, FS, IS_ONE_OF, \
                 S3CalendarWidget, S3HoursWidget, CustomForm, InlineLink, \
                 DateFilter, HierarchyFilter, OptionsFilter, TextFilter, \
                 get_filter_options, get_form_record_id, s3_redirect_default, \
                 represent_hours, set_default_filter, s3_fullname

from .pr import configure_person_tags

# -------------------------------------------------------------------------
def dvr_home():
    """ Redirect dvr/index to dvr/person """

    s3_redirect_default(URL(f="person"))

# -------------------------------------------------------------------------
def dvr_case_onaccept(form):
    """
        Onaccept of case:
            - if the case has been archived, or closed, make sure any
              active shelter registration is set to checked-out
            - if the client does not have a shelter registration, but
              there is a default shelter for new registrations, then
              create a new registration (unless there is a registration
              subform inline)
    """

    db = current.db
    s3db = current.s3db
    auth = current.auth

    record_id = get_form_record_id(form)
    if not record_id:
        return

    table = s3db.dvr_case
    record = db(table.id == record_id).select(table.id,
                                              table.person_id,
                                              table.status_id,
                                              table.archived,
                                              limitby = (0, 1),
                                              ).first()
    if not record:
        return

    # Inline shelter registration?
    inline = "sub_shelter_registration_registration_status" in current.request.post_vars

    cancel = False
    if record.archived:
        cancel = True
    else:
        stable = s3db.dvr_case_status
        status = db(stable.id == record.status_id).select(stable.is_closed,
                                                          limitby = (0, 1),
                                                          ).first()
        if status and status.is_closed:
            cancel = True

    rtable = s3db.cr_shelter_registration
    query = (rtable.person_id == record.person_id)
    if cancel:
        # If there is an active shelter registration, check-out the client
        rtable = s3db.cr_shelter_registration
        query &= (rtable.person_id == record.person_id) & \
                 (rtable.registration_status != 3) & \
                 (rtable.deleted == False)
        reg = db(query).select(rtable.id,
                               limitby = (0, 1),
                               ).first()
        if reg:
            r = CRUDRequest("cr", "shelter_registration", args=[], get_vars={})
            r.customise_resource("cr_shelter_registration")
            reg.update_record(registration_status=3)
            s3db.onaccept(rtable, reg, method="update")

    elif not inline:
        # If there is no shelter registration for this client, but we have a
        # default shelter for new registrations, then create a new registration
        reg = db(query).select(rtable.id,
                               limitby = (0, 1),
                               ).first()
        if not reg and rtable.shelter_id.default:
            reg = {"person_id": record.person_id}
            reg_id = reg["id"] = rtable.insert(person_id=record.person_id)
            s3db.update_super(table, reg)
            auth.s3_set_record_owner(table, reg_id)
            auth.s3_make_session_owner(table, reg_id)
            s3db.onaccept(rtable, reg, method="create")

# -------------------------------------------------------------------------
def dvr_case_resource(r, tablename):

    s3db = current.s3db
    ctable = s3db.dvr_case

    # Allow direct transfer of cases between organisations
    # TODO replace this by a formal takeover-procedure
    s3db.configure("dvr_case", update_realm=True)

    # Custom onaccept to propagate status changes
    s3db.add_custom_callback(tablename, "onaccept", dvr_case_onaccept)

    # All fields read-only except comments, unless user has permission
    # to create new cases
    if not current.auth.s3_has_permission("create", "dvr_case"):
        for field in ctable:
            if field.name != "comments":
                field.writable = False

# -------------------------------------------------------------------------
def dvr_task_controller(**attr):

    s3db = current.s3db
    s3 = current.response.s3

    current.deployment_settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.controller == "counsel":
            categories = {"A", "C"}
            default_category = "C"
        else:
            categories = {"A"}
            default_category = "A"

        s3db.dvr_configure_case_tasks(r,
                                      categories = categories,
                                      default_category = default_category,
                                      )
        r.resource.configure(insertable = False,
                             deletable = False,
                             )
        return result
    s3.prep = prep

    from ..rheaders import dvr_rheader
    attr["rheader"] = dvr_rheader

    return attr

# -------------------------------------------------------------------------
def note_date_dt_orderby(field, direction, orderby, left_joins):
    """
        When sorting notes by date, use created_on to maintain
        consistent order of multiple notes on the same date
    """

    sorting = {"table": field.tablename,
               "direction": direction,
               }
    orderby.append("%(table)s.date%(direction)s,%(table)s.created_on%(direction)s" % sorting)

# -------------------------------------------------------------------------
def dvr_note_resource(r, tablename):

    T = current.T

    db = current.db
    s3db = current.s3db
    auth = current.auth

    table = s3db.dvr_note

    # Consistent ordering of notes (newest on top)
    field = table.date
    field.represent.dt_orderby = note_date_dt_orderby

    type_id = "note_type_id"

    if not auth.s3_has_role("ADMIN"):

        # Restrict access by note type
        GENERAL = "General"
        MEDICAL = "Medical"
        SECURITY = "Security"

        permitted_note_types = [GENERAL]

        user = auth.user
        if user:
            has_roles = auth.s3_has_roles

            # Roles permitted to access "Security" type notes
            SECURITY_ROLES = ("CASE_ADMIN",
                              "SECURITY",
                              )
            if has_roles(SECURITY_ROLES):
                permitted_note_types.append(SECURITY)

            # Roles permitted to access "Health" type notes
            MEDICAL_ROLES = ("CASE_ADMIN",
                             "MEDICAL",
                             )
            if has_roles(MEDICAL_ROLES):
                permitted_note_types.append(MEDICAL)

        # Filter notes to permitted note types
        query = FS("note_type_id$name").belongs(permitted_note_types)
        if r.tablename == "dvr_note":
            r.resource.add_filter(query)
        else:
            r.resource.add_component_filter("case_note", query)

        # Filter note-type selector
        ttable = current.s3db.dvr_note_type
        dbset = db((ttable.is_task == False) & \
                   (ttable.name.belongs(permitted_note_types)))

        field = table.note_type_id
        field.label = T("Confidentiality")
        field.comment = T("Restricts access to this entry (e.g. medical notes are only accessible for medical team)")
        field.requires = IS_ONE_OF(dbset, "dvr_note_type.id",
                                   field.represent,
                                   )

        # Hide note type selector if only one choice
        note_types = dbset.select(ttable.id, ttable.name)
        if len(note_types) == 1:
            field.default = note_types.first().id
            field.readable = field.writable = False
            type_id = None # hide from list
        else:
            general = note_types.find(lambda row: row.name == GENERAL)
            if general:
                field.default = general.first().id

        if field.default:
            field.requires.zero = None

    # Make author visible
    field = table.created_by
    field.label = T("Author")
    field.readable = True

    form_fields = ["date", "note", type_id, "created_by"]
    list_fields = ["date", "note", type_id, "created_by"]
    s3db.configure("dvr_note",
                   crud_form = CustomForm(*form_fields),
                   list_fields = list_fields,
                   orderby = "%(tn)s.date desc,%(tn)s.created_on desc" % \
                             {"tn": table._tablename},
                   pdf_format = "list",
                   pdf_fields = list_fields,
                   )

# -------------------------------------------------------------------------
def dvr_need_resource(r, tablename):

    table = current.s3db.dvr_need

    # Expose code
    field = table.code
    field.readable = field.writable = True

# -------------------------------------------------------------------------
def dvr_case_activity_resource(r, tablename):

    T = current.T

    table = current.s3db.dvr_case_activity

    # Set default human_resource_id, alter label
    field = table.human_resource_id
    field.default = current.auth.s3_logged_in_human_resource()
    field.label = T("Registered by")
    field.widget = None # use standard drop-down

# -------------------------------------------------------------------------
def dvr_case_activity_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    current.deployment_settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        resource = r.resource

        # Filter to valid cases
        if not r.record:
            query = (FS("person_id$dvr_case.archived") == False) | \
                    (FS("person_id$dvr_case.archived") == None)
            resource.add_filter(query)
            # TODO filter to open cases

        if not r.component:

            if r.interactive:
                # Represent person_id as link (including ID)
                table = resource.table
                field = table.person_id
                fmt = "%(pe_label)s %(last_name)s, %(first_name)s"
                field.represent = s3db.pr_PersonRepresent(fields = ("pe_label",
                                                                    "last_name",
                                                                    "first_name",
                                                                    ),
                                                          labels = fmt,
                                                          show_link = True,
                                                          )

            # Custom list fields
            list_fields = [(T("ID"), "person_id$pe_label"),
                           "person_id$first_name",
                           "person_id$last_name",
                           "need_id",
                           "emergency",
                           "status_id",
                           ]
            resource.configure(list_fields=list_fields)

        return result
    s3.prep = custom_prep

    return attr

# -------------------------------------------------------------------------
def configure_response_action_reports(r,
                                      multiple_orgs = False,
                                      ):
    """
        Configures pivot report options for response actions

        Args:
            r: the CRUDRequest
            multiple_orgs: user has permission to read response actions
                           for multiple organisations (boolean)
    """

    T = current.T

    # Custom Report Options
    facts = ((T("Number of Actions"), "count(id)"),
             (T("Number of Clients"), "count(person_id)"),
             (T("Hours (Total)"), "sum(hours)"),
             (T("Hours (Average)"), "avg(hours)"),
             )
    axes = ["person_id$gender",
            "person_id$person_details.nationality",
            #"person_id$person_details.marital_status",
            #(T("Size of Family"), "person_id$dvr_case.household_size"),
            "response_type_id",
            (T("Theme"), "response_action_theme.theme_id"),
            (T("Need Type"), "response_action_theme.theme_id$need_id"),
            "response_action_theme.theme_id$sector_id",
            "human_resource_id",
            ]
    if multiple_orgs:
        # Add case organisation as report axis
        axes.append("person_id$dvr_case.organisation_id")

    report_options = {
        "rows": axes,
        "cols": axes,
        "fact": facts,
        "defaults": {"rows": "response_type_id",
                     "cols": None,
                     "fact": "count(id)",
                     "totals": True,
                     },
        "precision": {"hours": 2, # higher precision is impractical
                      },
        }

    current.s3db.configure("dvr_response_action",
                           report_options = report_options,
                           )

# -------------------------------------------------------------------------
def configure_response_action_filters(r,
                                      on_tab = None,
                                      multiple_orgs = False,
                                      organisation_ids = None,
                                      ):
    """
        Configures filter widgets for dvr_response_action

        Args:
            r: the CRUDRequest
            on_tab: viewing response tab in case file (boolean)
            multiple_orgs: user can see cases of multiple organisations,
                           so include an organisation-filter
            organisation_ids: the IDs of the organisations the user can access
    """

    T = current.T

    s3db = current.s3db
    table = s3db.dvr_response_action

    if on_tab is None:
        resource = r.resource
        on_tab = resource.tablename != "dvr_response_action"

    is_report = r.method == "report"

    if on_tab:
        filter_widgets = [TextFilter(["response_action_theme.comments",
                                      ],
                                     label = T("Search"),
                                     ),
                          DateFilter("start_date",
                                     hide_time = True,
                                     hidden = True,
                                     ),
                          HierarchyFilter("response_type_id",
                                          hidden = True,
                                          ),
                          OptionsFilter("response_action_theme.theme_id$sector_id",
                                        hidden = True,
                                        ),
                          OptionsFilter("response_action_theme.theme_id",
                                        hidden = True,
                                        ),
                          ]
    else:
        # TODO add case status filter
        from ..helpers import get_response_theme_sectors
        filter_widgets = [
            TextFilter(["person_id$pe_label",
                        "person_id$first_name",
                        "person_id$middle_name",
                        "person_id$last_name",
                        "response_action_theme.comments"
                        ],
                       label = T("Search"),
                       ),
            DateFilter("start_date",
                       hide_time = True,
                       hidden = not is_report,
                       ),
            OptionsFilter("status_id",
                          options = lambda: \
                                    get_filter_options("dvr_response_status",
                                                       orderby = "workflow_position",
                                                       ),
                          cols = 3,
                          orientation = "rows",
                          sort = False,
                          size = None,
                          translate = True,
                          hidden = True,
                          ),
            HierarchyFilter("response_type_id",
                            hidden = True,
                            ),
            OptionsFilter("response_action_theme.theme_id$sector_id",
                          header = True,
                          hidden = True,
                          options = get_response_theme_sectors,
                          ),
            OptionsFilter("response_action_theme.theme_id",
                          header = True,
                          hidden = True,
                          options = lambda: \
                                    get_filter_options("dvr_response_theme",
                                                       org_filter = True,
                                                       ),
                          ),
            ]

        if multiple_orgs:
            # Add case organisation filter
            if organisation_ids:
                # Provide the permitted organisations as filter options
                org_filter_opts = s3db.org_organisation_represent.bulk(organisation_ids,
                                                                       show_link = False,
                                                                       )
                org_filter_opts.pop(None, None)
            else:
                # Look up from records
                org_filter_opts = None
            filter_widgets.insert(1, OptionsFilter("person_id$dvr_case.organisation_id",
                                                   options = org_filter_opts,
                                                   ))

        # Filter by person responsible
        field = table.human_resource_id
        try:
            hr_filter_opts = field.requires.options()
        except AttributeError:
            pass
        else:
            hr_filter_opts = dict(hr_filter_opts)
            hr_filter_opts.pop('', None)
        if hr_filter_opts:
            filter_widgets.append(OptionsFilter("human_resource_id",
                                                header = True,
                                                hidden = True,
                                                options = hr_filter_opts,
                                                ))

    s3db.configure("dvr_response_action",
                   filter_widgets = filter_widgets,
                   )

# -------------------------------------------------------------------------
def dvr_response_action_resource(r, tablename):

    T = current.T

    s3db = current.s3db

    atable = s3db.dvr_response_action
    ltable = s3db.dvr_response_action_theme

    on_tab = r.controller == "counsel" and r.resource.tablename == "pr_person"

    if on_tab and r.representation in ("html", "aadata", "pdf"):
        # Show details per theme in interactive view and PDF exports
        ltable.id.represent = s3db.dvr_ResponseActionThemeRepresent(paragraph = True,
                                                                    details = True,
                                                                    )
        themes = (T("Themes"), "response_action_theme.id")
    else:
        # Show just list of themes
        themes = (T("Themes"), "response_action_theme.theme_id")

    # Configure hours-fields for both total and per-theme efforts
    for field in (ltable.hours, atable.hours):
        field.widget = S3HoursWidget(precision = 2,
                                     placeholder = "HH:MM",
                                     explicit_above = 3,
                                     )
        field.represent = represent_hours()

    if on_tab:
        person_id, pe_label = None, None
        configure_response_action_filters(r, on_tab=True)
    else:
        person_id, pe_label = "person_id", (T("ID"), "person_id$pe_label")
        field = atable.person_id
        field.readable = True
        field.writable = False
        field.represent =  s3db.pr_PersonRepresent(show_link = True,
                                                   linkto = URL(c = r.controller,
                                                                f = "person",
                                                                args = ["[id]"],
                                                                extension = "",
                                                                ),
                                                   )
        field.comment = None

    field = atable.human_resource_id
    field.represent = s3db.hrm_HumanResourceRepresent(show_link=False)

    # List fields
    list_fields = [pe_label,
                   person_id,
                   "start_date",
                   "response_type_id",
                   themes,
                   "human_resource_id",
                   "hours",
                   "status_id",
                   ]
    pdf_fields = [pe_label,
                  person_id,
                  "start_date",
                  "response_type_id",
                  themes,
                  "human_resource_id",
                  ]

    s3db.configure("dvr_response_action",
                   list_fields = list_fields,
                   pdf_format = "list" if on_tab else "table",
                   pdf_fields = pdf_fields,
                   orderby = "dvr_response_action.start_date desc, dvr_response_action.created_on desc",
                   )

# -------------------------------------------------------------------------
def dvr_response_action_controller(**attr):

    T = current.T
    db = current.db
    s3db = current.s3db

    s3 = current.response.s3
    settings = current.deployment_settings

    settings.base.bigtable = True

    #standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        #result = standard_prep(r) if callable(standard_prep) else True
        result = True

        resource = r.resource
        table = resource.table

        # Beneficiary is required and must have a case file
        ptable = s3db.pr_person
        ctable = s3db.dvr_case
        dbset = db((ptable.id == ctable.person_id) & \
                   (ctable.archived == False) & \
                   (ctable.deleted == False))
        field = table.person_id
        field.requires = IS_ONE_OF(dbset, "pr_person.id", field.represent)

        # Set defaults
        s3db.dvr_set_response_action_defaults()

        # Create/delete requires context perspective
        resource.configure(insertable = False,
                           deletable = False,
                           )

        record = r.record
        if not record:
            # Exclude archived (invalid) cases
            query = (FS("person_id$dvr_case.archived") == False) | \
                    (FS("person_id$dvr_case.archived") == None)
            resource.add_filter(query)

            from ..helpers import get_case_organisations
            multiple_orgs, organisation_ids = get_case_organisations()

            configure_response_action_filters(r,
                                              on_tab = False,
                                              multiple_orgs = multiple_orgs,
                                              organisation_ids = organisation_ids,
                                              )
            configure_response_action_reports(r,
                                              multiple_orgs = multiple_orgs,
                                              )

            # pisets = {pitype: (method, icon, title)}
            pisets = {"default": ("indicators",
                                  "line-chart",
                                  T("Performance Indicators"),
                                  ),
                      "bamf": ("indicators_bamf",
                               "tachometer",
                               "%s %s" % (T("Performance Indicators"), "BAMF"),
                               ),
                      }

            from ..stats import PerformanceIndicatorExport
            for pitype in ("bamf", "default"):
                piset = pisets.get(pitype)
                if not piset:
                    continue
                method, icon, title = piset
                s3db.set_method("dvr_response_action",
                                method = method,
                                action = PerformanceIndicatorExport(pitype),
                                )
                export_formats = list(settings.get_ui_export_formats())
                fmt = "%s.xls" % method
                export_formats.insert(0, (fmt, "fa fa-%s" % icon, title))
                s3.formats[fmt] = r.url(method=method)
                settings.ui.export_formats = export_formats

        elif settings.get_dvr_vulnerabilities():
            # Limit selectable vulnerabilities to case
            s3db.dvr_configure_case_vulnerabilities(record.person_id)

        return result
    s3.prep = prep

    return attr

# -------------------------------------------------------------------------
def dvr_case_appointment_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.dvr_case_appointment

    # Custom label for comments-field
    field = table.comments
    field.label = T("Details")
    field.comment = None

    # Organizer popups
    if r.tablename == "pr_person":
        title = "type_id"
        description = ["type_id",
                       "status",
                       "comments",
                       ]
    elif r.tablename == "dvr_case_appointment":
        title = "person_id"
        description = [(T("ID"), "person_id$pe_label"),
                       "type_id",
                       "status",
                       "comments",
                       ]
    else:
        title = description = None

    # Configure Organizer
    if title:
        s3db.configure("dvr_case_appointment",
                       organize = {#"start": "date",
                                   "start": "start_date",
                                   "end": "end_date",
                                   "title": title,
                                   "description": description,
                                   "reload_on_update": True,
                                   # Color by status
                                   "color": "status",
                                   "colors": {
                                       1: "#ffaa00", # required (amber)
                                       2: "#10427b", # planned (blue)
                                       3: "#009f00", # in progress (light green)
                                       4: "#006100", # completed (green)
                                       5: "#d10000", # missed (red)
                                       6: "#666",    # canceled (gray)
                                       7: "#666",    # not required (gray)
                                       }
                                   },
                       )

    if r.tablename == "dvr_case_appointment":

        from ..bulk import CompleteAppointments
        s3db.set_method("dvr_case_appointment", method="complete", action=CompleteAppointments)

        bulk_actions = [{"label": T("Mark Completed##appointment"),
                         "mode": "ajax",
                         "url": r.url(method="complete", representation="json", vars={}),
                         "script": S3CalendarWidget.global_scripts(current.calendar.name)[0],
                         }]

        s3db.configure("dvr_case_appointment",
                       bulk_actions = bulk_actions,
                       )

    else:
        s3db.configure("dvr_case_appointment",
                       list_fields = ["type_id",
                                      (T("Date"), "start_date"),
                                      "status",
                                      "comments",
                                      ],
                       )

# -------------------------------------------------------------------------
def dvr_case_appointment_controller(**attr):

    T = current.T

    db = current.db
    s3db = current.s3db
    auth = current.auth

    s3 = current.response.s3

    current.deployment_settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        resource = r.resource

        # Filter to active cases
        if not r.record:
            query = (FS("person_id$dvr_case.archived") == False) | \
                    (FS("person_id$dvr_case.archived") == None)
            resource.add_filter(query)

        # Filter for org-specific appointment types
        # - not necessary since appointments are within the realm of
        #   the type-defining organisation anyway, so permissions will
        #   filter anyway

        if not r.component:

            configure_person_tags()

            if r.interactive and not r.id:

                # Which organisation can the user see appointments for?
                permissions = current.auth.permission
                permitted_realms = permissions.permitted_realms("dvr_case_appointment", "read")
                if permitted_realms is not None:
                    otable = s3db.org_organisation
                    query = (otable.pe_id.belongs(permitted_realms)) & \
                            (otable.deleted == False)
                    organisations = db(query).select(otable.id)
                    organisation_ids = [o.id for o in organisations]
                else:
                    organisation_ids = None # global access

                # Which shelters can the user see appointments for?
                if organisation_ids is None or organisation_ids:
                    stable = s3db.cr_shelter
                    query = (stable.status != 1) & (stable.deleted == False)
                    if organisation_ids:
                        query = stable.organisation_id.belongs(organisation_ids) & query
                    shelters = db(query).select(stable.id, stable.name)
                    shelter_filter_opts = {s.id: s.name for s in shelters}
                else:
                    shelters = shelter_filter_opts = None # no shelters available

                # Which appointment types can the user see?
                ttable = s3db.dvr_case_appointment_type
                query = auth.s3_accessible_query("read", "dvr_case_appointment_type")
                if organisation_ids:
                    query = ttable.organisation_id.belongs(organisation_ids) & query
                types = db(query).select(ttable.id, ttable.name)
                type_filter_opts = {t.id: t.name for t in types}

                # Filter widgets
                filter_widgets = [
                    TextFilter(["person_id$pe_label",
                                "person_id$first_name",
                                "person_id$last_name",
                                "person_id$dvr_case.reference",
                                ],
                                label = T("Search"),
                                ),
                    OptionsFilter("type_id",
                                  options = type_filter_opts,
                                  cols = 3,
                                  ),
                    OptionsFilter("status",
                                  options = s3db.dvr_appointment_status_opts,
                                  default = 2,
                                  ),

                    TextFilter(["person_id$pe_label"],
                               label = T("IDs"),
                               match_any = True,
                               hidden = True,
                               comment = T("Search for multiple IDs (separated by blanks)"),
                               ),
                    OptionsFilter("person_id$dvr_case.status_id$is_closed",
                                  cols = 2,
                                  default = False,
                                  hidden = True,
                                  label = T("Case Closed"),
                                  options = {True: T("Yes"), False: T("No")},
                                  ),
                    ]
                if r.method != "organize":
                    now = r.utcnow
                    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    tomorrow = today + datetime.timedelta(days=1)
                    filter_widgets.insert(-2, DateFilter(#"date",
                                                         "start_date",
                                                         default = {"ge": today,
                                                                    "le": tomorrow,
                                                                    },
                                              ))

                # Add organisation filter if user can see appointments
                # from more than one org
                if organisation_ids is None or len(organisation_ids) > 1:
                    filter_widgets.insert(-2,
                        OptionsFilter("person_id$dvr_case.organisation_id",
                                      hidden = True,
                                      ))

                # Add shelter filter if user can see appointments from
                # more than one shelter
                if shelter_filter_opts:
                    filter_widgets.insert(-2,
                        OptionsFilter("person_id$shelter_registration.shelter_id",
                                      options = shelter_filter_opts,
                                      hidden = True,
                                      ))

                resource.configure(filter_widgets = filter_widgets)

            # Custom list fields
            list_fields = [(T("ID"), "person_id$pe_label"),
                           (T("Principal Ref.No."), "person_id$dvr_case.reference"),
                           # TODO render as link to person if not XLS
                           (T("Name"), "person_id"),
                           "type_id",
                           #"date",
                           (T("Date"), "start_date"),
                           #"end_date",
                           "status",
                           "comments",
                           ]

            resource.configure(list_fields = list_fields,
                               insertable = False,
                               deletable = False,
                               update_next = r.url(method=""),
                               )

        return result
    s3.prep = custom_prep

    return attr

# -------------------------------------------------------------------------
def case_event_report_default_filters(event_code=None):
    """
        Set default filters for case event report

        Args:
            event_code: code for the default event type
    """

    if event_code:
        ttable = current.s3db.dvr_case_event_type

        if event_code[-1] == "*":
            query = (ttable.code.like("%s%%" % event_code[:-1])) & \
                    (ttable.is_inactive == False)
        else:
            query = (ttable.code == event_code)
        query &= (ttable.deleted == False)

        rows = current.db(query).select(ttable.id)
        event_ids = [row.id for row in rows]
        if event_ids:
            set_default_filter("~.type_id",
                               event_ids,
                               tablename = "dvr_case_event",
                               )

    # Minimum date: one week
    WEEK_AGO = datetime.datetime.now() - \
                datetime.timedelta(days=7)
    min_date = WEEK_AGO.replace(hour=7, minute=0, second=0)

    set_default_filter("~.date",
                       {"ge": min_date,
                        },
                       tablename = "dvr_case_event",
                       )

# -------------------------------------------------------------------------
def dvr_case_event_resource(r, tablename):

    s3db = current.s3db

    from ..checkpoints import ActivityParticipation, FoodDistribution
    s3db.set_method("dvr_case_event",
                    method = "register_activity",
                    action = ActivityParticipation,
                    )
    s3db.set_method("dvr_case_event",
                    method = "register_food",
                    action = FoodDistribution,
                    )

    from ..reports import MealsReport
    s3db.set_method("dvr_case_event",
                    method = "meals_report",
                    action = MealsReport,
                    )

# -------------------------------------------------------------------------
def dvr_case_event_controller(**attr):

    auth = current.auth
    s3 = current.response.s3

    # Custom postp
    standard_postp = s3.postp
    def custom_postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.interactive and \
           r.method in ("register", "register_food", "register_activity"):
            if isinstance(output, dict):
                if auth.permission.has_permission("read", c="dvr", f="person"):
                    output["return_url"] = URL(c="dvr", f="person")
                else:
                    output["return_url"] = URL(c="default", f="index")
            CustomController._view("MRCMS", "register_case_event.html")
        return output
    s3.postp = custom_postp

    return attr

# -------------------------------------------------------------------------
def dvr_case_appointment_type_controller(**attr):

    T = current.T
    auth = current.auth

    s3 = current.response.s3

    # Selectable organisation
    from ..helpers import managed_orgs_field
    attr["csv_extra_fields"] = [{"label": "Organisation",
                                 "field": managed_orgs_field,
                                 }]

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        # Import-button
        if not r.record and not r.method and auth.s3_has_permission("create", "dvr_case_appointment_type"):
            if isinstance(output, dict):
                import_btn = A(T("Import"),
                               _href = r.url(method="import"),
                               _class = "action-btn activity button",
                               )
                showadd_btn = output.get("showadd_btn")
                if showadd_btn:
                    output["showadd_btn"] = TAG[""](import_btn, showadd_btn)
                else:
                    output["showadd_btn"] = import_btn

        return output
    s3.postp = postp

    return attr

# -------------------------------------------------------------------------
def dvr_case_event_type_resource(r, tablename):

    T = current.T

    s3db = current.s3db

    # TODO filter case event exclusion to types of same org
    #      if we have a r.record, otherwise OptionsFilterS3?

    # Custom form
    crud_form = CustomForm(# --- Event Type ---
                           "organisation_id",
                           "event_class",
                           "code",
                           "name",
                           "is_inactive",
                           "is_default",
                           # --- Process ---
                           "appointment_type_id",
                           "activity_id",
                           "presence_required",
                           # --- Restrictions ---
                           "residents_only",
                           "register_multiple",
                           "role_required",
                           "min_interval",
                           "max_per_day",
                           InlineLink("excluded_by",
                                      field = "excluded_by_id",
                                      label = T("Not Combinable With"),
                                      comment = T("Events that exclude registration of this event type on the same day"),
                                      ),
                           )

    # Sub-headings for custom form
    subheadings = {"organisation_id": T("Event Type"),
                   "appointment_type_id": T("Documentation"),
                   "residents_only": T("Restrictions"),
                   }

    # Reconfigure
    s3db.configure("dvr_case_event_type",
                   crud_form = crud_form,
                   subheadings = subheadings,
                   )

# -------------------------------------------------------------------------
def dvr_case_event_type_controller(**attr):

    T = current.T

    db = current.db
    auth = current.auth

    s3 = current.response.s3

    # Selectable organisation
    from ..helpers import managed_orgs_field
    attr["csv_extra_fields"] = [{"label": "Organisation",
                                 "field": managed_orgs_field,
                                 }]

    standard_prep = s3.prep
    def prep(r):
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        # Restrict role_required to managed roles
        from core import S3RoleManager
        managed_roles = S3RoleManager.get_managed_roles(auth.user.id)
        roles = {k for k, v in managed_roles.items() if v["a"]}

        rtable = auth.settings.table_group
        dbset = db(rtable.id.belongs(roles))

        field = table.role_required
        field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "%s.id" % rtable,
                                               field.represent,
                                               ))
        return result
    s3.prep = prep

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        # Import-button
        if not r.record and not r.method and auth.s3_has_permission("create", "dvr_case_event_type"):
            if isinstance(output, dict):
                import_btn = A(T("Import"),
                               _href = r.url(method="import"),
                               _class = "action-btn activity button",
                               )
                showadd_btn = output.get("showadd_btn")
                if showadd_btn:
                    output["showadd_btn"] = TAG[""](import_btn, showadd_btn)
                else:
                    output["showadd_btn"] = import_btn

        return output
    s3.postp = postp

    return attr

# -------------------------------------------------------------------------
def dvr_case_flag_controller(**attr):

    T = current.T
    auth = current.auth

    s3 = current.response.s3

    # Selectable organisation
    from ..helpers import managed_orgs_field
    attr["csv_extra_fields"] = [{"label": "Organisation",
                                 "field": managed_orgs_field,
                                 }]

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        # Import-button
        if not r.record and not r.method and auth.s3_has_permission("create", "dvr_case_flag"):
            if isinstance(output, dict):
                import_btn = A(T("Import"),
                               _href = r.url(method="import"),
                               _class = "action-btn activity button",
                               )
                showadd_btn = output.get("showadd_btn")
                if showadd_btn:
                    output["showadd_btn"] = TAG[""](import_btn, showadd_btn)
                else:
                    output["showadd_btn"] = import_btn

        return output
    s3.postp = postp

    return attr

# -------------------------------------------------------------------------
def dvr_service_contact_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    table = s3db.dvr_service_contact

    field = table.type_id
    field.label = T("Type")

    field = table.organisation_id
    field.readable = field.writable = False

    field = table.organisation
    field.label = T("Organization")
    field.readable = field.writable = True

# =============================================================================
def dvr_person_prep(r):
    """
        Prep-function for dvr/counsel person controller, replaces
        standard dvr/person prep so that it can be called from both
        dvr and counsel controllers
    """
    # TODO integrate in pr_person_controller?

    T = current.T

    db = current.db
    s3db = current.s3db

    s3 = current.response.s3
    settings = current.deployment_settings

    # Set the default case status
    s3db.dvr_case_default_status()

    # Filter to persons who have a case registered
    resource = r.resource
    resource.add_filter(FS("dvr_case.id") != None)

    get_vars = r.get_vars

    CASES = T("Cases")
    CURRENT = T("Current Cases")
    CLOSED = T("Closed Cases")

    # Filters to split case list
    if not r.record:

        # Filter to active/archived cases
        archived = get_vars.get("archived")
        if archived == "1":
            archived = True
            CASES = T("Archived Cases")
            query = FS("dvr_case.archived") == True
        else:
            archived = False
            query = (FS("dvr_case.archived") == False) | \
                    (FS("dvr_case.archived") == None)

        # Filter to open/closed cases
        closed = get_vars.get("closed")
        if closed == "only":
            # Show only closed cases
            CASES = CLOSED
            query &= FS("dvr_case.status_id$is_closed") == True
        elif closed not in {"1", "include"}:
            # Show only open cases (default)
            CASES = CURRENT
            query &= (FS("dvr_case.status_id$is_closed") == False) | \
                     (FS("dvr_case.status_id$is_closed") == None)

        resource.add_filter(query)
    else:
        archived = False

    # Should not be able to delete records in this view
    resource.configure(deletable = False)

    if r.component and r.id:
        ctable = r.component.table
        if "case_id" in ctable.fields and \
           str(ctable.case_id.type)[:18] == "reference dvr_case":

            # Find the Case ID
            dvr_case = s3db.dvr_case
            query = (dvr_case.person_id == r.id) & \
                    (dvr_case.deleted != True)
            cases = db(query).select(dvr_case.id, limitby=(0, 2))

            case_id = ctable.case_id
            if cases:
                # Set default
                case_id.default = cases.first().id
            if len(cases) == 1:
                # Only one case => hide case selector
                case_id.readable = case_id.writable = False
            else:
                # Configure case selector
                case_id.requires = IS_ONE_OF(db(query), "dvr_case.id",
                                             case_id.represent,
                                             )

    if r.interactive:
        s3.crud_strings["pr_person"] = Storage(
            label_create = T("Create Case"),
            title_display = T("Case Details"),
            title_list = CASES,
            title_update = T("Edit Case Details"),
            label_list_button = T("List Cases"),
            label_delete_button = T("Delete Case"),
            msg_record_created = T("Case added"),
            msg_record_modified = T("Case details updated"),
            msg_record_deleted = T("Case deleted"),
            msg_list_empty = T("No Cases currently registered")
            )

        component = r.component
        if not component:
            # Expose the "archived"-flag? (update forms only)
            if r.record and r.method != "read":
                ctable = s3db.dvr_case
                field = ctable.archived
                field.readable = field.writable = True

        elif component.tablename == "dvr_case_activity":

            person_id = r.record.id
            organisation_id = s3db.dvr_case_organisation(person_id)

            # Set default status
            s3db.dvr_case_activity_default_status()

            if settings.get_dvr_vulnerabilities():
                # Limit selectable vulnerabilities to case
                s3db.dvr_configure_case_vulnerabilities(person_id)

            if settings.get_dvr_manage_response_actions():

                # Set defaults for inline responses
                s3db.dvr_set_response_action_defaults()

                # Limit selectable response themes to case organisation
                if settings.get_dvr_response_themes():
                    s3db.dvr_configure_case_responses(organisation_id)

            # Configure CRUD form
            component.configure(crud_form=s3db.dvr_case_activity_form(r))

        elif component.tablename == "dvr_response_action":

            person_id = r.record.id
            organisation_id = s3db.dvr_case_organisation(person_id)

            # Set defaults
            s3db.dvr_set_response_action_defaults()

            if settings.get_dvr_vulnerabilities():
                # Limit selectable vulnerabilities to case
                s3db.dvr_configure_case_vulnerabilities(person_id)

            # Limit selectable response themes to case organisation
            if settings.get_dvr_response_themes():
                s3db.dvr_configure_case_responses(organisation_id)

        elif component.tablename == "dvr_vulnerability":

            person_id = r.record.id
            organisation_id = s3db.dvr_case_organisation(person_id)

            # Limit vulnerabilities by case organisation sectors
            s3db.dvr_configure_vulnerability_types(organisation_id)

            # Set default human_resource_id
            field = component.table.human_resource_id
            field.default = current.auth.s3_logged_in_human_resource()

        elif r.component_name == "patient":
            # On patient-tab of person record
            list_fields = ["date",
                           "unit_id",
                           "refno",
                           "reason",
                           "status",
                           ]
            r.component.configure(crud_form = CustomForm(*list_fields),
                                  subheadings = None,
                                  list_fields = list_fields,
                                  orderby = "%s.date desc" % r.component.tablename,
                                  insertable = False,
                                  editable = False,
                                  deletable = False,
                                  )
            s3.crud_strings["med_patient"] = Storage(
                # label_create = T("Add Treatment Occasion"),
                title_display = T("Treatment Occasion"),
                title_list = T("Treatment Occasions"),
                # title_update = T("Edit Treatment Occasion"),
                label_list_button = T("List Treatment Occasions"),
                # label_delete_button = T("Delete Treatment Occasion"),
                # msg_record_created = T("Treatment Occasion added"),
                # msg_record_modified = T("Treatment Occasion updated"),
                # msg_record_deleted = T("Treatment Occasion deleted"),
                msg_list_empty = T("No Treatment Occasions currently registered"),
                )


        elif r.component_name == "epicrisis":
            # Read-only in this perspective
            r.component.configure(insertable = False,
                                  editable = False,
                                  deletable = False,
                                  )

            ctable = r.component.table

            # Adapt patient_id visibility+label to perspective
            from core import S3Represent
            field = ctable.patient_id
            field.label = T("Treatment Occasion")
            field.readable = True

            # Include is-final flag
            field = ctable.is_final
            field.readable = True

            # Adapt list fields to perspective
            list_fields = ["date",
                           "patient_id",
                           "patient_id$status",
                           "situation",
                           "diagnoses",
                           "is_final",
                           ]
            r.component.configure(list_fields=list_fields)

    return True

# =============================================================================
def dvr_group_membership_prep(r):
    """
        Custom copy of dvr/group_membership prep(), so it can be called
        in proxy controllers too (e.g. counsel/group_membership)
    """

    db = current.db
    s3db = current.s3db

    table = r.table
    resource = r.resource

    # Hide unwanted fields from PersonSelector
    settings = current.deployment_settings
    settings.pr.request_email = False
    settings.pr.request_home_phone = False
    settings.hrm.email_required = False

    viewing = r.viewing
    if viewing:
        if viewing[0] == "pr_person":
            person_id = viewing[1]

            # Get all group_ids with this person_id
            gtable = s3db.pr_group
            join = gtable.on(gtable.id == table.group_id)
            query = (table.person_id == person_id) & \
                    (gtable.group_type == 7) & \
                    (table.deleted != True)
            rows = db(query).select(table.group_id, join=join)
            group_ids = set(row.group_id for row in rows)

            # Hide the link for this person (to prevent changes/deletion)
            if group_ids:
                # Single group ID?
                group_id = tuple(group_ids)[0] if len(group_ids) == 1 else None
            elif r.http == "POST":
                name = s3_fullname(person_id)
                group_id = gtable.insert(name=name, group_type=7)
                s3db.update_super(gtable, {"id": group_id})
                table.insert(group_id = group_id,
                                person_id = person_id,
                                group_head = True,
                                )
                group_ids = {group_id}
            resource.add_filter(FS("person_id") != person_id)
        else:
            group_ids = set()

        # Show only links for relevant cases
        # NB Filter also prevents showing all links if case_ids is empty
        if not r.id:
            if len(group_ids) == 1:
                r.resource.add_filter(FS("group_id") == group_id)
            else:
                r.resource.add_filter(FS("group_id").belongs(group_ids))

        list_fields = ["person_id",
                       "person_id$gender",
                       "person_id$date_of_birth",
                       ]

        if len(group_ids) == 0:
            # No case group exists, will be auto-generated on POST,
            # hide the field in the form:
            field = table.group_id
            field.readable = field.writable = False
        elif len(group_ids) == 1:
            field = table.group_id
            field.default = group_id
            # If we have only one relevant case, then hide the group ID:
            field.readable = field.writable = False
        elif len(group_ids) > 1:
            # Show the case ID in list fields if there is more than one
            # relevant case
            list_fields.insert(0, "group_id")
        r.resource.configure(list_fields = list_fields)

    # Do not allow update of person_id
    if r.id:
        field = table.person_id
        field.writable = False
        field.comment = None

    return True

# END =========================================================================
