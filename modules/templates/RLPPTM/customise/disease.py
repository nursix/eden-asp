"""
    DISEASE module customisations for RLPPTM

    License: MIT
"""

import calendar
import datetime

from collections import OrderedDict
from dateutil import rrule
from dateutil.relativedelta import relativedelta

from gluon import current, IS_EMPTY_OR, IS_IN_SET
from gluon.storage import Storage

from core import CustomController, IS_ONE_OF, IS_UTC_DATE, BasicCRUD, S3Represent, \
                 get_form_record_id

# -------------------------------------------------------------------------
def case_diagnostics_onaccept(form):
    """
        Custom onaccept routine for disease_case_diagnostics
        - auto-generate/update corresponding daily testing report
    """

    record_id = get_form_record_id(form)
    if not record_id:
        return

    settings = current.deployment_settings

    db = current.db
    s3db = current.s3db

    # Get the record
    table = s3db.disease_case_diagnostics
    query = (table.id == record_id)
    record = db(query).select(table.site_id,
                              table.result_date,
                              table.disease_id,
                              limitby = (0, 1),
                              ).first()
    if not record:
        return

    site_id = record.site_id
    result_date = record.result_date
    disease_id = record.disease_id

    if site_id and disease_id and result_date:
        # Update daily testing report
        if settings.get_disease_testing_report_by_demographic():
            from ..helpers import update_daily_report_by_demographic as update_daily_report
        else:
            from ..helpers import update_daily_report
        update_daily_report(site_id, result_date, disease_id)

# -------------------------------------------------------------------------
def disease_case_diagnostics_resource(r, tablename):

    T = current.T
    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    table = s3db.disease_case_diagnostics

    single_disease = single_site = False

    # Make site link visible + limit to managed+approved+active sites
    field = table.site_id
    field.readable = field.writable = True

    from ..helpers import get_managed_facilities
    site_ids = get_managed_facilities("TEST_PROVIDER")
    if site_ids is not None:
        if len(site_ids) == 1:
            single_site = True
            # Default + make r/o
            field.default = site_ids[0]
            field.writable = False
        else:
            # Limit to managed sites
            dbset = db(s3db.org_site.site_id.belongs(site_ids))
            field.requires = IS_ONE_OF(dbset, "org_site.site_id",
                                       field.represent,
                                       )
    else:
        # Site is required
        requires = field.requires
        if isinstance(requires, IS_EMPTY_OR):
            requires = requires.other

    # Enable disease link and make it mandatory
    field = table.disease_id
    field.readable = field.writable = True
    field.comment = None
    requires = field.requires
    if isinstance(requires, (list, tuple)):
        requires = requires[0]
    if isinstance(requires, IS_EMPTY_OR):
        field.requires = requires.other

    # If there is only one disease, default the selector + make r/o
    dtable = s3db.disease_disease
    rows = db(dtable.deleted == False).select(dtable.id,
                                              cache = s3db.cache,
                                              limitby = (0, 2),
                                              )
    if len(rows) == 1:
        single_disease = True
        field.default = rows[0].id
        field.writable = False

    # Default probe details
    field = table.probe_status
    field.default = "PROCESSED"

    now = current.request.utcnow

    # Probe date/time is mandatory
    field = table.probe_date
    field.label = T("Test Date/Time")
    field.default = now
    requires = field.requires
    if isinstance(requires, IS_EMPTY_OR):
        requires = requires.other

    # Default result date
    field = table.result_date
    field.default = now.date()
    field.writable = False

    # Formal test types
    # TODO move to lookup table?
    type_options = (("LFD", T("LFD Antigen Test")),
                    ("PCR", T("PCR Test")),
                    ("SER", T("Serum Antibody Test")),
                    ("OTH", T("Other")),
                    )
    field = table.test_type
    field.default = "LFD"
    field.writable = False # fixed for now
    field.requires = IS_IN_SET(type_options,
                               zero = "",
                               sort = False,
                               )
    field.represent = S3Represent(options=dict(type_options))

    # Formal results
    result_options = (("NEG", T("Negative")),
                      ("POS", T("Positive")),
                      # Only relevant for two-step workflow:
                      #("INC", T("Inconclusive")),
                      )
    field = table.result
    field.requires = IS_IN_SET(result_options,
                               zero = "",
                               sort = False,
                               error_message = T("Please select a value"),
                               )
    field.represent = S3Represent(options=dict(result_options))

    if not single_site or current.auth.s3_has_role("DISEASE_TEST_READER"):
        site_id = "site_id"
    else:
        site_id = None
    disease_id = "disease_id" if not single_disease else None

    if settings.get_disease_testing_report_by_demographic():
        table.demographic_id.readable = True
        demographic_id = "demographic_id"
    else:
        demographic_id = None

    # Custom list_fields
    list_fields = [site_id,
                   disease_id,
                   "probe_date",
                   demographic_id,
                   "result",
                   "device_id",
                   ]

    # Custom form (for read)
    from core import CustomForm
    crud_form = CustomForm(disease_id,
                           site_id,
                           "probe_date",
                           demographic_id,
                           "result",
                           "result_date",
                           )

    # Filters

    # Limit report by setting date filter default start date
    if r.method == "report":
        start = current.request.utcnow.date() - relativedelta(weeks=1)
        default = {"ge": start}
    else:
        default = None

    from core import DateFilter, OptionsFilter, get_filter_options
    filter_widgets = [DateFilter("probe_date",
                                 label = T("Date"),
                                 hide_time = True,
                                 default = default,
                                 ),
                      OptionsFilter("result",
                                    options = OrderedDict(result_options),
                                    hidden = True,
                                    ),
                      DateFilter("result_date",
                                 label = T("Result Date"),
                                 hidden = True,
                                 ),
                      ]
    if site_id:
        # Better to use text filter for site name?
        # - better scalability, but cannot select multiple
        filter_widgets.append(
            OptionsFilter("site_id", hidden=True))
    if disease_id:
        filter_widgets.append(
            OptionsFilter("disease_id",
                          options = lambda: get_filter_options("disease_disease"),
                          hidden=True,
                          ))
    if demographic_id:
        filter_widgets.append(
            OptionsFilter("demographic_id",
                          options = lambda: get_filter_options("disease_demographic"),
                          hidden=True,
                          ))

    # Report options
    facts = ((T("Number of Tests"), "count(id)"),
             )
    axes = ["result",
            "site_id",
            #"disease_id",
            ]
    if disease_id:
        axes.append(disease_id)
    report_options = {
        "rows": axes,
        "cols": axes,
        "fact": facts,
        "defaults": {"rows": axes[1],
                     "cols": axes[0],
                     "fact": facts[0],
                     "totals": True,
                     },
        }

    s3db.configure("disease_case_diagnostics",
                   insertable = False,
                   editable = False,
                   deletable = False,
                   crud_form = crud_form,
                   filter_widgets = filter_widgets,
                   list_fields = list_fields,
                   report_options = report_options,
                   orderby = "disease_case_diagnostics.probe_date desc",
                   )

    # Custom callback to auto-update test station daily reports
    s3db.add_custom_callback("disease_case_diagnostics",
                             "onaccept",
                             case_diagnostics_onaccept,
                             )

    # Custom REST methods
    from ..cwa import TestResultRegistration
    s3db.set_method("disease_case_diagnostics",
                    method = "register",
                    action = TestResultRegistration,
                    )
    s3db.set_method("disease_case_diagnostics",
                    method = "certify",
                    action = TestResultRegistration,
                    )
    s3db.set_method("disease_case_diagnostics",
                    method = "cwaretry",
                    action = TestResultRegistration,
                    )

    crud_strings = current.response.s3.crud_strings
    crud_strings["disease_case_diagnostics"] = Storage(
        label_create = T("Register Test Result"),
        title_display = T("Test Result"),
        title_list = T("Test Results"),
        title_update = T("Edit Test Result"),
        title_upload = T("Import Test Results"),
        label_list_button = T("List Test Results"),
        label_delete_button = T("Delete Test Result"),
        msg_record_created = T("Test Result added"),
        msg_record_modified = T("Test Result updated"),
        msg_record_deleted = T("Test Result deleted"),
        msg_list_empty = T("No Test Results currently registered"),
        )

# -------------------------------------------------------------------------
def disease_case_diagnostics_controller(**attr):

    T = current.T
    s3 = current.response.s3

    # Enable bigtable features
    current.deployment_settings.base.bigtable = True

    ## Custom prep
    #standard_prep = s3.prep
    #def prep(r):
    #    # Call standard prep
    #    result = standard_prep(r) if callable(standard_prep) else True
    #
    #    return result
    #s3.prep = prep

    standard_postp = s3.postp
    def custom_postp(r, output):

        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if isinstance(output, dict):

            record = r.record
            method = r.method

            # Add Register-button in list and read views
            key, label = None, None
            permitted = current.auth.s3_has_permission("create", r.table)
            if permitted:
                if not record and not method:
                    key, label = "add_btn", T("Register Test Result")
                elif record and method in (None, "read"):
                    key, label = "list_btn", T("Register another test result")
            if key:
                regbtn = BasicCRUD.crud_button(label = label,
                                               _href = r.url(id="", method="register"),
                                               )
                if record:
                    from gluon import BUTTON, TAG
                    pdfbtn = BUTTON(T("Certificate Form (PDF)"),
                                    _type = "button",
                                    _class = "action-btn s3-download-button",
                                    data = {"url": r.url(method = "certify",
                                                         representation = "pdf",
                                                         ),
                                            },
                                    )
                    regbtn = TAG[""](regbtn, pdfbtn)
                output["buttons"] = {key: regbtn}

        return output
    s3.postp = custom_postp

    return attr

# -----------------------------------------------------------------------------
def earliest_reporting_date(today=None):
    """
        Returns the first day of the current month if we're past the
        third business day of this month; otherwise the first of the
        previous month

        Args:
            today: the date of today

        Returns:
            a date
    """

    from ..helpers import rlp_holidays

    if today is None:
        today = datetime.datetime.utcnow().date()

    if today <= datetime.date(2022,3,3):
        return today - relativedelta(months=3, day=1)

    start = today.replace(day=1)
    end = today.replace(day=calendar.monthrange(today.year, today.month)[1])

    rules = rrule.rruleset()
    rules.rrule(rrule.rrule(rrule.MONTHLY, dtstart=start, until=end, bysetpos=3, count=1,
                            byweekday=(rrule.MO, rrule.TU, rrule.WE, rrule.TH, rrule.FR)))
    rules.exrule(rlp_holidays(start, end))

    if today > list(rules)[0].date():
        earliest = start
    else:
        earliest = today - relativedelta(months=1, day=1)

    return earliest

# -------------------------------------------------------------------------
def disease_testing_device_resource(r, tablename):

    s3db = current.s3db

    table = s3db.disease_testing_device

    # Cannot modify approved-flag manually
    field = table.approved
    field.writable = False

    s3db.configure("disease_testing_device",
                   insertable = False,
                   editable = current.auth.s3_has_role("ADMIN"),
                   deletable = False,
                   )

# -------------------------------------------------------------------------
def disease_testing_report_resource(r, tablename):

    from core import S3CalendarWidget, DateFilter, TextFilter

    T = current.T
    settings = current.deployment_settings

    db = current.db
    s3db = current.s3db
    auth = current.auth

    table = s3db.disease_testing_report

    list_fields = ["date",
                   (T("Test Station ID"), "site_id$org_facility.code"),
                   "site_id",
                   #"disease_id",
                   "tests_total",
                   "tests_positive",
                   "comments",
                   ]

    # No add-link on disease_id
    field = table.disease_id
    field.comment = None

    # If there is only one disease, set as default + hide field
    dtable = s3db.disease_disease
    rows = db(dtable.deleted == False).select(dtable.id,
                                              cache = s3db.cache,
                                              limitby = (0, 2),
                                              )
    if len(rows) == 1:
        field.default = rows[0].id
        field.readable = field.writable = False
    else:
        list_fields.insert(1, "disease_id")

    if r.tablename == "disease_testing_report" and r.record and \
       settings.get_disease_testing_report_by_demographic() and \
       r.method != "read" and \
       auth.s3_has_permission("update", table, record_id=r.record.id):
        # Hide totals in create/update form
        table.tests_total.readable = False
        table.tests_positive.readable = False

    # Order testing sites selector by obsolete-flag
    field = table.site_id
    stable = current.s3db.org_site
    field.requires = IS_ONE_OF(db, "org_site.site_id",
                               field.represent,
                               instance_types = ["org_facility"],
                               orderby = (stable.obsolete, stable.name),
                               sort = False,
                               )

    # Check how many sites are selectable
    selectable = [o[0] for o in field.requires.options() if o[0]]
    if len(selectable) == 1:
        # If only one selectable site, set as default + make r/o
        field.default = selectable[0]
        field.writable = False
    else:
        # If one active site, set it as default, but leave selectable
        query = (stable.site_id.belongs(selectable)) & \
                (stable.obsolete == False)
        active = db(query).select(stable.site_id, limitby = (0, 2))
        if len(active) == 1:
            field.default = active.first().site_id

    # Allow daily reports up to 3 months back in time (1st of month)
    today = current.request.utcnow.date()
    if auth.s3_has_role("ORG_GROUP_ADMIN"):
        # No limit for OrgGroupAdmins/Admins
        earliest = None
    else:
        earliest = earliest_reporting_date(today)
    field = table.date
    field.requires = IS_UTC_DATE(minimum = earliest,
                                 maximum = today,
                                 )
    field.widget = S3CalendarWidget(minimum = earliest,
                                    maximum = today,
                                    month_selector = True,
                                    )

    # Limit report by setting date filter default start date
    if r.method == "report":
        start = current.request.utcnow.date() - relativedelta(weeks=1)
        default = {"ge": start}
    else:
        default = None

    filter_widgets = [TextFilter(["site_id$name",
                                  "site_id$org_facility.code",
                                  "comments",
                                  ],
                                 label = T("Search"),
                                 ),
                      DateFilter("date",
                                 default = default,
                                 ),
                      ]

    # Daily reports only writable for ORG_ADMINs of test stations
    writable = auth.s3_has_roles(["ORG_ADMIN", "TEST_PROVIDER"], all=True)

    s3db.configure("disease_testing_report",
                   filter_widgets = filter_widgets,
                   list_fields = list_fields,
                   insertable = writable,
                   editable = writable,
                   deletable = writable,
                   )

# -------------------------------------------------------------------------
def disease_testing_report_controller(**attr):

    # Enable bigtable features
    current.deployment_settings.base.bigtable = True

    return attr

# -------------------------------------------------------------------------
def disease_testing_demographic_resource(r, tablename):

    # Limit report by setting date filter default start date
    if r.method == "report":
        start = current.request.utcnow.date() - relativedelta(weeks=1)
        default = {"ge": start}
    else:
        default = None

    from core import DateFilter, \
                     OptionsFilter, \
                     TextFilter, \
                     get_filter_options

    filter_widgets = [TextFilter(["report_id$site_id$name",
                                  "report_id$comments",
                                  ],
                                 label = current.T("Search"),
                                 ),
                      DateFilter("report_id$date",
                                 default = default,
                                 ),
                      OptionsFilter("demographic_id",
                                    options = get_filter_options("disease_demographic"),
                                    hidden = True,
                                    ),
                      ]

    current.s3db.configure("disease_testing_demographic",
                           filter_widgets = filter_widgets,
                           )

# -------------------------------------------------------------------------
def disease_testing_demographic_controller(**attr):

    # Enable bigtable features
    current.deployment_settings.base.bigtable = True

    return attr

# -------------------------------------------------------------------------
def disease_daycare_testing_controller(**attr):

    T = current.T

    s3db = current.s3db
    is_admin = current.auth.s3_has_role("ADMIN")

    s3 = current.response.s3

    # Enable bigtable features
    current.deployment_settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def prep(r):
        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource

        # Get pending responders
        managed_orgs = pending = None
        if not is_admin:
            from ..config import TESTSTATIONS
            from ..helpers import get_managed_orgs
            managed_orgs = get_managed_orgs(TESTSTATIONS)
            if managed_orgs:
                pending = s3db.disease_daycare_testing_get_pending_responders(managed_orgs)

        if pending:
            # Filter organisation_id selector to pending responders
            table = resource.table
            field = table.organisation_id
            if len(pending) == 1:
                field.default = pending[0]
                field.writable = False
            else:
                otable = s3db.org_organisation
                dbset = current.db(otable.id.belongs(pending))
                field.requires = IS_ONE_OF(dbset, "org_organisation.id",
                                           field.represent,
                                           )
            insertable = True
            if not r.method and not r.record:
                r.method = "create"
            current.session.s3.mandatory_page = True
        else:
            insertable = False

        editable = True if managed_orgs or is_admin else False
        resource.configure(insertable = insertable,
                           editable = editable,
                           deletable = editable,
                           )

        if (insertable or editable) and not is_admin:
            # Configure custom form
            from core import CustomForm
            crud_form = CustomForm("organisation_id",
                                   (T("Does your organization conduct tests in daycare centers?"),
                                    "daycare_testing"),
                                   (T("Do you test in daycare centers on a regular basis?"),
                                    "regular_testing"),
                                   (T("How frequently do you test in daycare centers?"),
                                    "frequency"),
                                   (T("How many daycare centers are regularly serviced by your organization?"),
                                    "number_of_dc"),
                                   "comments",
                                   )
            resource.configure(crud_form = crud_form)

        if r.method == "create":
            current.menu.options = None

        return result
    s3.prep = prep

    standard_postp = s3.postp
    def custom_postp(r, output):

        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.method == "create":

            CustomController._view("RLPPTM", "register.html")

            if isinstance(output, dict):
                output["title"] = s3.crud_strings["disease_daycare_testing"].title_list
                intro = s3db.cms_get_content("DaycareTestingInquiry",
                                             module = "disease",
                                             resource = "daycare_testing",
                                             )
                if intro:
                    output["intro"] = intro

        return output
    s3.postp = custom_postp

    return attr

# END =========================================================================
