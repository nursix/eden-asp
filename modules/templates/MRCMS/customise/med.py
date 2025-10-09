"""
    MED module customisations for MRCMS

    License: MIT
"""

import datetime

from gluon import current, A
from gluon.storage import Storage

from core import CustomForm, FS, ICON

RECENTLY=12 # hours

# =============================================================================
def configure_med_case_file(r):

    T = current.T
    db = current.db
    s3db = current.s3db

    s3 = current.response.s3

    record = r.record
    resource = r.resource

    recently = current.request.utcnow - datetime.timedelta(hours=RECENTLY)

    # Access to case files without case list permission requires
    # that the client is currently or has recently been a patient
    if not current.auth.s3_has_permission("read", "pr_person", c="dvr", f="person"):
        open_status = ("ARRIVED", "TREATMENT")
        if record:
            ptable = s3db.med_patient
            active = (ptable.status.belongs(open_status)) | \
                     (ptable.end_date != None) & (ptable.end_date > recently)
            query = (ptable.person_id == record.id) & active & \
                    (ptable.invalid == False) & \
                    (ptable.deleted == False)
            row = db(query).select(ptable.id, limitby=(0, 1)).first()
            if not row:
                r.error(403, current.ERROR.NOT_PERMITTED)
        elif r.method != "search_ac":
            query = FS("patient.status").belongs(open_status) | \
                    (FS("patient.end_date") != None) & \
                    (FS("patient.end_date") > recently)
            resource.add_filter(query)

    # The current patient ID for the person, if they have an open record
    current_patient_id = s3db.med_get_current_patient_id(record.id) if record else None

    # Configure components
    component = r.component
    component_name = r.component_name
    if component_name == "patient":

        ptable = component.table

        # Filter out invalid patient records
        component.add_filter(FS("invalid") == False)

        # Look up the patient record
        readonly = False
        if r.component_id:
            rows = component.load()
            patient = rows[0] if rows else None
        else:
            patient = None

        # Determine whether record is writable
        # - read-only if closed earlier than recently, or if a later
        #   patient record for the same person exists
        if patient:
            readonly = patient.end_date and patient.end_date < recently
            if not readonly and patient.date and patient.person_id:
                query = (ptable.person_id == patient.person_id) & \
                        (ptable.date > patient.date) & \
                        (ptable.invalid == False) & \
                        (ptable.deleted == False)
                row = db(query).select(ptable.id, limitby=(0, 1)).first()
                if row:
                    readonly = True

        # If read-only, then lock all fields except comments
        if readonly:
            for fn in ptable.fields:
                if fn != "comments":
                    ptable[fn].writable = False

        # Look up the epicrisis record for the patient record
        etable = s3db.med_epicrisis
        if patient:
            query = (etable.patient_id == patient.id) & \
                    (etable.deleted == False)
            epicrisis = db(query).select(etable.id,
                                         etable.is_final,
                                         limitby = (0, 1),
                                         ).first()
        else:
            epicrisis = None

        # Enable/disable epicrisis fields depending on is_final-flag
        efields = ("situation", "diagnoses", "progress", "outcome", "recommendation")
        if not epicrisis or not epicrisis.is_final:
            for fn in efields:
                etable[fn].writable = True
            etable.is_final.writable = True
        else:
            for fn in efields:
                etable[fn].writable = False
            etable.is_final.writable = False

        # CRUD form
        if current.auth.s3_has_permission("create", "med_patient"):
            priority = "priority"
            hazards = "hazards"
            hazards_advice = "hazards_advice"
            comments = "comments"
            invalid = "invalid"
        else:
            priority = hazards = hazards_advice = comments = invalid = None

        crud_form = CustomForm(# ------- Treatment Occasion ---------
                               "unit_id",
                               "date",
                               "refno",
                               "reason",
                               priority,
                               "status",
                               # ------- Epicrisis ------------------
                               "epicrisis.situation",
                               "epicrisis.diagnoses",
                               "epicrisis.progress",
                               "epicrisis.outcome",
                               "epicrisis.recommendation",
                               "epicrisis.is_final",
                               # ------- Hazards --------------------
                               hazards,
                               hazards_advice,
                               # ------- Administrative -------------
                               comments,
                               invalid,
                               )

        subheadings = {"unit_id": T("Treatment Occasion"),
                       "hazards": T("Hazards Advice"),
                       "epicrisis_situation": T("Progress"),
                       "comments": T("Administrative"),
                       }

        # Perspective-specific list fields
        list_fields = ["refno",
                       "date",
                       "unit_id",
                       "reason",
                       "status",
                       ]

        # Reconfigure component
        component.configure(crud_form = crud_form,
                            subheadings = subheadings,
                            list_fields = list_fields,
                            orderby = "%s.date desc" % r.component.tablename,
                            insertable = not current_patient_id,
                            editable = True,
                            deletable = False,
                            open_read_first = True,
                            )

        # Adapt CRUD strings to perspective
        # TODO translations
        s3.crud_strings["med_patient"] = Storage(
            label_create = T("Add Treatment Occasion"),
            title_display = T("Treatment Occasion"),
            title_list = T("Treatment Occasions"),
            title_update = T("Edit Treatment Occasion"),
            label_list_button = T("List Treatment Occasions"),
            # label_delete_button = T("Delete Treatment Occasion"),
            msg_record_created = T("Treatment Occasion added"),
            msg_record_modified = T("Treatment Occasion updated"),
            # msg_record_deleted = T("Treatment Occasion deleted"),
            msg_list_empty = T("No Treatment Occasions currently registered"),
            )

    elif component_name == "vitals":
        # Require active patient file for adding new record
        component.configure(insertable = bool(current_patient_id))
        component.table.patient_id.default = current_patient_id

    elif component_name == "med_status":
        # Require active patient file for adding new record
        component.configure(insertable = bool(current_patient_id))
        component.table.patient_id.default = current_patient_id

        ctable = component.table
        get_vars = r.get_vars
        is_delete = r.is_delete()

        # Look up the status record
        if r.component_id or not r.component.multiple:
            rows = component.load()
            crecord = rows[0] if rows else None
        elif is_delete and r.representation == "dl" and "delete" in get_vars:
            # Datalist delete-request
            crecord_id = get_vars.get("delete")
            crecord = db(ctable.id == crecord_id).select(limitby=(0, 1)).first()
        else:
            crecord = None

        # Prevent deletion of finalized records
        if is_delete and (not crecord or crecord.is_final):
            r.error(403, current.ERROR.NOT_PERMITTED)

        # Enforce author-locking and is-final status
        user = current.auth.user
        user_id = user.id if user else None
        if crecord:
            if crecord.is_final:
                editable = deletable = False
            else:
                editable = crecord.created_by == user_id
                deletable = True
            component.configure(editable=editable, deletable=deletable)

        # Expose is_final flag when not yet marked as final
        field = ctable.is_final
        field.readable = field.writable = not crecord or not crecord.is_final

    elif component_name == "treatment":
        # Require active patient file for adding new record
        component.configure(insertable = bool(current_patient_id))
        component.table.patient_id.default = current_patient_id

        list_fields = ["date",
                       (T("Occasion"), "patient_id"),
                       "details",
                       "status",
                       "start_date",
                       "end_date",
                       "comments",
                       ]
        component.configure(list_fields = list_fields,
                            )

# =============================================================================
def med_patient_resource(r, tablename):

    s3db = current.s3db

    s3db.configure("med_patient",
                   # Update realm when moving patient between units
                   update_realm = True,
                   realm_components = ("vitals",
                                       "status",
                                       "treatment",
                                       "epicrisis",
                                       ),
                   )

    from ..patient import PatientSummary
    s3db.set_method("med_patient",
                    method = "summarize",
                    action = PatientSummary,
                    )

# -----------------------------------------------------------------------------
def med_patient_controller(**attr):

    T = current.T
    db = current.db
    # s3db = current.s3db

    s3 = current.response.s3

    recently = current.request.utcnow - datetime.timedelta(hours=RECENTLY)

    standard_prep = s3.prep
    def prep(r):

        # Call standard prep
        result = standard_prep(r) if callable(standard_prep) else True

        resource = r.resource
        table = resource.table

        record = r.record
        readonly = False
        if record:
            readonly = record.end_date and record.end_date < recently
            if not readonly and record.date and record.person_id:
                query = (table.person_id == record.person_id) & \
                        (table.date > record.date) & \
                        (table.invalid == False) & \
                        (table.deleted == False)
                row = db(query).select(table.id, limitby=(0, 1)).first()
                if row:
                    readonly = True

        if readonly:
            for fn in table.fields:
                if fn != "comments":
                    table[fn].writable = False

        return result
    s3.prep = prep

    # Custom postp
    standard_postp = s3.postp
    def postp(r, output):
        # Call standard postp
        if callable(standard_postp):
            output = standard_postp(r, output)

        if r.record and isinstance(output, dict):
            if r.component_name == "epicrisis":
                # Inject button to generate summary PDF
                from ..helpers import inject_button
                btn = A(ICON("file-pdf"), T("Summary"),
                        data = {"url": r.url(component = "",
                                             method = "summarize",
                                             representation = "pdf",
                                             ),
                                },
                        _class = "action-btn activity button s3-download-button",
                        )
                inject_button(output, btn, before="delete_btn", alt=None)
        return output
    s3.postp = postp

    return attr

# END =========================================================================
