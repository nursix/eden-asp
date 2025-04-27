"""
    PR module customisations for DRKCM

    License: MIT
"""

from collections import OrderedDict

from gluon import current, URL, A, DIV, TAG, \
                  IS_EMPTY_OR, IS_IN_SET, IS_LENGTH, IS_NOT_EMPTY
from gluon.storage import Storage

from core import IS_ONE_OF

from ..uioptions import get_ui_options

# -------------------------------------------------------------------------
def pr_address_onaccept(form):
    """
        Custom onaccept to set the person's Location to the Private Address
        - unless their case is associated with a Site
    """

    try:
        record_id = form.vars.id
    except AttributeError:
        # Nothing we can do
        return

    db = current.db
    s3db = current.s3db

    atable = db.pr_address
    row = db(atable.id == record_id).select(atable.location_id,
                                            atable.pe_id,
                                            limitby=(0, 1),
                                            ).first()
    try:
        location_id = row.location_id
    except AttributeError:
        # Nothing we can do
        return

    pe_id = row.pe_id

    ctable = s3db.dvr_case
    ptable = s3db.pr_person
    query = (ptable.pe_id == pe_id) & \
            (ptable.id == ctable.person_id)
    case = db(query).select(ctable.site_id,
                            limitby=(0, 1),
                            ).first()

    if case and not case.site_id:
        db(ptable.pe_id == pe_id).update(location_id = location_id,
                                         # Indirect update by system rule,
                                         # do not change modified_* fields:
                                         modified_on = ptable.modified_on,
                                         modified_by = ptable.modified_by,
                                         )

# -------------------------------------------------------------------------
def pr_address_resource(r, tablename):

    # Custom onaccept to set the Person's Location to this address
    # - unless their case is associated with a Site
    current.s3db.add_custom_callback("pr_address",
                                     "onaccept",
                                     pr_address_onaccept,
                                     )

# -------------------------------------------------------------------------
def pr_contact_resource(r, tablename):

    table = current.s3db.pr_contact

    #field = table.contact_description
    #field.readable = field.writable = False

    field = table.value
    field.label = current.T("Number or Address")

    field = table.contact_method
    all_opts = current.msg.CONTACT_OPTS
    subset = ("SMS",
              "EMAIL",
              "HOME_PHONE",
              "WORK_PHONE",
              "FACEBOOK",
              "TWITTER",
              "SKYPE",
              "WHATSAPP",
              "OTHER",
              )
    contact_methods = [(k, all_opts[k]) for k in subset if k in all_opts]
    field.requires = IS_IN_SET(contact_methods, zero=None)
    field.default = "SMS"

# -------------------------------------------------------------------------
def pr_person_set_realm_components():
    """
        Configure components to inherit realm_entity from person record
    """

    current.s3db.configure("pr_person",
                           realm_components = ("person_details",
                                               "contact",
                                               "contact_emergency",
                                               "address",
                                               "image",
                                               "person_tag",
                                               "group_membership",
                                               "dvr_flag",
                                               "case_details",
                                               "case_language",
                                               "case_note",
                                               "residence_status",
                                               "vulnerability",
                                               "case_activity",
                                               "response_action",
                                               ),
                           )

# -------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    s3db = current.s3db
    auth = current.auth

    has_permission = auth.s3_has_permission

    if r.controller == "dvr":

        # Users who can not register new cases also have only limited
        # write-access to basic details of residents
        if not has_permission("create", "pr_person"):

            # Can not write any fields in main person record
            # (fields in components may still be writable, though)
            ptable = s3db.pr_person
            for field in ptable:
                field.writable = False

            # Can not add or edit contact data in person form
            s3db.configure("pr_contact", insertable=False)

            # Can not update shelter registration from person form
            # - check-in/check-out may still be permitted, however
            # - STAFF can update housing unit
            is_staff = auth.s3_has_role("STAFF")

            rtable = s3db.cr_shelter_registration
            for field in rtable:
                if field.name != "shelter_unit_id" or not is_staff:
                    field.writable = False

        if r.name == "person" and not r.component:

            # Configure anonymize-method
            from core import Anonymize
            s3db.set_method("pr_person",
                            method = "anonymize",
                            action = Anonymize,
                            )

            # Configure anonymize-rules
            from ..anonymize import drk_person_anonymize
            s3db.configure("pr_person",
                           anonymize = drk_person_anonymize(),
                           )

            if current.auth.s3_has_role("CASE_MANAGEMENT"):

                from core import GenerateDocument
                GenerateDocument.configure("pr_person")

    # Configure components to inherit realm_entity from person record
    pr_person_set_realm_components()

    from .dvr import dvr_case_onaccept
    s3db.add_custom_callback("dvr_case", "onaccept", dvr_case_onaccept)

# -------------------------------------------------------------------------
def configure_person_tags():
    """
        Configure filtered pr_person_tag components for
        registration numbers:
            - BAMF Registration Number (tag=BAMF)
    """

    current.s3db.add_components("pr_person",
                                pr_person_tag = ({"name": "bamf",
                                                  "joinby": "person_id",
                                                  "filterby": {
                                                    "tag": "BAMF",
                                                    },
                                                  "multiple": False,
                                                  },
                                                 )
                                )

# -------------------------------------------------------------------------
def configure_person_components(use_todos=None):
    """
        Configure custom components for pr_person
    """

    s3db = current.s3db

    if use_todos is None:
        use_todos = get_ui_options().get("case_use_tasks")

    if use_todos:
        # Add ToDo-list component
        ttable = s3db.dvr_note_type
        query = (ttable.is_task == True) & \
                (ttable.deleted == False)
        types = current.db(query).select(ttable.id, cache=s3db.cache)
        s3db.add_components("pr_person",
                            dvr_note = {"name": "todo",
                                        "joinby": "person_id",
                                        "filterby": {"note_type_id": [t.id for t in types],
                                                     }
                                        },
                            )

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    T = current.T
    s3db = current.s3db
    auth = current.auth
    s3 = current.response.s3
    settings = current.deployment_settings

    ui_options = get_ui_options()
    ui_options_get = ui_options.get
    response_tab_need_filter = ui_options_get("response_tab_need_filter")

    if current.request.controller == "dvr":
        configure_person_components(use_todos = ui_options_get("case_use_tasks"))

    settings.base.bigtable = True

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        crud_strings = s3.crud_strings["pr_person"]

        archived = r.get_vars.get("archived")
        if archived in ("1", "true", "yes"):
            crud_strings["title_list"] = T("Invalid Cases")

        if r.controller == "dvr":

            resource = r.resource
            configure = resource.configure

            # Set contacts-method for tab
            s3db.set_method("pr_person",
                            method = "contacts",
                            action = s3db.pr_Contacts,
                            )

            # Add explicit unclear-option for nationality if mandatory,
            # so that cases can be registered even if their nationality
            # is not at hand
            nationality_mandatory = ui_options_get("case_nationality_mandatory")
            settings.pr.nationality_explicit_unclear = nationality_mandatory

            # Autocomplete search-method
            if r.function == "person_search":
                # Autocomplete-Widget (e.g. response actions)
                search_fields = ("first_name", "last_name", "pe_label")
            else:
                # Add-Person-Widget (family members)
                search_fields = ("first_name", "last_name")
            s3db.set_method("pr_person",
                            method = "search_ac",
                            action = s3db.pr_PersonSearchAutocomplete(search_fields),
                            )

            table = r.table
            ctable = s3db.dvr_case

            # Case-sites must be shelters
            field = ctable.site_id
            field.label = T("Shelter")
            field.represent = s3db.org_SiteRepresent(show_type=False)
            requires = field.requires
            if isinstance(requires, IS_EMPTY_OR):
                requires = requires.other
            if hasattr(requires, "instance_types"):
                requires.instance_types = ("cr_shelter",)

            configure_person_tags()

            if not r.component:

                # Can the user see cases from more than one org?
                from ..helpers import case_read_multiple_orgs
                multiple_orgs = case_read_multiple_orgs()[0]

                # Optional: pe_label (ID)
                if ui_options_get("case_use_pe_label"):
                    pe_label = (T("ID"), "pe_label")
                else:
                    pe_label = None

                # Optional: use address in case files
                use_address = ui_options_get("case_use_address")

                # Alternatives: site_id or simple text field
                lodging_opt = ui_options_get("case_lodging")
                if lodging_opt == "site":
                    lodging = "dvr_case.site_id"
                elif lodging_opt == "text":
                    lodging = "case_details.lodging"
                else:
                    lodging = None

                if r.method == "report":

                    # Custom Report Options
                    facts = ((T("Number of Clients"), "count(id)"),
                             (T("Number of Actions"), "count(case_activity.response_action.id)"),
                             )
                    axes = ["gender",
                            "person_details.nationality",
                            "person_details.marital_status",
                            "dvr_case.status_id",
                            #lodging,
                            "residence_status.status_type_id",
                            "residence_status.permit_type_id",
                            ]
                    if lodging:
                        axes.insert(-2, lodging)
                    elif use_address:
                        axes.insert(-2, (T("Place of Residence"), "~.location_id$L3"))

                    report_options = {
                        "rows": axes,
                        "cols": axes,
                        "fact": facts,
                        "defaults": {"rows": axes[0],
                                     "cols": axes[1],
                                     "fact": facts[0],
                                     "totals": True,
                                     },
                        }
                    configure(report_options = report_options)
                    crud_strings["title_report"] = T("Case Statistic")

                if r.interactive and r.method != "import":

                    from core import CustomForm, \
                                     InlineComponent, \
                                     InlineLink, \
                                     TextFilter, \
                                     DateFilter, \
                                     OptionsFilter, \
                                     get_filter_options, \
                                     IS_PERSON_GENDER

                    # Default organisation
                    from ..helpers import case_default_org
                    ctable = s3db.dvr_case
                    field = ctable.organisation_id
                    default_org, selectable = case_default_org()
                    if default_org:
                        if ui_options_get("case_hide_default_org"):
                            field.writable = selectable
                            field.readable = selectable or multiple_orgs
                    if field.readable and not field.writable:
                        field.comment = None
                    field.default = default_org

                    # Organisation is required
                    requires = field.requires
                    if isinstance(requires, IS_EMPTY_OR):
                        field.requires = requires.other

                    # Expose human_resource_id
                    field = ctable.human_resource_id
                    field.comment = None
                    human_resource_id = auth.s3_logged_in_human_resource()
                    if human_resource_id:
                        field.default = human_resource_id
                    field.readable = field.writable = True
                    field.represent = s3db.hrm_HumanResourceRepresent(show_link=False)
                    field.widget = None

                    # Optional: Case Flags
                    if ui_options_get("case_use_flags"):
                        case_flags = InlineLink("case_flag",
                                                label = T("Flags"),
                                                field = "flag_id",
                                                help_field = "comments",
                                                cols = 4,
                                                )
                    else:
                        case_flags = None

                    # No comment for pe_label
                    field = table.pe_label
                    field.comment = None

                    # Optional: mandatory nationality
                    dtable = s3db.pr_person_details
                    if nationality_mandatory:
                        field = dtable.nationality
                        requires = field.requires
                        if isinstance(requires, IS_EMPTY_OR):
                            field.requires = requires.other

                    # Optional: place of birth
                    if ui_options_get("case_use_place_of_birth"):
                        field = dtable.place_of_birth
                        field.readable = field.writable = True
                        place_of_birth = "person_details.place_of_birth"
                    else:
                        place_of_birth = None

                    # Optional: BAMF No.
                    use_bamf = ui_options_get("case_use_bamf")
                    if use_bamf:
                        bamf = InlineComponent(
                                    "bamf",
                                    fields = [("", "value")],
                                    filterby = {"field": "tag",
                                                "options": "BAMF",
                                                },
                                    label = T("BAMF Reference Number"),
                                    multiple = False,
                                    name = "bamf",
                                    )
                    else:
                        bamf = None

                    # Optional: referred by/to
                    use_referral = ui_options_get("case_use_referral")
                    if use_referral:
                        referred_by = "case_details.referred_by"
                        referred_to = "case_details.referred_to"
                    else:
                        referred_by = referred_to = None

                    # Make marital status mandatory, remove "other"
                    field = dtable.marital_status
                    options = dict(s3db.pr_marital_status_opts)
                    del options[9] # Remove "other"
                    field.requires = IS_IN_SET(options, zero=None)

                    # Make gender mandatory, remove "unknown"
                    field = table.gender
                    field.default = None
                    options = dict(s3db.pr_gender_opts)
                    del options[1] # Remove "unknown"
                    field.requires = IS_PERSON_GENDER(options, sort=True)

                    # Last name is required
                    field = table.last_name
                    field.requires = [IS_NOT_EMPTY(), IS_LENGTH(512, minsize=1)]

                    # Optional: site dates
                    if ui_options_get("case_lodging_dates"):
                        on_site_from = (T("Moving-in Date"),
                                        "case_details.on_site_from",
                                        )
                        on_site_until = (T("Moving-out Date"),
                                         "case_details.on_site_until",
                                         )
                    else:
                        on_site_from = None
                        on_site_until = None

                    # Optional: Address
                    if use_address:
                        address = InlineComponent(
                                        "address",
                                        label = T("Current Address"),
                                        fields = [("", "location_id")],
                                        filterby = {"field": "type",
                                                    "options": "1",
                                                    },
                                        link = False,
                                        multiple = False,
                                        )
                    else:
                        address = None

                    # Date of Entry (alternative labels)
                    dtable = s3db.dvr_case_details
                    field = dtable.arrival_date
                    label = ui_options_get("case_arrival_date_label")
                    label = T(label) if label else T("Date of Entry")
                    field.label = label
                    field.comment = DIV(_class = "tooltip",
                                        _title = "%s|%s" % (label,
                                                            T("Date of Entry Certificate"),
                                                            ),
                                        )

                    # Optional: Residence Status
                    if ui_options_get("case_use_residence_status"):
                        # Remove Add-links
                        rtable = s3db.dvr_residence_status
                        field = rtable.status_type_id
                        field.comment = None
                        field = rtable.permit_type_id
                        field.comment = None
                        residence_status = InlineComponent(
                                            "residence_status",
                                            fields = [#"status_type_id",
                                                      "permit_type_id",
                                                      #"reference",
                                                      #"valid_from",
                                                      "valid_until",
                                                      "comments",
                                                      ],
                                            label = T("Residence Status"),
                                            multiple = False,
                                            )
                    else:
                        residence_status = None

                    # Optional: Occupation/Educational Background
                    if ui_options_get("case_use_occupation"):
                        occupation = "person_details.occupation"
                    else:
                        occupation = None
                    if ui_options_get("case_use_education"):
                        education = "person_details.education"
                    else:
                        education = None

                    # Custom CRUD form
                    crud_form = CustomForm(

                        # Case Details ----------------------------
                        "dvr_case.date",
                        "dvr_case.organisation_id",
                        "dvr_case.human_resource_id",
                        (T("Case Status"), "dvr_case.status_id"),
                        case_flags,

                        # Person Details --------------------------
                        pe_label,
                        "last_name",
                        "first_name",
                        "person_details.nationality",
                        "date_of_birth",
                        place_of_birth,
                        bamf,
                        "case_details.arrival_date",
                        "gender",
                        "person_details.marital_status",

                        # Process Data ----------------------------
                        referred_by,
                        referred_to,
                        lodging,
                        on_site_from,
                        on_site_until,
                        address,
                        residence_status,

                        # Other Details ---------------------------
                        InlineComponent(
                                "contact",
                                fields = [("", "value")],
                                filterby = {"field": "contact_method",
                                            "options": "SMS",
                                            },
                                label = T("Mobile Phone"),
                                multiple = False,
                                name = "phone",
                                ),
                        education,
                        occupation,
                        "person_details.literacy",
                        InlineComponent(
                                "case_language",
                                fields = ["language",
                                          "quality",
                                          "comments",
                                          ],
                                label = T("Language / Communication Mode"),
                                ),
                        "dvr_case.comments",

                        # Archived-flag ---------------------------
                        (T("Invalid"), "dvr_case.archived"),
                        )

                    # Subheadings for case form
                    person_details = "pe_label" if pe_label else "last_name"
                    subheadings = {
                        "dvr_case_date": T("Case Status"),
                        person_details: T("Person Details"),
                        "phonecontact": T("Other Details"),
                        "dvr_case_archived": T("File Status"),
                        }

                    # Custom filter widgets

                    # Extract case status options from original filter widget
                    status_opts = None
                    filter_widgets = resource.get_config("filter_widgets")
                    for fw in filter_widgets:
                        if fw.field == "dvr_case.status_id":
                            status_opts = fw.opts.get("options")
                            break
                    if status_opts is None:
                        # Fallback
                        status_opts = s3db.dvr_case_status_filter_opts

                    filter_widgets = [
                        TextFilter(["pe_label",
                                    "first_name",
                                    "middle_name",
                                    "last_name",
                                    "dvr_case.comments",
                                    ],
                                    label = T("Search"),
                                    comment = T("You can search by name, ID or comments"),
                                    ),
                        DateFilter("date_of_birth",
                                   hidden = True,
                                   ),
                        OptionsFilter("dvr_case.status_id",
                                      cols = 3,
                                      #default = None,
                                      #label = T("Case Status"),
                                      options = status_opts,
                                      sort = False,
                                      hidden = True,
                                      ),
                        OptionsFilter("person_details.nationality",
                                      hidden = True,
                                      ),
                        DateFilter("dvr_case.date",
                                   hidden = True,
                                   ),
                        ]

                    # BAMF-Ref.No.-filter if using BAMF
                    if use_bamf:
                        filter_widgets.append(
                            TextFilter(["bamf.value"],
                                       label = T("BAMF Ref.No."),
                                       hidden = True,
                                       ))

                    # Multi-ID filter if using ID
                    if pe_label is not None:
                        filter_widgets.append(
                            TextFilter(["pe_label"],
                                       label = T("IDs"),
                                       match_any = True,
                                       hidden = True,
                                       comment = T("Search for multiple IDs (separated by blanks)"),
                                       ))

                    # Ref.No.-filter if using service contacts
                    if ui_options_get("case_use_service_contacts"):
                        filter_widgets.append(
                            TextFilter(["service_contact.reference"],
                                       label = T("Ref.No."),
                                       hidden = True,
                                       comment = T("Search by service contact reference number"),
                                       ))

                    # Flag-filter if using case flags
                    if case_flags:
                        filter_widgets.insert(2,
                            OptionsFilter("case_flag_case.flag_id",
                                          label = T("Flags"),
                                          options = get_filter_options("dvr_case_flag",
                                                                       translate = True,
                                                                       ),
                                          cols = 3,
                                          hidden = True,
                                          ))
                    # Org-filter if user can see cases from multiple orgs/branches
                    if multiple_orgs:
                        filter_widgets.insert(1,
                            OptionsFilter("dvr_case.organisation_id"))

                    configure(crud_form = crud_form,
                              subheadings = subheadings,
                              filter_widgets = filter_widgets,
                              )

                # Custom list fields (must be outside of r.interactive)
                list_fields = [pe_label,
                               "last_name",
                               "first_name",
                               "date_of_birth",
                               "gender",
                               "person_details.nationality",
                               "dvr_case.date",
                               "dvr_case.status_id",
                               lodging,
                               ]
                if multiple_orgs:
                    list_fields.insert(-1, "dvr_case.organisation_id")

                configure(list_fields = list_fields)

            elif r.component_name == "case_appointment":

                if ui_options_get("appointments_use_organizer") and \
                    r.interactive and r.method is None and not r.component_id:
                    r.method = "organize"

            elif r.component_name == "case_activity":

                # Reconfigure dvr_case_activity
                # - overriding some default prep modifications
                from .dvr import configure_case_activity
                configure_case_activity(r)

            elif r.component_name == "response_action":

                if response_tab_need_filter:
                    # Configure filter widgets for response tab
                    from core import DateFilter, OptionsFilter, TextFilter
                    r.component.configure(
                        filter_widgets = [
                            TextFilter(["response_action_theme.theme_id$name",
                                        "response_action_theme.comments",
                                        ],
                                        label = T("Search"),
                                        ),
                            OptionsFilter("response_action_theme.theme_id$need_id",
                                          label = T("Counseling Reason"),
                                          hidden = True,
                                          ),
                            DateFilter("start_date",
                                       hidden = True,
                                       hide_time = not ui_options_get("response_use_time"),
                                       ),
                            ],
                        )
                    settings.search.filter_manager = False

            elif r.component_name == "todo":

                from core import OptionsFilter
                r.component.configure(
                    filter_widgets = [
                        OptionsFilter("status",
                                      options = OrderedDict((("CUR", T("Current")),
                                                             ("OBS", T("Obsolete")),
                                                             )),
                                      default = "CUR",
                                      cols = 2,
                                      sort = False,
                                      ),
                        ]
                    )
                settings.search.filter_manager = False

        elif r.controller == "default":

            # Personal Profile

            if r.component_name == "group_membership":

                # Team memberships are read-only
                r.component.configure(insertable = False,
                                      editable = False,
                                      deletable = False,
                                      )

            elif r.component_name == "human_resource":

                # Staff/Volunteer records are read-only
                r.component.configure(insertable = False,
                                      editable = False,
                                      deletable = False,
                                      )

        return result
    s3.prep = custom_prep

    standard_postp = s3.postp
    def custom_postp(r, output):

        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.controller == "dvr" and r.record and isinstance(output, dict):

            # Custom CRUD buttons
            if "buttons" not in output:
                buttons = output["buttons"] = {}
            else:
                buttons = output["buttons"]

            if not r.component and r.method in (None, "update", "read"):

                # Anonymize-button
                from core import AnonymizeWidget
                anonymize = AnonymizeWidget.widget(r, _class="action-btn anonymize-btn")

                # Doc-From-Template-button
                if ui_options_get("case_document_templates") and \
                    auth.s3_has_role("CASE_MANAGEMENT"):
                    doc_from_template = A(T("Document from Template"),
                                        _class = "action-btn s3_modal",
                                        _title = T("Generate Document from Template"),
                                        _href = URL(args=[r.id, "templates"]),
                                        )
                else:
                    doc_from_template = ""

                # Render in place of the delete-button
                buttons["delete_btn"] = TAG[""](doc_from_template, anonymize)

            elif r.component_name == "todo" and r.component_id:

                del_btn = buttons.get("delete_btn")
                pdf_btn = A(T("Download PDF"),
                            _href = r.url(method = "",
                                          target = r.component_id,
                                          representation = "pdf",
                                          ),
                            _class="action-btn",
                            )
                buttons["delete_btn"] = TAG[""](pdf_btn, del_btn) if del_btn else pdf_btn

        return output
    s3.postp = custom_postp

    if current.request.controller == "dvr":
        # Custom rheader
        from ..rheaders import drk_dvr_rheader
        attr["rheader"] = drk_dvr_rheader

        # Activate filters on component tabs
        attr["hide_filter"] = {"response_action": not response_tab_need_filter,
                               "todo": False,
                               }

        args = current.request.args
        if len(args) > 1 and args[1][:4] == "todo":
            attr["pdf_title"] = "ToDo"
            attr["pdf_filename"] = "todos.pdf"

    return attr

# -------------------------------------------------------------------------
def pr_group_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        if r.controller in ("hrm", "vol"):

            if not r.component:

                # No inline-adding new organisations
                ottable = s3db.org_organisation_team
                field = ottable.organisation_id
                field.comment = None

                # Organisation is required
                from core import CustomForm, \
                                 InlineComponent
                crud_form = CustomForm(
                                "name",
                                "description",
                                InlineComponent("organisation_team",
                                                label = T("Organization"),
                                                fields = ["organisation_id"],
                                                multiple = False,
                                                required = True,
                                                ),
                                "comments",
                                )
                r.resource.configure(crud_form = crud_form)

            elif r.component_name == "group_membership":

                from core import S3PersonAutocompleteWidget

                # Make sure only HRs can be added to teams
                mtable = s3db.pr_group_membership
                field = mtable.person_id
                field.widget = S3PersonAutocompleteWidget(
                                    #controller="hrm",
                                    ajax_filter="human_resource.id__ne=None",
                                    )
        return result
    s3.prep = custom_prep

    return attr


# -------------------------------------------------------------------------
def pr_group_membership_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    ui_options = get_ui_options()

    # Custom prep
    standard_prep = s3.prep
    def custom_prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        ROLE = T("Role")

        resource = r.resource
        if r.controller == "dvr":

            # Set contacts-method to retain the tab
            s3db.set_method("pr_person",
                            method = "contacts",
                            action = s3db.pr_Contacts,
                            )

            configure_person_tags()

            if ui_options.get("case_use_pe_label"):
                pe_label = (T("ID"), "person_id$pe_label")
            else:
                pe_label = None
            s3db.pr_person.pe_label.label = T("ID")

            if r.interactive:
                table = resource.table

                from core import PersonSelector

                field = table.person_id
                field.represent = s3db.pr_PersonRepresent(show_link=True)
                field.widget = PersonSelector(controller = "dvr",
                                              pe_label = bool(pe_label),
                                              nationality = True,
                                              )

                field = table.role_id
                field.readable = field.writable = True
                field.label = ROLE
                field.comment = DIV(_class="tooltip",
                                    _title="%s|%s" % (T("Role"),
                                                      T("The role of the person within the family"),
                                                      ))
                field.requires = IS_EMPTY_OR(
                                    IS_ONE_OF(current.db, "pr_group_member_role.id",
                                              field.represent,
                                              filterby = "group_type",
                                              filter_opts = (7,),
                                              ))

                field = table.group_head
                field.label = T("Head of Family")

                # Custom CRUD strings for this perspective
                s3.crud_strings["pr_group_membership"] = Storage(
                    label_create = T("Add Family Member"),
                    title_display = T("Family Member Details"),
                    title_list = T("Family Members"),
                    title_update = T("Edit Family Member"),
                    label_list_button = T("List Family Members"),
                    label_delete_button = T("Remove Family Member"),
                    msg_record_created = T("Family Member added"),
                    msg_record_modified = T("Family Member updated"),
                    msg_record_deleted = T("Family Member removed"),
                    msg_list_empty = T("No Family Members currently registered")
                    )

            list_fields = [pe_label,
                           "person_id",
                           "person_id$date_of_birth",
                           "person_id$gender",
                           "group_head",
                           (ROLE, "role_id"),
                           (T("Case Status"), "person_id$dvr_case.status_id"),
                           "comments",
                           ]
            # Retain group_id in list_fields if added in standard prep
            lfields = resource.get_config("list_fields")
            if "group_id" in lfields:
                list_fields.insert(0, "group_id")
            resource.configure(filter_widgets = None,
                               list_fields = list_fields,
                               )
        return result
    s3.prep = custom_prep

    # Custom rheader
    from ..rheaders import drk_dvr_rheader
    attr["rheader"] = drk_dvr_rheader

    return attr

# END =========================================================================
