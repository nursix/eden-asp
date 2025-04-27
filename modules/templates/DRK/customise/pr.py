"""
    PR module customisations for DRK

    License: MIT
"""

import datetime

from gluon import current, URL, A, SPAN, TAG
from gluon.storage import Storage

from core import FS, IS_ONE_OF, s3_str

# Limit after which a checked-out resident is reported overdue (days)
ABSENCE_LIMIT = 5

# =============================================================================
def drk_absence(row):
    """
        Field method to display duration of absence in
        dvr/person list view and rheader

        Args:
            row: the Row
    """

    if hasattr(row, "cr_shelter_registration"):
        registration = row.cr_shelter_registration
    else:
        registration = None

    result = current.messages["NONE"]

    if registration is None or \
       not hasattr(registration, "registration_status") or \
       not hasattr(registration, "check_out_date"):
        # must reload
        db = current.db
        s3db = current.s3db

        person = row.pr_person if hasattr(row, "pr_person") else row
        person_id = person.id
        if not person_id:
            return result
        table = s3db.cr_shelter_registration
        query = (table.person_id == person_id) & \
                (table.deleted != True)
        registration = db(query).select(table.registration_status,
                                        table.check_out_date,
                                        limitby = (0, 1),
                                        ).first()

    if registration and \
       registration.registration_status == 3:

        T = current.T

        check_out_date = registration.check_out_date
        if check_out_date:

            delta = (current.request.utcnow - check_out_date).total_seconds()
            if delta < 0:
                delta = 0
            days = int(delta / 86400)

            if days < 1:
                result = "<1 %s" % T("Day")
            elif days == 1:
                result = "1 %s" % T("Day")
            else:
                result = "%s %s" % (days, T("Days"))

            if days >= ABSENCE_LIMIT:
                result = SPAN(result, _class="overdue")

        else:
            result = SPAN(T("Date unknown"), _class="overdue")

    return result

# -------------------------------------------------------------------------
def event_overdue(code, interval):
    """
        Get cases (person_ids) for which a certain event is overdue

        Args:
            code: the event code
            interval: the interval in days
    """

    db = current.db
    s3db = current.s3db

    ttable = s3db.dvr_case_event_type
    ctable = s3db.dvr_case
    stable = s3db.dvr_case_status
    etable = s3db.dvr_case_event

    # Get event type ID
    if code[-1] == "*":
        # Prefix
        query = (ttable.code.like("%s%%" % code[:-1]))
        limitby = None
    else:
        query = (ttable.code == code)
        limitby = (0, 1)
    query &= (ttable.deleted == False)

    rows = db(query).select(ttable.id, limitby=limitby)
    if not rows:
        # No such event type
        return set()
    elif limitby:
        type_query = (etable.type_id == rows.first().id)
    else:
        type_query = (etable.type_id.belongs(set(row.id for row in rows)))

    # Determine deadline
    now = current.request.utcnow
    then = now - datetime.timedelta(days=interval)

    # Check only open cases
    join = stable.on((stable.id == ctable.status_id) & \
                     (stable.is_closed == False))

    # Join only events after the deadline
    left = etable.on((etable.person_id == ctable.person_id) & \
                     type_query & \
                     (etable.date != None) & \
                     (etable.date >= then) & \
                     (etable.deleted == False))

    # ...and then select the rows which don't have any
    query = (ctable.archived == False) & \
            (ctable.date < then.date()) & \
            (ctable.deleted == False)
    rows = db(query).select(ctable.person_id,
                            left = left,
                            join = join,
                            groupby = ctable.person_id,
                            having = (etable.date.max() == None),
                            )
    return set(row.person_id for row in rows)

# -------------------------------------------------------------------------
def pr_person_resource(r, tablename):

    s3db = current.s3db
    auth = current.auth

    has_permission = auth.s3_has_permission

    # Users who can not register new residents also have
    # only limited write-access to basic details of residents
    if r.controller == "dvr" and not has_permission("create", "pr_person"):

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

    # Do not include acronym in Case-Org Representation
    table = s3db.dvr_case
    field = table.organisation_id
    field.represent = s3db.org_OrganisationRepresent(parent=False, acronym=False)

# -------------------------------------------------------------------------
def configure_person_tags():
    """
        Configure filtered pr_person_tag components for
        registration numbers:
            - EasyOpt Number (tag=EONUMBER)
            - BAMF Registration Number (tag=BAMF)
    """

    current.s3db.add_components("pr_person",
                                pr_person_tag = (#{"name": "eo_number",
                                                 # "joinby": "person_id",
                                                 # "filterby": {
                                                 #   "tag": "EONUMBER",
                                                 #   },
                                                 # "multiple": False,
                                                 # },
                                                 {"name": "bamf",
                                                  "joinby": "person_id",
                                                  "filterby": {
                                                    "tag": "BAMF",
                                                    },
                                                  "multiple": False,
                                                  },
                                                 )
                                )

# -------------------------------------------------------------------------
def configure_case_form(resource, privileged=False, cancel=False):

    T = current.T

    from core import CustomForm, InlineComponent, InlineLink

    if cancel:
        # Ignore registration data in form if the registration
        # is to be cancelled - otherwise a new registration is
        # created by the subform-processing right after
        # dvr_case_onaccept deletes the current one:
        reg_shelter = None
        reg_status = None
        reg_unit_id = None
        reg_check_in_date = None
        reg_check_out_date = None
    else:
        reg_shelter = "shelter_registration.shelter_id"
        reg_status = (T("Presence"),
                      "shelter_registration.registration_status",
                      )
        reg_unit_id = "shelter_registration.shelter_unit_id"
        reg_check_in_date = "shelter_registration.check_in_date"
        reg_check_out_date = "shelter_registration.check_out_date"

    if privileged:

        # Extended form for privileged user roles
        crud_form = CustomForm(
                # Case Details ----------------------------
                (T("Case Status"), "dvr_case.status_id"),
                InlineLink("case_flag",
                           label = T("Flags"),
                           field = "flag_id",
                           help_field = "comments",
                           cols = 4,
                           ),

                # Person Details --------------------------
                (T("ID"), "pe_label"),
                "last_name",
                "first_name",
                "person_details.nationality",
                "date_of_birth",
                "gender",
                "person_details.marital_status",

                # Process Data ----------------------------
                # Will always default & be hidden
                "dvr_case.organisation_id",
                # Will always default & be hidden
                "dvr_case.site_id",
                (T("EA Arrival"), "dvr_case.date"),
                "dvr_case.origin_site_id",
                "dvr_case.destination_site_id",
                #InlineComponent(
                #        "eo_number",
                #        fields = [("", "value")],
                #        filterby = {"field": "tag",
                #                    "options": "EONUMBER",
                #                    },
                #        label = T("EasyOpt Number"),
                #        multiple = False,
                #        name = "eo_number",
                #        ),
                InlineComponent(
                        "bamf",
                        fields = [("", "value")],
                        filterby = {"field": "tag",
                                    "options": "BAMF",
                                    },
                        label = T("BAMF Reference Number"),
                        multiple = False,
                        name = "bamf",
                        ),
                "dvr_case.valid_until",
                InlineComponent(
                        "identity",
                        fields = ["value",
                                  "valid_until",
                                  ],
                        filterby = {"field": "type",
                                    "options": 5,
                                    },
                        label = T("Preliminary Residence Permit"),
                        multiple = False,
                        ),
                #"dvr_case.stay_permit_until",

                # Shelter Data ----------------------------
                # Will always default & be hidden
                #"shelter_registration.site_id",
                reg_shelter,
                # @ ToDo: Automate this from the Case Status?
                reg_unit_id,
                reg_status,
                reg_check_in_date,
                reg_check_out_date,

                # Other Details ---------------------------
                "person_details.occupation",
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

        subheadings = {"dvr_case_status_id": T("Case Status"),
                       "pe_label": T("Person Details"),
                       "dvr_case_date": T("Registration"),
                       "shelter_registration_shelter_unit_id": T("Lodging"),
                       "person_details_occupation": T("Other Details"),
                       "dvr_case_archived": T("File Status")
                       }
    else:
        # Reduced form for non-privileged user roles
        crud_form = CustomForm(
                InlineLink("case_flag",
                           label = T("Flags"),
                           field = "flag_id",
                           help_field = "comments",
                           cols = 4,
                           ),
                (T("ID"), "pe_label"),
                "last_name",
                "first_name",
                "person_details.nationality",
                "date_of_birth",
                "gender",
                reg_unit_id,
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
                "dvr_case.comments",
                )

        subheadings = None

    resource.configure(crud_form = crud_form,
                       subheadings = subheadings,
                       )

# -------------------------------------------------------------------------
def configure_case_filters(resource, privileged=False, show_family_transferable=False):

    T = current.T
    s3db = current.s3db

    filter_widgets = resource.get_config("filter_widgets")
    if filter_widgets:
        from core import DateFilter, \
                         OptionsFilter, \
                         TextFilter

        extend_text_filter = True
        for fw in filter_widgets:
            # No filter default for case status
            if fw.field == "dvr_case.status_id":
                fw.opts.default = None
            if fw.field == "case_flag_case.flag_id":
                fw.opts.size = None
            # Text filter includes EasyOpt Number and Case Comments
            if extend_text_filter and isinstance(fw, TextFilter):
                fw.field.extend((#"eo_number.value",
                                 "dvr_case.comments",
                                 ))
                fw.opts.comment = T("You can search by name, ID or comments")
                extend_text_filter = False

        # Add filter for date of birth
        dob_filter = DateFilter("date_of_birth")
        #dob_filter.operator = ["eq"]
        filter_widgets.insert(1, dob_filter)

        # Additional filters for privileged roles
        if privileged:
            # Add filter for family transferability
            if show_family_transferable:
                ft_filter = OptionsFilter("dvr_case.household_transferable",
                                          label = T("Family Transferable"),
                                          options = {True: T("Yes"),
                                                     False: T("No"),
                                                     },
                                          cols = 2,
                                          hidden = True,
                                          )
                filter_widgets.append(ft_filter)

            # Add filter for registration date
            reg_filter = DateFilter("dvr_case.date",
                                    hidden = True,
                                    )
            filter_widgets.append(reg_filter)

            # Add filter for registration status
            reg_filter = OptionsFilter("shelter_registration.registration_status",
                                       label = T("Presence"),
                                       options = s3db.cr_shelter_registration_status_opts,
                                       hidden = True,
                                       cols = 3,
                                       )
            filter_widgets.append(reg_filter)

            # Add filter for BAMF Registration Number
            bamf_filter = TextFilter(["bamf.value"],
                                     label = T("BAMF Ref.No."),
                                     hidden = True,
                                     )
            filter_widgets.append(bamf_filter)

        # Add filter for IDs
        id_filter = TextFilter(["pe_label"],
                               label = T("IDs"),
                               match_any = True,
                               hidden = True,
                               comment = T("Search for multiple IDs (separated by blanks)"),
                               )
        filter_widgets.append(id_filter)

# -------------------------------------------------------------------------
def configure_case_list_fields(resource,
                               privileged = False,
                               check_overdue = False,
                               show_family_transferable = False,
                               fmt = None,
                               ):

    T = current.T
    db = current.db
    s3db = current.s3db

    settings = current.deployment_settings

    if fmt in ("html", "iframe", "aadata"):
        # Delivers HTML, so restrict to GUI:
        absence_field = (T("Checked-out"), "absence")
        resource.configure(extra_fields = ["shelter_registration.registration_status",
                                           "shelter_registration.check_out_date",
                                           ],
                           )
    else:
        absence_field = None

    # Standard list fields
    list_fields = [(T("ID"), "pe_label"),
                   #(T("EasyOpt No."), "eo_number.value"),
                   "last_name",
                   "first_name",
                   "date_of_birth",
                   "gender",
                   "person_details.nationality",
                   #"dvr_case.date",
                   #"dvr_case.status_id",
                   (T("Shelter"), "shelter_registration.shelter_unit_id"),
                   ]

    if privileged:
        # Additional list fields for privileged roles
        #list_fields.insert(1, (T("EasyOpt No."), "eo_number.value"))
        list_fields[-1:-1] = ("dvr_case.date",
                              "dvr_case.status_id",
                              )

        # Add fields for managing transferability
        if settings.get_dvr_manage_transferability() and not check_overdue:
            transf_fields = ["dvr_case.transferable",
                             (T("Size of Family"), "dvr_case.household_size"),
                             ]
            if show_family_transferable:
                transf_fields.append((T("Family Transferable"), "dvr_case.household_transferable"))
            list_fields[-1:-1] = transf_fields

        # Days of absence (virtual field)
        if absence_field:
            list_fields.append(absence_field)

    if fmt in ("xlsx", "xls"):
        # Additional fields for XLS export

        # Add appointment dates
        atypes = ["GU",
                  "X-Ray",
                  "Reported Transferable",
                  "Transfer",
                  "Sent to RP",
                  ]
        COMPLETED = 4
        afields = []
        attable = s3db.dvr_case_appointment_type
        query = attable.name.belongs(atypes)
        rows = db(query).select(attable.id,
                                attable.name,
                                )

        add_components = s3db.add_components
        for row in rows:
            type_id = row.id
            name = "appointment%s" % type_id
            hook = {"name": name,
                    "joinby": "person_id",
                    "filterby": {"type_id": type_id,
                                 "status": COMPLETED,
                                 },
                    }
            add_components("pr_person",
                           dvr_case_appointment = hook,
                           )
            afields.append((T(row.name), "%s.date" % name))

        list_fields.extend(afields)

        # Add family key
        s3db.add_components("pr_person",
                            pr_group = {"name": "family",
                                        "link": "pr_group_membership",
                                        "joinby": "person_id",
                                        "key": "group_id",
                                        "filterby": {
                                            "group_type": 7,
                                            },
                                        },
                            )

        list_fields += [# Current check-in/check-out status
                        (T("Registration Status"),
                            "shelter_registration.registration_status",
                            ),
                        # Last Check-in date
                        "shelter_registration.check_in_date",
                        # Last Check-out date
                        "shelter_registration.check_out_date",
                        # Person UUID
                        ("UUID", "uuid"),
                        # Family Record ID
                        (T("Family ID"), "family.id"),
                        ]

    resource.configure(list_fields = list_fields)

# -------------------------------------------------------------------------
def configure_id_cards(r, resource, administration=False):

    if administration:
        s3 = current.response.s3
        settings = current.deployment_settings

        if r.representation == "card":
            # Configure ID card layout
            from ..idcards import IDCardLayout
            resource.configure(pdf_card_layout = IDCardLayout,
                               pdf_card_pagesize = "A4",
                               )

        if not r.id and not r.component:
            # Add export-icon for ID cards
            export_formats = list(settings.get_ui_export_formats())
            export_formats.append(("card", "fa fa-id-card", current.T("Export ID Cards")))
            settings.ui.export_formats = export_formats
            s3.formats["card"] = r.url(method="")

# -------------------------------------------------------------------------
def configure_dvr_person_controller(r, privileged=False, administration=False):

    T = current.T
    db = current.db
    s3db = current.s3db
    settings = current.deployment_settings

    resource = r.resource

    from gluon import Field, IS_EMPTY_OR, IS_IN_SET, IS_NOT_EMPTY

    table = r.table
    ctable = s3db.dvr_case

    # Used in both list_fields and rheader
    table.absence = Field.Method("absence", drk_absence)

    # List modes
    check_overdue = False
    show_family_transferable = False

    # ID Card Export
    configure_id_cards(r, resource, administration=administration)

    if not r.record:

        get_vars = r.get_vars

        overdue = get_vars.get("overdue")
        if overdue in ("check-in", "!check-in"):
            # Filter case list for overdue check-in
            reg_status = FS("shelter_registration.registration_status")
            checkout_date = FS("shelter_registration.check_out_date")

            checked_out = (reg_status == 3)
            # Must catch None explicitly because it is neither
            # equal nor unequal with anything according to SQL rules
            not_checked_out = ((reg_status == None) | (reg_status != 3))

            # Due date for check-in
            due_date = r.utcnow - \
                        datetime.timedelta(days=ABSENCE_LIMIT)

            if overdue[0] == "!":
                query = not_checked_out | \
                        checked_out & (checkout_date >= due_date)
            else:
                query = checked_out & \
                        ((checkout_date < due_date) | (checkout_date == None))
            resource.add_filter(query)
            check_overdue = True

        elif overdue:
            # Filter for cases for which no such event was
            # registered for at least 3 days:
            record_ids = event_overdue(overdue.upper(), 3)
            query = FS("id").belongs(record_ids)
            resource.add_filter(query)

        show_family_transferable = get_vars.get("show_family_transferable")
        if show_family_transferable == "1":
            show_family_transferable = True

    if not r.component:

        configure_person_tags()

        # Set default shelter for shelter registration
        from ..helpers import drk_default_shelter
        shelter_id = drk_default_shelter()
        if shelter_id:
            rtable = s3db.cr_shelter_registration
            field = rtable.shelter_id
            field.default = shelter_id
            field.readable = field.writable = False

            # Filter housing units to units of this shelter
            field = rtable.shelter_unit_id
            dbset = db(s3db.cr_shelter_unit.shelter_id == shelter_id)
            field.requires = IS_EMPTY_OR(IS_ONE_OF(dbset,
                                "cr_shelter_unit.id",
                                field.represent,
                                # Only available units:
                                filterby = "status",
                                filter_opts = (1,),
                                sort=True,
                                ))

        settings = current.deployment_settings
        default_site = settings.get_org_default_site()
        default_organisation = settings.get_org_default_organisation()

        if default_organisation and not default_site:
            # Limit sites to default_organisation
            field = ctable.site_id
            requires = field.requires
            if requires:
                if isinstance(requires, IS_EMPTY_OR):
                    requires = requires.other
                if hasattr(requires, "dbset"):
                    stable = s3db.org_site
                    query = (stable.organisation_id == default_organisation)
                    requires.dbset = db(query)

        if r.interactive and r.method != "import":

            # Registration status effective dates not manually updateable
            if r.id:
                rtable = s3db.cr_shelter_registration
                field = rtable.check_in_date
                field.writable = False
                field.label = T("Last Check-in")
                field = rtable.check_out_date
                field.writable = False
                field.label = T("Last Check-out")

            # Make marital status mandatory, remove "other"
            dtable = s3db.pr_person_details
            field = dtable.marital_status
            options = dict(s3db.pr_marital_status_opts)
            del options[9] # Remove "other"
            field.requires = IS_IN_SET(options, zero=None)

            # Make gender mandatory, remove "unknown"
            field = table.gender
            field.default = None
            from core import IS_PERSON_GENDER
            options = dict(s3db.pr_gender_opts)
            del options[1] # Remove "unknown"
            field.requires = IS_PERSON_GENDER(options, sort = True)

            # No comment for pe_label
            field = table.pe_label
            field.writable = not settings.get_custom("autogenerate_case_ids")
            field.comment = None

            # Last name is required
            field = table.last_name
            field.requires = IS_NOT_EMPTY()

            # Check whether the shelter registration shall be cancelled
            cancel = False
            if r.http == "POST":
                post_vars = r.post_vars
                archived = post_vars.get("sub_dvr_case_archived")
                status_id = post_vars.get("sub_dvr_case_status_id")
                if archived:
                    cancel = True
                if not cancel and status_id:
                    stable = s3db.dvr_case_status
                    status = db(stable.id == status_id).select(stable.is_closed,
                                                               limitby = (0, 1),
                                                               ).first()
                    if status and status.is_closed:
                        cancel = True

            # Configure case form
            configure_case_form(resource,
                                privileged = privileged,
                                cancel = cancel,
                                )

            # Configure case filters
            configure_case_filters(resource,
                                   privileged = privileged,
                                   show_family_transferable = show_family_transferable,
                                   )

        # Configure case list fields (must be outside of r.interactive)
        configure_case_list_fields(resource,
                                   privileged = privileged,
                                   check_overdue = check_overdue,
                                   show_family_transferable = show_family_transferable,
                                   fmt = r.representation,
                                   )

    elif r.component_name == "case_appointment":

        # Make appointments tab read-only even if the user is permitted
        # to create or update appointments (via event registration),
        # except for ADMINISTRATION/ADMIN_HEAD:
        if not administration:
            r.component.configure(insertable = False,
                                  editable = False,
                                  deletable = False,
                                  )

# -------------------------------------------------------------------------
def configure_security_person_controller(r):

    T = current.T
    db = current.db
    s3db = current.s3db

    # Restricted view for Security staff
    if r.component:
        from gluon import redirect
        redirect(r.url(method=""))

    resource = r.resource

    # Autocomplete using alternative search method
    search_fields = ("first_name", "last_name", "pe_label")
    s3db.set_method("pr_person",
                    method = "search_ac",
                    action = s3db.pr_PersonSearchAutocomplete(search_fields),
                    )

    current.deployment_settings.ui.export_formats = None

    # Filter to valid and open cases
    query = (FS("dvr_case.id") != None) & \
            ((FS("dvr_case.archived") == False) | \
             (FS("dvr_case.archived") == None)) & \
            (FS("dvr_case.status_id$is_closed") == False)
    resource.add_filter(query)

    # Adjust CRUD strings
    current.response.s3.crud_strings["pr_person"].update(
        {"title_list": T("Current Residents"),
         "label_list_button": T("List Residents"),
         })

    # No side menu
    current.menu.options = None

    # Only Show Security Notes
    ntable = s3db.dvr_note_type
    note_type = db(ntable.name == "Security").select(ntable.id,
                                                     limitby=(0, 1),
                                                     ).first()
    try:
        note_type_id = note_type.id
    except AttributeError:
        current.log.error("Prepop not done - deny access to dvr_note component")
        note_type_id = None
        atable = s3db.dvr_note
        atable.date.readable = atable.date.writable = False
        atable.note.readable = atable.note.writable = False

    # Custom CRUD form
    from core import CustomForm, InlineComponent
    crud_form = CustomForm(
                    (T("ID"), "pe_label"),
                    "last_name",
                    "first_name",
                    "date_of_birth",
                    #"gender",
                    "person_details.nationality",
                    "shelter_registration.shelter_unit_id",
                    InlineComponent(
                            "case_note",
                            fields = [(T("Date"), "date"),
                                        "note",
                                        ],
                            filterby = {"field": "note_type_id",
                                        "options": note_type_id,
                                        },
                            label = T("Security Notes"),
                            ),
                    )

    # Custom list fields
    list_fields = [(T("ID"), "pe_label"),
                   "last_name",
                   "first_name",
                   "date_of_birth",
                   #"gender",
                   "person_details.nationality",
                   "shelter_registration.shelter_unit_id",
                   ]

    # Profile page (currently unused)
    if r.method == "profile":
        from gluon.html import DIV, H2, TABLE, TR, TD
        from core import s3_fullname
        person_id = r.id
        record = r.record
        table = r.table
        dtable = s3db.pr_person_details
        details = db(dtable.person_id == person_id).select(dtable.nationality,
                                                           limitby=(0, 1)
                                                           ).first()
        try:
            nationality = details.nationality
        except AttributeError:
            nationality = None
        rtable = s3db.cr_shelter_registration
        reg = db(rtable.person_id == person_id).select(rtable.shelter_unit_id,
                                                       limitby=(0, 1)
                                                       ).first()
        try:
            shelter_unit_id = reg.shelter_unit_id
        except AttributeError:
            shelter_unit_id = None
        profile_header = DIV(H2(s3_fullname(record)),
                                TABLE(TR(TD(T("ID")),
                                         TD(record.pe_label)
                                         ),
                                      TR(TD(table.last_name.label),
                                         TD(record.last_name)
                                         ),
                                      TR(TD(table.first_name.label),
                                         TD(record.first_name)
                                         ),
                                      TR(TD(table.date_of_birth.label),
                                         TD(record.date_of_birth)
                                         ),
                                      TR(TD(dtable.nationality.label),
                                         TD(nationality)
                                         ),
                                      TR(TD(rtable.shelter_unit_id.label),
                                         TD(shelter_unit_id)
                                         ),
                                      ),
                                _class="profile-header",
                                )

        notes_widget = dict(label = "Security Notes",
                            label_create = "Add Note",
                            type = "datatable",
                            tablename = "dvr_note",
                            filter = ((FS("note_type_id$name") == "Security") & \
                                        (FS("person_id") == person_id)),
                            #icon = "report",
                            create_controller = "dvr",
                            create_function = "note",
                            )
        profile_widgets = [notes_widget]
    else:
        profile_header = None
        profile_widgets = None

    resource.configure(crud_form = crud_form,
                       list_fields = list_fields,
                       profile_header = profile_header,
                       profile_widgets = profile_widgets,
                       )

# -------------------------------------------------------------------------
def pr_person_controller(**attr):

    T = current.T
    auth = current.auth
    s3 = current.response.s3

    ADMINISTRATION = ("ADMIN_HEAD",
                      "ADMINISTRATION",
                      )
    administration = auth.s3_has_roles(ADMINISTRATION)

    PRIVILEGED = ("INFO_POINT",
                  "MEDICAL",
                  "POLICE",
                  "RP",
                  "SECURITY_HEAD",
                  )
    privileged = administration or auth.s3_has_roles(PRIVILEGED)

    QUARTIERMANAGER = auth.s3_has_role("QUARTIER") and not privileged

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        if QUARTIERMANAGER:
            # Enforce closed=0
            r.vars["closed"] = r.get_vars["closed"] = "0"

        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        get_vars = r.get_vars

        archived = get_vars.get("archived")
        if archived in ("1", "true", "yes"):
            crud_strings = s3.crud_strings["pr_person"]
            crud_strings["title_list"] = T("Invalid Cases")

        controller = r.controller
        if controller == "security":
            configure_security_person_controller(r)

        elif controller == "dvr":
            configure_dvr_person_controller(r,
                                            privileged = privileged,
                                            administration = administration,
                                            )
        return result
    s3.prep = prep

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if QUARTIERMANAGER:
            # Add Action Button to assign Housing Unit to the Resident
            s3.actions = [dict(label=s3_str(T("Assign Shelter")),
                               _class="action-btn",
                               url=URL(c="cr",
                                       f="shelter_registration",
                                       args=["assign"],
                                       vars={"person_id": "[id]"},
                                       )),
                          ]

        if not r.component and r.record and isinstance(output, dict):

            # Custom CRUD buttons
            if "buttons" not in output:
                buttons = output["buttons"] = {}
            else:
                buttons = output["buttons"]

            # ID-Card button
            if administration:
                card_button = A(T("Generate ID"),
                                data = {"url": URL(c="dvr", f="person",
                                                   args = ["%s.card" % r.id]
                                                   ),
                                        },
                                _class = "action-btn s3-download-button",
                                )
            else:
                card_button = ""

            # Render in place of the delete-button
            buttons["delete_btn"] = TAG[""](card_button,
                                            )
        return output
    s3.postp = postp

    # Custom rheader tabs
    if current.request.controller == "dvr":
        from ..rheaders import drk_dvr_rheader
        attr = dict(attr)
        attr["rheader"] = drk_dvr_rheader

    return attr

# -------------------------------------------------------------------------
def pr_group_membership_controller(**attr):

    T = current.T
    s3db = current.s3db
    s3 = current.response.s3

    # Custom prep
    standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        if callable(standard_prep):
            result = standard_prep(r)
        else:
            result = True

        ROLE = T("Role")

        resource = r.resource
        if r.controller == "dvr":

            # Set default shelter
            from ..helpers import drk_default_shelter
            shelter_id = drk_default_shelter()
            if shelter_id:
                rtable = s3db.cr_shelter_registration
                field = rtable.shelter_id
                field.default = shelter_id

            if r.interactive:
                table = resource.table

                from gluon import IS_EMPTY_OR
                from core import PersonSelector

                s3db.pr_person.pe_label.label = T("ID")

                field = table.person_id
                field.represent = s3db.pr_PersonRepresent(show_link=True)
                field.widget = PersonSelector(controller = "dvr",
                                              pe_label = True,
                                              )

                field = table.role_id
                field.readable = field.writable = True
                field.label = ROLE
                field.comment = None
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

            list_fields = [(T("ID"), "person_id$pe_label"),
                           "person_id",
                           "person_id$date_of_birth",
                           "person_id$gender",
                           "group_head",
                           (ROLE, "role_id"),
                           (T("Case Status"), "person_id$dvr_case.status_id"),
                           "person_id$dvr_case.transferable",
                           ]
            # Retain group_id in list_fields if added in standard prep
            lfields = resource.get_config("list_fields")
            if "group_id" in lfields:
                list_fields.insert(0, "group_id")
            resource.configure(filter_widgets = None,
                               list_fields = list_fields,
                               )
        return result
    s3.prep = prep

    from ..rheaders import drk_dvr_rheader
    attr["rheader"] = drk_dvr_rheader

    return attr

# END =========================================================================
