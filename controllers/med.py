"""
    Medical Journals - Controllers
"""

module = request.controller
resourcename = request.function

if not settings.has_module(module):
    raise HTTP(404, body="Module disabled: %s" % module)

# =============================================================================
def index():
    """ Module's Home Page """

    return s3db.cms_index(module, alt_function="index_alt")

# -----------------------------------------------------------------------------
def index_alt():
    """
        Module homepage for non-Admin users when no CMS content found
    """

    # Just redirect to the list of persons
    s3_redirect_default(URL(f="patient"))

# =============================================================================
def unit():
    """ Medical Units - CRUD Controller """

    def prep(r):

        resource = r.resource
        table = resource.table

        record = r.record
        if not r.component:
            if record:
                # Organisation cannot be changed
                field = table.organisation_id
                field.writable = False

                ptable = s3db.med_patient

                # Unit cannot be deleted while there are patients assigned to it
                query = (ptable.unit_id == record.id)
                row = db(query).select(ptable.id, limitby=(0, 1)).first()
                if row:
                    r.resource.configure(deletable=False)

                # Unit cannot be marked obsolete while it has current patients
                query &= (ptable.status.belongs(("ARRIVED", "TREATMENT"))) & \
                         (ptable.invalid == False) & \
                         (ptable.deleted == False)
                row = db(query).select(ptable.id, limitby=(0, 1)).first()
                if row:
                    field = table.obsolete
                    field.readable = field.writable = record.obsolete

        elif r.component_name == "patient":
            list_fields = ["date",
                           "refno",
                           "person_id",
                           "reason",
                           "status",
                           ]
            r.component.configure(crud_form = s3base.CustomForm(*list_fields),
                                  subheadings = None,
                                  list_fields = list_fields,
                                  orderby = "%s.date desc" % r.component.tablename,
                                  insertable = False,
                                  editable = False,
                                  deletable = False,
                                  )
        return True
    s3.prep = prep

    def postp(r, output):

        if not r.component:
            if r.interactive and not r.record:
                # No delete-action by default (must open record to delete)
                s3_action_buttons(r, deletable=False)

        elif r.component_name == "patient":
            if isinstance(output, dict) and \
               auth.permission.has_permission("read", c="med", f="patient"):
                # Open in med/patient controller rather than on component tab
                output["native"] = True

        return output
    s3.postp = postp

    return crud_controller(rheader=s3db.med_rheader)

def area():
    """ Treatment Areas (Rooms) - CRUD Controller """

    # Only used for options lookups (in patient form)
    def prep(r):
        if r.http == "GET" and r.representation == "json":
            r.resource.add_filter(~FS("status").belongs(("M", "X")))
            return True
        else:
            return False
    s3.prep = prep

    return crud_controller()

# =============================================================================
def patient():
    """ Patients - CRUD Controller """

    user = current.auth.user
    user_id = user.id if user else None

    def prep(r):

        get_vars = r.get_vars

        resource = r.resource
        table = resource.table

        record = r.record
        if record:
            if record.person_id:
                # Person cannot be changed once set
                field = table.person_id
                field.writable = False
                # Hide unregistered+person fields
                field = table.unregistered
                field.readable = field.writable = False
                field = table.person
                field.readable = field.writable = False
        else:
            # Filter for valid/invalid patient records
            invalid = get_vars.get("invalid") == "1"
            if invalid:
                query = FS("invalid") == True
            else:
                query = (FS("invalid") == False) | (FS("invalid") == None)

            # Filter to open/closed patient records
            if not invalid:
                closed = get_vars.get("closed")
                open_status = ("ARRIVED", "TREATMENT")
                if closed == "only":
                    query &= ~(FS("status").belongs(open_status))
                    list_title = T("Former Patients")
                elif closed not in ("1", "include"):
                    query &= FS("status").belongs(open_status)
                    list_title = T("Current Patients")
                else:
                    list_title = T("Patients")
            else:
                list_title = T("Invalid Patient Records")

            resource.add_filter(query)
            s3.crud_strings["med_patient"]["title_list"] = list_title

        component_name = r.component_name
        component = r.component
        if not component:
            # Configure unit/area choices
            s3db.med_configure_unit_id(table, record)

            # Inject form control script
            script = "s3.med.js" if s3.debug else "s3.med.min.js"
            path = "/%s/static/scripts/S3/%s" % (current.request.application, script)
            if path not in s3.scripts:
                s3.scripts.append(path)

        elif component_name == "treatment":

            ctable = component.table

            if r.component_id:
                rows = component.load()
                crecord = rows[0] if rows else None
            else:
                crecord = None

            if crecord:
                status = crecord.status
                if status in ("R", "O"):
                    # Cannot edit once marked canceled or obsolete
                    component.configure(editable=False)
                if status != "P":
                    # Cannot change details once started
                    ctable.details.writable = False
                    # Cannot change back to status "pending"
                    field = ctable.status
                    options = field.requires.options(zero=False)
                    field.requires = IS_IN_SET([o for o in options if o[0] != "P"],
                                               zero = None,
                                               sort = False,
                                               )
                # Restrict change of start/end dates if already set
                if crecord.start_date:
                    ctable.start_date.writable = status in ("P", "S")
                    if crecord.end_date:
                        ctable.end_date.writable = status in ("P", "S")

        elif component_name in ("status", "epicrisis"):

            ctable = component.table

            is_delete = r.is_delete()

            if r.component_id or not r.component.multiple:
                rows = component.load()
                crecord = rows[0] if rows else None
            elif is_delete and r.representation == "dl" and "delete" in get_vars:
                # Datalist delete-request
                crecord_id = get_vars.get("delete")
                crecord = db(ctable.id == record_id).select(limitby=(0, 1)).first()
            else:
                crecord = None

            if is_delete and (not crecord or crecord.is_final):
                # Finalized records must not be deleted
                r.error(403, current.ERROR.NOT_PERMITTED)

            # Components which records can only be edited by their original author
            author_locked = component_name == "status"

            # Enforce author-locking and is-final status
            if crecord:
                if crecord.is_final:
                    editable = deletable = False
                else:
                    editable = not author_locked or crecord.created_by == user_id
                    deletable = True
                component.configure(editable=editable, deletable=deletable)

            # Expose is_final flag when not yet marked as final
            field = ctable.is_final
            field.readable = field.writable = not crecord or not crecord.is_final

        return True
    s3.prep = prep

    def postp(r, output):

        if r.component_name in ("status", "epicrisis"):
            if r.interactive and r.record and not r.component_id:
                # No delete-action by default (must open record to delete)
                s3_action_buttons(r, deletable=False)

        return output
    s3.postp = postp

    return crud_controller(rheader=s3db.med_rheader)

# -----------------------------------------------------------------------------
def person_search():
    """
        Controller for autocomplete-searches
    """

    from core import StringTemplateParser

    # Search fields
    search_fields = settings.get_pr_name_fields()
    if settings.get_med_use_pe_label():
        search_fields.append("pe_label")

    # Autocomplete using alternative search method
    s3db.set_method("pr_person",
                    method = "search_ac",
                    action = s3db.pr_PersonSearchAutocomplete(search_fields),
                    )

    def prep(r):

        if r.method != "search_ac":
            return False

        resource = r.resource

        # Restrict search to persons associated with modules
        filters = []
        modules = settings.get_med_restrict_person_search_to()
        if "dvr" in modules:
            filters.append((FS("dvr_case.id") != None) & \
                           (FS("dvr_case.archived") == False))
        if "hrm" in modules:
            filters.append(FS("hrm_human_resource.id") != None)
        if filters:
            query = reduce(lambda x, y: x | y, filters)
            resource.add_filter(query)
        return True

    s3.prep = prep

    return crud_controller("pr", "person")

# -----------------------------------------------------------------------------
def person():
    """ Persons (MED Perspective) - CRUD controller """

    def prep(r):

        resource = r.resource
        table = resource.table

        viewing = r.viewing
        if viewing:
            # On person-tab of patient record
            person_id = None

            vtablename, record_id = viewing
            if vtablename == "med_patient" and record_id:
                # Load person_id from patient
                ptable = s3db.med_patient
                query = (ptable.id == record_id) & (ptable.deleted == False)
                row = db(query).select(ptable.person_id, limitby=(0, 1)).first()
                person_id = row.person_id if row else None

            if not person_id:
                r.error(404, current.ERROR.BAD_RECORD)
            elif r.record:
                if r.record.id != person_id:
                    r.error(404, current.ERROR.BAD_RECORD)
            else:
                # Load the person record
                resource = s3db.resource(r.resource, id=[person_id])
                resource.load()
                if len(resource) == 1:
                    from core import set_last_record_id
                    r.resource = resource
                    r.record = resource.records().first()
                    r.id = r.record[resource._id.name]
                    set_last_record_id(r.tablename, r.id)
                else:
                    r.error(404, current.ERROR.BAD_RECORD)

            # Expose deceased-flag and date_of_death, and
            # make those the only writable fields in this
            # perspective
            writable = ("deceased", "date_of_death")
            for fn in table.fields:
                field = table[fn]
                is_writable = fn in writable
                field.writable = is_writable
                if is_writable:
                    # Must set to readable as well
                    field.readable = True
                else:
                    field.comment = None

            # Make details fields read-only too
            dtable = resource.components.get("person_details").table
            for fn in dtable.fields:
                field = dtable[fn]
                field.writable = False
                field.comment = None

        elif r.component_name == "patient":
            # On patient-tab of person record
            list_fields = ["date",
                           "unit_id",
                           "refno",
                           "reason",
                           "status",
                           ]
            r.component.configure(crud_form = s3base.CustomForm(*list_fields),
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

        # CRUD Form
        crud_fields = settings.get_pr_name_fields()
        crud_fields.extend(["date_of_birth",
                            "gender",
                            "person_details.nationality",
                            # "person_details.marital_status",
                            # "person_details.nationality",
                            # "person_details.religion",
                            # "person_details.occupation",
                            "deceased",
                            "date_of_death",
                            "comments",
                            ])

        resource.configure(crud_form = s3base.CustomForm(*crud_fields),
                           insertable = False,
                           deletable = False,
                           )
        return True
    s3.prep = prep

    def postp(r, output):

        if r.component_name == "patient":
            if isinstance(output, dict) and \
               auth.permission.has_permission("read", c="med", f="patient"):
                # Open in med/patient controller rather than on component tab
                output["native"] = True

        return output
    s3.postp = postp

    return crud_controller("pr", "person", rheader=s3db.med_rheader)

# =============================================================================
# Documents
#
def document():
    """
        Module-context specific document controller, viewing person or
        patient files
    """

    def prep(r):

        table = r.table
        resource = r.resource

        viewing = r.viewing
        if viewing:
            vtablename, record_id = viewing
        else:
            return False

        ptable = s3db.med_patient
        auth = current.auth
        has_permission = auth.s3_has_permission
        accessible_query = auth.s3_accessible_query

        if vtablename == "pr_person":
            if not has_permission("read", "pr_person", record_id):
                r.unauthorised()
            query = accessible_query("read", ptable) & \
                    (ptable.person_id == record_id) & \
                    (ptable.deleted == False)

        elif vtablename == "med_patient":
            query = accessible_query("read", ptable) & \
                    (ptable.id == record_id) & \
                    (ptable.deleted == False)
        else:
            # Unsupported
            return False

        # Get the patient doc_ids
        patients = db(query).select(ptable.doc_id,
                                    orderby = ~ptable.date, # latest first
                                    )
        doc_ids = [patient.doc_id for patient in patients]

        field = r.table.doc_id

        # Make doc_id readable and visible in table
        field.represent = s3db.med_DocEntityRepresent(show_link=True)
        field.label = T("Attachment of")
        field.readable = True
        s3db.configure("doc_document",
                       list_fields = ["id",
                                      (T("Attachment of"), "doc_id"),
                                      "name",
                                      "file",
                                      "date",
                                      "comments",
                                      ],
                       )

        # Apply filter and defaults
        if len(doc_ids) == 1:
            # Single doc_id => set default, hide field
            doc_id = doc_ids[0]
            field.default = doc_id
            r.resource.add_filter(FS("doc_id") == doc_id)
        else:
            # Multiple doc_ids => default to case, make selectable
            field.default = doc_ids[0]
            field.readable = field.writable = True
            field.requires = IS_ONE_OF(db, "doc_entity.doc_id",
                                       field.represent,
                                       filterby = "doc_id",
                                       filter_opts = doc_ids,
                                       orderby = "instance_type",
                                       sort = False,
                                       )
            r.resource.add_filter(FS("doc_id").belongs(doc_ids))

        return True
    s3.prep = prep

    return crud_controller("doc", "document",
                           rheader = s3db.med_rheader,
                           )

# =============================================================================
# Vaccinations
#
def vaccination_type():
    """ Vaccination Types - CRUD Controller """

    return crud_controller()

# -----------------------------------------------------------------------------
def vaccination():
    """ Vaccinations - CRUD Controller """

    def prep(r):

        viewing = r.viewing
        if viewing:

            person_id = None

            vtablename, record_id = viewing
            if vtablename == "med_patient" and record_id:
                # Load person_id from patient record
                ptable = s3db.med_patient
                query = (ptable.id == record_id) & (ptable.deleted == False)
                row = db(query).select(ptable.person_id, limitby=(0, 1)).first()
                person_id = row.person_id if row else None

            if person_id:
                # Filter records by person_id
                resource = r.resource
                resource.add_filter((FS("person_id") == person_id))

                # Default person ID and hide field
                field = resource.table.person_id
                field.default = person_id
                field.writable = field.readable = False
            else:
                r.error(404, current.ERROR.BAD_RECORD)
        else:
            r.resource.configure(insertable = False,
                                 )
        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.med_rheader)

# -----------------------------------------------------------------------------
def anamnesis():
    """ Anamnesis - CRUD Controller """

    def prep(r):

        resource = r.resource
        table = resource.table

        viewing = r.viewing
        if viewing:

            person_id = None

            vtablename, record_id = viewing
            if vtablename == "med_patient" and record_id:

                # Look up the patient record
                ptable = s3db.med_patient
                query = (ptable.id == record_id) & (ptable.deleted == False)
                patient = db(query).select(ptable.person_id, limitby=(0, 1)).first()

                # Look up existing anamnesis record
                if patient:
                    person_id = patient.person_id
                    query = (table.person_id == person_id) & (table.deleted == False)
                    record = db(query).select(table.ALL, limitby=(0, 1)).first()
                else:
                    record = None

                # Set default person_id
                if not person_id:
                    r.error(404, current.ERROR.BAD_RECORD)
                else:
                    field = table.person_id
                    field.default = person_id
                    field.readable = field.writable = False

                # Adjust target record and method
                if r.record:
                    if r.record.person_id != person_id:
                        r.error(404, current.ERROR.BAD_RECORD)
                elif record:
                    r.record, r.id = record, record.id
                    from core import set_last_record_id
                    set_last_record_id(r.tablename, r.id)
                elif r.interactive and not r.method and current.auth.s3_has_permission("create", table):
                    r.method = "create"
                else:
                    resource.add_filter(FS("person_id") == person_id)
            else:
                # Invalid view
                r.error(400, current.ERROR.BAD_REQUEST)
        else:
            # Viewing is required
            r.error(400, current.ERROR.BAD_REQUEST)

        return True
    s3.prep = prep

    settings.ui.open_read_first = True

    return crud_controller(rheader=s3db.med_rheader,
                           custom_crud_buttons = {"list_btn": None,
                                                  "delete_btn": None,
                                                  },
                           )

# -----------------------------------------------------------------------------
# Medication
#
def substance():
    """ Substances - CRUD Controller """

    return crud_controller()

def medication():
    """ Medication - CRUD Controller """

    def prep(r):

        resource = r.resource

        viewing = r.viewing
        if viewing:

            person_id = None

            vtablename, record_id = viewing
            if vtablename == "med_patient" and record_id:
                # Load person_id from patient record
                ptable = s3db.med_patient
                query = (ptable.id == record_id) & (ptable.deleted == False)
                row = db(query).select(ptable.person_id, limitby=(0, 1)).first()
                person_id = row.person_id if row else None

            if person_id:
                # Filter records by person_id
                resource.add_filter((FS("person_id") == person_id))

                # Default person ID and hide field
                field = resource.table.person_id
                field.default = person_id
                field.writable = field.readable = False
            else:
                r.error(404, current.ERROR.BAD_RECORD)
        else:
            # Viewing is required
            r.error(400, current.ERROR.BAD_REQUEST)

        # Forward to list view after create/update
        resource.configure(create_next = r.url(method=""),
                           update_next = r.url(method=""),
                           )
        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.med_rheader)

# END =========================================================================
