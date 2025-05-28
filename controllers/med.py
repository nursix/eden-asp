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

        if r.record:
            # Organisation cannot be changed
            table = r.resource.table
            field = table.organisation_id
            field.writable = False

        return True
    s3.prep = prep

    return crud_controller(rheader=s3db.med_rheader)

# =============================================================================
def patient():
    """ Patients - CRUD Controller """

    def prep(r):

        get_vars = r.get_vars

        if not r.record:
            # Filter for valid/invalid patient records
            invalid = get_vars.get("invalid") == "1"
            if invalid:
                query = FS("invalid") == True
            else:
                query = (FS("invalid") == False) | (FS("invalid") == None)

            # Filter to open/closed patient records
            if not invalid:
                closed = get_vars.get("closed")
                if closed == "only":
                    query &= FS("closed") == True
                elif closed not in ("1", "include"):
                    query &= FS("closed") == False

            r.resource.add_filter(query)

        if r.component_name in ("status", "epicrisis") and r.component_id:

            # Records only editable/deletable for original author
            rows = r.component.load()
            record = rows[0] if rows else None

            user = current.auth.user
            user_id = user.id if user else None

            if record and record.created_by != user_id:
                r.component.configure(editable = False,
                                      deletable = False,
                                      )
        return True
    s3.prep = prep

    # TODO postp
    # * status/epicrisis components: set filter for deletable records

    return crud_controller(rheader=s3db.med_rheader)

# -----------------------------------------------------------------------------
def person():
    """ Persons (MED Perspective) - CRUD controller """

    def prep(r):

        viewing = r.viewing
        if viewing:

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

        elif r.component_name == "patient":

            r.component.configure(insertable = False,
                                  editable = False,
                                  deletable = False,
                                  )
            s3.crud_strings["med_patient"] = Storage(
                label_create = T("Add Care Occasion"),
                title_display = T("Care Occasion"),
                title_list = T("Care Occasions"),
                title_update = T("Edit Care Occasion"),
                label_list_button = T("List Care Occasions"),
                label_delete_button = T("Delete Care Occasion"),
                msg_record_created = T("Care Occasion added"),
                msg_record_modified = T("Care Occasion updated"),
                msg_record_deleted = T("Care Occasion deleted"),
                msg_list_empty = T("No Care Occasions currently registered"),
                )

        resource = r.resource
        table = resource.table

        # Expose deceased-flag and date_of_death
        fields = ["deceased", "date_of_death"]
        for fn in fields:
            field = table[fn]
            field.readable = field.writable = True


        # CRUD Form
        from core import CustomForm
        crud_form = CustomForm("first_name",
                               "middle_name",
                               "last_name",
                               "person_details.year_of_birth",
                               "date_of_birth",
                               "gender",
                               # "person_details.marital_status",
                               # "person_details.nationality",
                               # "person_details.religion",
                               # "person_details.occupation",
                               "deceased",
                               "date_of_death",
                               "comments",
                               )

        r.resource.configure(crud_form = crud_form,
                             insertable = False,
                             deletable = False,
                             )
        return True
    s3.prep = prep

    def postp(r, output):

        if r.component_name == "patient":
            if isinstance(output, dict):
                output["native"] = True
        return output
    s3.postp = postp

    return crud_controller("pr", "person", rheader=s3db.med_rheader)

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
