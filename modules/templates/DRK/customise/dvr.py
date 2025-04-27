"""
    DVR module customisations for DRK

    License: MIT
"""

import datetime

from gluon import current, URL, A
from gluon.storage import Storage

from core import CRUDMethod, FS, IS_ONE_OF, S3DateTime, s3_str

from .pr import configure_person_tags

# -------------------------------------------------------------------------
def dvr_home():
    """ Redirect dvr/index to dvr/person?closed=0 """

    from core import s3_redirect_default

    s3_redirect_default(URL(f="person", vars={"closed": "0"}))

# -------------------------------------------------------------------------
def generate_pe_label(person_id):
    """
        Auto-generate a case ID (pe_label)

        Args:
            person_id: the person ID
    """

    db = current.db
    s3db = current.s3db

    table = s3db.pr_person
    person = db(table.id == person_id).select(table.id,
                                              table.pe_label,
                                              limitby = (0, 1),
                                              ).first()
    if person and not person.pe_label:
        pe_label = "MA%05d" % person.id
        person.update_record(pe_label = pe_label,
                             modified_on = table.modified_on,
                             modified_by = table.modified_by,
                             )

# -------------------------------------------------------------------------
def dvr_case_onaccept(form):
    """
        If case is archived or closed then remove shelter_registration,
        otherwise ensure that a shelter_registration exists for any
        open and valid case
    """

    T = current.T

    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    form_vars = form.vars
    archived = form_vars.archived
    person_id = form_vars.person_id

    if settings.get_custom("autogenerate_case_ids"):
        generate_pe_label(person_id)

    # Inline shelter registration?
    inline = "sub_shelter_registration_registration_status" in current.request.post_vars

    cancel = False

    if archived:
        cancel = True

    else:
        status_id = form_vars.status_id
        if status_id:

            stable = s3db.dvr_case_status
            status = db(stable.id == status_id).select(stable.is_closed,
                                                       limitby = (0, 1)
                                                       ).first()
            try:
                if status.is_closed:
                    cancel = True
            except AttributeError:
                current.log.error("Status %s not found" % status_id)
                return

    rtable = s3db.cr_shelter_registration
    query = (rtable.person_id == person_id)

    if cancel:
        reg = db(query).select(rtable.id, limitby=(0, 1)).first()
        if reg:
            resource = s3db.resource("cr_shelter_registration",
                                     id = reg.id,
                                     )
            resource.delete()

    elif not inline:
        # We're called without inline shelter registration, so
        # make sure there is a shelter registration if the case
        # is valid and open:
        reg = db(query).select(rtable.id, limitby=(0, 1)).first()
        if not reg:
            if rtable.shelter_id.default is not None:
                # Create default shelter registration
                rtable.insert(person_id=person_id)
            else:
                current.response.warning = T("Person could not be registered to a shelter, please complete case manually")

# -------------------------------------------------------------------------
def dvr_case_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    s3db.add_custom_callback(tablename,
                             "onaccept",
                             dvr_case_onaccept,
                             )

    ctable = s3db.dvr_case

    # Expose expiration dates
    field = ctable.valid_until
    field.label = T("BÜMA valid until")
    field.readable = field.writable = True
    field = ctable.stay_permit_until
    field.readable = field.writable = True

    # Set all fields read-only except comments, unless
    # the user has permission to create cases
    if not current.auth.s3_has_permission("create", "dvr_case"):
        for field in ctable:
            if field.name != "comments":
                field.writable = False

# -------------------------------------------------------------------------
def dvr_note_resource(r, tablename):

    T = current.T
    auth = current.auth

    if not auth.s3_has_role("ADMIN"):

        db = current.db
        s3db = current.s3db

        # Restrict access by note type
        GENERAL = "General"
        MEDICAL = "Medical"
        SECURITY = "Security"

        permitted_note_types = [GENERAL]

        user = auth.user
        if user:
            has_roles = auth.s3_has_roles

            # Roles permitted to access "Security" type notes
            SECURITY_ROLES = ("ADMIN_HEAD",
                              "SECURITY_HEAD",
                              "POLICE",
                              "MEDICAL",
                              )
            if has_roles(SECURITY_ROLES):
                permitted_note_types.append(SECURITY)

            # Roles permitted to access "Health" type notes
            MEDICAL_ROLES = ("ADMIN_HEAD",
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

        # Filter note type selector to permitted note types
        ttable = s3db.dvr_note_type
        query = ttable.name.belongs(permitted_note_types)
        rows = db(query).select(ttable.id)
        note_type_ids = [row.id for row in rows]

        table = s3db.dvr_note
        field = table.note_type_id
        field.label = T("Category")

        if len(note_type_ids) == 1:
            field.default = note_type_ids[0]
            field.writable = False

        field.requires = IS_ONE_OF(db(query), "dvr_note_type.id",
                                   field.represent,
                                   )

# -------------------------------------------------------------------------
def dvr_case_activity_resource(r, tablename):

    if not current.auth.s3_has_role("MEDICAL"):

        s3db = current.s3db
        from gluon import IS_EMPTY_OR

        HEALTH = "Health"

        # Remove "Health" need type from need_id options widget
        ntable = s3db.dvr_need
        dbset = current.db(ntable.name != HEALTH)

        table = s3db.dvr_case_activity
        field = table.need_id
        field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset, "dvr_need.id",
                                               field.represent,
                                               ))

        # Hide activities for need type "Health"
        query = (FS("need_id$name") != HEALTH)

        if r.tablename == "dvr_case_activity":
            r.resource.add_filter(query)

            # @todo: remove "Health" need type from need_id filter widget

        elif r.component and r.component.tablename == "dvr_case_activity":
            r.component.add_filter(query)

# -------------------------------------------------------------------------
def dvr_case_activity_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

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

        if not r.component:

            # Add EasyOpt Number to text filter fields
            #filter_widgets = resource.get_config("filter_widgets")
            #if filter_widgets:
            #    configure_person_tags()
            #    from core import TextFilter
            #    for fw in filter_widgets:
            #        if isinstance(fw, TextFilter):
            #            fw.field.append("person_id$eo_number.value")
            #            break

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

                # Custom form (excluding case reference)
                from core import CustomForm
                crud_form = CustomForm("person_id",
                                       "start_date",
                                       "need_id",
                                       "need_details",
                                       "emergency",
                                       "activity_details",
                                       "followup",
                                       "followup_date",
                                       "outcome",
                                       "completed",
                                       "comments",
                                       )
                resource.configure(crud_form=crud_form)

            # Custom list fields
            list_fields = [(T("ID"), "person_id$pe_label"),
                           "person_id$first_name",
                           "person_id$last_name",
                           "need_id",
                           "need_details",
                           "emergency",
                           "activity_details",
                           "followup",
                           "followup_date",
                           "completed",
                           ]
            resource.configure(list_fields=list_fields)

        return result
    s3.prep = custom_prep

    return attr

# -------------------------------------------------------------------------
def dvr_case_appointment_controller(**attr):

    T = current.T
    s3 = current.response.s3
    s3db = current.s3db

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

        if not r.component:

            configure_person_tags()

            if r.interactive and not r.id:

                # Custom filter widgets
                from core import TextFilter, OptionsFilter, DateFilter, get_filter_options
                filter_widgets = [
                    TextFilter(["person_id$pe_label",
                                "person_id$first_name",
                                "person_id$last_name",
                                #"person_id$eo_number.value",
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
                    TextFilter(["person_id$pe_label"],
                               label = T("IDs"),
                               match_any = True,
                               hidden = True,
                               comment = T("Search for multiple IDs (separated by blanks)"),
                               ),
                    ]

                resource.configure(filter_widgets = filter_widgets)

            # Default filter today's and tomorrow's appointments
            from core import set_default_filter
            now = r.utcnow
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            tomorrow = today + datetime.timedelta(days=1)
            set_default_filter("~.date", {"ge": today, "le": tomorrow},
                               tablename = "dvr_case_appointment",
                               )

            # Field Visibility
            table = resource.table
            field = table.case_id
            field.readable = field.writable = False

            # Custom list fields
            list_fields = [(T("ID"), "person_id$pe_label"),
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
def dvr_allowance_controller(**attr):

    T = current.T
    s3 = current.response.s3
    s3db = current.s3db

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

        if not r.component:

            if r.interactive and not r.id:
                # Custom filter widgets
                from core import TextFilter, \
                                 OptionsFilter, \
                                 DateFilter

                filter_widgets = [
                    TextFilter(["person_id$pe_label",
                                "person_id$first_name",
                                "person_id$middle_name",
                                "person_id$last_name",
                                ],
                                label = T("Search"),
                                ),
                    OptionsFilter("status",
                                  default = 1,
                                  cols = 4,
                                  options = s3db.dvr_allowance_status_opts,
                                  ),
                    DateFilter("date"),
                    DateFilter("paid_on"),
                    DateFilter("entitlement_period",
                               hidden = True,
                               )
                    ]
                resource.configure(filter_widgets = filter_widgets)

            # Field Visibility
            table = resource.table
            field = table.case_id
            field.readable = field.writable = False

            # Can't change beneficiary
            field = table.person_id
            field.writable = False

            # Custom list fields
            list_fields = [(T("ID"), "person_id$pe_label"),
                           "person_id",
                           "entitlement_period",
                           "date",
                           "currency",
                           "amount",
                           "status",
                           "paid_on",
                           "comments",
                           ]
            if r.representation in ("xlsx", "xls"):
                list_fields.append(("UUID", "person_id$uuid"))

            resource.configure(list_fields = list_fields,
                               insertable = False,
                               deletable = False,
                               #editable = False,
                               )

        return result
    s3.prep = custom_prep

    # Custom postp
    standard_postp = s3.postp
    def custom_postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.method == "register":
            from core import CustomController
            CustomController._view("DRK", "register_case_event.html")
        return output
    s3.postp = custom_postp

    return attr

# -------------------------------------------------------------------------
def dvr_case_event_resource(r, tablename):

    s3db = current.s3db

    from ..food import DRKRegisterFoodEvent
    s3db.set_method("dvr_case_event",
                    method = "register_food",
                    action = DRKRegisterFoodEvent,
                    )

    #s3db.add_custom_callback("dvr_case_event",
    #                         "onaccept",
    #                         case_event_create_onaccept,
    #                         method = "create",
    #                         )

# -------------------------------------------------------------------------
def case_event_report_default_filters(event_code=None):
    """
        Set default filters for case event report

        Args:
            event_code: code for the default event type
    """

    from core import set_default_filter

    if event_code:
        ttable = current.s3db.dvr_case_event_type

        if event_code[-1] == "*":
            query = (ttable.code.like("%s%%" % event_code[:-1])) & \
                    (ttable.is_inactive == False)
            if event_code[:-1] == "FOOD":
                # Include SURPLUS-MEALS events
                query |= (ttable.code == "SURPLUS-MEALS")
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
def dvr_case_event_controller(**attr):

    T = current.T
    s3 = current.response.s3

    standard_prep = s3.prep
    def custom_prep(r):
        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        resource = r.resource
        table = resource.table

        if r.method == "report":
            # Set report default filters
            event_code = r.get_vars.get("code")
            case_event_report_default_filters(event_code)

            dates = DRKCaseEventDateAxes()

            # Field method for day-date of events
            from core import s3_fieldmethod
            table.date_day = s3_fieldmethod(
                                "date_day",
                                dates.case_event_date_day,
                                represent = dates.case_event_date_day_represent,
                                )
            table.date_tod = s3_fieldmethod(
                                "date_tod",
                                dates.case_event_time_of_day,
                                )

            # Pivot axis options
            report_axes = ["type_id",
                           (T("Date"), "date_day"),
                           (T("Time of Day"), "date_tod"),
                           "created_by",
                           ]

            # Configure report options
            code = r.get_vars.get("code")
            if code and code[-1] != "*":
                # Single event type => group by ToD (legacy)
                default_cols = "date_tod"
            else:
                # Group by type (standard behavior)
                default_cols = "type_id"
            report_options = {
                "rows": report_axes,
                "cols": report_axes,
                "fact": [(T("Total Quantity"), "sum(quantity)"),
                         #(T("Number of Events"), "count(id)"),
                         ],
                "defaults": {"rows": "date_day",
                             "cols": default_cols,
                             "fact": "sum(quantity)",
                             "totals": True,
                             },
                }
            resource.configure(report_options = report_options,
                               extra_fields = ["date",
                                               "person_id",
                                               "type_id",
                                               ],
                               )
        return result
    s3.prep = custom_prep

    # Custom postp
    standard_postp = s3.postp
    def custom_postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.method in ("register", "register_food"):
            from core import CustomController
            CustomController._view("DRK", "register_case_event.html")
        return output
    s3.postp = custom_postp

    return attr

# -------------------------------------------------------------------------
def dvr_case_event_type_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    from core import CustomForm, \
                     InlineLink

    crud_form = CustomForm("code",
                           "name",
                           "is_inactive",
                           "is_default",
                           "role_required",
                           "appointment_type_id",
                           "min_interval",
                           "max_per_day",
                           InlineLink("excluded_by",
                                      field = "excluded_by_id",
                                      label = T("Not Combinable With"),
                                      ),
                           "presence_required",
                           )

    s3db.configure("dvr_case_event_type",
                   crud_form = crud_form,
                   )

# -------------------------------------------------------------------------
def dvr_site_activity_resource(r, tablename):

    T = current.T
    s3db = current.s3db

    s3db.set_method("dvr_site_activity",
                    method = "create",
                    action = DRKCreateSiteActivityReport,
                    )
    s3db.configure("dvr_site_activity",
                   listadd = False,
                   addbtn = True,
                   editable = False,
                   )

    crud_strings = current.response.s3.crud_strings
    crud_strings["dvr_site_activity"] = Storage(
        label_create = T("Create Residents Report"),
        title_display = T("Residents Report"),
        title_list = T("Residents Reports"),
        title_update = T("Edit Residents Report"),
        label_list_button = T("List Residents Reports"),
        label_delete_button = T("Delete Residents Report"),
        msg_record_created = T("Residents Report created"),
        msg_record_modified = T("Residents Report updated"),
        msg_record_deleted = T("Residents Report deleted"),
        msg_list_empty = T("No Residents Reports found"),
        )

# =============================================================================
class DRKCaseEventDateAxes:
    """
        Helper class for virtual date axes in case event statistics
    """

    def __init__(self):
        """
            Perform all slow lookups outside of the field methods
        """

        from dateutil import tz

        # Get timezone descriptions
        self.UTC = tz.tzutc()
        self.LOCAL = tz.gettz("Europe/Berlin")

        # Lookup FOOD event type_id
        table = current.s3db.dvr_case_event_type
        query = (table.code == "FOOD") & \
                (table.deleted != True)
        row = current.db(query).select(table.id, limitby=(0, 1)).first()
        self.FOOD = row.id if row else None

        self.SURPLUS_MEALS = s3_str(current.T("Surplus Meals"))

    # -------------------------------------------------------------------------
    def case_event_date_day(self, row):
        """
            Field method to reduce case event date/time to just date,
            used in pivot table reports to group case events by day
        """

        if hasattr(row, "dvr_case_event"):
            row = row.dvr_case_event

        try:
            date = row.date
        except AttributeError:
            date = None

        if date:
            # Get local hour
            date = date.replace(tzinfo=self.UTC).astimezone(self.LOCAL)
            hour = date.time().hour

            # Convert to date
            date = date.date()
            if hour <= 7:
                # Map early hours to previous day
                return date - datetime.timedelta(days=1)
        else:
            date = None
        return date

    # -------------------------------------------------------------------------
    @staticmethod
    def case_event_date_day_represent(value):
        """
            Representation method for case_event_date_day, needed in order
            to sort pivot axis values by raw date, but show them in locale
            format (default DD.MM.YYYY, doesn't sort properly).
        """

        return S3DateTime.date_represent(value, utc=True)

    # -------------------------------------------------------------------------
    def case_event_time_of_day(self, row):
        """
            Field method to group events by time of day
        """

        if hasattr(row, "dvr_case_event"):
            row = row.dvr_case_event

        try:
            date = row.date
        except AttributeError:
            date = None

        if date:
            try:
                person_id = row.person_id
                type_id = row.type_id
            except AttributeError:
                person_id = 0
                type_id = None

            if type_id == self.FOOD and person_id is None:
                tod = self.SURPLUS_MEALS
            else:
                date = date.replace(tzinfo=self.UTC).astimezone(self.LOCAL)
                hour = date.time().hour

                if 7 <= hour < 13:
                    tod = "07:00 - 13:00"
                elif 13 <= hour < 17:
                    tod = "13:00 - 17:00"
                elif 17 <= hour < 20:
                    tod = "17:00 - 20:00"
                else:
                    tod = "20:00 - 07:00"
        else:
            tod = "-"
        return tod

# =============================================================================
class DRKCreateSiteActivityReport(CRUDMethod):
    """ Custom method to create a dvr_site_activity entry """

    def apply_method(self, r, **attr):
        """
            Entry point for REST controller

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        if r.representation in ("html", "iframe"):
            if r.http in ("GET", "POST"):
                output = self.create_form(r, **attr)
            else:
                r.error(405, current.ERROR.BAD_METHOD)
        else:
            r.error(415, current.ERROR.BAD_FORMAT)

        return output

    # -------------------------------------------------------------------------
    def create_form(self, r, **attr):
        """
            Generate and process the form

            Args:
                r: the CRUDRequest
                attr: dict of controller parameters
        """

        # User must be permitted to create site activity reports
        authorised = self._permitted(method="create")
        if not authorised:
            r.unauthorised()

        s3db = current.s3db

        T = current.T
        response = current.response
        settings = current.deployment_settings

        # Page title
        output = {"title": T("Create Residents Report")}

        # Form fields
        table = s3db.dvr_site_activity
        table.date.default = r.utcnow.date()
        formfields = [table.site_id,
                      table.date,
                      ]

        # Form buttons
        from gluon import INPUT, SQLFORM
        submit_btn = INPUT(_class = "tiny primary button",
                           _name = "submit",
                           _type = "submit",
                           _value = T("Create Report"),
                           )
        cancel_btn = A(T("Cancel"),
                       _href = r.url(id=None, method=""),
                       _class = "action-lnk",
                       )
        buttons = [submit_btn, cancel_btn]

        # Generate the form and add it to the output
        resourcename = r.resource.name
        formstyle = settings.get_ui_formstyle()
        form = SQLFORM.factory(record = None,
                               showid = False,
                               formstyle = formstyle,
                               table_name = resourcename,
                               buttons = buttons,
                               *formfields)
        output["form"] = form

        # Process the form
        formname = "%s/manage" % resourcename
        if form.accepts(r.post_vars,
                        current.session,
                        formname = formname,
                        onvalidation = self.validate,
                        keepvalues = False,
                        hideerror = False,
                        ):

            from core import S3PermissionError, set_last_record_id
            from ..helpers import DRKSiteActivityReport

            formvars = form.vars
            report = DRKSiteActivityReport(site_id = formvars.site_id,
                                           date = formvars.date,
                                           )
            try:
                record_id = report.store()
            except S3PermissionError:
                # Redirect to list view rather than index page
                current.auth.permission.homepage = r.url(id=None, method="")
                r.unauthorised()

            r.resource.lastid = str(record_id)
            set_last_record_id("dvr_site_activity", record_id)

            current.response.confirmation = T("Report created")
            self.next = r.url(id=record_id, method="read")

        response.view = self._view(r, "create.html")

        return output

    # -------------------------------------------------------------------------
    @staticmethod
    def validate(form):
        """
            Validate the form

            Args:
                form: the FORM
        """

        T = current.T
        formvars = form.vars

        if "site_id" in formvars:
            site_id = formvars.site_id
        else:
            # Fall back to default site
            site_id = current.deployment_settings.get_org_default_site()
        if not site_id:
            form.errors["site_id"] = T("No site specified")
        formvars.site_id = site_id

        if "date" in formvars:
            date = formvars.date
        else:
            # Fall back to today
            date = current.request.utcnow.date()
        formvars.date = date

# END =========================================================================
