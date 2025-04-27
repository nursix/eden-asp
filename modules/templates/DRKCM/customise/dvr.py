"""
    DVR module customisations for DRKCM

    License: MIT
"""

import datetime

from collections import OrderedDict

from gluon import current, IS_EMPTY_OR, IS_FLOAT_IN_RANGE, IS_IN_SET, IS_LENGTH
from gluon.storage import Storage

from core import FS, IS_ONE_OF, PopupLink, CustomForm, \
                 get_form_record_data, get_form_record_id

from ..uioptions import get_ui_options

# -------------------------------------------------------------------------
def dvr_home():
    """ Do not redirect to person-controller """

    return {"module_name": current.T("Case Consulting"),
            }

# -------------------------------------------------------------------------
def get_case_root_org(person_id):
    """
        Returns the root organisation managing a case

        Args:
            person_id: the person record ID

        Returns:
            the root organisation record ID
    """

    db = current.db
    s3db = current.s3db

    if person_id:
        ctable = s3db.dvr_case
        otable = s3db.org_organisation
        left = otable.on(otable.id == ctable.organisation_id)
        query = (ctable.person_id == person_id) & \
                (ctable.archived == False) & \
                (ctable.deleted == False)
        row = db(query).select(otable.root_organisation,
                               left = left,
                               limitby = (0, 1),
                               orderby = ~ctable.modified_on,
                               ).first()
        case_root_org = row.root_organisation if row else None
    else:
        case_root_org = None

    return case_root_org

# -------------------------------------------------------------------------
def dvr_case_onaccept(form):
    """
        Additional custom-onaccept for dvr_case to:
        * Force-update the realm entity of the person record:
          - the organisation managing the case is the realm-owner,
            but the person record is written first, so we need to
            update it after writing the case
          - the case can be transferred to another organisation/branch,
            and then the person record needs to be transferred to that
            same realm as well
        * Update the Population of all Shelters
        * Update the Location of the person record:
          - if the Case is linked to a Site then use that for the Location of
            the Person
          - otherwise use the Private Address
    """

    try:
        form_vars = form.vars
    except AttributeError:
        return

    record_id = form_vars.id
    if not record_id:
        # Nothing we can do
        return

    db = current.db
    s3db = current.s3db

    # Update the Population of all Shelters
    from .cr import cr_shelter_population
    cr_shelter_population()

    # Get the Person ID & Site ID for this case
    person_id = form_vars.person_id
    if not person_id or "site_id" not in form_vars:
        # Reload the record
        table = s3db.dvr_case
        query = (table.id == record_id)
        row = db(query).select(table.person_id,
                               table.site_id,
                               limitby = (0, 1),
                               ).first()

        if row:
            person_id = row.person_id
            site_id = row.site_id
    else:
        site_id = form_vars.site_id

    if person_id:

        set_realm_entity = current.auth.set_realm_entity

        from .pr import pr_person_set_realm_components
        pr_person_set_realm_components()

        # Force-update the realm entity for the person
        set_realm_entity("pr_person", person_id, force_update=True)

        # Configure components to inherit realm entity
        # from the case activity record
        s3db.configure("dvr_case_activity",
                       realm_components = ("case_activity_need",
                                           "case_activity_update",
                                           ),
                       )

        # Force-update the realm entity for all case activities
        # linked to the person_id
        atable = s3db.dvr_case_activity
        query = (atable.person_id == person_id)
        set_realm_entity(atable, query, force_update=True)

        # Update the person's location_id
        ptable = s3db.pr_person
        location_id = None

        if site_id:
            # Use the Shelter's Address
            stable = s3db.org_site
            site = db(stable.site_id == site_id).select(stable.location_id,
                                                        limitby = (0, 1),
                                                        ).first()
            if site:
                location_id = site.location_id
        else:
            # Use the Private Address (no need to filter by address type as only
            # 'Current Address' is exposed)
            # NB If this is a New/Modified Address then this won't be caught here
            # - we use pr_address_onaccept to catch those
            atable = s3db.pr_address
            query = (ptable.id == person_id) & \
                    (ptable.pe_id == atable.pe_id) & \
                    (atable.deleted == False)
            address = db(query).select(atable.location_id,
                                       limitby = (0, 1),
                                       ).first()
            if address:
                location_id = address.location_id

        db(ptable.id == person_id).update(location_id = location_id,
                                          # Indirect update by system rule,
                                          # do not change modified_* fields:
                                          modified_on = ptable.modified_on,
                                          modified_by = ptable.modified_by,
                                          )

# -------------------------------------------------------------------------
def dvr_case_resource(r, tablename):

    s3db = current.s3db

    ctable = s3db.dvr_case

    if r.function == "group_membership":
        viewing = r.viewing
        if viewing and viewing[0] == "pr_person":
            # New cases created on family tab inherit organisation_id
            # and human_resource_id from master case:
            ctable = s3db.dvr_case
            query = (ctable.person_id == viewing[1]) & \
                    (ctable.archived == False) & \
                    (ctable.deleted == False)
            case = current.db(query).select(ctable.organisation_id,
                                            ctable.human_resource_id,
                                            limitby = (0, 1),
                                            ).first()
            if case:
                ctable.organisation_id.default = case.organisation_id
                ctable.human_resource_id.default = case.human_resource_id

    # Custom onaccept to update realm-entity of the
    # beneficiary and case activities of this case
    # (incl. their respective realm components)
    s3db.add_custom_callback("dvr_case", "onaccept", dvr_case_onaccept)

    # Update the realm-entity when the case gets updated
    # (because the assigned organisation/branch can change)
    s3db.configure("dvr_case", update_realm = True)

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

    db = current.db
    s3db = current.s3db

    ttable = current.s3db.dvr_note_type
    if r.component_name == "todo":
        table = r.component.table

        r.component.add_filter(FS("note_type_id$is_task") == True)
        dbset = db(ttable.is_task == True)

        T = current.T

        # Alternative label for task type
        field = table.note_type_id
        field.label = T("Task Type")

        # Alternative label for note text
        field = table.note
        field.label = T("Details")
        field.widget = None

        # Expose Status
        field = table.status
        field.readable = field.writable = True

        # Alternative CRUD strings
        current.response.s3.crud_strings["dvr_note"] = Storage(
            label_create = T("Create Task List"),
            title_display = T("Task List"),
            title_list = T("Task Lists"),
            title_update = T("Edit Task List"),
            label_list_button = T("All Task Lists"),
            label_delete_button = T("Delete Task List"),
            msg_record_created = T("Task List added"),
            msg_record_modified = T("Task List updated"),
            msg_record_deleted = T("Task List deleted"),
            msg_list_empty = T("No Task Lists found"),
            )

    elif r.component_name == "case_note":
        # Notes-tab
        table = r.component.table
        r.component.add_filter(FS("note_type_id$is_task") == False)
        dbset = db(ttable.is_task == False)
    elif r.tablename == "dvr_note":
        # Primary controller
        table = r.resource.table
        dbset = db(ttable.is_task == False)
    else:
        return

    # Consistent ordering of notes (newest on top)
    field = table.date
    field.represent.dt_orderby = note_date_dt_orderby
    s3db.configure("dvr_note",
                   orderby = "%(tn)s.date desc,%(tn)s.created_on desc" % \
                             {"tn": table._tablename},
                   pdf_format = "list",
                   pdf_fields = ["date", "status", "note"],
                   )

    # Filter note-type selector
    field = table.note_type_id
    field.requires = IS_ONE_OF(dbset, "dvr_note_type.id", field.represent)
    options = dbset.select(ttable.id, limitby=(0, 2))
    if len(options) == 1:
        # Single option => default+hide
        field.default = options.first().id
        field.readable = field.writable = False

# -------------------------------------------------------------------------
def configure_case_activity_reports(status_id = None,
                                    use_sector = False,
                                    use_need = False,
                                    use_priority = False,
                                    use_theme = False,
                                    ):
    """
        Configures reports for case activities

        Args:
            status_id: the status field
            use_sector: activities use sectors
            use_need: use need type in activities
            use_priority: activities have priorities
            use_theme: response actions have themes
    """

    T = current.T

    # Custom Report Options
    facts = ((T("Number of Activities"), "count(id)"),
             (T("Number of Clients"), "count(person_id)"),
             )
    axes = ["person_id$gender",
            "person_id$person_details.nationality",
            "person_id$person_details.marital_status",
            ]

    if use_theme:
        axes.append((T("Theme"), "response_action.response_theme_ids"))
        default_rows = "response_action.response_theme_ids"
    else:
        default_rows = "person_id$person_details.nationality"
    if use_priority:
        axes.insert(-1, "priority")

    if use_sector:
        axes.insert(-1, "sector_id")
        default_rows = "sector_id"
    if use_need:
        axes.insert(-1, "need_id")
        default_rows = "need_id"
    if status_id == "status_id":
        axes.insert(3, status_id)

    report_options = {
        "rows": axes,
        "cols": axes,
        "fact": facts,
        "defaults": {"rows": default_rows,
                     "cols": None,
                     "fact": "count(id)",
                     "totals": True,
                     },
        }
    current.s3db.configure("dvr_case_activity",
                           report_options = report_options,
                           )

# -------------------------------------------------------------------------
def configure_case_activity_filters(r,
                                    ui_options,
                                    use_priority = False,
                                    emergencies = False,
                                    ):
    """
        Configure filters for case activity list

        Args:
            r: the CRUDRequest
            ui_options: the UI options
            use_priority: expose the priority
            emergencies: list is prefiltered for emergency-priority
    """

    resource = r.resource

    from core import TextFilter, OptionsFilter

    T = current.T
    db = current.db
    s3db = current.s3db

    # Sector filter options
    # - field options are configured in dvr_case_activity_sector
    sector_id = resource.table.sector_id
    sector_options = {k:v for k, v in sector_id.requires.options() if k}

    # Status filter options + defaults, status list field
    if ui_options.get("activity_closure"):
        stable = s3db.dvr_case_activity_status
        query = (stable.deleted == False)
        rows = db(query).select(stable.id,
                                stable.name,
                                stable.is_closed,
                                cache = s3db.cache,
                                orderby = stable.workflow_position,
                                )
        status_filter_options = OrderedDict((row.id, T(row.name)) for row in rows)
        status_filter_defaults = [row.id for row in rows if not row.is_closed]
        status_filter = OptionsFilter("status_id",
                                        options = status_filter_options,
                                        cols = 3,
                                        default = status_filter_defaults,
                                        sort = False,
                                        )
    else:
        status_filter = None

    # Filter widgets
    filter_widgets = [
        TextFilter(["person_id$pe_label",
                    "person_id$first_name",
                    "person_id$last_name",
                    "need_details",
                    ],
                    label = T("Search"),
                    ),
        OptionsFilter("person_id$person_details.nationality",
                      label = T("Client Nationality"),
                      hidden = True,
                      ),
        ]

    if sector_id.readable:
        filter_widgets.insert(1, OptionsFilter("sector_id",
                                                hidden = True,
                                                options = sector_options,
                                                ))
    if status_filter:
        filter_widgets.insert(1, status_filter)

    # Priority filter (unless pre-filtered to emergencies anyway)
    if use_priority and not emergencies:
        field = resource.table.priority
        priority_opts = OrderedDict(field.requires.options())
        priority_filter = OptionsFilter("priority",
                                        options = priority_opts,
                                        cols = 4,
                                        sort = False,
                                        )
        filter_widgets.insert(2, priority_filter)

    # Can the user see cases from more than one org?
    from ..helpers import case_read_multiple_orgs
    multiple_orgs = case_read_multiple_orgs()[0]
    if multiple_orgs:
        # Add org-filter widget
        filter_widgets.insert(1, OptionsFilter("person_id$dvr_case.organisation_id"))

    # Person responsible filter
    if not r.get_vars.get("mine"):
        filter_widgets.insert(2, OptionsFilter("human_resource_id"))

    # Reconfigure table
    resource.configure(filter_widgets = filter_widgets,
                        )

# -------------------------------------------------------------------------
def configure_case_activity_sector(r, table, case_root_org):
    """
        Configures the case activity sector_id field

        Args:
            r: the CRUDRequest
            table: the case activity table
            case_root_org: the ID of the case root organisation
    """

    db = current.db
    s3db = current.s3db

    field = table.sector_id
    field.comment = None

    if case_root_org:
        # Limit the sector selection
        ltable = s3db.org_sector_organisation
        query = (ltable.organisation_id == case_root_org) & \
                (ltable.deleted == False)
        rows = db(query).select(ltable.sector_id)
        sector_ids = set(row.sector_id for row in rows)

        # Default sector
        if len(sector_ids) == 1:
            default_sector_id = rows.first().sector_id
        else:
            default_sector_id = None

        # Include the sector_id of the current record (if any)
        record = None
        component = r.component
        if not component:
            if r.tablename == "dvr_case_activity":
                record = r.record
        elif component.tablename == "dvr_case_activity" and r.component_id:
            query = table.id == r.component_id
            record = db(query).select(table.sector_id,
                                      limitby = (0, 1),
                                      ).first()
        if record and record.sector_id:
            sector_ids.add(record.sector_id)

        # Set selectable sectors
        subset = db(s3db.org_sector.id.belongs(sector_ids))
        field.requires = IS_EMPTY_OR(IS_ONE_OF(subset, "org_sector.id",
                                               field.represent,
                                               ))

        # Default selection?
        if len(sector_ids) == 1 and default_sector_id:
            # Single option => set as default and hide selector
            field.default = default_sector_id
            field.readable = field.writable = False

# -------------------------------------------------------------------------
def configure_case_activity_subject(r,
                                    table,
                                    case_root_org,
                                    person_id,
                                    use_need = False,
                                    use_subject = False,
                                    autolink = False,
                                    ):
    """
        Configures the subject field(s) for case activities
            - need_id, or simple free-text subject

        Args:
            table: the case activity table
            case_root_org: the ID of the case root organisation
            person_id: the person ID of the case
            use_need: activities use need types
            use_subject: activities use free-text subject field
            autolink: whether response actions shall be automatically
                      linked to case activities
    """

    T = current.T
    db = current.db
    s3db = current.s3db

    if use_need:
        # Are we looking at a particular case activity?
        if r.tablename != "dvr_case_activity":
            activity_id = r.component_id
        else:
            activity_id = r.id

        # Expose need_id
        field = table.need_id
        if not use_subject:
            field.label = T("Counseling Reason")
        field.readable = True
        field.writable = not activity_id or not autolink

        # Limit to org-specific need types
        ntable = s3db.dvr_need
        if case_root_org:
            query = (ntable.organisation_id == case_root_org)
        else:
            query = None

        # With autolink, prevent multiple activities per need type
        if autolink:
            joinq = (table.need_id == ntable.id) & \
                    (table.person_id == person_id) & \
                    (table.deleted == False)
            if activity_id:
                joinq &= (table.id != activity_id)
            left = table.on(joinq)
            q = (table.id == None)
            query = query & q if query else q
        else:
            left = None

        if query:
            field.requires = IS_ONE_OF(db(query), "dvr_need.id",
                                       field.represent,
                                       left = left,
                                       )

    if use_subject:
        # Expose simple free-text subject
        field = table.subject
        field.readable = field.writable = True
        requires = IS_LENGTH(512, minsize=1)
        if use_need:
            # Subject optional when using needs
            requires = IS_EMPTY_OR(requires)
        field.requires = requires

# -------------------------------------------------------------------------
def configure_inline_responses(person_id,
                               human_resource_id,
                               hr_represent,
                               use_theme = False,
                               ):
    """
        Configures the inline-responses for case activity form
            - can be either response_action or response_action_theme

        Args:
            person_id: the person ID of the case
            human_resource_id: the HR-ID of the consultant in charge
            hr_represent: representation function for human_resource_id
            use_theme: use theme(s) with responses

        Returns:
            InlineComponent
    """

    T = current.T
    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    rtable = s3db.dvr_response_action

    from core import InlineComponent, SubFormLayoutVertical

    if use_theme and settings.get_dvr_response_themes_details():
        # Expose response_action_theme inline

        if settings.get_dvr_response_themes_efforts():
            # Cannot edit inline theme details
            readonly = True
        else:
            # Can add and edit inline theme details
            readonly = False

            # Filter action_id in inline response_themes to same beneficiary
            ltable = s3db.dvr_response_action_theme
            field = ltable.action_id
            dbset = db(rtable.person_id == person_id) if person_id else db
            field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "dvr_response_action.id",
                                                   field.represent,
                                                   orderby = ~rtable.start_date,
                                                   sort = False,
                                                   ))

        # Inline-component
        inline_responses = InlineComponent(
                                "response_action_theme",
                                fields = ["action_id",
                                          "theme_id",
                                          "comments",
                                          ],
                                label = T("Themes"),
                                orderby = "action_id",
                                readonly = readonly,
                                )
    else:
        # Expose response_action inline

        # Set the person_id for inline responses (does not not happen
        # automatically since using case_activity_id as component key)
        if person_id:
            field = rtable.person_id
            field.default = person_id

        # Configure consultant in charge
        field = rtable.human_resource_id
        field.default = human_resource_id
        field.represent = hr_represent
        field.widget = field.comment = None

        # Require explicit unit in hours-widget above 4 hours
        from core import S3HoursWidget
        field = rtable.hours
        field.widget = S3HoursWidget(precision=2, explicit_above=4)

        # Add custom callback to validate inline responses
        s3db.add_custom_callback("dvr_response_action",
                                 "onvalidation",
                                 response_action_onvalidation,
                                 )

        # Inline-component
        response_theme_ids = "response_theme_ids" if use_theme else None
        response_action_fields = ["start_date",
                                  response_theme_ids,
                                  "comments",
                                  "human_resource_id",
                                  "status_id",
                                  "hours",
                                  ]
        if settings.get_dvr_response_due_date():
            response_action_fields.insert(-2, "date_due")
        if settings.get_dvr_response_types():
            response_action_fields.insert(1, "response_type_id")

        inline_responses = InlineComponent(
                                "response_action",
                                fields = response_action_fields,
                                label = T("Actions"),
                                layout = SubFormLayoutVertical,
                                explicit_add = T("Add Action"),
                                )

    return inline_responses

# -------------------------------------------------------------------------
def configure_case_activity(r):

    T = current.T
    s3db = current.s3db
    auth = current.auth

    table = s3db.dvr_case_activity

    if r.method == "count_due_followups":
        # Just counting due followups => skip customisation
        return

    human_resource_id = auth.s3_logged_in_human_resource()

    ui_options = get_ui_options()
    ui_options_get = ui_options.get

    use_priority = ui_options_get("activity_priority")

    # Optional: closure details
    if ui_options_get("activity_closure"):
        # Activities can be closed
        status_id = "status_id"
        end_date = "end_date"
        outcome = "outcome"
    else:
        # Activities are never closed
        status_id = None
        table.start_date.label = T("Date")
        end_date = None
        outcome = None

    # Deployment-specific terminology for case activities
    crud_strings = current.response.s3.crud_strings["dvr_case_activity"]
    crud_strings.update({
        "label_create": T("Add Counseling Reason"),
        "title_display": T("Counseling Reason Details"),
        "title_list": T("Counseling Reasons"),
        "title_update": T("Edit Counseling Reason"),
        "title_report": T("Activity Statistic"),
        "label_list_button": T("List Counseling Reasons"),
        "label_delete_button": T("Delete Counseling Reason"),
        "msg_record_created": T("Counseling Reason added"),
        "msg_record_modified": T("Counseling Reason updated"),
        "msg_record_deleted": T("Counseling Reason deleted"),
        })

    # Need type and subject
    subject_type = ui_options_get("activity_subject_type")
    use_need = subject_type in ("need", "both")
    use_subject = subject_type in ("subject", "both") or not use_need

    need_label = T("Counseling Reason") if not use_subject else T("Need Type")

    need_id = (need_label, "need_id") if use_need else None
    subject = "subject" if use_subject else None

    # Using sectors?
    activity_use_sector = ui_options_get("activity_use_sector")

    if r.interactive or r.representation in ("aadata", "json", "xlsx", "pdf"):

        # Fields and CRUD-Form
        from core import InlineComponent, \
                         InlineLink, \
                         SubFormLayoutVertical

        # Get person_id, case_activity_id and case activity record
        person_id = case_activity_id = case_activity = None
        if r.tablename == "pr_person":
            # On activities-tab of a case
            person_id = r.record.id if r.record else None
            component = r.component
            if component and component.tablename == "dvr_case_activity":
                case_activity_id = r.component_id

        elif r.tablename == "dvr_case_activity":
            # Primary case activity controller
            case_activity = r.record
            if case_activity:
                person_id = case_activity.person_id
                case_activity_id = r.id

        # Get the root org of the case
        case_root_org = get_case_root_org(person_id)
        if not case_root_org:
            case_root_org = auth.root_org()

        # Represent person_id as link (both list_fields and read-form, in primary controller)
        field = table.person_id
        field.represent = s3db.pr_PersonRepresent(show_link = True)

        # Configure sector_id
        field = table.sector_id
        if activity_use_sector:
            configure_case_activity_sector(r, table, case_root_org)
        else:
            field.readable = field.writable = False

        # Configure subject field (alternatives)
        autolink = ui_options_get("response_activity_autolink")
        configure_case_activity_subject(r,
                                        table,
                                        case_root_org,
                                        person_id,
                                        use_need = use_need,
                                        use_subject = use_subject,
                                        autolink = autolink,
                                        )

        # Show need details (optional)
        field = table.need_details
        field.readable = field.writable = ui_options_get("activity_need_details")

        # Embed PSS Diagnoses
        if ui_options_get("activity_pss_diagnoses"):
            suspected_diagnosis = InlineLink("suspected_diagnosis",
                                             label = T("Suspected Diagnosis"),
                                             field = "diagnosis_id",
                                             selectedList = 5,
                                             #multiple = False,
                                             )
            confirmed_diagnosis = InlineLink("confirmed_diagnosis",
                                             label = T("Diagnosis"),
                                             field = "diagnosis_id",
                                             selectedList = 5,
                                             #multiple = False,
                                             )
        else:
            suspected_diagnosis = confirmed_diagnosis = None

        # Customise Priority
        from ..helpers import PriorityRepresent
        field = table.priority
        priority_opts = [(0, T("Emergency")),
                         (1, T("High")),
                         (2, T("Normal")),
                         (3, T("Low")),
                         ]
        field.readable = field.writable = use_priority
        field.label = T("Priority")
        field.default = 2
        field.requires = IS_IN_SET(priority_opts, sort=False, zero=None)
        field.represent = PriorityRepresent(priority_opts,
                                            {0: "red",
                                             1: "blue",
                                             2: "lightblue",
                                             3: "grey",
                                             }).represent
        priority_field = "priority" if use_priority else None

        # Show human_resource_id
        hr_represent = s3db.hrm_HumanResourceRepresent(show_link=False)
        field = table.human_resource_id
        field.comment = None
        field.default = human_resource_id
        field.label = T("Consultant in charge")
        field.readable = field.writable = True
        field.represent = hr_represent
        field.widget = None

        # Show end_date field (read-only)
        if end_date is not None:
            field = table.end_date
            field.label = T("Completed on")
            field.readable = True

        # Show comments
        field = table.comments
        field.readable = field.writable = ui_options_get("activity_comments")

        if r.representation == "popup":
            # Reduced form for popup (create-only)
            crud_fields = ["person_id",
                           "sector_id",
                           need_id,
                           subject,
                           suspected_diagnosis,
                           confirmed_diagnosis,
                           (T("Initial Situation Details"), ("need_details")),
                           "start_date",
                           priority_field,
                           "human_resource_id",
                           "comments",
                           ]
        else:
            # Inline-responses
            use_theme = ui_options_get("response_use_theme")
            if use_theme:
                configure_response_action_theme(ui_options,
                                                case_root_org = case_root_org,
                                                case_activity = case_activity,
                                                case_activity_id = case_activity_id,
                                                )
            inline_responses = configure_inline_responses(person_id,
                                                          human_resource_id,
                                                          hr_represent,
                                                          use_theme = use_theme,
                                                          )

            # Inline updates
            utable = current.s3db.dvr_case_activity_update
            field = utable.human_resource_id
            field.default = human_resource_id
            field.represent = hr_represent
            field.widget = field.comment = None

            # Inline attachments
            dtable = s3db.doc_document
            field = dtable.date
            field.default = r.utcnow.date()

            # Custom onaccept to make sure each document has a title
            # (doc_document_onvalidation does not apply here)
            from .doc import document_onaccept
            s3db.add_custom_callback("doc_document",
                                     "onaccept",
                                     document_onaccept,
                                     )

            crud_fields = ["person_id",
                           "sector_id",
                           need_id,
                           subject,
                           suspected_diagnosis,
                           confirmed_diagnosis,
                           (T("Initial Situation Details"), ("need_details")),
                           "start_date",
                           priority_field,
                           "human_resource_id",
                           inline_responses,
                           "followup",
                           "followup_date",
                           InlineComponent("case_activity_update",
                                           label = T("Progress"),
                                           fields = ["date",
                                                     (T("Occasion"), "update_type_id"),
                                                     "human_resource_id",
                                                     "comments",
                                                     ],
                                           layout = SubFormLayoutVertical,
                                           explicit_add = T("Add Entry"),
                                           ),
                           status_id,
                           end_date,
                           outcome,
                           InlineComponent("document",
                                           name = "file",
                                           label = T("Attachments"),
                                           fields = ["file", "comments"],
                                           filterby = {"field": "file",
                                                       "options": "",
                                                       "invert": True,
                                                       },
                                           ),
                           "comments",
                           ]

        s3db.configure("dvr_case_activity",
                       crud_form = CustomForm(*crud_fields),
                       orderby = "dvr_case_activity.priority" \
                                 if use_priority else "dvr_case_activity.start_date desc",
                       )

        # List fields
        sector_id = "sector_id" if table.sector_id.readable else None
        if r.tablename == "dvr_case_activity":
            # Activity list

            if ui_options_get("case_use_pe_label"):
                pe_label = (T("ID"), "person_id$pe_label")
            else:
                pe_label = None

            human_resource_id = "human_resource_id" \
                                if not r.get_vars.get("mine") else None

            list_fields = ["priority" if use_priority else None,
                           pe_label,
                           (T("Case"), "person_id"),
                           sector_id,
                           need_id,
                           subject,
                           "start_date",
                           human_resource_id,
                           status_id,
                           ]

        else:
            # Activity tab
            list_fields = ["priority" if use_priority else None,
                           sector_id,
                           need_id,
                           subject,
                           "start_date",
                           "human_resource_id",
                           status_id,
                           ]

        s3db.configure("dvr_case_activity",
                       list_fields = list_fields,
                       )

    # Report options
    if r.method == "report":
        configure_case_activity_reports(status_id = status_id,
                                        use_sector = activity_use_sector,
                                        use_need = use_need,
                                        use_priority = use_priority,
                                        use_theme = use_theme,
                                        )

    # Configure components to inherit realm entity
    # from the case activity record
    s3db.configure("dvr_case_activity",
                   realm_components = ("case_activity_need",
                                       "case_activity_update",
                                       "response_action",
                                       ),
                   )

# -------------------------------------------------------------------------
def dvr_case_activity_resource(r, tablename):

    s3db = current.s3db

    # Add custom components
    s3db.add_components("dvr_case_activity",
                        dvr_diagnosis = (
                                {"name": "suspected_diagnosis",
                                 "link": "dvr_diagnosis_suspected",
                                 "joinby": "case_activity_id",
                                 "key": "diagnosis_id",
                                 },
                                {"name": "confirmed_diagnosis",
                                 "link": "dvr_diagnosis_confirmed",
                                 "joinby": "case_activity_id",
                                 "key": "diagnosis_id",
                                 },
                                ),
                        )

# -------------------------------------------------------------------------
def dvr_case_activity_controller(**attr):

    T = current.T

    s3 = current.response.s3
    settings = current.deployment_settings

    settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        resource = r.resource

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        # Reconfigure dvr_case_activity
        # - overriding some default prep modifications
        configure_case_activity(r)

        # Configure person tags
        from .pr import configure_person_tags
        configure_person_tags()

        # Get UI options
        ui_options = get_ui_options()
        use_priority = ui_options.get("activity_priority")

        # Adapt list title when filtering for priority 0 (Emergency)
        if use_priority and r.get_vars.get("~.priority") == "0":
            emergencies = True
            s3.crud_strings["dvr_case_activity"]["title_list"] = T("Emergencies")
        else:
            emergencies = False

        # Filter to active cases
        if not r.record:
            query = (FS("person_id$dvr_case.archived") == False) | \
                    (FS("person_id$dvr_case.archived") == None)
            resource.add_filter(query)

        if not r.component and not r.record:

            configure_case_activity_filters(r,
                                            ui_options,
                                            use_priority = use_priority,
                                            emergencies = emergencies,
                                            )
            if r.representation == "popup":
                resource.configure(insertable = True)

        return result
    s3.prep = custom_prep

    return attr

# -------------------------------------------------------------------------
def dvr_case_appointment_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    ui_options = get_ui_options()

    # Organizer popups
    if r.tablename == "pr_person":
        title = "type_id"
        description = ["status",
                       "comments",
                       ]
    elif r.tablename == "dvr_case_appointment":
        title = "person_id"
        description = ["type_id",
                       "status",
                       "comments",
                       ]
        if ui_options.get("case_use_pe_label"):
            description.insert(0, (T("ID"), "person_id$pe_label"))
    else:
        title = description = None

    table = s3db.dvr_case_appointment

    field = table.status
    # Using only a subset of the standard status opts
    appointment_status_opts = {#1: T("Planning"),
                               2: T("Planned"),
                               #3: T("In Progress"),
                               4: T("Completed##appointment"),
                               5: T("Missed"),
                               6: T("Cancelled"),
                               #7: T("Not Required"),
                               }
    field.default = 2
    field.requires = IS_IN_SET(appointment_status_opts,
                               zero = None,
                               )

    if ui_options.get("appointments_staff_link"):
        # Enable staff link and default to logged-in user
        field = table.human_resource_id
        field.default = current.auth.s3_logged_in_human_resource()
        field.readable = field.writable = True
        field.represent = s3db.hrm_HumanResourceRepresent(show_link=False)
        field.widget = None
        # Also show staff link in organizer popup
        if description:
            description.insert(-1, "human_resource_id")

    # Configure Organizer
    if title:
        s3db.configure("dvr_case_appointment",
                       organize = {"start": "date",
                                   "title": title,
                                   "description": description,
                                   },
                       )

# -------------------------------------------------------------------------
def dvr_case_appointment_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    ui_options = get_ui_options()

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource

        # Filter to active cases
        if not r.record:
            query = (FS("person_id$dvr_case.archived") == False) | \
                    (FS("person_id$dvr_case.archived") == None)
            resource.add_filter(query)

        if not r.component:

            from .pr import configure_person_tags
            configure_person_tags()
            use_pe_label = ui_options.get("case_use_pe_label")

            if r.interactive and not r.id:

                # Custom filter widgets
                from core import TextFilter, OptionsFilter, DateFilter, get_filter_options
                filter_widgets = [
                    TextFilter(["person_id$pe_label",
                                "person_id$first_name",
                                "person_id$last_name",
                                ],
                                label = T("Search"),
                                ),
                    OptionsFilter("type_id",
                                  options = get_filter_options("dvr_case_appointment_type",
                                                               translate = True,
                                                               ),
                                  cols = 3,
                                  ),
                    OptionsFilter("status",
                                  options = s3db.dvr_appointment_status_opts,
                                  default = 2,
                                  ),
                    DateFilter("date",
                               ),
                    OptionsFilter("person_id$dvr_case.status_id$is_closed",
                                  cols = 2,
                                  default = False,
                                  #hidden = True,
                                  label = T("Case Closed"),
                                  options = {True: T("Yes"),
                                             False: T("No"),
                                             },
                                  ),
                    ]

                if use_pe_label:
                    filter_widgets.append(
                        TextFilter(["person_id$pe_label"],
                                   label = T("IDs"),
                                   match_any = True,
                                   hidden = True,
                                   comment = T("Search for multiple IDs (separated by blanks)"),
                                   ))

                resource.configure(filter_widgets = filter_widgets)

            # Default filter today's and tomorrow's appointments
            from core import set_default_filter
            now = r.utcnow
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + datetime.timedelta(days=1)
            set_default_filter("~.date",
                               {"ge": today, "le": tomorrow},
                               tablename = "dvr_case_appointment",
                               )

            # Field Visibility
            table = resource.table
            field = table.case_id
            field.readable = field.writable = False

            # Optional: ID
            if use_pe_label:
                pe_label = (T("ID"), "person_id$pe_label")
            else:
                pe_label = None

            # Custom list fields
            list_fields = [pe_label,
                           "person_id$first_name",
                           "person_id$last_name",
                           "type_id",
                           "date",
                           "status",
                           "comments",
                           ]

            if r.representation in ("xlsx", "xls"):
                # Include Person UUID
                list_fields.append(("UUID", "person_id$uuid"))

            resource.configure(list_fields = list_fields,
                               insertable = False,
                               deletable = False,
                               update_next = r.url(method=""),
                               )

        return result
    s3.prep = custom_prep

    return attr

# -------------------------------------------------------------------------
def dvr_case_flag_resource(r, tablename):

    table = current.s3db.dvr_case_flag

    # Hide unwanted fields
    unused = ("advise_at_check_in",
              "advise_at_check_out",
              "advise_at_id_check",
              "instructions",
              "deny_check_in",
              "deny_check_out",
              "allowance_suspended",
              "is_not_transferable",
              "is_external",
              )

    for fieldname in unused:
        field = table[fieldname]
        field.readable = field.writable = False

# -------------------------------------------------------------------------
def dvr_need_resource(r, tablename):

    T = current.T

    table = current.s3db.dvr_need

    # Expose code
    field = table.code
    field.readable = field.writable = True

    # Expose organisation_id (only relevant for ADMINs)
    field = table.organisation_id
    field.readable = field.writable = True

    # Expose protection flag
    field = table.protection
    field.readable = field.writable = True

    # Custom CRUD Strings
    current.response.s3.crud_strings["dvr_need"] = Storage(
        label_create = T("Create Counseling Reason"),
        title_display = T("Counseling Reason Details"),
        title_list = T("Counseling Reason"),
        title_update = T("Edit Counseling Reason"),
        label_list_button = T("List Counseling Reasons"),
        label_delete_button = T("Delete Counseling Reason"),
        msg_record_created = T("Counseling Reason created"),
        msg_record_modified = T("Counseling Reason updated"),
        msg_record_deleted = T("Counseling Reason deleted"),
        msg_list_empty = T("No Counseling Reasons currently defined"),
        )

# -------------------------------------------------------------------------
def response_action_onvalidation(form):
    """
        Onvalidation for response actions:
            - make sure an initial consultation is documented before
              any follow-up consultations
            - enforce hours for closed-statuses (org-specific UI option)
    """

    T = current.T

    db = current.db
    s3db = current.s3db

    table = s3db.dvr_response_action
    ttable = s3db.dvr_response_type
    stable = s3db.dvr_response_status

    # Get form record data
    data = get_form_record_data(form, table, ["person_id",
                                              "response_type_id",
                                              "status_id",
                                              ])

    ui_options = get_ui_options()
    if ui_options.get("response_types"):
        record_id = get_form_record_id(form)

        follow_up_types = ("FUP", "FUP+I")
        query = (ttable.id == data.get("response_type_id"))
        row = db(query).select(ttable.code,
                               ttable.is_consultation,
                               limitby = (0, 1),
                               ).first()

        # If this is a follow-up consultation, make sure that an initial
        # consultation has already been documented for the client
        if row and row.is_consultation and row.code in follow_up_types:
            initial_types = ("INI", "INI+I")
            join = [ttable.on((ttable.id == table.response_type_id) & \
                              (ttable.is_consultation == True) & \
                              (ttable.code.belongs(initial_types))),
                    stable.on((stable.id == table.status_id) & \
                              (stable.is_canceled == False)),
                    ]
            query = (table.person_id == data.get("person_id")) & \
                    (table.deleted == False)
            if record_id:
                query = (table.id != record_id) & query
            initial = db(query).select(table.id, join=join, limitby=(0, 1)).first()
            if not initial:
                form.errors["response_type_id"] = T("No initial consultation registered yet")

    if ui_options.get("response_effort_required") and not \
       current.deployment_settings.get_dvr_response_themes_efforts():

        try:
            hours = form.vars.hours
        except AttributeError:
            # No hours field in form, so no point validating it
            return

        if hours is None:
            # If new status is closed, require hours
            query = (stable.id == data.get("status_id"))
            status = db(query).select(stable.is_closed, limitby=(0, 1)).first()
            if status and status.is_closed:
                form.errors["hours"] = T("Please specify the effort spent")

# -------------------------------------------------------------------------
def response_action_postprocess(default_postprocess):
    """
        Custom extension for response action postprocess:
        - warns if the action concerns a vulnerability report but
          no vulnerabilities have been specified

        Args:
            default_postprocess: the default postprocess

        Returns:
            the extended postprocess
    """

    def postprocess(form):

        if callable(default_postprocess):
            default_postprocess(form)

        record_id = get_form_record_id(form)
        if not record_id:
            return

        db = current.db
        s3db = current.s3db

        table = s3db.dvr_response_action
        ttable = s3db.dvr_response_type
        ltable = s3db.dvr_vulnerability_response_action

        join = ttable.on((ttable.id == table.response_type_id) & \
                         (ttable.code.belongs(("VRBAMF", "VRRP")))
                         )
        left = ltable.on((ltable.action_id == table.id) & \
                         (ltable.vulnerability_id != None) & \
                         (ltable.deleted == False)
                         )
        query = (table.id == record_id) & (table.deleted == False)
        row = db(query).select(table.id,
                               table.person_id,
                               ltable.id,
                               join = join,
                               left = left,
                               limitby = (0, 1),
                               ).first()
        if row and not row[ltable].id:
            current.response.warning = current.T("No vulnerabilities specified!")

    return postprocess

# -------------------------------------------------------------------------
def response_date_dt_orderby(field, direction, orderby, left_joins):
    """
        When sorting response actions by date, use created_on to maintain
        consistent order of multiple response actions on the same date
    """

    sorting = {"table": field.tablename,
               "direction": direction,
               }
    orderby.append("%(table)s.start_date%(direction)s,%(table)s.created_on%(direction)s" % sorting)

# -------------------------------------------------------------------------
def configure_response_action_reports(ui_options,
                                      response_type = None,
                                      multiple_orgs = False,
                                      ):

    T = current.T
    settings = current.deployment_settings

    ui_options_get = ui_options.get

    use_theme = ui_options_get("response_use_theme")

    # Sector Axis
    if use_theme and settings.get_dvr_response_themes_sectors():
        sector = "dvr_response_action_theme.theme_id$sector_id"
        default_cols = None
    else:
        sector = "case_activity_id$sector_id"
        default_cols = sector if use_theme else None

    # Needs Axis
    if use_theme:
        themes = (T("Theme"), "response_theme_ids")
        if settings.get_dvr_response_themes_needs():
            need = (T("Counseling Reason"),
                    "dvr_response_action_theme.theme_id$need_id",
                    )
        else:
            need = None
    else:
        themes = need = None

    # Vulnerability Axis
    if ui_options_get("activity_pss_diagnoses"):
        suspected_diagnosis = (T("Suspected Diagnosis"),
                               "case_activity_id$diagnosis_suspected__link.diagnosis_id",
                               )
        confirmed_diagnosis = (T("Diagnosis"),
                               "case_activity_id$diagnosis_confirmed__link.diagnosis_id",
                               )
    else:
        suspected_diagnosis = confirmed_diagnosis = None

    # Custom Report Options
    facts = ((T("Number of Actions"), "count(id)"),
             (T("Number of Clients"), "count(person_id)"),
             (T("Hours (Total)"), "sum(hours)"),
             (T("Hours (Average)"), "avg(hours)"),
             )
    axes = ["person_id$gender",
            "person_id$person_details.nationality",
            "person_id$person_details.marital_status",
            (T("Size of Family"), "person_id$dvr_case.household_size"),
            suspected_diagnosis,
            confirmed_diagnosis,
            response_type,
            themes,
            need,
            sector,
            "human_resource_id",
            ]
    if ui_options_get("case_use_address"):
        axes.insert(3, (T("Place of Residence"), "person_id$location_id$L3"))
    if multiple_orgs:
        # Add case organisation as report axis
        axes.append("person_id$dvr_case.organisation_id")

    report_options = {
        "rows": axes,
        "cols": axes,
        "fact": facts,
        "defaults": {"rows": "response_theme_ids" if use_theme else sector,
                     "cols": default_cols,
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
                                      use_theme = False,
                                      use_time = False,
                                      use_response_type = False,
                                      use_due_date = False,
                                      multiple_orgs = False,
                                      org_ids = None,
                                      ):
    """
        Configures filter widgets for dvr_response_action

        Args:
            r: the CRUDRequest
            use_theme: use themes for response actions
            use_time: use time part of start_date
            use_response_type: use response types
            use_due_date: use a separate due-date
            multiple_orgs: user can see cases of multiple organisations,
                           so include an organisation-filter
            org_ids: the IDs of the organisations the user can access
    """

    T = current.T
    s3db = current.s3db

    hr_filter_opts = False
    hr_filter_default = None

    is_report = r.method == "report"

    from core import AgeFilter, \
                     DateFilter, \
                     HierarchyFilter, \
                     OptionsFilter, \
                     TextFilter, \
                     get_filter_options

    filter_widgets = [
        TextFilter(["person_id$pe_label",
                    "person_id$first_name",
                    "person_id$middle_name",
                    "person_id$last_name",
                    "comments",
                    ],
                    label = T("Search"),
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
                      ),
        DateFilter("start_date",
                   hidden = not is_report,
                   hide_time = True, #not use_time,
                   ),
        OptionsFilter("person_id$person_details.nationality",
                      label = T("Client Nationality"),
                      hidden = True,
                      ),
        AgeFilter("person_id$date_of_birth",
                  label = T("Client Age"),
                  hidden = True,
                  )
        ]

    if use_theme:
        settings = current.deployment_settings
        themes_details = settings.get_dvr_response_themes_details()
        themes_sectors = settings.get_dvr_response_themes_sectors()
        if themes_details and themes_sectors:
            from ..helpers import response_theme_sectors
            filter_widgets.insert(-2,
                OptionsFilter("response_action_theme.theme_id$sector_id",
                              header = True,
                              hidden = True,
                              options = response_theme_sectors,
                              ))

        filter_widgets.insert(-2,
            OptionsFilter("response_theme_ids",
                          header = True,
                          hidden = True,
                          options = lambda: \
                                    get_filter_options("dvr_response_theme",
                                                       org_filter = True,
                                                       ),
                          ))


    if use_response_type:
        filter_widgets.insert(3,
            HierarchyFilter("response_type_id",
                            hidden = True,
                            ))
    if use_due_date:
        filter_widgets.insert(3,
            DateFilter("date_due",
                        hidden = is_report,
                        ))

    # Filter by case manager in charge
    mine = r.get_vars.get("mine")
    if mine not in ("a", "r"):
        # Populate hr_filter_opts to enable filter widget
        # - use field options as filter options
        table = s3db.dvr_response_action
        field = table.human_resource_id
        try:
            hr_filter_opts = field.requires.options()
        except AttributeError:
            pass
        else:
            hr_filter_opts = dict(hr_filter_opts)
            hr_filter_opts.pop('', None)
        if mine == "f":
            hr_filter_default = field.default

    if hr_filter_opts:
        filter_widgets.insert(2,
            OptionsFilter("human_resource_id",
                          default = hr_filter_default,
                          header = True,
                          options = hr_filter_opts,
                          ))

    if multiple_orgs:
        # Add case organisation filter
        if org_ids:
            # Provide the permitted organisations as filter options
            org_filter_opts = s3db.org_organisation_represent.bulk(
                                                org_ids,
                                                show_link = False,
                                                )
            org_filter_opts.pop(None, None)
        else:
            # Look up from records
            org_filter_opts = None
        filter_widgets.insert(1, OptionsFilter("person_id$dvr_case.organisation_id",
                                               options = org_filter_opts,
                                               ))

    s3db.configure("dvr_response_action",
                   filter_widgets = filter_widgets,
                   )

# -------------------------------------------------------------------------
def configure_response_action_theme(ui_options,
                                    case_root_org = None,
                                    person_id = None,
                                    record_id = None,
                                    case_activity = None,
                                    case_activity_id = None,
                                    ):
    """
        Configures response theme selector

        Args:
            ui_options: the UI options for the current org
            case_root_org: the case root organisation
            person_id: the person record ID (to look up the root org)
            record_id: the response action record ID (if updating)
            case_activity: the case activity record
            case_activity_id: the case activity record ID
                                (to look up the case activity record)
    """

    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    ttable = s3db.dvr_response_theme
    query = (ttable.obsolete == False) | (ttable.obsolete == None)
    # Limit themes to the themes of the case root organisation
    if not case_root_org:
        case_root_org = get_case_root_org(person_id)
        if not case_root_org:
            case_root_org = current.auth.root_org()
    if case_root_org:
        query = (ttable.organisation_id == case_root_org) & query

    themes_needs = settings.get_dvr_response_themes_needs()
    if ui_options.get("activity_subject_type") in ("need", "both") and themes_needs:
        # Limit themes to those matching the need of the activity
        if case_activity:
            need_id = case_activity.need_id
        elif case_activity_id:
            # Look up the parent record
            catable = s3db.dvr_case_activity
            case_activity = db(catable.id == case_activity_id).select(catable.id,
                                                                      catable.need_id,
                                                                      limitby = (0, 1),
                                                                      ).first()
            need_id = case_activity.need_id if case_activity else None
        else:
            need_id = None
        if need_id:
            q = (ttable.need_id == need_id)
            query = q & query if query else q

    table = s3db.dvr_response_action
    if record_id:
        # Include currently selected themes even if they do not match
        # any of the previous criteria
        q = (table.id == record_id)
        row = db(q).select(table.response_theme_ids,
                           limitby = (0, 1),
                           ).first()
        if row and row.response_theme_ids:
            query |= ttable.id.belongs(row.response_theme_ids)

    elif case_activity:
        # Include all themes currently linked to this case activity
        # (for inline responses)
        q = (table.case_activity_id == case_activity.id) & \
            (table.deleted == False)
        rows = db(q).select(table.response_theme_ids)
        theme_ids = set()
        for row in rows:
            if row.response_theme_ids:
                theme_ids |= set(row.response_theme_ids)
        if theme_ids:
            query |= ttable.id.belongs(theme_ids)

    dbset = db(query) if query else db

    themes_optional = ui_options.get("response_themes_optional")
    field = table.response_theme_ids
    if themes_needs:
        # Include the need in the themes-selector
        # - helps to find themes using the selector search field
        represent = s3db.dvr_ResponseThemeRepresent(multiple = True,
                                                    translate = True,
                                                    show_need = True,
                                                    )
    else:
        represent = field.represent

    field.requires = IS_ONE_OF(dbset, "dvr_response_theme.id",
                               represent,
                               multiple = True,
                               )
    if themes_optional:
        # Allow responses without theme
        field.requires = IS_EMPTY_OR(field.requires)

    table = s3db.dvr_response_action_theme
    field = table.theme_id
    field.requires = IS_ONE_OF(dbset, "dvr_response_theme.id",
                               represent,
                               )
    if themes_optional:
        field.requires = IS_EMPTY_OR(field.requires)

# -------------------------------------------------------------------------
def configure_response_action_view(ui_options,
                                   response_type = None,
                                   use_due_date = False,
                                   use_theme = False,
                                   themes_details = False,
                                   ):
    """
        Configures dvr/response_action view

        Args:
            ui_options: the UI options for the organisation
            response_type: the response_type field (selector)
            use_due_date: use a separate due-date
            use_theme: use response action themes
            theme_details: enter details per theme
    """

    T = current.T

    s3db = current.s3db
    table = s3db.dvr_response_action

    ui_options_get = ui_options.get
    date_due = "date_due" if use_due_date else None

    if ui_options_get("case_use_pe_label"):
        pe_label = (T("ID"), "person_id$pe_label")
    else:
        pe_label = None

    # Adapt list-fields to perspective
    list_fields = [pe_label,
                   response_type,
                   "human_resource_id",
                   date_due,
                   "start_date",
                   "hours",
                   "status_id",
                   ]

    if themes_details:
        list_fields[2:2] = [(T("Themes"), "dvr_response_action_theme.id")]
    elif use_theme:
        list_fields[2:2] = ["response_theme_ids", "comments"]

    if not use_theme or ui_options_get("response_themes_optional"):
        # Show person_id (read-only)
        field = table.person_id
        field.represent =  s3db.pr_PersonRepresent(show_link = True)
        field.readable = True
        field.writable = False
        list_fields.insert(1, (T("Case"), "person_id"))

        field = table.case_activity_id
        if response_type:
            # Hide activity_id
            field.readable = field.writable = False
        else:
            # Show activity_id (read-only)
            subject_type = ui_options_get("activity_subject_type")
            use_need = subject_type in ("need", "both")
            use_subject = subject_type in ("subject", "both")
            field.label = T("Counseling Reason")
            field.represent = s3db.dvr_CaseActivityRepresent(
                                        show_as = "need" if use_need else "subject",
                                        show_subject = use_subject,
                                        show_link = True,
                                        )
            field.readable = True
            field.writable = False
            list_fields.insert(2, "case_activity_id")
    else:
        # Hide person_id
        field = table.person_id
        field.readable = field.writable = False

        # Show activity_id (read-only)
        field = table.case_activity_id
        field.label = T("Case")
        field.represent = s3db.dvr_CaseActivityRepresent(
                                    show_as = "beneficiary",
                                    fmt = "%(last_name)s, %(first_name)s",
                                    show_link = True,
                                    )
        field.readable = True
        field.writable = False
        list_fields.insert(1, "case_activity_id")

    s3db.configure("dvr_response_action",
                   list_fields = list_fields,
                   )

# -------------------------------------------------------------------------
def configure_response_action_tab(person_id,
                                  ui_options,
                                  response_type = None,
                                  use_due_date = False,
                                  use_theme = False,
                                  themes_details = False,
                                  ):
    """
        Configures response_action tab of case file

        Args:
            person_id: the person ID of the case
            ui_options: the UI options for the organisation
            response_type: the response_type field (selector)
            use_due_date: use a separate due-date
            use_theme: use response action themes
            theme_details: enter details per theme
    """

    T = current.T
    db = current.db
    s3db = current.s3db

    table = s3db.dvr_response_action

    ui_options_get = ui_options.get
    date_due = "date_due" if use_due_date else None

    # Hide person_id (already have the rheader context)
    field = table.person_id
    field.readable = field.writable = False

    if themes_details:
        # Hide case_activity_id
        field = table.case_activity_id
        field.readable = False

        list_fields = ["start_date",
                       response_type,
                       (T("Themes"), "dvr_response_action_theme.id"),
                       "human_resource_id",
                       "hours",
                       "status_id",
                       ]
        pdf_fields = ["start_date",
                       response_type,
                      (T("Themes"), "dvr_response_action_theme.id"),
                      #"human_resource_id",
                      ]
    else:
        # Show case_activity_id
        field = table.case_activity_id
        field.readable = True

        # Adjust representation to perspective
        subject_type = ui_options_get("activity_subject_type")
        use_need = subject_type in ("need", "both")
        use_subject = subject_type in ("subject", "both")
        if use_need:
            field.label = T("Counseling Reason")
            show_as = "need"
        else:
            field.label = T("Subject")
            show_as = "subject"

        represent = s3db.dvr_CaseActivityRepresent(show_as = show_as,
                                                   show_link = True,
                                                   show_subject = use_subject,
                                                   )
        field.represent = represent

        if not ui_options_get("response_activity_autolink"):
            # Make activity selectable
            field.writable = True

            # Selectable options to include date
            represent = s3db.dvr_CaseActivityRepresent(show_as = show_as,
                                                       show_link = True,
                                                       show_subject = use_subject,
                                                       show_date = True,
                                                       )

            # Limit to activities of the same case
            atable = s3db.dvr_case_activity
            db = current.db
            dbset = db(atable.person_id == person_id)
            field.requires = IS_ONE_OF(dbset, "dvr_case_activity.id",
                                       represent,
                                       orderby = ~db.dvr_case_activity.start_date,
                                       sort = False,
                                       )

            # Allow in-popup creation of new activities for the case
            field.comment = PopupLink(label = T("Create Counseling Reason"),
                                        c = "dvr",
                                        f = "case_activity",
                                        vars = {"~.person_id": person_id,
                                                "prefix": "dvr/person/%s" % person_id,
                                                "parent": "response_action",
                                                },
                                        )

        else:
            field.writable = False

        # Adapt list-fields to perspective
        theme_ids = "response_theme_ids" if use_theme else None
        list_fields = ["case_activity_id",
                       response_type,
                       theme_ids,
                       "comments",
                       "human_resource_id",
                       date_due,
                       "start_date",
                       "hours",
                       "status_id",
                       ]
        pdf_fields = ["start_date",
                      #"human_resource_id",
                      "case_activity_id",
                      response_type,
                      theme_ids,
                      "comments",
                      ]

    s3db.configure("dvr_response_action",
                   filter_widgets = None,
                   list_fields = list_fields,
                   pdf_fields = pdf_fields,
                   )

# -------------------------------------------------------------------------
def dvr_response_action_resource(r, tablename):

    T = current.T
    s3db = current.s3db
    settings = current.deployment_settings

    table = s3db.dvr_response_action

    ui_options = get_ui_options()
    ui_options_get = ui_options.get

    # Can the user see cases from more than one org?
    from ..helpers import case_read_multiple_orgs
    multiple_orgs, org_ids = case_read_multiple_orgs()

    use_theme = ui_options_get("response_use_theme")
    themes_details = use_theme and settings.get_dvr_response_themes_details()
    themes_efforts = use_theme and settings.get_dvr_response_themes_efforts()

    # Represent for dvr_response_action_theme.id
    if themes_details:
        ltable = s3db.dvr_response_action_theme
        ltable.id.represent = s3db.dvr_ResponseActionThemeRepresent(
                                            paragraph = True,
                                            details = True,
                                            )

    # Use date+time in responses?
    use_time = settings.get_dvr_response_use_time()

    # Using response types?
    use_response_type = settings.get_dvr_response_types()
    response_type = "response_type_id" if use_response_type else None

    is_report = r.method == "report"
    if is_report:
        configure_response_action_reports(ui_options,
                                          response_type = response_type,
                                          multiple_orgs = multiple_orgs,
                                          )
        crud_strings = current.response.s3.crud_strings["dvr_response_action"]
        crud_strings["title_report"] = T("Action Statistic")

    if r.interactive or r.representation in ("aadata", "xlsx", "xls", "pdf", "json", "s3json"):

        human_resource_id = current.auth.s3_logged_in_human_resource()

        # Use drop-down for human_resource_id
        field = table.human_resource_id
        field.default = human_resource_id
        field.represent = s3db.hrm_HumanResourceRepresent(show_link=False)
        field.widget = None

        ltable = s3db.dvr_response_action_theme

        # Require explicit unit in hours-widget above 4 hours
        from core import S3HoursWidget
        for f in (table.hours, ltable.hours):
            f.widget = S3HoursWidget(precision=2, explicit_above=4)

        # Require input when documenting effort per theme
        if themes_efforts:
            ltable.hours.requires = IS_FLOAT_IN_RANGE(0.0, None)

        # Use separate due-date field?
        use_due_date = settings.get_dvr_response_due_date()

        # Configure theme selector
        viewing = r.viewing
        is_master = r.tablename == "dvr_response_action" and viewing is None

        person_id = record_id = None
        record = r.record
        if record:
            if r.tablename == "dvr_response_action":
                person_id = record.person_id
                record_id = record.id
            elif r.tablename == "pr_person" and \
                 r.component and r.component.tablename == "dvr_response_action":
                person_id = record.id
                record_id = r.component_id

        if use_theme:
            configure_response_action_theme(ui_options,
                                            person_id = person_id,
                                            record_id = record_id,
                                            )

        if not is_master:
            # Component (or viewing) tab of dvr/person
            configure_response_action_tab(person_id,
                                          ui_options,
                                          response_type = response_type,
                                          use_due_date = use_due_date,
                                          use_theme = use_theme,
                                          themes_details = themes_details,
                                          )
            if viewing:
                s3db.configure("dvr_response_action",
                               create_next = r.url(id="", method=""),
                               update_next = r.url(id="", method=""),
                               )
        else:
            # Primary dvr/response_action controller
            configure_response_action_view(ui_options,
                                           response_type = response_type,
                                           use_due_date = use_due_date,
                                           use_theme = use_theme,
                                           themes_details = themes_details,
                                           )

            # Custom Filter Options
            if r.interactive:
                configure_response_action_filters(r,
                                                  use_theme = use_theme,
                                                  use_time = use_time,
                                                  use_response_type = use_response_type,
                                                  use_due_date = use_due_date,
                                                  multiple_orgs = multiple_orgs,
                                                  org_ids = org_ids,
                                                  )

    # Organizer and PDF exports
    if themes_details:
        description = [(T("Themes"), "response_action_theme.id"),
                       "human_resource_id",
                       "status_id",
                       ]
    elif use_theme:
        description = ["response_theme_ids",
                       "comments",
                       "human_resource_id",
                       "status_id",
                       ]
    else:
        description = ["comments",
                       "human_resource_id",
                       "status_id",
                       ]

    if r.method == "organize":
        table.end_date.writable = True

    s3db.configure("dvr_response_action",
                   organize = {"title": "person_id",
                               "description": description,
                               "color": "status_id",
                               "colors": s3db.dvr_response_status_colors,
                               "start": "start_date",
                               "end": "end_date",
                               "use_time": use_time,
                               },
                   pdf_format = "list" if themes_details else "table",
                   orderby = "dvr_response_action.start_date desc, dvr_response_action.created_on desc",
                   )

    # Maintain consistent order for multiple response actions
    # on the same day (by enforcing created_on as secondary order criterion)
    field = table.start_date
    field.represent.dt_orderby = response_date_dt_orderby

    # Custom onvalidation
    s3db.add_custom_callback("dvr_response_action",
                             "onvalidation",
                             response_action_onvalidation,
                             )

    # Custom postprocess to warn for missing vulnerability links
    if settings.get_dvr_response_vulnerabilities():
        crud_form = s3db.get_config("dvr_response_action", "crud_form")
        if isinstance(crud_form, CustomForm):
            postprocess = crud_form.opts.get("postprocess")
            crud_form.opts["postprocess"] = response_action_postprocess(postprocess)

# -------------------------------------------------------------------------
def dvr_response_action_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3
    settings = current.deployment_settings

    if "viewing" in current.request.get_vars:
        # Set contacts-method to retain the tab
        s3db.set_method("pr_person",
                        method = "contacts",
                        action = s3db.pr_Contacts,
                        )

    else:
        settings.base.bigtable = True

    standard_prep = s3.prep
    def custom_prep(r):
        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
            if not result:
                return False

        if not r.id:
            # pisets = {pitype: (method, icon, title)}
            pisets = {None: ("indicators",
                             "line-chart",
                             T("Performance Indicators"),
                             ),
                      "rp": ("indicators_rp",
                             "line-chart",
                             "%s %s" % (T("Performance Indicators"), "RP"),
                             ),
                      "bamf": ("indicators_bamf",
                               "tachometer",
                               "%s %s" % (T("Performance Indicators"), "BAMF"),
                               ),
                      }

            from ..stats import PerformanceIndicatorExport
            pitypes = get_ui_options().get("response_performance_indicators")
            if not isinstance(pitypes, (tuple, list)):
                pitypes = [pitypes]

            for pitype in pitypes:
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
                export_formats.append((fmt, "fa fa-%s" % icon, title))
                s3.formats[fmt] = r.url(method=method)
                settings.ui.export_formats = export_formats

        return result
    s3.prep = custom_prep

    # Custom rheader
    if current.request.controller == "dvr":
        from ..rheaders import drk_dvr_rheader
        attr["rheader"] = drk_dvr_rheader

    return attr

# -------------------------------------------------------------------------
def dvr_response_theme_resource(r, tablename):

    T = current.T
    settings = current.deployment_settings

    is_admin = current.auth.s3_has_role("ADMIN")

    if r.tablename == "org_organisation" and r.id:

        s3db = current.s3db

        ttable = s3db.dvr_response_theme

        if is_admin or settings.get_dvr_response_themes_sectors():

            # Limit sector selection to the sectors of the organisation
            stable = s3db.org_sector
            ltable = s3db.org_sector_organisation

            dbset = current.db((ltable.sector_id == stable.id) & \
                               (ltable.organisation_id == r.id) & \
                               (ltable.deleted == False))
            field = ttable.sector_id
            field.comment = None
            field.readable = field.writable = True
            field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "org_sector.id",
                                                   field.represent,
                                                   ))

        if is_admin or settings.get_dvr_response_themes_needs():

            # Limit needs selection to the needs of the organisation
            ntable = s3db.dvr_need

            dbset = current.db(ntable.organisation_id == r.id)
            field = ttable.need_id
            field.label = T("Counseling Reason")
            field.comment = None
            field.readable = field.writable = True
            field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "dvr_need.id",
                                                   field.represent,
                                                   ))

    # Custom CRUD Strings
    current.response.s3.crud_strings["dvr_response_theme"] = Storage(
        label_create = T("Create Counseling Theme"),
        title_display = T("Counseling Theme Details"),
        title_list = T("Counseling Themes"),
        title_update = T("Edit Counseling Theme"),
        label_list_button = T("List Counseling Themes"),
        label_delete_button = T("Delete Counseling Theme"),
        msg_record_created = T("Counseling Theme created"),
        msg_record_modified = T("Counseling Theme updated"),
        msg_record_deleted = T("Counseling Theme deleted"),
        msg_list_empty = T("No Counseling Themes currently defined"),
        )

# -------------------------------------------------------------------------
def dvr_response_type_resource(r, tablename):

    table = current.s3db.dvr_response_type
    field = table.code
    field.readable = field.writable = True

# -------------------------------------------------------------------------
def dvr_service_contact_resource(r, tablename):

    s3db = current.s3db

    table = s3db.dvr_service_contact

    field = table.type_id
    field.label = current.T("Type")

    field = table.organisation_id
    field.readable = field.writable = False

    field = table.organisation
    field.readable = field.writable = True

# -------------------------------------------------------------------------
def dvr_vulnerability_resource(r, tablename):

    table = current.s3db.dvr_vulnerability

    # Expose human_resource_id and set default
    field = table.human_resource_id
    field.default = current.auth.s3_logged_in_human_resource()
    field.readable = field.writable = True

# END =========================================================================
